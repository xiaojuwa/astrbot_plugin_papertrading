"""称号服务"""
import time
from typing import Dict, Any, List, Optional
from astrbot.api import logger

from ..models.user_title import UserTitle, TITLE_RULES
from ..utils.data_storage import DataStorage


class TitleService:
    """称号服务"""
    
    def __init__(self, storage: DataStorage):
        self.storage = storage
    
    async def update_user_title(self, user_id: str):
        """更新用户称号"""
        try:
            # 获取用户交易统计
            stats = await self._get_user_trading_stats(user_id)
            
            # 确定新称号
            new_title = self._determine_title(stats)
            
            # 获取当前称号
            current_title = self.storage.get_user_title(user_id)
            if not current_title:
                current_title = UserTitle(user_id=user_id)
            else:
                current_title = UserTitle.from_dict(current_title)
            
            # 更新称号
            if new_title != current_title.current_title:
                old_title = current_title.current_title
                current_title.update_title(new_title)
                current_title.total_profit = stats.get('total_profit', 0)
                current_title.total_trades = stats.get('total_trades', 0)
                current_title.win_rate = stats.get('win_rate', 0)
                
                self.storage.save_user_title(user_id, current_title)
                
                # 发送称号升级通知
                await self._send_title_upgrade_notification(user_id, old_title, new_title)
                logger.info(f"用户 {user_id} 称号升级: {old_title} -> {new_title}")
            
        except Exception as e:
            logger.error(f"更新用户称号失败 {user_id}: {e}")
    
    def _determine_title(self, stats: Dict[str, Any]) -> str:
        """根据统计确定称号"""
        total_profit = stats.get('total_profit', 0)
        total_trades = stats.get('total_trades', 0)
        initial_balance = stats.get('initial_balance', 1000000)  # 默认100万初始资金
        
        # 计算收益率
        profit_rate = total_profit / initial_balance if initial_balance > 0 else 0
        
        for title, rules in TITLE_RULES.items():
            if (rules['min_profit_rate'] <= profit_rate < rules['max_profit_rate'] and
                rules['min_trades'] <= total_trades < rules['max_trades']):
                return title
        
        return '新手'
    
    async def _get_user_trading_stats(self, user_id: str) -> Dict[str, Any]:
        """获取用户交易统计"""
        try:
            # 获取用户数据
            user_data = self.storage.get_user(user_id)
            if not user_data:
                return {'total_profit': 0, 'total_trades': 0, 'win_rate': 0, 'initial_balance': 1000000}
            
            initial_balance = user_data.get('total_assets', 1000000)  # 使用总资产作为初始资金
            current_balance = user_data.get('balance', 0)
            
            # 获取持仓数据
            positions = self.storage.get_positions(user_id)
            total_market_value = sum(pos.get('market_value', 0) for pos in positions)
            
            # 计算总资产
            total_assets = current_balance + total_market_value
            
            # 计算总盈亏
            total_profit = total_assets - initial_balance
            
            # 获取交易统计
            orders = self.storage.get_orders(user_id)
            filled_orders = [order for order in orders if order.get('status') == 'filled']
            total_trades = len(filled_orders)
            
            # 计算胜率
            win_trades = 0
            for order in filled_orders:
                if order.get('order_type') == 'sell':
                    # 简单计算：卖出订单都算盈利（实际应该计算具体盈亏）
                    win_trades += 1
            
            win_rate = win_trades / total_trades if total_trades > 0 else 0
            
            return {
                'total_profit': total_profit,
                'total_trades': total_trades,
                'win_rate': win_rate,
                'initial_balance': initial_balance
            }
            
        except Exception as e:
            logger.error(f"获取用户交易统计失败 {user_id}: {e}")
            return {'total_profit': 0, 'total_trades': 0, 'win_rate': 0, 'initial_balance': 1000000}
    
    async def _send_title_upgrade_notification(self, user_id: str, old_title: str, new_title: str):
        """发送称号升级通知"""
        try:
            # 这里可以发送通知消息，暂时只记录日志
            logger.info(f"称号升级通知: {user_id} {old_title} -> {new_title}")
        except Exception as e:
            logger.error(f"发送称号升级通知失败: {e}")
    
    async def get_user_title(self, user_id: str) -> Optional[UserTitle]:
        """获取用户称号"""
        title_data = self.storage.get_user_title(user_id)
        if not title_data:
            return None
        return UserTitle.from_dict(title_data)
    
    async def get_title_ranking(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取称号排行榜"""
        try:
            all_titles = self.storage.get_all_user_titles()
            if not all_titles:
                return []
            
            # 转换为UserTitle对象并排序
            title_objects = []
            for user_id, title_data in all_titles.items():
                title_obj = UserTitle.from_dict(title_data)
                title_objects.append({
                    'user_id': user_id,
                    'title': title_obj.current_title,
                    'total_profit': title_obj.total_profit,
                    'total_trades': title_obj.total_trades,
                    'win_rate': title_obj.win_rate
                })
            
            # 按总盈亏排序
            title_objects.sort(key=lambda x: x['total_profit'], reverse=True)
            
            return title_objects[:limit]
            
        except Exception as e:
            logger.error(f"获取称号排行榜失败: {e}")
            return []
    
    def get_title_emoji(self, title: str) -> str:
        """获取称号对应的表情"""
        emoji_map = {
            '新手': '🆕',
            '韭菜': '🥬',
            '小散': '👤',
            '股民': '📈',
            '高手': '💪',
            '股神': '👑',
            '巴菲特': '🧙‍♂️'
        }
        return emoji_map.get(title, '❓')
    
    def get_title_progress(self, user_id: str) -> Dict[str, Any]:
        """获取称号进度信息"""
        try:
            stats = await self._get_user_trading_stats(user_id)
            current_title = self._determine_title(stats)
            
            # 找到下一个称号
            next_title = None
            next_requirements = None
            
            titles = list(TITLE_RULES.keys())
            current_index = titles.index(current_title) if current_title in titles else 0
            
            if current_index < len(titles) - 1:
                next_title = titles[current_index + 1]
                next_requirements = TITLE_RULES[next_title]
            
            return {
                'current_title': current_title,
                'next_title': next_title,
                'next_requirements': next_requirements,
                'current_stats': stats,
                'progress': self._calculate_progress(stats, next_requirements) if next_requirements else None
            }
        except Exception as e:
            logger.error(f"获取称号进度失败 {user_id}: {e}")
            return {
                'current_title': '新手',
                'next_title': None,
                'next_requirements': None,
                'current_stats': {'total_profit': 0, 'total_trades': 0, 'win_rate': 0, 'initial_balance': 1000000},
                'progress': None
            }
    
    def _calculate_progress(self, stats: Dict[str, Any], next_requirements: Dict[str, Any]) -> Dict[str, Any]:
        """计算到下一个称号的进度"""
        total_profit = stats.get('total_profit', 0)
        total_trades = stats.get('total_trades', 0)
        initial_balance = stats.get('initial_balance', 1000000)
        profit_rate = total_profit / initial_balance if initial_balance > 0 else 0
        
        # 计算收益率进度
        profit_rate_progress = 0
        if next_requirements['min_profit_rate'] > 0:
            profit_rate_progress = min(100, (profit_rate / next_requirements['min_profit_rate']) * 100)
        elif next_requirements['min_profit_rate'] <= 0 and profit_rate >= next_requirements['min_profit_rate']:
            profit_rate_progress = 100
        
        # 计算交易次数进度
        trades_progress = min(100, (total_trades / next_requirements['min_trades']) * 100) if next_requirements['min_trades'] > 0 else 100
        
        return {
            'profit_rate_progress': max(0, profit_rate_progress),
            'trades_progress': max(0, trades_progress),
            'overall_progress': min(profit_rate_progress, trades_progress)
        }