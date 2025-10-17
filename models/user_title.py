"""用户称号数据模型"""
from dataclasses import dataclass, asdict
from typing import Dict, Any, List
import time


@dataclass
class UserTitle:
    """用户称号模型"""
    user_id: str
    current_title: str = "新手"
    title_history: List[str] = None
    total_profit: float = 0.0
    total_trades: int = 0
    win_rate: float = 0.0
    last_updated: int = 0
    
    def __post_init__(self):
        """初始化后处理"""
        if self.title_history is None:
            self.title_history = []
        if self.last_updated == 0:
            self.last_updated = int(time.time())
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UserTitle':
        """从字典创建用户称号对象"""
        return cls(**data)
    
    def update_title(self, new_title: str):
        """更新称号"""
        if new_title != self.current_title:
            self.title_history.append(self.current_title)
            self.current_title = new_title
            self.last_updated = int(time.time())
    
    def get_title_description(self) -> str:
        """获取称号描述"""
        descriptions = {
            '新手': '刚入市的小白',
            '韭菜': '被割的韭菜',
            '小散': '小散户',
            '股民': '普通股民',
            '高手': '交易高手',
            '股神': '股神附体',
            '巴菲特': '价值投资大师'
        }
        return descriptions.get(self.current_title, '未知称号')


# 基于100万初始资金的合理称号规则
TITLE_RULES = {
    '新手': {'min_profit_rate': -1.0, 'max_profit_rate': -0.1, 'min_trades': 0, 'max_trades': 3},
    '韭菜': {'min_profit_rate': -0.1, 'max_profit_rate': 0.0, 'min_trades': 3, 'max_trades': 10},
    '小散': {'min_profit_rate': 0.0, 'max_profit_rate': 0.05, 'min_trades': 5, 'max_trades': 20},
    '股民': {'min_profit_rate': 0.05, 'max_profit_rate': 0.15, 'min_trades': 10, 'max_trades': 50},
    '高手': {'min_profit_rate': 0.15, 'max_profit_rate': 0.30, 'min_trades': 20, 'max_trades': 100},
    '股神': {'min_profit_rate': 0.30, 'max_profit_rate': 0.50, 'min_trades': 30, 'max_trades': 200},
    '巴菲特': {'min_profit_rate': 0.50, 'max_profit_rate': 999.0, 'min_trades': 50, 'max_trades': 999999}
}
