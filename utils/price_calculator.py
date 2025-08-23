"""股票涨跌停价格计算器"""
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
from astrbot.api import logger
from .market_time import market_time_manager


class StockType:
    """股票类型枚举"""
    NORMAL = "normal"      # 普通股票 ±10%
    ST = "st"              # ST股票 ±5%
    CHINEXT = "chinext"    # 创业板 ±20%（注册制后）
    STAR = "star"          # 科创板 ±20%
    BSE = "bse"            # 北交所 ±30%


class PriceCalculator:
    """涨跌停价格计算器"""
    
    # 涨跌停比例配置
    LIMIT_RATIOS = {
        StockType.NORMAL: 0.10,    # 普通股票 ±10%
        StockType.ST: 0.05,        # ST股票 ±5%
        StockType.CHINEXT: 0.20,   # 创业板 ±20%
        StockType.STAR: 0.20,      # 科创板 ±20%
        StockType.BSE: 0.30        # 北交所 ±30%
    }
    
    def __init__(self, storage_instance=None):
        """
        初始化价格计算器
        
        Args:
            storage_instance: 数据存储实例，用于获取历史数据
        """
        self.storage = storage_instance
    
    def get_stock_type(self, stock_code: str, stock_name: str) -> StockType:
        """
        识别股票类型
        
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            
        Returns:
            股票类型
        """
        # 检查ST股票（通过名称）
        if 'ST' in stock_name or '*ST' in stock_name:
            return StockType.ST
        
        # 检查北交所（代码前缀）
        if stock_code.startswith(('43', '83', '87')):
            return StockType.BSE
        
        # 检查科创板（688开头）
        if stock_code.startswith('688'):
            return StockType.STAR
        
        # 检查创业板（300开头）
        if stock_code.startswith('300'):
            return StockType.CHINEXT
        
        # 其他为普通股票（60、00开头等）
        return StockType.NORMAL
    
    async def calculate_price_limits(self, stock_code: str, stock_name: str, 
                                   current_time: Optional[datetime] = None) -> Dict[str, float]:
        """
        基于收盘价本地计算涨跌停价格
        
        Args:
            stock_code: 股票代码
            stock_name: 股票名称  
            current_time: 当前时间，默认为系统当前时间（用于获取正确的基准价格）
            
        Returns:
            包含limit_up和limit_down的字典
        """
        if current_time is None:
            current_time = datetime.now()
        
        # 获取基准价格（通常是最近的收盘价）
        base_price = await self._get_base_close_price(stock_code)
        if base_price is None or base_price <= 0:
            logger.error(f"无法获取股票 {stock_code} 的基准收盘价")
            return {'limit_up': 0, 'limit_down': 0}
        
        # 识别股票类型
        stock_type = self.get_stock_type(stock_code, stock_name)
        
        # 获取涨跌停比例
        limit_ratio = self.LIMIT_RATIOS.get(stock_type, 0.10)
        
        # 计算涨跌停价格
        limit_up = base_price * (1 + limit_ratio)
        limit_down = base_price * (1 - limit_ratio)
        
        # A股价格精度为0.01元
        limit_up = round(limit_up, 2)
        limit_down = round(limit_down, 2)
        
        # 确保跌停价格不低于0.01元
        limit_down = max(limit_down, 0.01)
        
        logger.debug(f"股票 {stock_code} ({stock_type}) 基准价: {base_price:.2f}, "
                    f"涨停: {limit_up:.2f}, 跌停: {limit_down:.2f}")
        
        return {
            'limit_up': limit_up,
            'limit_down': limit_down,
            'base_price': base_price,
            'stock_type': stock_type,
            'limit_ratio': limit_ratio
        }
    
    async def _get_base_close_price(self, stock_code: str) -> Optional[float]:
        """
        获取基准收盘价（用于本地涨跌停计算）
        
        Args:
            stock_code: 股票代码
            
        Returns:
            基准收盘价
        """
        try:
            from ..services.stock_data import StockDataService
            stock_service = StockDataService(self.storage) if self.storage else None
            
            if stock_service:
                # 获取股票信息，跳过涨跌停计算（防止递归调用）
                stock_info = await stock_service.get_stock_info(stock_code, skip_limit_calculation=True)
                if stock_info and hasattr(stock_info, 'close_price') and stock_info.close_price > 0:
                    logger.debug(f"股票 {stock_code} 基准收盘价: {stock_info.close_price}")
                    return stock_info.close_price
                    
            logger.warning(f"无法获取股票 {stock_code} 的收盘价")
            return None
            
        except Exception as e:
            logger.error(f"获取收盘价失败: {e}")
            return None
    
    def parse_price_text(self, price_text: str, limit_up: float, limit_down: float) -> Optional[float]:
        """
        解析价格文本，支持涨停/跌停关键词
        
        Args:
            price_text: 价格文本
            limit_up: 涨停价
            limit_down: 跌停价
            
        Returns:
            解析后的价格，如果无法解析返回None
        """
        if not price_text:
            return None
        
        price_text = price_text.strip()
        
        # 检查涨停/跌停关键词
        if price_text in ['涨停', 'zt', 'ZT']:
            return limit_up
        elif price_text in ['跌停', 'dt', 'DT']:
            return limit_down
        
        # 尝试解析为数字
        try:
            price = float(price_text)
            if price > 0:
                return round(price, 2)
        except (ValueError, TypeError):
            pass
        
        return None
    
    def validate_price_within_limits(self, price: float, limit_up: float, 
                                   limit_down: float, order_type: str) -> Tuple[bool, str]:
        """
        验证价格是否在涨跌停范围内
        
        Args:
            price: 委托价格
            limit_up: 涨停价
            limit_down: 跌停价
            order_type: 订单类型 ('buy' 或 'sell')
            
        Returns:
            (是否有效, 错误信息)
        """
        if order_type == 'buy':
            if price > limit_up:
                return False, f"买入价格{price:.2f}超过涨停价{limit_up:.2f}"
        elif order_type == 'sell':
            if price < limit_down:
                return False, f"卖出价格{price:.2f}低于跌停价{limit_down:.2f}"
        
        return True, ""
    
    def get_stock_type_description(self, stock_type: StockType) -> str:
        """获取股票类型描述"""
        descriptions = {
            StockType.NORMAL: "普通股票(±10%)",
            StockType.ST: "ST股票(±5%)",
            StockType.CHINEXT: "创业板(±20%)",
            StockType.STAR: "科创板(±20%)",
            StockType.BSE: "北交所(±30%)"
        }
        return descriptions.get(stock_type, "未知类型")


# 全局价格计算器实例（将在需要时初始化）
_price_calculator_instance = None


def get_price_calculator(storage_instance=None) -> PriceCalculator:
    """获取价格计算器实例"""
    global _price_calculator_instance
    if _price_calculator_instance is None:
        _price_calculator_instance = PriceCalculator(storage_instance)
    elif storage_instance is not None:
        # 更新storage引用
        _price_calculator_instance.storage = storage_instance
    return _price_calculator_instance
