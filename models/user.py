"""用户数据模型"""
from dataclasses import dataclass, asdict
from typing import Dict, Any
import time


@dataclass
class User:
    """用户模型"""
    user_id: str                    # 用户ID
    username: str                   # 用户名
    balance: float                  # 可用余额
    total_assets: float             # 总资产
    register_time: int              # 注册时间戳
    last_login: int                 # 最后登录时间
    
    def __post_init__(self):
        """初始化后处理"""
        if self.register_time == 0:
            self.register_time = int(time.time())
        if self.last_login == 0:
            self.last_login = int(time.time())
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'User':
        """从字典创建用户对象"""
        return cls(**data)
    
    def update_login_time(self):
        """更新登录时间"""
        self.last_login = int(time.time())
    
    def can_buy(self, amount: float) -> bool:
        """检查是否有足够余额购买"""
        return self.balance >= amount
    
    def deduct_balance(self, amount: float) -> bool:
        """扣除余额"""
        if self.can_buy(amount):
            self.balance -= amount
            return True
        return False
    
    def add_balance(self, amount: float):
        """增加余额"""
        self.balance += amount
    
    def update_total_assets(self, assets: float):
        """更新总资产"""
        self.total_assets = assets
