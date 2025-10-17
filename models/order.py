"""订单数据模型"""
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional
from enum import Enum
import time
import uuid


class OrderType(Enum):
    """订单类型"""
    BUY = "buy"          # 买入
    SELL = "sell"        # 卖出


class OrderStatus(Enum):
    """订单状态"""
    PENDING = "pending"          # 待成交
    FILLED = "filled"            # 已成交
    CANCELLED = "cancelled"      # 已撤销
    PARTIAL_FILLED = "partial"   # 部分成交


class PriceType(Enum):
    """价格类型"""
    MARKET = "market"    # 市价
    LIMIT = "limit"      # 限价


@dataclass
class Order:
    """订单模型"""
    order_id: str                   # 订单ID
    user_id: str                    # 用户ID
    stock_code: str                 # 股票代码
    stock_name: str                 # 股票名称
    order_type: OrderType           # 订单类型（买入/卖出）
    price_type: PriceType           # 价格类型（市价/限价）
    order_price: float              # 委托价格
    order_volume: int               # 委托数量
    filled_volume: int              # 已成交数量
    filled_amount: float            # 已成交金额
    status: OrderStatus             # 订单状态
    create_time: int                # 创建时间
    update_time: int                # 更新时间
    filled_time: Optional[int] = None  # 成交时间
    profit_amount: Optional[float] = None  # 盈亏金额（仅卖出订单有）
    profit_rate: Optional[float] = None   # 盈亏比例（仅卖出订单有）
    
    def __post_init__(self):
        """初始化后处理"""
        if not self.order_id:
            # 使用简单的五位数字序号，需要在创建时传入storage实例
            self.order_id = str(uuid.uuid4())  # 临时方案，在实际使用时会被覆盖
        if self.create_time == 0:
            self.create_time = int(time.time())
        if self.update_time == 0:
            self.update_time = int(time.time())
    

    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        # 转换枚举为字符串
        data['order_type'] = self.order_type.value
        data['price_type'] = self.price_type.value
        data['status'] = self.status.value
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Order':
        """从字典创建订单对象"""
        # 转换字符串为枚举
        if isinstance(data.get('order_type'), str):
            data['order_type'] = OrderType(data['order_type'])
        if isinstance(data.get('price_type'), str):
            data['price_type'] = PriceType(data['price_type'])
        if isinstance(data.get('status'), str):
            data['status'] = OrderStatus(data['status'])
        return cls(**data)
    
    def is_buy_order(self) -> bool:
        """是否为买单"""
        return self.order_type == OrderType.BUY
    
    def is_sell_order(self) -> bool:
        """是否为卖单"""
        return self.order_type == OrderType.SELL
    
    def is_market_order(self) -> bool:
        """是否为市价单"""
        return self.price_type == PriceType.MARKET
    
    def is_limit_order(self) -> bool:
        """是否为限价单"""
        return self.price_type == PriceType.LIMIT
    
    def is_pending(self) -> bool:
        """是否待成交"""
        return self.status == OrderStatus.PENDING
    
    def is_filled(self) -> bool:
        """是否已成交"""
        return self.status == OrderStatus.FILLED
    
    def is_cancelled(self) -> bool:
        """是否已撤销"""
        return self.status == OrderStatus.CANCELLED
    
    def remaining_volume(self) -> int:
        """剩余待成交数量"""
        return self.order_volume - self.filled_volume
    
    def fill_order(self, volume: int, price: float):
        """部分或全部成交"""
        self.filled_volume += volume
        self.filled_amount += volume * price
        self.update_time = int(time.time())
        
        if self.filled_volume >= self.order_volume:
            self.status = OrderStatus.FILLED
            self.filled_time = int(time.time())
        elif self.filled_volume > 0:
            self.status = OrderStatus.PARTIAL_FILLED
    
    def cancel_order(self):
        """撤销订单"""
        self.status = OrderStatus.CANCELLED
        self.update_time = int(time.time())
    
    def can_be_filled_at_price(self, current_price: float) -> bool:
        """检查在当前价格下是否可以成交"""
        if not self.is_pending():
            return False
        
        if self.is_market_order():
            return True
        
        if self.is_buy_order():
            # 买单：当前价格低于等于委托价格时可以成交
            return current_price <= self.order_price
        else:
            # 卖单：当前价格高于等于委托价格时可以成交
            return current_price >= self.order_price
    
    def get_total_amount(self) -> float:
        """获取订单总金额"""
        return self.order_volume * self.order_price
