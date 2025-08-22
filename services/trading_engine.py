"""交易引擎"""
import time
from typing import Optional, Tuple, Dict, Any
from ..models.user import User
from ..models.stock import StockInfo
from ..models.order import Order, OrderType, OrderStatus, PriceType
from ..models.position import Position
from ..utils.data_storage import DataStorage
from .market_rules import MarketRulesEngine


class TradingEngine:
    """交易引擎"""
    
    def __init__(self, storage: DataStorage, stock_service=None):
        self.storage = storage
        self.market_rules = MarketRulesEngine(storage)
        self.stock_service = stock_service  # 依赖注入，避免循环依赖
    
    async def place_buy_order(self, user_id: str, stock_code: str, volume: int, 
                            price: Optional[float] = None) -> Tuple[bool, str, Optional[Order]]:
        """下买单"""
        # 1. 获取用户信息
        user_data = self.storage.get_user(user_id)
        if not user_data:
            return False, "用户未注册，请先使用 /股票注册 注册账户", None
        
        user = User.from_dict(user_data)
        
        # 2. 获取股票信息
        if not self.stock_service:
            from .stock_data import StockDataService
            self.stock_service = StockDataService(self.storage)
        stock_info = await self.stock_service.get_stock_info(stock_code)
        
        if not stock_info:
            return False, f"无法获取股票{stock_code}的信息", None
        
        # 3. 确定订单价格和类型
        if price is None:
            # 市价单
            order_price = stock_info.get_market_buy_price()
            price_type = PriceType.MARKET
        else:
            # 限价单
            order_price = price
            price_type = PriceType.LIMIT
        
        # 4. 创建订单
        order = Order(
            order_id="",  # 将在__post_init__中生成
            user_id=user_id,
            stock_code=stock_code,
            stock_name=stock_info.name,
            order_type=OrderType.BUY,
            price_type=price_type,
            order_price=order_price,
            order_volume=volume,
            filled_volume=0,
            filled_amount=0,
            status=OrderStatus.PENDING,
            create_time=0,  # 将在__post_init__中生成
            update_time=0   # 将在__post_init__中生成
        )
        
        # 5. 市场规则验证（包含涨停跌停检查）
        is_valid, error_msg = self.market_rules.validate_buy_order(stock_info, order, user.balance)
        if not is_valid:
            return False, error_msg, None
        
        # 6. 处理订单（简化逻辑）
        if order.is_market_order():
            # 市价单立即按当前价格成交
            order.order_price = stock_info.current_price
            return await self._execute_buy_order_immediately(user, order, stock_info)
        else:
            # 限价单检查是否能立即成交
            if order.order_price >= stock_info.current_price:
                # 可以立即成交，使用当前价格
                order.order_price = stock_info.current_price
                return await self._execute_buy_order_immediately(user, order, stock_info)
            else:
                # 挂单等待
                return await self._place_pending_buy_order(user, order)
    
    async def place_sell_order(self, user_id: str, stock_code: str, volume: int,
                             price: Optional[float] = None) -> Tuple[bool, str, Optional[Order]]:
        """下卖单"""
        # 1. 获取用户信息
        user_data = self.storage.get_user(user_id)
        if not user_data:
            return False, "用户未注册，请先使用 /股票注册 注册账户", None
        
        user = User.from_dict(user_data)
        
        # 2. 获取持仓信息
        position_data = self.storage.get_position(user_id, stock_code)
        position = Position.from_dict(position_data) if position_data else None
        
        # 3. 获取股票信息
        if not self.stock_service:
            from .stock_data import StockDataService
            self.stock_service = StockDataService(self.storage)
        stock_info = await self.stock_service.get_stock_info(stock_code)
        
        if not stock_info:
            return False, f"无法获取股票{stock_code}的信息", None
        
        # 4. 确定订单价格和类型
        if price is None:
            # 市价单
            order_price = stock_info.get_market_sell_price()
            price_type = PriceType.MARKET
        else:
            # 限价单
            order_price = price
            price_type = PriceType.LIMIT
        
        # 5. 创建订单
        order = Order(
            order_id="",
            user_id=user_id,
            stock_code=stock_code,
            stock_name=stock_info.name,
            order_type=OrderType.SELL,
            price_type=price_type,
            order_price=order_price,
            order_volume=volume,
            filled_volume=0,
            filled_amount=0,
            status=OrderStatus.PENDING,
            create_time=0,
            update_time=0
        )
        
        # 6. 市场规则验证（包含涨停跌停检查）
        is_valid, error_msg = self.market_rules.validate_sell_order(stock_info, order, position)
        if not is_valid:
            return False, error_msg, None
        
        # 7. 处理订单（简化逻辑）
        if order.is_market_order():
            # 市价单立即按当前价格成交
            order.order_price = stock_info.current_price
            return await self._execute_sell_order_immediately(user, order, position, stock_info)
        else:
            # 限价单检查是否能立即成交
            if order.order_price <= stock_info.current_price:
                # 可以立即成交，使用当前价格
                order.order_price = stock_info.current_price
                return await self._execute_sell_order_immediately(user, order, position, stock_info)
            else:
                # 挂单等待
                return await self._place_pending_sell_order(user, order, position)
    
    async def _execute_buy_order_immediately(self, user: User, order: Order, 
                                           stock_info: StockInfo) -> Tuple[bool, str, Order]:
        """立即执行买入订单"""
        # 1. 计算实际费用
        total_cost = self.market_rules.calculate_buy_amount(order.order_volume, order.order_price)
        
        # 2. 检查资金
        if not user.can_buy(total_cost):
            return False, f"资金不足，需要{total_cost:.2f}元", order
        
        # 3. 扣除资金
        user.deduct_balance(total_cost)
        
        # 4. 更新订单状态
        order.fill_order(order.order_volume, order.order_price)
        
        # 5. 更新或创建持仓
        position_data = self.storage.get_position(user.user_id, order.stock_code)
        if position_data:
            position = Position.from_dict(position_data)
            position.add_position(order.order_volume, order.order_price)
        else:
            position = Position(
                user_id=user.user_id,
                stock_code=order.stock_code,
                stock_name=order.stock_name,
                total_volume=order.order_volume,
                available_volume=0,  # T+1，当日买入不可卖出
                avg_cost=order.order_price,
                total_cost=order.order_volume * order.order_price,
                market_value=order.order_volume * stock_info.current_price,
                profit_loss=0,
                profit_loss_percent=0,
                last_price=stock_info.current_price,
                update_time=int(time.time())
            )
        
        # 6. 更新持仓市值
        position.update_market_data(stock_info.current_price)
        
        # 7. 保存数据
        self.storage.save_user(user.user_id, user.to_dict())
        self.storage.save_position(user.user_id, order.stock_code, position.to_dict())
        self.storage.save_order(order.order_id, order.to_dict())
        
        return True, f"买入成功！{order.stock_name} {order.order_volume}股，价格{order.order_price:.2f}元", order
    
    async def _execute_sell_order_immediately(self, user: User, order: Order, position: Position,
                                            stock_info: StockInfo) -> Tuple[bool, str, Order]:
        """立即执行卖出订单"""
        # 1. 计算实际收入
        total_income = self.market_rules.calculate_sell_amount(order.order_volume, order.order_price)
        
        # 2. 减少持仓
        success = position.reduce_position(order.order_volume)
        if not success:
            return False, "减少持仓失败", order
        
        # 3. 增加资金
        user.add_balance(total_income)
        
        # 4. 更新订单状态
        order.fill_order(order.order_volume, order.order_price)
        
        # 5. 更新持仓市值
        if not position.is_empty():
            position.update_market_data(stock_info.current_price)
        
        # 6. 保存数据
        self.storage.save_user(user.user_id, user.to_dict())
        
        if position.is_empty():
            self.storage.delete_position(user.user_id, order.stock_code)
        else:
            self.storage.save_position(user.user_id, order.stock_code, position.to_dict())
        
        self.storage.save_order(order.order_id, order.to_dict())
        
        return True, f"卖出成功！{order.stock_name} {order.order_volume}股，价格{order.order_price:.2f}元，到账{total_income:.2f}元", order
    
    async def _place_pending_buy_order(self, user: User, order: Order) -> Tuple[bool, str, Order]:
        """挂买单"""
        # 1. 冻结资金
        total_cost = self.market_rules.calculate_buy_amount(order.order_volume, order.order_price)
        
        if not user.can_buy(total_cost):
            return False, f"资金不足，需要{total_cost:.2f}元", order
        
        user.deduct_balance(total_cost)
        
        # 2. 保存挂单
        self.storage.save_order(order.order_id, order.to_dict())
        self.storage.save_user(user.user_id, user.to_dict())
        
        return True, f"买入挂单成功！{order.stock_name} {order.order_volume}股，价格{order.order_price:.2f}元", order
    
    async def _place_pending_sell_order(self, user: User, order: Order, position: Position) -> Tuple[bool, str, Order]:
        """挂卖单"""
        # 1. 冻结股票（这里简化处理，实际应该单独记录冻结数量）
        # 为简化，我们不实际冻结，在成交时再次检查
        
        # 2. 保存挂单
        self.storage.save_order(order.order_id, order.to_dict())
        
        return True, f"卖出挂单成功！{order.stock_name} {order.order_volume}股，价格{order.order_price:.2f}元", order
    
    async def cancel_order(self, user_id: str, order_id: str) -> Tuple[bool, str]:
        """撤销订单"""
        # 1. 获取订单
        order_data = self.storage.get_order(order_id)
        if not order_data:
            return False, "订单不存在"
        
        order = Order.from_dict(order_data)
        
        # 2. 检查权限
        if order.user_id != user_id:
            return False, "无权撤销此订单"
        
        # 3. 检查状态
        if not order.is_pending():
            return False, f"订单状态为{order.status.value}，无法撤销"
        
        # 4. 撤销订单
        order.cancel_order()
        
        # 5. 退还资金（如果是买单）
        if order.is_buy_order():
            user_data = self.storage.get_user(user_id)
            if user_data:
                user = User.from_dict(user_data)
                total_cost = self.market_rules.calculate_buy_amount(order.order_volume, order.order_price)
                user.add_balance(total_cost)
                self.storage.save_user(user_id, user.to_dict())
        
        # 6. 保存订单
        self.storage.save_order(order.order_id, order.to_dict())
        
        return True, f"订单撤销成功！{order.stock_name} {order.order_volume}股"
    
    async def update_user_assets(self, user_id: str):
        """更新用户总资产"""
        user_data = self.storage.get_user(user_id)
        if not user_data:
            return
        
        user = User.from_dict(user_data)
        positions = self.storage.get_positions(user_id)
        
        # 计算持仓市值
        total_market_value = 0
        for pos_data in positions:
            total_market_value += pos_data.get('market_value', 0)
        
        # 更新总资产
        user.update_total_assets(user.balance + total_market_value)
        self.storage.save_user(user_id, user.to_dict())
    
    def get_user_trading_summary(self, user_id: str) -> Dict[str, Any]:
        """获取用户交易汇总"""
        user_data = self.storage.get_user(user_id)
        if not user_data:
            return {}
        
        user = User.from_dict(user_data)
        positions = self.storage.get_positions(user_id)
        orders = self.storage.get_orders(user_id)
        
        # 计算统计数据
        total_market_value = sum(pos.get('market_value', 0) for pos in positions)
        total_profit_loss = sum(pos.get('profit_loss', 0) for pos in positions)
        total_positions = len([pos for pos in positions if pos.get('total_volume', 0) > 0])
        pending_orders = len([order for order in orders if order.get('status') == 'pending'])
        
        return {
            'user': user.to_dict(),
            'total_market_value': total_market_value,
            'total_profit_loss': total_profit_loss,
            'total_positions': total_positions,
            'pending_orders': pending_orders,
            'positions': positions,
            'recent_orders': sorted(orders, key=lambda x: x.get('create_time', 0), reverse=True)[:5]
        }
