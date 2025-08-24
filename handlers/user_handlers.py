"""用户管理处理器 - 处理用户注册等相关命令"""
import time
from typing import AsyncGenerator
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageEventResult

from ..services.trade_coordinator import TradeCoordinator
from ..services.user_interaction import UserInteractionService
from ..models.user import User
from ..utils.formatters import Formatters


class UserCommandHandlers:
    """用户命令处理器集合"""
    
    def __init__(self, trade_coordinator: TradeCoordinator, user_interaction: UserInteractionService, storage):
        self.trade_coordinator = trade_coordinator
        self.user_interaction = user_interaction
        self.storage = storage
    
    async def handle_user_registration(self, event: AstrMessageEvent) -> AsyncGenerator[MessageEventResult, None]:
        """用户注册"""
        user_id = self.trade_coordinator.get_isolated_user_id(event)
        user_name = event.get_sender_name() or f"用户{user_id}"
        
        # 检查是否已注册
        existing_user = self.trade_coordinator.storage.get_user(user_id)
        if existing_user:
            yield MessageEventResult().message("您已经注册过了！使用 /股票账户 查看账户信息")
            return
        
        try:
            # 创建新用户，从插件配置获取初始资金
            initial_balance = self.storage.get_plugin_config_value('initial_balance', 1000000)
            
            user = User(
                user_id=user_id,
                username=user_name,
                balance=initial_balance,
                total_assets=initial_balance,
                register_time=int(time.time()),
                last_login=int(time.time())
            )
            
            # 保存用户
            self.trade_coordinator.storage.save_user(user_id, user.to_dict())
            
            yield MessageEventResult().message(
                f"🎉 注册成功！\n"
                f"👤 用户名: {user_name}\n"
                f"💰 初始资金: {Formatters.format_currency(initial_balance)}元\n\n"
                f"📖 输入 /股票帮助 查看使用说明"
            )
            
        except Exception as e:
            logger.error(f"用户注册失败: {e}")
            yield MessageEventResult().message("❌ 注册失败，请稍后重试")
