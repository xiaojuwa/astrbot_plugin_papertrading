"""A股市场规则引擎"""
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
from ..models.stock import StockInfo
from ..models.order import Order, OrderType
from ..models.position import Position
from ..utils.data_storage import DataStorage


class MarketRulesEngine:
    """A股市场规则引擎"""
    
    def __init__(self, storage: DataStorage):
        self.storage = storage
    
    def validate_trading_time(self) -> Tuple[bool, str]:
        """验证交易时间"""
        now = datetime.now()
        
        # 检查是否是工作日
        if now.weekday() >= 5:  # 周六日
            return False, "非交易日，无法进行交易"
        
        # 检查是否在交易时间
        current_time = now.time()
        
        # 交易时间：9:30-11:30, 13:00-15:00
        morning_start = datetime.strptime("09:30", "%H:%M").time()
        morning_end = datetime.strptime("11:30", "%H:%M").time()
        afternoon_start = datetime.strptime("13:00", "%H:%M").time()
        afternoon_end = datetime.strptime("15:00", "%H:%M").time()
        
        is_morning = morning_start <= current_time <= morning_end
        is_afternoon = afternoon_start <= current_time <= afternoon_end
        
        if not (is_morning or is_afternoon):
            return False, "非交易时间，交易时间为9:30-11:30, 13:00-15:00"
        
        return True, ""
    
    def validate_buy_order(self, stock_info: StockInfo, order: Order, user_balance: float) -> Tuple[bool, str]:
        """验证买入订单"""
        # 1. 检查股票是否停牌
        if stock_info.is_suspended:
            return False, f"{stock_info.name}当前停牌，无法交易"
        
        # 2. 检查涨跌停限制：涨停时不能买入
        if stock_info.is_limit_up():
            return False, f"{stock_info.name}已涨停，无法买入"
        
        # 3. 检查价格是否超出涨跌停
        if not stock_info.can_buy_at_price(order.order_price):
            return False, f"买入价格{order.order_price:.2f}超出涨停价{stock_info.limit_up:.2f}"
        
        # 3. 检查资金是否充足
        total_amount = self.calculate_buy_amount(order.order_volume, order.order_price)
        if user_balance < total_amount:
            return False, f"资金不足，需要{total_amount:.2f}元，可用余额{user_balance:.2f}元"
        
        # 4. 检查最小交易单位
        if order.order_volume % 100 != 0:
            return False, "交易数量必须是100股的整数倍"
        
        # 5. 检查最小交易金额
        if total_amount < 100:
            return False, "单笔交易金额不能少于100元"
        
        return True, ""
    
    def validate_sell_order(self, stock_info: StockInfo, order: Order, position: Optional[Position]) -> Tuple[bool, str]:
        """验证卖出订单"""
        # 1. 检查是否有持仓
        if not position or position.is_empty():
            return False, f"您没有持有{stock_info.name}，无法卖出"
        
        # 2. 检查股票是否停牌
        if stock_info.is_suspended:
            return False, f"{stock_info.name}当前停牌，无法交易"
        
        # 3. 检查涨跌停限制：跌停时不能卖出
        if stock_info.is_limit_down():
            return False, f"{stock_info.name}已跌停，无法卖出"
        
        # 4. 检查价格是否超出涨跌停
        if not stock_info.can_sell_at_price(order.order_price):
            return False, f"卖出价格{order.order_price:.2f}超出跌停价{stock_info.limit_down:.2f}"
        
        # 4. 检查可卖数量（T+1限制）
        if not position.can_sell(order.order_volume):
            return False, f"可卖数量不足，持有{position.total_volume}股，可卖{position.available_volume}股（T+1限制）"
        
        # 5. 检查最小交易单位
        if order.order_volume % 100 != 0:
            return False, "交易数量必须是100股的整数倍"
        
        return True, ""
    
    def calculate_buy_amount(self, volume: int, price: float) -> float:
        """计算买入所需金额（含手续费）"""
        # 股票金额
        stock_amount = volume * price
        
        # 手续费计算
        commission = self.calculate_commission(stock_amount)
        
        # 印花税（买入免征）
        stamp_tax = 0
        
        # 过户费（上海股票收取，按成交金额的0.002%，最低1元）
        transfer_fee = max(1, stock_amount * 0.00002)
        
        return stock_amount + commission + stamp_tax + transfer_fee
    
    def calculate_sell_amount(self, volume: int, price: float) -> float:
        """计算卖出所得金额（扣除手续费）"""
        # 股票金额
        stock_amount = volume * price
        
        # 手续费计算
        commission = self.calculate_commission(stock_amount)
        
        # 印花税（卖出征收0.1%）
        stamp_tax = stock_amount * 0.001
        
        # 过户费
        transfer_fee = max(1, stock_amount * 0.00002)
        
        return stock_amount - commission - stamp_tax - transfer_fee
    
    def calculate_commission(self, amount: float) -> float:
        """计算手续费"""
        config = self.storage.get_config()
        commission_rate = config.get('commission_rate', 0.0003)  # 默认0.03%
        min_commission = config.get('min_commission', 5)         # 最低5元
        
        commission = amount * commission_rate
        return max(commission, min_commission)
    
    def check_price_limit(self, stock_info: StockInfo, price: float, order_type: OrderType) -> Tuple[bool, str]:
        """检查价格是否触及涨跌停"""
        if order_type == OrderType.BUY:
            if price > stock_info.limit_up:
                return False, f"买入价格{price:.2f}不能超过涨停价{stock_info.limit_up:.2f}"
        else:
            if price < stock_info.limit_down:
                return False, f"卖出价格{price:.2f}不能低于跌停价{stock_info.limit_down:.2f}"
        
        return True, ""
    
    def check_trading_suspension(self, stock_info: StockInfo) -> Tuple[bool, str]:
        """检查交易是否暂停"""
        if stock_info.is_suspended:
            return False, f"{stock_info.name}({stock_info.code})当前停牌，暂停交易"
        
        return True, ""
    
    def apply_t_plus_one_rule(self, position: Position, buy_volume: int):
        """应用T+1规则"""
        # 买入的股票当日不能卖出
        # 这里不增加available_volume，需要在第二天开盘前调用make_available_for_sale
        pass
    
    def make_positions_available_for_next_day(self, user_id: str):
        """使持仓可在下一交易日卖出（T+1规则）"""
        positions = self.storage.get_positions(user_id)
        
        for pos_data in positions:
            if pos_data['total_volume'] > pos_data['available_volume']:
                # 有新买入的股票，使其可卖
                pos_data['available_volume'] = pos_data['total_volume']
                
                # 保存更新
                position = Position.from_dict(pos_data)
                self.storage.save_position(user_id, position.stock_code, position.to_dict())
    
    def is_call_auction_period(self) -> bool:
        """检查是否在集合竞价期间"""
        now = datetime.now()
        current_time = now.time()
        
        # 开盘集合竞价：9:15-9:25
        morning_start = datetime.strptime("09:15", "%H:%M").time()
        morning_end = datetime.strptime("09:25", "%H:%M").time()
        
        # 收盘集合竞价：14:57-15:00
        afternoon_start = datetime.strptime("14:57", "%H:%M").time()
        afternoon_end = datetime.strptime("15:00", "%H:%M").time()
        
        is_morning_auction = morning_start <= current_time <= morning_end
        is_afternoon_auction = afternoon_start <= current_time <= afternoon_end
        
        return is_morning_auction or is_afternoon_auction
    
    def validate_order_in_auction(self, order: Order) -> Tuple[bool, str]:
        """验证集合竞价期间的订单"""
        if self.is_call_auction_period():
            # 集合竞价期间只能使用限价单
            if order.is_market_order():
                return False, "集合竞价期间只能使用限价委托"
        
        return True, ""
    
    def check_st_stock_rules(self, stock_code: str, stock_name: str) -> Tuple[bool, str]:
        """检查ST股票特殊规则"""
        # ST股票涨跌幅限制为5%
        if 'ST' in stock_name or '*ST' in stock_name:
            return True, "ST股票涨跌幅限制为5%"
        
        return True, ""
    
    def get_price_precision(self, price: float) -> float:
        """获取价格精度"""
        # A股价格精度为0.01元
        return round(price, 2)
    
    def validate_order_price(self, price: float) -> Tuple[bool, str]:
        """验证订单价格格式"""
        # 检查价格精度
        if round(price, 2) != price:
            return False, "价格精度不能超过2位小数"
        
        # 检查价格范围
        if price <= 0:
            return False, "价格必须大于0"
        
        if price > 10000:
            return False, "价格不能超过10000元"
        
        return True, ""
