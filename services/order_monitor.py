"""挂单监控服务"""
import asyncio
import time
from typing import List
from astrbot.api import logger
from ..models.order import Order, OrderStatus
from ..models.user import User
from ..models.position import Position
from ..utils.data_storage import DataStorage
from .stock_data import StockDataService
from .trading_engine import TradingEngine


class OrderMonitorService:
    """挂单监控服务"""
    
    def __init__(self, storage: DataStorage):
        self.storage = storage
        self.stock_service = StockDataService(storage)
        self.trading_engine = TradingEngine(storage)
        self._running = False
        self._task = None
        self._paused = False  # 新增：暂停状态
    
    async def start_monitoring(self):
        """开始监控"""
        if self._running:
            return
        
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("挂单监控服务已启动")
    
    async def stop_monitoring(self):
        """停止监控"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("挂单监控服务已停止")
    
    async def _monitor_loop(self):
        """监控循环 - 支持动态配置和暂停/恢复"""
        last_trading_status = False
        no_orders_count = 0
        
        while self._running:
            try:
                # 动态读取配置
                interval = self.storage.get_plugin_config_value('monitor_interval', 15)
                
                # 如果间隔为0，进入暂停状态
                if interval <= 0:
                    if not self._paused:
                        logger.info("轮询间隔设为0，暂停挂单监控")
                        self._paused = True
                    await asyncio.sleep(5)  # 暂停时每5秒检查一次配置
                    continue
                else:
                    # 从暂停状态恢复
                    if self._paused:
                        logger.info(f"轮询间隔设为{interval}秒，恢复挂单监控")
                        self._paused = False
                
                is_trading = self.stock_service.is_trading_time()
                
                if is_trading:
                    # 只在交易时间检查订单
                    has_orders = await self._check_pending_orders()
                    
                    # 减少日志输出
                    if not has_orders:
                        no_orders_count += 1
                        if no_orders_count % 10 == 1:  # 每10次检查才输出一次"无订单"日志
                            logger.info(f"当前无待成交订单")
                    else:
                        no_orders_count = 0
                    
                    if not last_trading_status:
                        logger.info("交易时段开始，启动订单监控")
                        last_trading_status = True
                else:
                    # 非交易时间
                    if last_trading_status:
                        logger.info("交易时段结束，暂停订单监控")
                        last_trading_status = False
                    
                    # 非交易时间检查间隔加长，节省资源
                    await asyncio.sleep(min(interval * 4, 60))  # 最长1分钟
                    continue
                
                # 等待下次检查
                await asyncio.sleep(interval)
                
            except Exception as e:
                logger.error(f"监控循环错误: {e}")
                # 使用最小间隔避免过度重试
                await asyncio.sleep(5)
    
    async def _check_pending_orders(self):
        """检查待成交订单"""
        pending_orders = self.storage.get_pending_orders()
        
        if not pending_orders:
            return False
        
        # 减少日志频率 - 只在订单数量变化时输出
        order_count = len(pending_orders)
        if not hasattr(self, '_last_order_count') or self._last_order_count != order_count:
            logger.info(f"监控 {order_count} 个待成交订单")
            self._last_order_count = order_count
        
        # 按股票代码分组，减少API调用
        stock_groups = {}
        for order_data in pending_orders:
            stock_code = order_data['stock_code']
            if stock_code not in stock_groups:
                stock_groups[stock_code] = []
            stock_groups[stock_code].append(order_data)
        
        # 逐个股票检查
        filled_orders = 0
        for stock_code, orders in stock_groups.items():
            try:
                filled_count = await self._check_orders_for_stock(stock_code, orders)
                filled_orders += filled_count
            except Exception as e:
                logger.warning(f"检查股票 {stock_code} 的订单时出错: {e}")
        
        # 有成交时输出信息
        if filled_orders > 0:
            logger.info(f"本轮检查完成，成交 {filled_orders} 个订单")
        
        return True
    
    async def _check_orders_for_stock(self, stock_code: str, orders: List[dict]) -> int:
        """检查特定股票的订单"""
        filled_count = 0
        
        # 获取最新股价
        stock_info = await self.stock_service.get_stock_info(stock_code)
        if not stock_info:
            # 减少错误日志频率
            if not hasattr(self, '_stock_error_count'):
                self._stock_error_count = {}
            if self._stock_error_count.get(stock_code, 0) % 5 == 0:
                logger.warning(f"无法获取股票 {stock_code} 的信息")
            self._stock_error_count[stock_code] = self._stock_error_count.get(stock_code, 0) + 1
            return filled_count
        
        # 检查每个订单
        for order_data in orders:
            try:
                order = Order.from_dict(order_data)
                
                # 检查是否可以成交
                if self._can_fill_order(order, stock_info):
                    await self._fill_order(order, stock_info)
                    filled_count += 1
            
            except Exception as e:
                logger.warning(f"处理订单 {order_data.get('order_id', 'unknown')} 时出错: {e}")
        
        return filled_count
    
    def _can_fill_order(self, order: Order, stock_info) -> bool:
        """检查订单是否可以成交（简化逻辑）"""
        if not order.is_pending():
            return False
        
        # 检查股票是否停牌
        if stock_info.is_suspended:
            return False
        
        # 检查涨跌停限制
        if order.is_buy_order() and stock_info.is_limit_up():
            return False  # 涨停时不能买入
        if order.is_sell_order() and stock_info.is_limit_down():
            return False  # 跌停时不能卖出
        
        # 检查价格条件（简化：直接比较当前价格）
        current_price = stock_info.current_price
        
        if order.is_buy_order():
            # 买单：当前价格低于等于委托价格时成交
            return current_price <= order.order_price
        else:
            # 卖单：当前价格高于等于委托价格时成交
            return current_price >= order.order_price
    
    async def _fill_order(self, order: Order, stock_info):
        """成交订单"""
        logger.info(f"订单 {order.order_id} 达到成交条件，开始成交")
        
        try:
            if order.is_buy_order():
                await self._fill_buy_order(order, stock_info)
            else:
                await self._fill_sell_order(order, stock_info)
        
        except Exception as e:
            logger.info(f"订单成交失败: {e}")
    
    async def _fill_buy_order(self, order: Order, stock_info):
        """成交买单"""
        # 获取用户信息
        user_data = self.storage.get_user(order.user_id)
        if not user_data:
            logger.info(f"用户 {order.user_id} 不存在")
            return
        
        user = User.from_dict(user_data)
        
        # 确定成交价格（使用当前实时价格）
        fill_price = stock_info.current_price
        
        # 计算实际费用
        from .market_rules import MarketRulesEngine
        market_rules = MarketRulesEngine(self.storage)
        total_cost = market_rules.calculate_buy_amount(order.order_volume, fill_price)
        
        # 用户在下单时已经冻结了资金，这里需要处理差价
        original_cost = market_rules.calculate_buy_amount(order.order_volume, order.order_price)
        cost_difference = original_cost - total_cost
        
        # 退还差价
        if cost_difference > 0:
            user.add_balance(cost_difference)
        
        # 更新订单状态
        order.fill_order(order.order_volume, fill_price)
        
        # 更新或创建持仓
        position_data = self.storage.get_position(user.user_id, order.stock_code)
        if position_data:
            position = Position.from_dict(position_data)
            position.add_position(order.order_volume, fill_price)
        else:
            position = Position(
                user_id=user.user_id,
                stock_code=order.stock_code,
                stock_name=order.stock_name,
                total_volume=order.order_volume,
                available_volume=0,  # T+1
                avg_cost=fill_price,
                total_cost=order.order_volume * fill_price,
                market_value=order.order_volume * stock_info.current_price,
                profit_loss=0,
                profit_loss_percent=0,
                last_price=stock_info.current_price,
                update_time=int(time.time())
            )
        
        position.update_market_data(stock_info.current_price)
        
        # 保存数据
        self.storage.save_user(user.user_id, user.to_dict())
        self.storage.save_position(user.user_id, order.stock_code, position.to_dict())
        self.storage.save_order(order.order_id, order.to_dict())
        
        logger.info(f"买单成交: {order.stock_name} {order.order_volume}股，价格{fill_price:.2f}元")
        
        # 向用户推送成交通知
        await self._send_fill_notification(order, fill_price, "买入")
    
    async def _fill_sell_order(self, order: Order, stock_info):
        """成交卖单"""
        # 获取用户信息
        user_data = self.storage.get_user(order.user_id)
        if not user_data:
            logger.info(f"用户 {order.user_id} 不存在")
            return
        
        user = User.from_dict(user_data)
        
        # 获取持仓信息
        position_data = self.storage.get_position(order.user_id, order.stock_code)
        if not position_data:
            logger.info(f"用户 {order.user_id} 没有股票 {order.stock_code} 的持仓")
            order.cancel_order()
            self.storage.save_order(order.order_id, order.to_dict())
            return
        
        position = Position.from_dict(position_data)
        
        # 检查可卖数量
        if not position.can_sell(order.order_volume):
            logger.info(f"用户 {order.user_id} 可卖数量不足")
            order.cancel_order()
            self.storage.save_order(order.order_id, order.to_dict())
            return
        
        # 确定成交价格（使用当前实时价格）
        fill_price = stock_info.current_price
        
        # 计算实际收入
        from .market_rules import MarketRulesEngine
        market_rules = MarketRulesEngine(self.storage)
        total_income = market_rules.calculate_sell_amount(order.order_volume, fill_price)
        
        # 减少持仓
        position.reduce_position(order.order_volume)
        
        # 增加资金
        user.add_balance(total_income)
        
        # 更新订单状态
        order.fill_order(order.order_volume, fill_price)
        
        # 更新持仓市值
        if not position.is_empty():
            position.update_market_data(stock_info.current_price)
        
        # 保存数据
        self.storage.save_user(user.user_id, user.to_dict())
        
        if position.is_empty():
            self.storage.delete_position(user.user_id, order.stock_code)
        else:
            self.storage.save_position(user.user_id, order.stock_code, position.to_dict())
        
        self.storage.save_order(order.order_id, order.to_dict())
        
        logger.info(f"卖单成交: {order.stock_name} {order.order_volume}股，价格{fill_price:.2f}元，到账{total_income:.2f}元")
        
        # 向用户推送成交通知
        await self._send_fill_notification(order, fill_price, "卖出", total_income)
    
    async def force_check_order(self, order_id: str) -> bool:
        """强制检查单个订单"""
        order_data = self.storage.get_order(order_id)
        if not order_data:
            return False
        
        order = Order.from_dict(order_data)
        if not order.is_pending():
            return False
        
        # 获取股票信息
        stock_info = await self.stock_service.get_stock_info(order.stock_code)
        if not stock_info:
            return False
        
        # 检查是否可以成交
        if self._can_fill_order(order, stock_info):
            await self._fill_order(order, stock_info)
            return True
        
        return False
    
    async def _send_fill_notification(self, order: Order, fill_price: float, action: str, total_amount: float = None):
        """向用户发送成交通知"""
        try:
            from astrbot.core.star.star_tools import StarTools
            from astrbot.core.message.message_event_result import MessageEventResult
            
            # 构造成交通知消息
            if action == "买入":
                message = (
                    f"🎉 挂单成交通知\n\n"
                    f"📈 买入成交\n"
                    f"🏷️ {order.stock_name}({order.stock_code})\n"
                    f"📊 数量: {order.order_volume}股\n"
                    f"💰 成交价: {fill_price:.2f}元\n"
                    f"💳 总金额: {order.order_volume * fill_price:.2f}元\n"
                    f"⏰ 成交时间: {time.strftime('%H:%M:%S')}"
                )
            else:  # 卖出
                message = (
                    f"🎉 挂单成交通知\n\n"
                    f"📉 卖出成交\n"
                    f"🏷️ {order.stock_name}({order.stock_code})\n"
                    f"📊 数量: {order.order_volume}股\n"
                    f"💰 成交价: {fill_price:.2f}元\n"
                    f"💳 到账金额: {total_amount:.2f}元\n"
                    f"⏰ 成交时间: {time.strftime('%H:%M:%S')}"
                )
            
            # 构造消息会话（需要从用户ID推导）
            # 注意：这里需要知道用户所在的平台和群组，简化处理使用用户ID
            session_str = f"unknown:private:{order.user_id}"
            
            # 发送消息
            message_chain = MessageEventResult().message(message)
            await StarTools.send_message(session_str, message_chain)
            
            logger.info(f"成交通知已发送给用户 {order.user_id}")
            
        except Exception as e:
            logger.error(f"发送成交通知失败: {e}")
            # 成交通知失败不应影响交易本身
