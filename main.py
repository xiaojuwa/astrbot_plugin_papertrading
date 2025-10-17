"""A股模拟交易插件
完整的模拟股票交易系统，支持买卖、挂单、持仓管理等功能
"""
import asyncio
from datetime import datetime, time as dt_time, timedelta
from astrbot.api.event import AstrMessageEvent, MessageEventResult, filter
from astrbot.api.star import Context, Star
from astrbot.api import logger, AstrBotConfig
from astrbot.core.star.filter.permission import PermissionType

# 导入重构后的处理器
from .handlers.trading_handlers import TradingCommandHandlers
from .handlers.query_handlers import QueryCommandHandlers
from .handlers.user_handlers import UserCommandHandlers

# 导入服务层
from .services.trade_coordinator import TradeCoordinator
from .services.user_interaction import UserInteractionService
from .services.stock_data import StockDataService
from .services.trading_engine import TradingEngine
from .services.order_monitor import OrderMonitorService
from .services.market_rules import MarketRulesEngine
from .services.daily_guess_service import DailyGuessService
from .services.title_service import TitleService
from .services.broadcast_service import BroadcastService
from .utils.data_storage import DataStorage


class PaperTradingPlugin(Star):
    """
    A股模拟交易插件
    
    功能特点：
    - 🎯 完整的模拟交易体验：买入、卖出、挂单、撤单
    - 📊 实时股价查询和持仓管理  
    - 🏆 群内排行榜功能
    - ⚡ 基于真实股票数据的现价交易
    - 🛡️ 完整的A股交易规则支持（T+1、涨跌停等）
    - 🤝 真正的用户交互等待机制
    """
    
    def __init__(self, context: Context, config: dict = None):
        super().__init__(context, config)
        self.plugin_config = config  # 保存插件配置
        self.astrbot_config: AstrBotConfig = context.get_config()  # AstrBot全局配置
        
        # 初始化服务层（依赖注入模式）
        self._initialize_services()
        
        # 初始化命令处理器
        self._initialize_handlers()
        
        logger.info("A股模拟交易插件初始化完成")
    
    def _initialize_services(self):
        """初始化服务层"""
        # 数据存储服务 - 传递插件配置
        self.storage = DataStorage("papertrading", self.plugin_config)
        
        # 股票数据服务
        self.stock_service = StockDataService(self.storage)
        
        # 交易引擎（依赖注入）
        self.trading_engine = TradingEngine(self.storage, self.stock_service)
        
        # 交易协调器服务
        self.trade_coordinator = TradeCoordinator(self.storage, self.stock_service)
        
        # 用户交互服务
        self.user_interaction = UserInteractionService()
        
        # 挂单监控服务（修复参数不匹配问题）
        self.order_monitor = OrderMonitorService(self.storage, self.stock_service)
        
        # 每日一猜服务
        self.daily_guess_service = DailyGuessService(self.storage, self.stock_service)
        
        # 称号服务
        self.title_service = TitleService(self.storage)
        
        # 播报服务
        self.broadcast_service = BroadcastService(self.storage)
    
    def _initialize_handlers(self):
        """初始化命令处理器"""
        # 交易命令处理器（注入TradingEngine）
        self.trading_handlers = TradingCommandHandlers(
            self.trade_coordinator, 
            self.user_interaction,
            self.trading_engine,
            self.title_service
        )
        
        # 查询命令处理器
        self.query_handlers = QueryCommandHandlers(
            self.trade_coordinator, 
            self.user_interaction,
            self.order_monitor,
            self.daily_guess_service,
            self.title_service
        )
        
        # 用户管理处理器
        self.user_handlers = UserCommandHandlers(
            self.trade_coordinator, 
            self.user_interaction, 
            self.storage  # 传递storage而不是config
        )
    
    async def initialize(self):
        """插件初始化（AstrBot生命周期方法）"""
        try:
            # 启动挂单监控服务
            monitor_interval = self.storage.get_plugin_config_value("monitor_interval", 15)
            if monitor_interval > 0:
                await self.order_monitor.start_monitoring()
                logger.info(f"挂单监控服务已启动，轮询间隔: {monitor_interval}秒")
            else:
                logger.info("轮询间隔为0，挂单监控服务暂停")
            
            # 注册定时任务
            asyncio.create_task(self._daily_maintenance_task())
            
            logger.info("A股模拟交易插件启动完成")
        except Exception as e:
            logger.error(f"插件初始化失败: {e}")
    
    async def terminate(self):
        """插件销毁（AstrBot生命周期方法）"""
        try:
            # 停止挂单监控
            await self.order_monitor.stop_monitoring()
            logger.info("A股模拟交易插件已停止")
        except Exception as e:
            logger.error(f"插件停止时出错: {e}")
    
    async def _daily_maintenance_task(self):
        """每日维护任务"""        
        while True:
            try:
                # 每天凌晨2点执行维护
                now = datetime.now()
                target_time = datetime.combine(now.date(), dt_time(2, 0))
                
                if now > target_time:
                    # 修复日期计算错误：使用timedelta避免跨月问题
                    target_time = target_time + timedelta(days=1)
                
                sleep_seconds = (target_time - now).total_seconds()
                await asyncio.sleep(sleep_seconds)
                
                # 执行维护任务
                await self._perform_daily_maintenance()
                
            except Exception as e:
                logger.error(f"每日维护任务错误: {e}")
                await asyncio.sleep(3600)  # 出错后等待1小时
    
    async def _perform_daily_maintenance(self):
        """执行每日维护"""
        logger.info("开始执行每日维护任务")
        
        try:
            # 更新所有用户的T+1持仓状态
            all_users = self.storage.get_all_users()
            for user_id in all_users:
                try:
                    # 使用已初始化的服务实例，避免局部导入
                    market_rules = MarketRulesEngine(self.storage)
                    market_rules.make_positions_available_for_next_day(user_id)
                    
                    # 更新用户总资产（使用已有的trading_engine实例）
                    await self.trading_engine.update_user_assets(user_id)
                except Exception as e:
                    logger.error(f"更新用户 {user_id} 数据失败: {e}")
            
            # 清理过期的市场数据缓存
            self.storage.clear_market_cache()
            
            # 结束昨日猜股活动
            try:
                yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
                await self.daily_guess_service.finish_daily_guess(yesterday)
            except Exception as e:
                logger.error(f"结束昨日猜股失败: {e}")
            
            # 启动播报定时任务
            asyncio.create_task(self._broadcast_scheduler())
            
            # 启动猜股定时任务
            asyncio.create_task(self._daily_guess_scheduler())
            
            logger.info("每日维护任务完成")
        except Exception as e:
            logger.error(f"每日维护任务执行失败: {e}")
    
    async def _broadcast_scheduler(self):
        """播报定时任务"""
        while True:
            try:
                now = datetime.now()
                
                # 中午收盘播报 (11:30)
                morning_time = datetime.combine(now.date(), dt_time(11, 30))
                if now <= morning_time:
                    sleep_seconds = (morning_time - now).total_seconds()
                    await asyncio.sleep(sleep_seconds)
                    await self._send_morning_broadcast()
                
                # 下午收盘播报 (15:00)
                evening_time = datetime.combine(now.date(), dt_time(15, 0))
                if now <= evening_time:
                    sleep_seconds = (evening_time - now).total_seconds()
                    await asyncio.sleep(sleep_seconds)
                    await self._send_evening_broadcast()
                
                # 等待到明天
                tomorrow = now + timedelta(days=1)
                tomorrow_morning = datetime.combine(tomorrow.date(), dt_time(11, 30))
                sleep_seconds = (tomorrow_morning - now).total_seconds()
                await asyncio.sleep(sleep_seconds)
                
            except Exception as e:
                logger.error(f"播报定时任务错误: {e}")
                await asyncio.sleep(3600)
    
    async def _send_morning_broadcast(self):
        """发送中午播报"""
        try:
            # 这里需要获取群ID，暂时跳过具体实现
            # group_id = event.group_id  # 需要从事件中获取
            # message = await self.broadcast_service.generate_morning_broadcast(group_id)
            # await self._send_group_message(group_id, message)
            logger.info("中午播报任务执行")
        except Exception as e:
            logger.error(f"发送中午播报失败: {e}")
    
    async def _send_evening_broadcast(self):
        """发送下午播报"""
        try:
            # 这里需要获取群ID，暂时跳过具体实现
            # group_id = event.group_id  # 需要从事件中获取
            # message = await self.broadcast_service.generate_evening_broadcast(group_id)
            # await self._send_group_message(group_id, message)
            logger.info("下午播报任务执行")
        except Exception as e:
            logger.error(f"发送下午播报失败: {e}")
    
    async def _daily_guess_scheduler(self):
        """猜股定时任务"""
        from .utils.market_time import market_time_manager
        
        while True:
            try:
                now = datetime.now()
                today = now.date()
                
                # 检查是否为交易日
                if not market_time_manager.is_trading_day(today):
                    # 非交易日，等待到下一个交易日
                    next_trading_day = None
                    for i in range(1, 8):  # 最多查找7天
                        check_date = today + timedelta(days=i)
                        if market_time_manager.is_trading_day(check_date):
                            next_trading_day = check_date
                            break
                    
                    if next_trading_day:
                        next_trading_time = datetime.combine(next_trading_day, dt_time(9, 35))
                        sleep_seconds = (next_trading_time - now).total_seconds()
                        logger.info(f"今日非交易日，等待到下一个交易日 {next_trading_day}")
                        await asyncio.sleep(sleep_seconds)
                    else:
                        # 找不到下一个交易日，等待1小时后重试
                        await asyncio.sleep(3600)
                    continue
                
                # 交易日逻辑
                today_str = today.strftime('%Y-%m-%d')
                daily_guess = await self.daily_guess_service.get_daily_guess_status(today_str)
                
                # 09:35 开始今日猜股
                guess_start_time = datetime.combine(today, dt_time(9, 35))
                if now <= guess_start_time:
                    # 等待到09:35
                    sleep_seconds = (guess_start_time - now).total_seconds()
                    await asyncio.sleep(sleep_seconds)
                    await self._start_today_guess()
                elif not daily_guess:
                    # 如果已经过了09:35但没有猜股记录，立即开始
                    await self._start_today_guess()
                
                # 15:05 结束今日猜股
                guess_end_time = datetime.combine(today, dt_time(15, 5))
                if now <= guess_end_time:
                    # 等待到15:05
                    sleep_seconds = (guess_end_time - now).total_seconds()
                    await asyncio.sleep(sleep_seconds)
                    await self._finish_today_guess()
                elif daily_guess and not daily_guess.is_finished:
                    # 如果已经过了15:05但猜股未结束，立即结束
                    await self._finish_today_guess()
                
                # 等待到明天
                tomorrow = today + timedelta(days=1)
                tomorrow_guess_start = datetime.combine(tomorrow, dt_time(9, 35))
                sleep_seconds = (tomorrow_guess_start - now).total_seconds()
                await asyncio.sleep(sleep_seconds)
                
            except Exception as e:
                logger.error(f"猜股定时任务错误: {e}")
                await asyncio.sleep(3600)
    
    async def _start_today_guess(self):
        """开始今日猜股"""
        try:
            # 检查是否为交易日
            from .utils.market_time import market_time_manager
            if not market_time_manager.is_trading_day():
                logger.info("今日非交易日，跳过每日竞猜")
                return
            
            today = datetime.now().strftime('%Y-%m-%d')
            daily_guess = await self.daily_guess_service.create_daily_guess(today)
            if daily_guess:
                # 生成开始消息
                message = f"""
🎯 今日一猜
━━━━━━━━━━━━━━━━━━━━
📈 股票: {daily_guess.stock_name} ({daily_guess.stock_code})
💰 开盘价: {daily_guess.open_price:.2f}元
🏆 奖励: {daily_guess.prize_amount}元
👥 参与人数: 0人
⏰ 进行中 (15:05结束)
━━━━━━━━━━━━━━━━━━━━
💡 发送 /我猜 价格 参与猜测
                """
                
                # 发送到配置的群聊
                await self._broadcast_to_configured_groups(message)
                logger.info(f"今日猜股开始: {daily_guess.stock_name} ({daily_guess.stock_code})")
            else:
                logger.warning("创建今日猜股失败")
        except Exception as e:
            logger.error(f"开始今日猜股失败: {e}")
    
    async def _finish_today_guess(self):
        """结束今日猜股"""
        try:
            # 检查是否为交易日
            from .utils.market_time import market_time_manager
            if not market_time_manager.is_trading_day():
                logger.info("今日非交易日，跳过每日竞猜结束")
                return
            
            today = datetime.now().strftime('%Y-%m-%d')
            success, message = await self.daily_guess_service.finish_daily_guess(today)
            if success:
                # 获取猜股结果
                daily_guess = await self.daily_guess_service.get_daily_guess_status(today)
                if daily_guess:
                    # 获取排行榜
                    rankings = await self.daily_guess_service.get_guess_ranking(today)
                    
                    # 生成结束消息
                    result_message = f"""
🎯 今日一猜结果
━━━━━━━━━━━━━━━━━━━━
📈 股票: {daily_guess.stock_name} ({daily_guess.stock_code})
💰 收盘价: {daily_guess.close_price:.2f}元
🏆 获胜者: {daily_guess.winner if daily_guess.winner else '无'}
🎁 奖励: {daily_guess.prize_amount}元
👥 参与人数: {len(daily_guess.guesses)}人
━━━━━━━━━━━━━━━━━━━━
                    """
                    
                    # 添加排行榜
                    if rankings:
                        result_message += "\n📊 排行榜:\n"
                        for i, rank in enumerate(rankings[:5], 1):
                            user_id = rank['user_id'][:8] + "..." if len(rank['user_id']) > 8 else rank['user_id']
                            accuracy = rank['accuracy']
                            is_winner = rank['is_winner']
                            winner_icon = "👑" if is_winner else ""
                            result_message += f"{i}. {winner_icon} {user_id}: {rank['guess_price']:.2f}元"
                            if accuracy is not None:
                                result_message += f" (误差: {accuracy:.2f}元)"
                            result_message += "\n"
                    
                    result_message += "\n💡 明天09:35继续猜股！"
                    
                    # 发送到配置的群聊
                    await self._broadcast_to_configured_groups(result_message)
                    logger.info(f"今日猜股结束: {message}")
            else:
                logger.warning(f"结束今日猜股失败: {message}")
        except Exception as e:
            logger.error(f"结束今日猜股失败: {e}")
    
    async def _broadcast_to_configured_groups(self, message: str):
        """向配置的群聊广播消息"""
        try:
            # 检查是否启用推送
            enable_broadcast = self.storage.get_plugin_config_value('enable_daily_guess_broadcast', False)
            if not enable_broadcast:
                logger.info("每日一猜推送功能未启用")
                return
            
            # 获取配置的群聊列表
            broadcast_groups = self.storage.get_plugin_config_value('broadcast_groups', '')
            if not broadcast_groups:
                logger.info("未配置推送群聊，跳过广播")
                return
            
            from astrbot.core.star.star_tools import StarTools
            from astrbot.api.event import MessageEventResult
            
            # 解析群聊列表
            group_sessions = []
            for group_str in broadcast_groups.split(','):
                group_str = group_str.strip()
                if group_str:
                    group_sessions.append(group_str)
            
            if not group_sessions:
                logger.info("配置的群聊列表为空，跳过广播")
                return
            
            # 向每个配置的群聊发送消息
            success_count = 0
            for session_id in group_sessions:
                try:
                    message_chain = MessageEventResult().message(message)
                    success = await StarTools.send_message(session_id, message_chain)
                    if success:
                        logger.info(f"群聊广播成功: {session_id}")
                        success_count += 1
                    else:
                        logger.warning(f"群聊广播失败: {session_id}")
                except Exception as e:
                    logger.error(f"向群聊 {session_id} 发送消息失败: {e}")
            
            logger.info(f"群聊广播完成，成功发送到 {success_count}/{len(group_sessions)} 个群聊")
            
        except Exception as e:
            logger.error(f"群聊广播失败: {e}")

    # ==================== 用户管理命令 ====================
    
    @filter.command("股票注册")
    async def register_user(self, event: AstrMessageEvent):
        """用户注册"""
        async for result in self.user_handlers.handle_user_registration(event):
            yield result

    # ==================== 交易命令 ====================
    
    @filter.command("买入")
    async def market_buy_stock(self, event: AstrMessageEvent):
        """市价买入股票"""
        async for result in self.trading_handlers.handle_market_buy(event):
            yield result
    
    @filter.command("限价买入")
    async def limit_buy_stock(self, event: AstrMessageEvent):
        """限价买入股票"""
        async for result in self.trading_handlers.handle_limit_buy(event):
            yield result
    
    @filter.command("卖出")
    async def market_sell_stock(self, event: AstrMessageEvent):
        """市价卖出股票"""
        async for result in self.trading_handlers.handle_market_sell(event):
            yield result
    
    @filter.command("限价卖出")
    async def limit_sell_stock(self, event: AstrMessageEvent):
        """限价卖出股票"""
        async for result in self.trading_handlers.handle_limit_sell(event):
            yield result
    
    @filter.command("股票撤单")
    async def cancel_order(self, event: AstrMessageEvent):
        """撤销订单"""
        async for result in self.trading_handlers.handle_cancel_order(event):
            yield result

    # ==================== 查询命令 ====================
    
    @filter.command("股票账户")
    async def show_account_info(self, event: AstrMessageEvent):
        """显示账户信息"""
        async for result in self.query_handlers.handle_account_info(event):
            yield result
    
    @filter.command("股价")
    async def show_stock_price(self, event: AstrMessageEvent):
        """查询股价"""
        async for result in self.query_handlers.handle_stock_price(event):
            yield result
    
    @filter.command("股票排行")
    async def show_ranking(self, event: AstrMessageEvent):
        """显示群内排行榜"""
        async for result in self.query_handlers.handle_ranking(event):
            yield result
    
    @filter.command("历史订单")
    async def show_order_history(self, event: AstrMessageEvent):
        """显示历史订单"""
        async for result in self.query_handlers.handle_order_history(event):
            yield result
    
    @filter.command("股票帮助")
    async def show_help(self, event: AstrMessageEvent):
        """显示帮助信息"""
        async for result in self.query_handlers.handle_help(event):
            yield result
    
    # ==================== 游戏化功能命令 ====================
    
    @filter.command("今日一猜")
    async def daily_guess(self, event: AstrMessageEvent):
        """显示今日猜股活动"""
        async for result in self.query_handlers.handle_daily_guess(event):
            yield result
    
    @filter.command("我猜")
    async def submit_guess(self, event: AstrMessageEvent):
        """提交猜测价格"""
        async for result in self.query_handlers.handle_submit_guess(event):
            yield result
    
    @filter.command("猜股结果")
    async def guess_result(self, event: AstrMessageEvent):
        """显示猜股结果"""
        async for result in self.query_handlers.handle_guess_result(event):
            yield result
    
    @filter.command("我的称号")
    async def my_title(self, event: AstrMessageEvent):
        """显示我的称号"""
        async for result in self.query_handlers.handle_my_title(event):
            yield result
    
    
    @filter.command("称号榜")
    async def title_ranking(self, event: AstrMessageEvent):
        """显示称号排行榜"""
        async for result in self.query_handlers.handle_title_ranking(event):
            yield result
    
    @filter.command("股票池")
    async def stock_pool(self, event: AstrMessageEvent):
        """显示猜股股票池信息"""
        async for result in self.query_handlers.handle_stock_pool(event):
            yield result
    
    # ==================== 管理员命令 ====================
    
    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("轮询状态")
    async def show_polling_status(self, event: AstrMessageEvent):
        """显示轮询监控状态（管理员专用）"""
        async for result in self.query_handlers.handle_polling_status(event):
            yield result