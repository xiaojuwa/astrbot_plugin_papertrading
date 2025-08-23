"""查询命令处理器 - 处理所有查询相关命令"""
import asyncio
from typing import AsyncGenerator, List, Dict, Any
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageEventResult

from ..models.user import User
from ..models.position import Position
from ..services.trade_coordinator import TradeCoordinator
from ..services.user_interaction import UserInteractionService
from ..utils.formatters import Formatters
from ..utils.validators import Validators


class QueryCommandHandlers:
    """查询命令处理器集合"""
    
    def __init__(self, trade_coordinator: TradeCoordinator, user_interaction: UserInteractionService):
        self.trade_coordinator = trade_coordinator
        self.user_interaction = user_interaction
    
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
