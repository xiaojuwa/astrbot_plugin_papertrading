"""群聊播报服务"""
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from astrbot.api import logger

from ..utils.data_storage import DataStorage


class BroadcastService:
    """群聊播报服务"""
    
    def __init__(self, storage: DataStorage):
        self.storage = storage
    
    async def generate_morning_broadcast(self, group_id: str) -> str:
        """生成中午收盘播报"""
        try:
            # 获取上午交易统计
            morning_stats = await self._get_morning_trading_stats(group_id)
            
            message = f"""
📢 中午收盘播报
━━━━━━━━━━━━━━━━━━━━
⏰ 时间: {datetime.now().strftime('%H:%M')}
💰 上午总交易额: {morning_stats['total_volume']:.2f}元
📈 上午总盈利: {morning_stats['total_profit']:.2f}元
👥 活跃用户: {morning_stats['active_users']}人
🏆 上午股神: {morning_stats['top_trader']}
📉 最惨韭菜: {morning_stats['worst_trader']}
🎯 最热门股票: {morning_stats['hot_stock']}
━━━━━━━━━━━━━━━━━━━━
            """
            return message.strip()
            
        except Exception as e:
            logger.error(f"生成中午播报失败: {e}")
            return "📢 中午收盘播报生成失败"
    
    async def generate_evening_broadcast(self, group_id: str) -> str:
        """生成下午收盘播报"""
        try:
            # 获取全天交易统计
            daily_stats = await self._get_daily_trading_stats(group_id)
            
            message = f"""
📢 下午收盘播报
━━━━━━━━━━━━━━━━━━━━
⏰ 时间: {datetime.now().strftime('%H:%M')}
💰 全天总交易额: {daily_stats['total_volume']:.2f}元
📈 全天总盈利: {daily_stats['total_profit']:.2f}元
👥 活跃用户: {daily_stats['active_users']}人
🏆 今日股神: {daily_stats['top_trader']}
📉 今日韭菜: {daily_stats['worst_trader']}
🎯 最热门股票: {daily_stats['hot_stock']}
🏆 今日猜股获胜者: {daily_stats['guess_winner']}
━━━━━━━━━━━━━━━━━━━━
            """
            return message.strip()
            
        except Exception as e:
            logger.error(f"生成下午播报失败: {e}")
            return "📢 下午收盘播报生成失败"
    
    async def _get_morning_trading_stats(self, group_id: str) -> Dict[str, Any]:
        """获取上午交易统计"""
        try:
            # 获取今日上午的订单（9:30-11:30）
            today = datetime.now().date()
            morning_start = datetime.combine(today, datetime.min.time().replace(hour=9, minute=30))
            morning_end = datetime.combine(today, datetime.min.time().replace(hour=11, minute=30))
            
            morning_start_ts = int(morning_start.timestamp())
            morning_end_ts = int(morning_end.timestamp())
            
            # 获取所有订单
            all_orders = self.storage.get_orders()
            morning_orders = [
                order for order in all_orders
                if morning_start_ts <= order.get('create_time', 0) <= morning_end_ts
                and order.get('status') == 'filled'
            ]
            
            # 统计信息
            total_volume = sum(order.get('filled_amount', 0) for order in morning_orders)
            active_users = len(set(order.get('user_id') for order in morning_orders))
            
            # 计算用户盈亏
            user_profits = {}
            for order in morning_orders:
                user_id = order.get('user_id')
                if user_id not in user_profits:
                    user_profits[user_id] = 0
                
                # 简单计算：卖出订单算盈利，买入订单算成本
                if order.get('order_type') == 'sell':
                    user_profits[user_id] += order.get('filled_amount', 0)
                else:
                    user_profits[user_id] -= order.get('filled_amount', 0)
            
            # 找出最佳和最差交易者
            if user_profits:
                top_trader = max(user_profits.items(), key=lambda x: x[1])
                worst_trader = min(user_profits.items(), key=lambda x: x[1])
                top_trader_name = top_trader[0][:8] + "..." if len(top_trader[0]) > 8 else top_trader[0]
                worst_trader_name = worst_trader[0][:8] + "..." if len(worst_trader[0]) > 8 else worst_trader[0]
            else:
                top_trader_name = "无"
                worst_trader_name = "无"
            
            # 找出最热门股票
            stock_counts = {}
            for order in morning_orders:
                stock_code = order.get('stock_code')
                stock_counts[stock_code] = stock_counts.get(stock_code, 0) + 1
            
            hot_stock = max(stock_counts.items(), key=lambda x: x[1])[0] if stock_counts else "无"
            
            total_profit = sum(user_profits.values())
            
            return {
                'total_volume': total_volume,
                'total_profit': total_profit,
                'active_users': active_users,
                'top_trader': top_trader_name,
                'worst_trader': worst_trader_name,
                'hot_stock': hot_stock
            }
            
        except Exception as e:
            logger.error(f"获取上午交易统计失败: {e}")
            return {
                'total_volume': 0,
                'total_profit': 0,
                'active_users': 0,
                'top_trader': '无',
                'worst_trader': '无',
                'hot_stock': '无'
            }
    
    async def _get_daily_trading_stats(self, group_id: str) -> Dict[str, Any]:
        """获取全天交易统计"""
        try:
            # 获取今日所有订单
            today = datetime.now().date()
            day_start = datetime.combine(today, datetime.min.time())
            day_end = datetime.combine(today, datetime.min.time().replace(hour=23, minute=59))
            
            day_start_ts = int(day_start.timestamp())
            day_end_ts = int(day_end.timestamp())
            
            # 获取所有订单
            all_orders = self.storage.get_orders()
            daily_orders = [
                order for order in all_orders
                if day_start_ts <= order.get('create_time', 0) <= day_end_ts
                and order.get('status') == 'filled'
            ]
            
            # 统计信息
            total_volume = sum(order.get('filled_amount', 0) for order in daily_orders)
            active_users = len(set(order.get('user_id') for order in daily_orders))
            
            # 计算用户盈亏
            user_profits = {}
            for order in daily_orders:
                user_id = order.get('user_id')
                if user_id not in user_profits:
                    user_profits[user_id] = 0
                
                # 简单计算：卖出订单算盈利，买入订单算成本
                if order.get('order_type') == 'sell':
                    user_profits[user_id] += order.get('filled_amount', 0)
                else:
                    user_profits[user_id] -= order.get('filled_amount', 0)
            
            # 找出最佳和最差交易者
            if user_profits:
                top_trader = max(user_profits.items(), key=lambda x: x[1])
                worst_trader = min(user_profits.items(), key=lambda x: x[1])
                top_trader_name = top_trader[0][:8] + "..." if len(top_trader[0]) > 8 else top_trader[0]
                worst_trader_name = worst_trader[0][:8] + "..." if len(worst_trader[0]) > 8 else worst_trader[0]
            else:
                top_trader_name = "无"
                worst_trader_name = "无"
            
            # 找出最热门股票
            stock_counts = {}
            for order in daily_orders:
                stock_code = order.get('stock_code')
                stock_counts[stock_code] = stock_counts.get(stock_code, 0) + 1
            
            hot_stock = max(stock_counts.items(), key=lambda x: x[1])[0] if stock_counts else "无"
            
            # 获取今日猜股获胜者
            today = datetime.now().strftime('%Y-%m-%d')
            daily_guess = self.storage.get_daily_guess(today)
            guess_winner = "无"
            if daily_guess and daily_guess.get('winner'):
                guess_winner = daily_guess['winner'][:8] + "..." if len(daily_guess['winner']) > 8 else daily_guess['winner']
            
            total_profit = sum(user_profits.values())
            
            return {
                'total_volume': total_volume,
                'total_profit': total_profit,
                'active_users': active_users,
                'top_trader': top_trader_name,
                'worst_trader': worst_trader_name,
                'hot_stock': hot_stock,
                'guess_winner': guess_winner
            }
            
        except Exception as e:
            logger.error(f"获取全天交易统计失败: {e}")
            return {
                'total_volume': 0,
                'total_profit': 0,
                'active_users': 0,
                'top_trader': '无',
                'worst_trader': '无',
                'hot_stock': '无',
                'guess_winner': '无'
            }
