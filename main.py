"""A股模拟交易插件"""
import time
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

# 导入本地模块
from .models.user import User
from .utils.data_storage import DataStorage
from .utils.validators import Validators
from .utils.formatters import Formatters
from .services.stock_data import StockDataService
from .services.trading_engine import TradingEngine
from .services.order_monitor import OrderMonitorService


@register("papertrading", "AI Assistant", "A股模拟交易插件，支持实时买卖、挂单交易、持仓查询、群内排行等功能。", "1.0.0")
class PaperTradingPlugin(Star):
    """A股模拟交易插件主类"""
    
    def __init__(self, context: Context):
        super().__init__(context)
        
        # 初始化服务
        self.storage = DataStorage("papertrading")
        self.stock_service = StockDataService(self.storage)
        self.trading_engine = TradingEngine(self.storage)
        self.order_monitor = OrderMonitorService(self.storage)
        
        logger.info("A股模拟交易插件初始化完成")

    async def initialize(self):
        """插件初始化"""
        try:
            # 启动挂单监控服务
            await self.order_monitor.start_monitoring()
            
            # 注册定时任务
            self.context.register_task(self._daily_maintenance(), "每日维护任务")
            
            logger.info("A股模拟交易插件启动成功")
        except Exception as e:
            logger.error(f"插件初始化失败: {e}")
    
    async def _daily_maintenance(self):
        """每日维护任务"""
        import asyncio
        from datetime import datetime, time as dt_time
        
        while True:
            try:
                # 每天凌晨2点执行维护
                now = datetime.now()
                target_time = datetime.combine(now.date(), dt_time(2, 0))
                
                if now > target_time:
                    target_time = target_time.replace(day=target_time.day + 1)
                
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
        
        # 更新所有用户的T+1持仓状态
        all_users = self.storage.get_all_users()
        for user_id in all_users:
            try:
                from .services.market_rules import MarketRulesEngine
                market_rules = MarketRulesEngine(self.storage)
                market_rules.make_positions_available_for_next_day(user_id)
                
                # 更新用户总资产
                await self.trading_engine.update_user_assets(user_id)
            except Exception as e:
                logger.error(f"更新用户 {user_id} 数据失败: {e}")
        
        # 清理过期的市场数据缓存
        self.storage.clear_market_cache()
        
        logger.info("每日维护任务完成")

    # ==================== 用户注册相关 ====================
    
    @filter.command("股票注册")
    async def register_user(self, event: AstrMessageEvent):
        """用户注册"""
        user_id = event.get_sender_id()
        user_name = event.get_sender_name() or f"用户{user_id}"
        
        # 检查是否已注册
        existing_user = self.storage.get_user(user_id)
        if existing_user:
            yield event.plain_result("您已经注册过了！使用 /我的账户 查看账户信息")
            return
        
        # 创建新用户
        config = self.storage.get_config()
        initial_balance = config.get('initial_balance', 1000000)
        
        user = User(
            user_id=user_id,
            username=user_name,
            balance=initial_balance,
            total_assets=initial_balance,
            register_time=int(time.time()),
            last_login=int(time.time())
        )
        
        # 保存用户
        self.storage.save_user(user_id, user.to_dict())
        
        yield event.plain_result(
            f"🎉 注册成功！\n"
            f"👤 用户名: {user_name}\n"
            f"💰 初始资金: {Formatters.format_currency(initial_balance)}元\n\n"
            f"📖 输入 /帮助 查看使用说明"
        )

    # ==================== 交易相关 ====================
    
    @filter.command("买入")
    async def buy_stock(self, event: AstrMessageEvent):
        """买入股票"""
        user_id = event.get_sender_id()
        
        # 解析参数
        params = event.message_str.strip().split()[1:]  # 去掉命令本身
        parsed = Validators.parse_order_params(params)
        
        if parsed['error']:
            yield event.plain_result(f"❌ {parsed['error']}\n\n格式: /买入 股票代码 数量 [价格]\n例: /买入 000001 1000 12.50")
            return
        
        # 执行买入
        try:
            success, message, order = await self.trading_engine.place_buy_order(
                user_id, 
                parsed['stock_code'], 
                parsed['volume'],
                parsed['price']
            )
            
            if success:
                yield event.plain_result(f"✅ {message}")
            else:
                yield event.plain_result(f"❌ {message}")
                
        except Exception as e:
            logger.error(f"买入操作失败: {e}")
            yield event.plain_result("❌ 交易失败，请稍后重试")
    
    @filter.command("卖出")
    async def sell_stock(self, event: AstrMessageEvent):
        """卖出股票"""
        user_id = event.get_sender_id()
        
        # 解析参数
        params = event.message_str.strip().split()[1:]
        parsed = Validators.parse_order_params(params)
        
        if parsed['error']:
            yield event.plain_result(f"❌ {parsed['error']}\n\n格式: /卖出 股票代码 数量 [价格]\n例: /卖出 000001 500 13.00")
            return
        
        # 执行卖出
        try:
            success, message, order = await self.trading_engine.place_sell_order(
                user_id,
                parsed['stock_code'],
                parsed['volume'],
                parsed['price']
            )
            
            if success:
                yield event.plain_result(f"✅ {message}")
            else:
                yield event.plain_result(f"❌ {message}")
                
        except Exception as e:
            logger.error(f"卖出操作失败: {e}")
            yield event.plain_result("❌ 交易失败，请稍后重试")
    
    @filter.command("撤单")
    async def cancel_order(self, event: AstrMessageEvent):
        """撤销订单"""
        user_id = event.get_sender_id()
        params = event.message_str.strip().split()[1:]
        
        if not params:
            yield event.plain_result("❌ 请提供订单号\n格式: /撤单 订单号")
            return
        
        order_id = params[0]
        
        try:
            success, message = await self.trading_engine.cancel_order(user_id, order_id)
            
            if success:
                yield event.plain_result(f"✅ {message}")
            else:
                yield event.plain_result(f"❌ {message}")
                
        except Exception as e:
            logger.error(f"撤单操作失败: {e}")
            yield event.plain_result("❌ 撤单失败，请稍后重试")

    # ==================== 查询相关 ====================
    
    @filter.command("我的账户")
    async def show_account_info(self, event: AstrMessageEvent):
        """显示账户信息（合并持仓、余额、订单查询）"""
        user_id = event.get_sender_id()
        
        # 检查用户是否注册
        user_data = self.storage.get_user(user_id)
        if not user_data:
            yield event.plain_result("❌ 您还未注册，请先使用 /股票注册 注册账户")
            return
        
        try:
            # 更新用户总资产
            await self.trading_engine.update_user_assets(user_id)
            
            # 获取最新用户数据
            user_data = self.storage.get_user(user_id)
            user = User.from_dict(user_data)
            
            # 获取持仓数据
            positions = self.storage.get_positions(user_id)
            
            # 更新持仓市值
            for pos_data in positions:
                if pos_data['total_volume'] > 0:
                    stock_info = await self.stock_service.get_stock_info(pos_data['stock_code'])
                    if stock_info:
                        from .models.position import Position
                        position = Position.from_dict(pos_data)
                        position.update_market_data(stock_info.current_price)
                        self.storage.save_position(user_id, position.stock_code, position.to_dict())
                        pos_data.update(position.to_dict())
            
            # 格式化输出
            info_text = Formatters.format_user_info(user.to_dict(), positions)
            
            # 添加待成交订单信息
            pending_orders = [order for order in self.storage.get_orders(user_id) if order.get('status') == 'pending']
            if pending_orders:
                info_text += "\n\n" + Formatters.format_pending_orders(pending_orders)
            
            yield event.plain_result(info_text)
            
        except Exception as e:
            logger.error(f"查询账户信息失败: {e}")
            yield event.plain_result("❌ 查询失败，请稍后重试")
    
    @filter.command("股价")
    async def show_stock_price(self, event: AstrMessageEvent):
        """查询股价"""
        params = event.message_str.strip().split()[1:]
        
        if not params:
            yield event.plain_result("❌ 请提供股票代码\n格式: /股价 股票代码\n例: /股价 000001")
            return
        
        stock_code = Validators.normalize_stock_code(params[0])
        if not stock_code:
            yield event.plain_result(f"❌ 无效的股票代码: {params[0]}")
            return
        
        try:
            stock_info = await self.stock_service.get_stock_info(stock_code)
            if stock_info:
                info_text = Formatters.format_stock_info(stock_info.to_dict())
                yield event.plain_result(info_text)
            else:
                yield event.plain_result(f"❌ 无法获取股票 {stock_code} 的信息")
                
        except Exception as e:
            logger.error(f"查询股价失败: {e}")
            yield event.plain_result("❌ 查询失败，请稍后重试")
    
    @filter.command("排行")
    async def show_ranking(self, event: AstrMessageEvent):
        """显示群内排行榜"""
        try:
            all_users_data = self.storage.get_all_users()
            users_list = []
            
            for user_id, user_data in all_users_data.items():
                # 更新用户总资产
                await self.trading_engine.update_user_assets(user_id)
                updated_user_data = self.storage.get_user(user_id)
                if updated_user_data:
                    users_list.append(updated_user_data)
            
            current_user_id = event.get_sender_id()
            ranking_text = Formatters.format_ranking(users_list, current_user_id)
            yield event.plain_result(ranking_text)
            
        except Exception as e:
            logger.error(f"查询排行榜失败: {e}")
            yield event.plain_result("❌ 查询失败，请稍后重试")

    # ==================== 帮助信息 ====================
    
    @filter.command("帮助")
    async def show_help(self, event: AstrMessageEvent):
        """显示帮助信息"""
        help_text = Formatters.format_help_message()
        yield event.plain_result(help_text)

    # ==================== 插件生命周期 ====================
    
    async def terminate(self):
        """插件销毁"""
        try:
            # 停止挂单监控
            await self.order_monitor.stop_monitoring()
            logger.info("A股模拟交易插件已停止")
        except Exception as e:
            logger.error(f"插件停止时出错: {e}")
