"""查询命令处理器 - 处理所有查询相关命令"""
import asyncio
from typing import AsyncGenerator, List, Dict, Any
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageEventResult

from ..models.user import User
from ..models.position import Position
from ..services.trade_coordinator import TradeCoordinator
from ..services.user_interaction import UserInteractionService
from ..services.daily_guess_service import DailyGuessService
from ..services.title_service import TitleService
from ..utils.formatters import Formatters
from ..utils.validators import Validators


class QueryCommandHandlers:
    """查询命令处理器集合"""
    
    def __init__(self, trade_coordinator: TradeCoordinator, user_interaction: UserInteractionService, order_monitor=None, daily_guess_service=None, title_service=None):
        self.trade_coordinator = trade_coordinator
        self.user_interaction = user_interaction
        self.order_monitor = order_monitor
        self.daily_guess_service = daily_guess_service
        self.title_service = title_service
    
    async def handle_account_info(self, event: AstrMessageEvent) -> AsyncGenerator[MessageEventResult, None]:
        """显示账户信息（合并持仓、余额、订单查询）"""
        user_id = self.trade_coordinator.get_isolated_user_id(event)
        
        # 检查用户是否注册
        user_data = self.trade_coordinator.storage.get_user(user_id)
        if not user_data:
            yield MessageEventResult().message("❌ 您还未注册，请先使用 /股票注册 注册账户")
            return
        
        try:
            # 更新用户总资产
            await self.trade_coordinator.update_user_assets_if_needed(user_id)
            
            # 获取最新用户数据
            user_data = self.trade_coordinator.storage.get_user(user_id)
            user = User.from_dict(user_data)
            
            # 获取持仓数据
            positions = self.trade_coordinator.storage.get_positions(user_id)
            
            # 更新持仓市值
            for pos_data in positions:
                if pos_data['total_volume'] > 0:
                    stock_info = await self.trade_coordinator.stock_service.get_stock_info(pos_data['stock_code'])
                    if stock_info:
                        position = Position.from_dict(pos_data)
                        position.update_market_data(stock_info.current_price)
                        self.trade_coordinator.storage.save_position(user_id, position.stock_code, position.to_dict())
                        pos_data.update(position.to_dict())
            
            # 获取冻结资金
            frozen_funds = self.trade_coordinator.storage.calculate_frozen_funds(user_id)
            
            # 格式化输出
            info_text = Formatters.format_user_info(user.to_dict(), positions, frozen_funds)
            
            # 添加待成交订单信息
            pending_orders = [order for order in self.trade_coordinator.storage.get_orders(user_id) if order.get('status') == 'pending']
            if pending_orders:
                info_text += "\n\n" + Formatters.format_pending_orders(pending_orders)
            
            yield MessageEventResult().message(info_text)
            
        except Exception as e:
            logger.error(f"查询账户信息失败: {e}")
            yield MessageEventResult().message("❌ 查询失败，请稍后重试")
    
    async def handle_stock_price(self, event: AstrMessageEvent) -> AsyncGenerator[MessageEventResult, None]:
        """查询股价（支持模糊搜索）"""
        params = event.message_str.strip().split()[1:]
        
        if not params:
            yield MessageEventResult().message("❌ 请提供股票代码或名称\n格式: /股价 股票代码/名称\n例: /股价 000001 或 /股价 平安银行")
            return
        
        keyword = params[0]
        
        try:
            # 搜索股票
            success, error_msg, result = await self.trade_coordinator.search_and_validate_stock(keyword)
            if not success:
                yield MessageEventResult().message(error_msg)
                return
            
            # 处理多个候选的情况
            if result.get("multiple"):
                candidates = result["candidates"]
                selected_stock, error_msg = await self.user_interaction.wait_for_stock_selection(
                    event, candidates, "股价查询"
                )
                if error_msg:
                    yield MessageEventResult().message(error_msg)
                    return
                if not selected_stock:
                    yield MessageEventResult().message("💭 查询已取消")
                    return
                
                # 查询选中股票的价格
                stock_code = selected_stock['code']
                stock_info = await self.trade_coordinator.stock_service.get_stock_info(stock_code)
                if stock_info:
                    info_text = Formatters.format_stock_info(stock_info.to_dict())
                    yield MessageEventResult().message(info_text)
                else:
                    yield MessageEventResult().message("❌ 无法获取股票信息")
                return
            else:
                # 单个结果，直接查询
                stock_code = result['code']
                stock_info = await self.trade_coordinator.stock_service.get_stock_info(stock_code)
                if stock_info:
                    info_text = Formatters.format_stock_info(stock_info.to_dict())
                    yield MessageEventResult().message(info_text)
                else:
                    yield MessageEventResult().message("❌ 无法获取股票信息")
                    
        except Exception as e:
            logger.error(f"查询股价失败: {e}")
            yield MessageEventResult().message("❌ 查询失败，请稍后重试")
    
    async def handle_ranking(self, event: AstrMessageEvent) -> AsyncGenerator[MessageEventResult, None]:
        """显示群内排行榜"""
        try:
            # 获取当前会话的标识，用于过滤同群用户
            platform_name = event.get_platform_name()
            session_id = event.get_session_id()
            session_prefix = f"{platform_name}:"
            session_suffix = f":{session_id}"
            
            all_users_data = self.trade_coordinator.storage.get_all_users()
            users_list = []
            
            # 筛选同会话用户
            same_session_users = []
            for user_id, user_data in all_users_data.items():
                # 只包含相同会话（群聊）的用户
                if user_id.startswith(session_prefix) and user_id.endswith(session_suffix):
                    same_session_users.append(user_id)
            
            # 使用并发批量更新用户资产，提高性能
            if same_session_users:
                update_tasks = [
                    self.trade_coordinator.update_user_assets_if_needed(user_id)
                    for user_id in same_session_users
                ]
                await asyncio.gather(*update_tasks, return_exceptions=True)
                
                # 获取更新后的用户数据
                for user_id in same_session_users:
                    updated_user_data = self.trade_coordinator.storage.get_user(user_id)
                    if updated_user_data:
                        users_list.append(updated_user_data)
            
            current_user_id = self.trade_coordinator.get_isolated_user_id(event)
            
            if not users_list:
                yield MessageEventResult().message("📊 当前群聊暂无用户排行数据\n请先使用 /股票注册 注册账户")
                return
            
            ranking_text = Formatters.format_ranking(users_list, current_user_id)
            yield MessageEventResult().message(ranking_text)
            
        except Exception as e:
            logger.error(f"查询排行榜失败: {e}")
            yield MessageEventResult().message("❌ 查询失败，请稍后重试")
    
    async def handle_order_history(self, event: AstrMessageEvent) -> AsyncGenerator[MessageEventResult, None]:
        """显示历史订单"""
        user_id = self.trade_coordinator.get_isolated_user_id(event)
        
        # 检查用户是否注册
        if not self.trade_coordinator.storage.get_user(user_id):
            yield MessageEventResult().message("❌ 您还未注册，请先使用 /股票注册 注册账户")
            return
        
        # 解析页码参数
        params = event.message_str.strip().split()[1:]
        page = 1
        if params:
            try:
                page = int(params[0])
                if page < 1:
                    page = 1
            except ValueError:
                yield MessageEventResult().message("❌ 页码格式错误\n\n格式: /历史订单 [页码]\n例: /历史订单 1")
                return
        
        try:
            # 获取历史订单
            history_data = self.trade_coordinator.storage.get_user_order_history(user_id, page)
            
            # 格式化输出
            history_text = Formatters.format_order_history(history_data)
            yield MessageEventResult().message(history_text)
            
        except Exception as e:
            logger.error(f"查询历史订单失败: {e}")
            yield MessageEventResult().message("❌ 查询失败，请稍后重试")
    
    async def handle_help(self, event: AstrMessageEvent) -> AsyncGenerator[MessageEventResult, None]:
        """显示帮助信息"""
        help_text = Formatters.format_help_message()
        yield MessageEventResult().message(help_text)
    
    async def handle_polling_status(self, event: AstrMessageEvent) -> AsyncGenerator[MessageEventResult, None]:
        """显示轮询监控状态（管理员专用）"""
        if not self.order_monitor:
            yield MessageEventResult().message("❌ 轮询监控服务未初始化")
            return
        
        try:
            status = self.order_monitor.get_monitor_status()
            
            # 构建状态信息
            status_text = "📊 挂单轮询监控状态\n\n"
            
            # 运行状态
            if status['is_running']:
                if status['is_paused']:
                    status_text += "⏸️ 状态: 已暂停（间隔为0）\n"
                else:
                    status_text += "✅ 状态: 正在运行\n"
            else:
                status_text += "❌ 状态: 已停止\n"
            
            # 轮询配置
            status_text += f"⏱️ 轮询间隔: {status['current_interval']}秒\n"
            
            # 上次轮询时间
            status_text += f"🕒 上次轮询: {status['last_poll_time']}\n"
            
            # 下次轮询时间
            status_text += f"🕓 下次轮询: {status['next_poll_time']}\n"
            
            # 连通性状态
            connectivity_icon = "🟢" if status['last_connectivity_status'] else "🔴"
            status_text += f"{connectivity_icon} 连通性: {'正常' if status['last_connectivity_status'] else '异常'}\n"
            status_text += f"📈 连通成功率: {status['connectivity_rate']:.1f}% ({status['connectivity_stats']})\n"
            
            # 交易时间状态
            trading_icon = "🟢" if status['is_trading_time'] else "⭕"
            status_text += f"{trading_icon} 交易时间: {'是' if status['is_trading_time'] else '否'}"
            
            yield MessageEventResult().message(status_text)
            
        except Exception as e:
            logger.error(f"获取轮询状态失败: {e}")
            yield MessageEventResult().message("❌ 获取轮询状态失败，请稍后重试")
    
    # 每日一猜相关命令
    async def handle_daily_guess(self, event: AstrMessageEvent) -> AsyncGenerator[MessageEventResult, None]:
        """显示今日猜股"""
        if not self.daily_guess_service:
            yield MessageEventResult().message("❌ 每日一猜功能未启用")
            return
        
        try:
            from datetime import datetime
            today = datetime.now().strftime('%Y-%m-%d')
            daily_guess = await self.daily_guess_service.get_daily_guess_status(today)
            
            if not daily_guess:
                # 创建今日猜股
                daily_guess = await self.daily_guess_service.create_daily_guess(today)
            
            # 获取板块信息（如果有的话）
            sector_info = ""
            if hasattr(daily_guess, 'sector') and daily_guess.sector:
                sector_info = f"🏷️ 板块: {daily_guess.sector}\n"
            
            # 检查当前时间状态
            now = datetime.now()
            guess_start = now.replace(hour=9, minute=35, second=0, microsecond=0)
            guess_end = now.replace(hour=15, minute=5, second=0, microsecond=0)
            
            if now < guess_start:
                time_status = f"⏰ 开始时间: 09:35 (还有{int((guess_start - now).total_seconds() / 60)}分钟)"
            elif now > guess_end:
                time_status = "⏰ 已结束 (15:05结束)"
            else:
                time_status = f"⏰ 进行中 (15:05结束，还有{int((guess_end - now).total_seconds() / 60)}分钟)"
            
            message = f"""
🎯 今日一猜
━━━━━━━━━━━━━━━━━━━━
📈 股票: {daily_guess.stock_name} ({daily_guess.stock_code})
{sector_info}💰 开盘价: {daily_guess.open_price:.2f}元
🏆 奖励: {daily_guess.prize_amount:.0f}元
👥 参与人数: {len(daily_guess.guesses)}人
{time_status}
━━━━━━━━━━━━━━━━━━━━
💡 发送 /我猜 价格 参与猜测
            """
            
            yield MessageEventResult().message(message.strip())
            
        except Exception as e:
            logger.error(f"获取每日一猜失败: {e}")
            yield MessageEventResult().message("❌ 获取每日一猜失败，请稍后重试")
    
    async def handle_submit_guess(self, event: AstrMessageEvent) -> AsyncGenerator[MessageEventResult, None]:
        """提交猜测"""
        if not self.daily_guess_service:
            yield MessageEventResult().message("❌ 每日一猜功能未启用")
            return
        
        user_id = self.trade_coordinator.get_isolated_user_id(event)
        params = event.message_str.strip().split()[1:]
        
        if not params:
            yield MessageEventResult().message("❌ 请提供猜测价格\n格式: /我猜 12.50")
            return
        
        try:
            guess_price = float(params[0])
            if guess_price <= 0:
                yield MessageEventResult().message("❌ 价格必须大于0")
                return
            
            success, message = await self.daily_guess_service.submit_guess(user_id, guess_price)
            yield MessageEventResult().message(f"{'✅' if success else '❌'} {message}")
            
        except ValueError:
            yield MessageEventResult().message("❌ 价格格式错误")
        except Exception as e:
            logger.error(f"提交猜测失败: {e}")
            yield MessageEventResult().message("❌ 提交猜测失败，请稍后重试")
    
    async def handle_guess_result(self, event: AstrMessageEvent) -> AsyncGenerator[MessageEventResult, None]:
        """显示猜股结果"""
        if not self.daily_guess_service:
            yield MessageEventResult().message("❌ 每日一猜功能未启用")
            return
        
        try:
            from datetime import datetime
            today = datetime.now().strftime('%Y-%m-%d')
            daily_guess = await self.daily_guess_service.get_daily_guess_status(today)
            
            if not daily_guess:
                yield MessageEventResult().message("❌ 今日猜股活动未开始")
                return
            
            if not daily_guess.is_finished:
                yield MessageEventResult().message("⏰ 猜股活动尚未结束，请等待收盘")
                return
            
            # 获取排行榜
            rankings = await self.daily_guess_service.get_guess_ranking(today)
            
            # 构建结果消息
            message = f"""
🎯 猜股结果
━━━━━━━━━━━━━━━━━━━━
📈 股票: {daily_guess.stock_name} ({daily_guess.stock_code})
💰 收盘价: {daily_guess.close_price:.2f}元
🏆 获胜者: {daily_guess.winner or '无'}
🎁 奖励: {daily_guess.prize_amount:.0f}元
━━━━━━━━━━━━━━━━━━━━
            """
            
            if rankings:
                message += "\n📊 排行榜:\n"
                for i, rank in enumerate(rankings[:5], 1):
                    user_id = rank['user_id'][:8] + "..." if len(rank['user_id']) > 8 else rank['user_id']
                    accuracy = rank['accuracy']
                    is_winner = rank['is_winner']
                    winner_icon = "👑" if is_winner else ""
                    message += f"{i}. {winner_icon} {user_id}: {rank['guess_price']:.2f}元"
                    if accuracy is not None:
                        message += f" (误差: {accuracy:.2f}元)"
                    message += "\n"
            
            yield MessageEventResult().message(message.strip())
            
        except Exception as e:
            logger.error(f"获取猜股结果失败: {e}")
            yield MessageEventResult().message("❌ 获取猜股结果失败，请稍后重试")
    
    # 称号相关命令
    async def handle_my_title(self, event: AstrMessageEvent) -> AsyncGenerator[MessageEventResult, None]:
        """显示我的称号"""
        if not self.title_service:
            yield MessageEventResult().message("❌ 称号功能未启用")
            return
        
        user_id = self.trade_coordinator.get_isolated_user_id(event)
        
        try:
            user_title = await self.title_service.get_user_title(user_id)
            if not user_title:
                yield MessageEventResult().message("❌ 您还没有称号，请先进行交易")
                return
            
            emoji = self.title_service.get_title_emoji(user_title.current_title)
            description = user_title.get_title_description()
            
            message = f"""
🏆 我的称号
━━━━━━━━━━━━━━━━━━━━
{emoji} 当前称号: {user_title.current_title}
📝 称号描述: {description}
💰 总盈亏: {user_title.total_profit:.2f}元
📊 交易次数: {user_title.total_trades}次
🎯 胜率: {user_title.win_rate:.1%}
━━━━━━━━━━━━━━━━━━━━
            """
            
            yield MessageEventResult().message(message.strip())
            
        except Exception as e:
            logger.error(f"获取称号失败: {e}")
            yield MessageEventResult().message("❌ 获取称号失败，请稍后重试")
    
    async def handle_title_ranking(self, event: AstrMessageEvent) -> AsyncGenerator[MessageEventResult, None]:
        """显示称号排行榜"""
        if not self.title_service:
            yield MessageEventResult().message("❌ 称号功能未启用")
            return
        
        try:
            rankings = await self.title_service.get_title_ranking(10)
            if not rankings:
                yield MessageEventResult().message("❌ 暂无称号数据")
                return
            
            message = "🏆 称号排行榜\n━━━━━━━━━━━━━━━━━━━━\n"
            
            for i, rank in enumerate(rankings, 1):
                emoji = self.title_service.get_title_emoji(rank['title'])
                user_id = rank['user_id'][:8] + "..." if len(rank['user_id']) > 8 else rank['user_id']
                profit = rank['total_profit']
                trades = rank['total_trades']
                win_rate = rank['win_rate']
                
                message += f"{i}. {emoji} {user_id} - {rank['title']}\n"
                message += f"   💰 盈亏: {profit:.2f}元 | 📊 交易: {trades}次 | 🎯 胜率: {win_rate:.1%}\n"
            
            message += "━━━━━━━━━━━━━━━━━━━━"
            
            yield MessageEventResult().message(message)
            
        except Exception as e:
            logger.error(f"获取称号排行榜失败: {e}")
            yield MessageEventResult().message("❌ 获取称号排行榜失败，请稍后重试")
    
    async def handle_stock_pool(self, event: AstrMessageEvent) -> AsyncGenerator[MessageEventResult, None]:
        """显示股票池信息"""
        if not self.daily_guess_service:
            yield MessageEventResult().message("❌ 每日一猜功能未启用")
            return
        
        try:
            pool_info = self.daily_guess_service.get_stock_pool_info()
            
            message = f"""
📊 猜股股票池信息
━━━━━━━━━━━━━━━━━━━━
📈 总股票数: {pool_info['total_stocks']}只
🏷️ 板块数量: {len(pool_info['sectors'])}个
⏰ 猜股时间: 09:35 - 15:05
━━━━━━━━━━━━━━━━━━━━
📋 板块分布:
            """
            
            for sector, count in pool_info['sector_counts'].items():
                message += f"• {sector}: {count}只\n"
            
            message += "\n🎲 系统完全随机选择股票，保证公平性"
            
            yield MessageEventResult().message(message.strip())
            
        except Exception as e:
            logger.error(f"获取股票池信息失败: {e}")
            yield MessageEventResult().message("❌ 获取股票池信息失败，请稍后重试")
