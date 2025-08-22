"""股票市场交易时间判断工具"""
import asyncio
from datetime import datetime, time as dt_time, date
from typing import List, Optional, Tuple, Dict, Any
from astrbot.api import logger


class MarketTimeManager:
    """市场交易时间管理器"""
    
    def __init__(self):
        # A股交易时间段
        self.trading_sessions = [
            (dt_time(9, 30), dt_time(11, 30)),   # 上午交易时间
            (dt_time(13, 0), dt_time(15, 0))     # 下午交易时间
        ]
        
        # 集合竞价时间段
        self.call_auction_sessions = [
            (dt_time(9, 15), dt_time(9, 25)),    # 开盘集合竞价
            (dt_time(14, 57), dt_time(15, 0))    # 收盘集合竞价
        ]
        
        # 法定节假日缓存（简化实现，实际应用中可以对接节假日API）
        self.holidays = self._get_default_holidays()
    
    def _get_default_holidays(self) -> List[date]:
        """
        获取默认节假日列表
        简化实现，包含主要法定节假日
        实际项目中建议对接专业的节假日API
        """
        current_year = datetime.now().year
        holidays = []
        
        # 元旦
        holidays.append(date(current_year, 1, 1))
        
        # 春节假期（简化为前后7天）
        for day in range(10, 17):  # 2月10-16日作为示例
            try:
                holidays.append(date(current_year, 2, day))
            except ValueError:
                pass
        
        # 清明节
        holidays.append(date(current_year, 4, 5))
        
        # 劳动节
        for day in range(1, 4):  # 5月1-3日
            holidays.append(date(current_year, 5, day))
        
        # 国庆节
        for day in range(1, 8):  # 10月1-7日
            holidays.append(date(current_year, 10, day))
        
        return holidays
    
    def is_weekday(self, target_date: Optional[date] = None) -> bool:
        """
        判断是否为工作日（周一到周五）
        
        Args:
            target_date: 目标日期，默认为今天
            
        Returns:
            是否为工作日
        """
        if target_date is None:
            target_date = datetime.now().date()
        
        return target_date.weekday() < 5  # 0-4 是周一到周五
    
    def is_holiday(self, target_date: Optional[date] = None) -> bool:
        """
        判断是否为法定节假日
        
        Args:
            target_date: 目标日期，默认为今天
            
        Returns:
            是否为法定节假日
        """
        if target_date is None:
            target_date = datetime.now().date()
        
        return target_date in self.holidays
    
    def is_trading_day(self, target_date: Optional[date] = None) -> bool:
        """
        判断是否为交易日
        
        Args:
            target_date: 目标日期，默认为今天
            
        Returns:
            是否为交易日（工作日且非节假日）
        """
        if target_date is None:
            target_date = datetime.now().date()
        
        return self.is_weekday(target_date) and not self.is_holiday(target_date)
    
    def is_trading_time(self, target_time: Optional[datetime] = None) -> bool:
        """
        判断是否在交易时间内
        
        Args:
            target_time: 目标时间，默认为当前时间
            
        Returns:
            是否在交易时间内
        """
        if target_time is None:
            target_time = datetime.now()
        
        # 首先检查是否为交易日
        if not self.is_trading_day(target_time.date()):
            return False
        
        current_time = target_time.time()
        
        # 检查是否在任一交易时间段内
        for start_time, end_time in self.trading_sessions:
            if start_time <= current_time <= end_time:
                return True
        
        return False
    
    def is_call_auction_time(self, target_time: Optional[datetime] = None) -> bool:
        """
        判断是否在集合竞价时间内
        
        Args:
            target_time: 目标时间，默认为当前时间
            
        Returns:
            是否在集合竞价时间内
        """
        if target_time is None:
            target_time = datetime.now()
        
        # 首先检查是否为交易日
        if not self.is_trading_day(target_time.date()):
            return False
        
        current_time = target_time.time()
        
        # 检查是否在任一集合竞价时间段内
        for start_time, end_time in self.call_auction_sessions:
            if start_time <= current_time <= end_time:
                return True
        
        return False
    
    def is_market_open(self, target_time: Optional[datetime] = None) -> bool:
        """
        判断市场是否开放（交易时间或集合竞价时间）
        
        Args:
            target_time: 目标时间，默认为当前时间
            
        Returns:
            市场是否开放
        """
        return self.is_trading_time(target_time) or self.is_call_auction_time(target_time)
    
    def get_next_trading_time(self, from_time: Optional[datetime] = None) -> Optional[datetime]:
        """
        获取下一个交易时间点
        
        Args:
            from_time: 起始时间，默认为当前时间
            
        Returns:
            下一个交易时间点或None
        """
        if from_time is None:
            from_time = datetime.now()
        
        current_date = from_time.date()
        current_time = from_time.time()
        
        # 如果是交易日
        if self.is_trading_day(current_date):
            # 检查今日剩余的交易时间段
            for start_time, _ in self.trading_sessions:
                if current_time < start_time:
                    return datetime.combine(current_date, start_time)
        
        # 寻找下一个交易日的开盘时间
        for i in range(1, 15):  # 最多向前查找15天
            next_date = date.fromordinal(current_date.toordinal() + i)
            if self.is_trading_day(next_date):
                return datetime.combine(next_date, self.trading_sessions[0][0])
        
        return None
    
    def get_trading_sessions_info(self, target_date: Optional[date] = None) -> Dict[str, Any]:
        """
        获取指定日期的交易时间段信息
        
        Args:
            target_date: 目标日期，默认为今天
            
        Returns:
            交易时间段信息字典
        """
        if target_date is None:
            target_date = datetime.now().date()
        
        return {
            'date': target_date,
            'is_trading_day': self.is_trading_day(target_date),
            'is_weekday': self.is_weekday(target_date),
            'is_holiday': self.is_holiday(target_date),
            'trading_sessions': [
                {
                    'start': session[0].strftime('%H:%M'),
                    'end': session[1].strftime('%H:%M')
                }
                for session in self.trading_sessions
            ],
            'call_auction_sessions': [
                {
                    'start': session[0].strftime('%H:%M'),
                    'end': session[1].strftime('%H:%M')
                }
                for session in self.call_auction_sessions
            ]
        }
    
    def can_place_order(self, target_time: Optional[datetime] = None) -> Tuple[bool, str]:
        """
        判断是否可以下单，返回详细原因
        
        Args:
            target_time: 目标时间，默认为当前时间
            
        Returns:
            (是否可以下单, 原因说明)
        """
        if target_time is None:
            target_time = datetime.now()
        
        # 检查是否为交易日
        if not self.is_trading_day(target_time.date()):
            if not self.is_weekday(target_time.date()):
                return False, "今日为周末，不可交易"
            else:
                return False, "今日为法定节假日，不可交易"
        
        # 检查具体时间
        if self.is_trading_time(target_time):
            return True, "正常交易时间"
        elif self.is_call_auction_time(target_time):
            return True, "集合竞价时间"
        else:
            current_time = target_time.time()
            
            # 判断是交易前、交易中休息还是交易后
            if current_time < dt_time(9, 15):
                return False, "尚未到开盘时间"
            elif dt_time(9, 25) < current_time < dt_time(9, 30):
                return False, "开盘前准备时间"
            elif dt_time(11, 30) < current_time < dt_time(13, 0):
                return False, "午间休市时间"
            elif current_time > dt_time(15, 0):
                return False, "已过收盘时间"
            else:
                return False, "非交易时间"


# 全局市场时间管理器实例
market_time_manager = MarketTimeManager()


def is_trading_time(target_time: Optional[datetime] = None) -> bool:
    """
    便捷函数：判断是否在交易时间内
    
    Args:
        target_time: 目标时间，默认为当前时间
        
    Returns:
        是否在交易时间内
    """
    return market_time_manager.is_trading_time(target_time)


def is_call_auction_time(target_time: Optional[datetime] = None) -> bool:
    """
    便捷函数：判断是否在集合竞价时间内
    
    Args:
        target_time: 目标时间，默认为当前时间
        
    Returns:
        是否在集合竞价时间内
    """
    return market_time_manager.is_call_auction_time(target_time)


def is_market_open(target_time: Optional[datetime] = None) -> bool:
    """
    便捷函数：判断市场是否开放
    
    Args:
        target_time: 目标时间，默认为当前时间
        
    Returns:
        市场是否开放
    """
    return market_time_manager.is_market_open(target_time)


def can_place_order(target_time: Optional[datetime] = None) -> Tuple[bool, str]:
    """
    便捷函数：判断是否可以下单
    
    Args:
        target_time: 目标时间，默认为当前时间
        
    Returns:
        (是否可以下单, 原因说明)
    """
    return market_time_manager.can_place_order(target_time)


def get_next_trading_time(from_time: Optional[datetime] = None) -> Optional[datetime]:
    """
    便捷函数：获取下一个交易时间点
    
    Args:
        from_time: 起始时间，默认为当前时间
        
    Returns:
        下一个交易时间点或None
    """
    return market_time_manager.get_next_trading_time(from_time)
