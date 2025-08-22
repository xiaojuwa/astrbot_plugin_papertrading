"""挂单监控服务"""
import asyncio
import time
from typing import List
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
    
    async def start_monitoring(self):
        """开始监控"""
        if self._running:
            return
        
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        print("挂单监控服务已启动")
    
    async def stop_monitoring(self):
        """停止监控"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        print("挂单监控服务已停止")
    
    async def _monitor_loop(self):
        """监控循环"""
        config = self.storage.get_config()
        interval = config.get('monitor_interval', 15)  # 默认15秒
        
        while self._running:
            try:
                # 只在交易时间监控
                if self.stock_service.is_trading_time():
                    await self._check_pending_orders()
                else:
                    print("非交易时间，暂停挂单监控")
                
                # 等待下次检查
                await asyncio.sleep(interval)
                
            except Exception as e:
                print(f"监控循环错误: {e}")
                await asyncio.sleep(interval)
    
    async def _check_pending_orders(self):
        """检查待成交订单"""
        pending_orders = self.storage.get_pending_orders()
        
        if not pending_orders:
            return
        
        print(f"检查 {len(pending_orders)} 个待成交订单")
        
        # 按股票代码分组，减少API调用
        stock_groups = {}
        for order_data in pending_orders:
            stock_code = order_data['stock_code']
            if stock_code not in stock_groups:
                stock_groups[stock_code] = []
            stock_groups[stock_code].append(order_data)
        
        # 逐个股票检查
        for stock_code, orders in stock_groups.items():
            try:
                await self._check_orders_for_stock(stock_code, orders)
            except Exception as e:
                print(f"检查股票 {stock_code} 的订单时出错: {e}")
    
    async def _check_orders_for_stock(self, stock_code: str, orders: List[dict]):
        """检查特定股票的订单"""
        # 获取最新股价
        stock_info = await self.stock_service.get_stock_info(stock_code)
        if not stock_info:
            print(f"无法获取股票 {stock_code} 的信息")
            return
        
        # 检查每个订单
        for order_data in orders:
            try:
                order = Order.from_dict(order_data)
                
                # 检查是否可以成交
                if self._can_fill_order(order, stock_info):
                    await self._fill_order(order, stock_info)
            
            except Exception as e:
                print(f"处理订单 {order_data.get('order_id', 'unknown')} 时出错: {e}")
    
    def _can_fill_order(self, order: Order, stock_info) -> bool:
        """检查订单是否可以成交"""
        if not order.is_pending():
            return False
        
        # 检查股票是否停牌
        if stock_info.is_suspended:
            return False
        
        # 检查价格条件
        current_price = stock_info.current_price
        
        if order.is_buy_order():
            # 买单：当前价格低于等于委托价格时成交
            return current_price <= order.order_price
        else:
            # 卖单：当前价格高于等于委托价格时成交
            return current_price >= order.order_price
    
    async def _fill_order(self, order: Order, stock_info):
        """成交订单"""
        print(f"订单 {order.order_id[:8]}... 达到成交条件，开始成交")
        
        try:
            if order.is_buy_order():
                await self._fill_buy_order(order, stock_info)
            else:
                await self._fill_sell_order(order, stock_info)
        
        except Exception as e:
            print(f"订单成交失败: {e}")
    
    async def _fill_buy_order(self, order: Order, stock_info):
        """成交买单"""
        # 获取用户信息
        user_data = self.storage.get_user(order.user_id)
        if not user_data:
            print(f"用户 {order.user_id} 不存在")
            return
        
        user = User.from_dict(user_data)
        
        # 确定成交价格（取委托价格和市价的较小值）
        fill_price = min(order.order_price, stock_info.get_market_buy_price())
        
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
        
        print(f"买单成交: {order.stock_name} {order.order_volume}股，价格{fill_price:.2f}元")
    
    async def _fill_sell_order(self, order: Order, stock_info):
        """成交卖单"""
        # 获取用户信息
        user_data = self.storage.get_user(order.user_id)
        if not user_data:
            print(f"用户 {order.user_id} 不存在")
            return
        
        user = User.from_dict(user_data)
        
        # 获取持仓信息
        position_data = self.storage.get_position(order.user_id, order.stock_code)
        if not position_data:
            print(f"用户 {order.user_id} 没有股票 {order.stock_code} 的持仓")
            order.cancel_order()
            self.storage.save_order(order.order_id, order.to_dict())
            return
        
        position = Position.from_dict(position_data)
        
        # 检查可卖数量
        if not position.can_sell(order.order_volume):
            print(f"用户 {order.user_id} 可卖数量不足")
            order.cancel_order()
            self.storage.save_order(order.order_id, order.to_dict())
            return
        
        # 确定成交价格（取委托价格和市价的较大值）
        fill_price = max(order.order_price, stock_info.get_market_sell_price())
        
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
        
        print(f"卖单成交: {order.stock_name} {order.order_volume}股，价格{fill_price:.2f}元，到账{total_income:.2f}元")
    
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
