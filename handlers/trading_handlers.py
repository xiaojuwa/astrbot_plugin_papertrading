"""交易命令处理器 - 处理所有交易相关命令"""
from typing import AsyncGenerator
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageEventResult

from .base_trading_handler import BuyOrderHandler, SellOrderHandler
from ..services.trade_coordinator import TradeCoordinator
from ..services.user_interaction import UserInteractionService
from ..services.trading_engine import TradingEngine


class TradingCommandHandlers:
    """交易命令处理器集合"""
    
    def __init__(self, trade_coordinator: TradeCoordinator, user_interaction: UserInteractionService, trading_engine: TradingEngine):
        self.trade_coordinator = trade_coordinator
        self.user_interaction = user_interaction
        self.trading_engine = trading_engine
        
        # 移除冗余子类，直接实例化基类并传入描述信息
        self.buy_handler = BuyOrderHandler(trade_coordinator, user_interaction, trading_engine)
        self.sell_handler = SellOrderHandler(trade_coordinator, user_interaction, trading_engine)
    
    async def handle_market_buy(self, event: AstrMessageEvent) -> AsyncGenerator[MessageEventResult, None]:
        """市价买入处理"""
        self.buy_handler.set_action_description("市价买入")
        async for result in self.buy_handler.execute_trade_flow(event, require_price=False):
            yield result
    
    async def handle_limit_buy(self, event: AstrMessageEvent) -> AsyncGenerator[MessageEventResult, None]:
        """限价买入处理"""
        self.buy_handler.set_action_description("限价买入")
        async for result in self.buy_handler.execute_trade_flow(event, require_price=True):
            yield result
    
    async def handle_market_sell(self, event: AstrMessageEvent) -> AsyncGenerator[MessageEventResult, None]:
        """市价卖出处理"""
        self.sell_handler.set_action_description("市价卖出")
        async for result in self.sell_handler.execute_trade_flow(event, require_price=False):
            yield result
    
    async def handle_limit_sell(self, event: AstrMessageEvent) -> AsyncGenerator[MessageEventResult, None]:
        """限价卖出处理"""
        self.sell_handler.set_action_description("限价卖出")
        async for result in self.sell_handler.execute_trade_flow(event, require_price=True):
            yield result
    
    async def handle_cancel_order(self, event: AstrMessageEvent) -> AsyncGenerator[MessageEventResult, None]:
        """撤销订单处理"""
        user_id = self.trade_coordinator.get_isolated_user_id(event)
        params = event.message_str.strip().split()[1:]
        
        # 验证用户注册
        is_registered, error_msg, user = await self.trade_coordinator.validate_user_registration(event)
        if not is_registered:
            yield MessageEventResult().message(error_msg)
            return
        
        # 检查参数
        if not params:
            yield MessageEventResult().message("❌ 请提供订单号\n格式: /股票撤单 订单号")
            return
        
        order_id = params[0]
        
        try:
            # 使用注入的trading_engine实例，避免局部导入
            success, message = await self.trading_engine.cancel_order(user_id, order_id)
            
            if success:
                yield MessageEventResult().message(f"✅ {message}")
            else:
                yield MessageEventResult().message(f"❌ {message}")
                
        except Exception as e:
            logger.error(f"撤单操作失败: {e}")
            yield MessageEventResult().message("❌ 撤单失败，请稍后重试")


