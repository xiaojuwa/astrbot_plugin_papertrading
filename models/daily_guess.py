"""每日一猜数据模型"""
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional, List
import time


@dataclass
class DailyGuess:
    """每日猜股模型"""
    date: str                    # 日期 YYYY-MM-DD
    stock_code: str             # 股票代码
    stock_name: str             # 股票名称
    open_price: float           # 开盘价
    close_price: Optional[float] = None  # 收盘价
    guesses: Dict[str, float] = None  # 用户猜测 {user_id: guess_price}
    winner: Optional[str] = None  # 获胜者
    prize_amount: float = 10000.0  # 奖励金额
    is_finished: bool = False   # 是否已结束
    create_time: int = 0        # 创建时间
    finish_time: Optional[int] = None  # 结束时间
    
    def __post_init__(self):
        """初始化后处理"""
        if self.guesses is None:
            self.guesses = {}
        if self.create_time == 0:
            self.create_time = int(time.time())
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DailyGuess':
        """从字典创建每日猜股对象"""
        return cls(**data)
    
    def add_guess(self, user_id: str, guess_price: float):
        """添加猜测"""
        self.guesses[user_id] = guess_price
    
    def finish_guess(self, close_price: float):
        """结束猜股并确定获胜者"""
        self.close_price = close_price
        self.is_finished = True
        self.finish_time = int(time.time())
        
        if self.guesses:
            # 找到最接近收盘价的猜测
            self.winner = min(self.guesses.keys(), 
                            key=lambda x: abs(self.guesses[x] - close_price))
    
    def get_winner_accuracy(self) -> Optional[float]:
        """获取获胜者的准确度"""
        if not self.winner or not self.close_price:
            return None
        return abs(self.guesses[self.winner] - self.close_price)


@dataclass
class GuessRecord:
    """猜测记录模型"""
    user_id: str
    guess_price: float
    guess_time: int
    accuracy: Optional[float] = None  # 准确度（与收盘价的差距）
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'GuessRecord':
        """从字典创建猜测记录对象"""
        return cls(**data)
