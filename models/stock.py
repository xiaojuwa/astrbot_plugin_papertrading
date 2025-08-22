"""股票数据模型"""
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional
import time


@dataclass
class StockInfo:
    """股票信息模型"""
    code: str                       # 股票代码
    name: str                       # 股票名称
    current_price: float            # 当前价格
    open_price: float               # 开盘价
    close_price: float              # 收盘价
    high_price: float               # 最高价
    low_price: float                # 最低价
    volume: int                     # 成交量
    turnover: float                 # 成交额
    bid1_price: float               # 买一价
    ask1_price: float               # 卖一价
    change_percent: float           # 涨跌幅
    change_amount: float            # 涨跌额
    limit_up: float                 # 涨停价
    limit_down: float               # 跌停价
    is_suspended: bool              # 是否停牌
    update_time: int                # 更新时间戳
    
    def __post_init__(self):
        """初始化后处理"""
        if self.update_time == 0:
            self.update_time = int(time.time())
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StockInfo':
        """从字典创建股票信息对象"""
        return cls(**data)
    
    def is_limit_up(self) -> bool:
        """是否涨停"""
        return abs(self.current_price - self.limit_up) < 0.01
    
    def is_limit_down(self) -> bool:
        """是否跌停"""
        return abs(self.current_price - self.limit_down) < 0.01
    
    def can_buy_at_price(self, price: float) -> bool:
        """检查是否可以以指定价格买入"""
        if self.is_suspended:
            return False
        return price <= self.limit_up
    
    def can_sell_at_price(self, price: float) -> bool:
        """检查是否可以以指定价格卖出"""
        if self.is_suspended:
            return False
        return price >= self.limit_down
    
    def get_market_buy_price(self) -> float:
        """获取市价买入价格（卖一价）"""
        return self.ask1_price if self.ask1_price > 0 else self.current_price
    
    def get_market_sell_price(self) -> float:
        """获取市价卖出价格（买一价）"""
        return self.bid1_price if self.bid1_price > 0 else self.current_price
    
    def is_data_fresh(self, max_age_seconds: int = 30) -> bool:
        """检查数据是否新鲜"""
        return (int(time.time()) - self.update_time) <= max_age_seconds
