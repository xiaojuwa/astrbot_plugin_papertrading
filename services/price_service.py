"""统一的涨跌停价格服务
前置时间判断，统一管理涨跌停价格的获取策略
"""
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
from astrbot.api import logger

from ..utils.price_strategy import price_strategy_decider, PriceStrategy
from ..utils.data_storage import DataStorage


class PriceLimitService:
    """
    涨跌停价格服务
    
    核心职责：
    1. 前置时间判断，决定使用API还是本地计算
    2. 根据策略调用相应的获取方法
    3. 提供统一的涨跌停价格接口
    """
    
    def __init__(self, storage: DataStorage):
        self.storage = storage
    
    async def get_limit_prices(self, raw_api_data: Dict[str, Any], stock_code: str, 
                             stock_name: str, current_time: Optional[datetime] = None) -> Tuple[float, float]:
        """
        获取涨跌停价格 - 统一入口
        
        Args:
            raw_api_data: API返回的原始股票数据
            stock_code: 股票代码
            stock_name: 股票名称
            current_time: 当前时间，默认为系统当前时间
            
        Returns:
            (涨停价, 跌停价)
        """
        if current_time is None:
            current_time = datetime.now()
        
        # 前置时间判断，决定策略
        strategy, reason = price_strategy_decider.decide_strategy(current_time)
        logger.debug(f"涨跌停价格获取策略: {reason}")
        
        if strategy == PriceStrategy.API_DIRECT:
            # 使用API返回的涨跌停价格
            return await self._get_api_limit_prices(raw_api_data, stock_code, stock_name)
        else:
            # 基于收盘价本地计算涨跌停价格
            return await self._calculate_local_limit_prices(raw_api_data, stock_code, stock_name, current_time)
    
    async def _get_api_limit_prices(self, raw_api_data: Dict[str, Any], 
                                  stock_code: str, stock_name: str) -> Tuple[float, float]:
        """
        从API数据中获取涨跌停价格
        
        Args:
            raw_api_data: API返回的原始数据
            stock_code: 股票代码  
            stock_name: 股票名称
            
        Returns:
            (涨停价, 跌停价)
        """
        api_limit_up = raw_api_data.get('limit_up', 0)
        api_limit_down = raw_api_data.get('limit_down', 0)
        
        if api_limit_up > 0 and api_limit_down > 0:
            logger.debug(f"使用API涨跌停价格: {stock_name}({stock_code}) 涨停 {api_limit_up}, 跌停 {api_limit_down}")
            return api_limit_up, api_limit_down
        else:
            # API数据无效，回退到本地计算
            logger.warning(f"API涨跌停价格无效，回退到本地计算: {stock_name}({stock_code})")
            return await self._calculate_local_limit_prices(raw_api_data, stock_code, stock_name)
    
    async def _calculate_local_limit_prices(self, raw_api_data: Dict[str, Any], 
                                          stock_code: str, stock_name: str,
                                          current_time: Optional[datetime] = None) -> Tuple[float, float]:
        """
        基于收盘价本地计算涨跌停价格
        
        Args:
            raw_api_data: API返回的原始数据
            stock_code: 股票代码
            stock_name: 股票名称
            current_time: 当前时间
            
        Returns:
            (涨停价, 跌停价)
        """
        try:
            # 使用重构后的价格计算器
            from ..utils.price_calculator import get_price_calculator
            price_calc = get_price_calculator(self.storage)
            
            price_limits = await price_calc.calculate_price_limits(stock_code, stock_name, current_time)
            calculated_limit_up = price_limits.get('limit_up', 0)
            calculated_limit_down = price_limits.get('limit_down', 0)
            
            if calculated_limit_up > 0 and calculated_limit_down > 0:
                logger.debug(f"本地计算涨跌停价格: {stock_name}({stock_code}) 涨停 {calculated_limit_up}, 跌停 {calculated_limit_down}")
                return calculated_limit_up, calculated_limit_down
            else:
                logger.warning(f"本地计算涨跌停价格失败，使用API原值: {stock_name}({stock_code})")
                
        except Exception as e:
            logger.error(f"本地计算涨跌停价格时出错: {e}")
        
        # 兜底：使用API原值
        api_limit_up = raw_api_data.get('limit_up', 0)
        api_limit_down = raw_api_data.get('limit_down', 0)
        logger.debug(f"使用API原值作为兜底: {stock_name}({stock_code}) 涨停 {api_limit_up}, 跌停 {api_limit_down}")
        return api_limit_up, api_limit_down
    
    async def get_limit_prices_for_trading(self, stock_code: str, stock_name: str, 
                                         current_time: Optional[datetime] = None) -> Dict[str, Any]:
        """
        为交易操作获取涨跌停价格（不依赖现有API数据）
        
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            current_time: 当前时间
            
        Returns:
            涨跌停价格信息字典
        """
        if current_time is None:
            current_time = datetime.now()
        
        strategy, reason = price_strategy_decider.decide_strategy(current_time)
        
        if strategy == PriceStrategy.API_DIRECT:
            # 交易时间：需要先获取实时API数据再提取涨跌停
            logger.debug(f"交易时间，需要获取实时API数据: {reason}")
            try:
                from .stock_data import StockDataService
                stock_service = StockDataService(self.storage)
                stock_info = await stock_service.get_stock_info(stock_code, use_cache=False)
                
                if stock_info:
                    return {
                        'limit_up': stock_info.limit_up,
                        'limit_down': stock_info.limit_down,
                        'strategy': 'api_direct',
                        'reason': reason,
                        'base_price': stock_info.current_price or stock_info.close_price
                    }
            except Exception as e:
                logger.error(f"获取实时API数据失败: {e}")
        
        # 非交易时间或API失败：本地计算
        logger.debug(f"使用本地计算策略: {reason}")
        try:
            from ..utils.price_calculator import get_price_calculator
            price_calc = get_price_calculator(self.storage)
            
            price_limits = await price_calc.calculate_price_limits(stock_code, stock_name, current_time)
            return {
                'limit_up': price_limits.get('limit_up', 0),
                'limit_down': price_limits.get('limit_down', 0),
                'strategy': 'local_calculate',
                'reason': reason,
                'base_price': price_limits.get('base_price', 0),
                'stock_type': price_limits.get('stock_type', 'unknown'),
                'limit_ratio': price_limits.get('limit_ratio', 0)
            }
            
        except Exception as e:
            logger.error(f"本地计算涨跌停价格失败: {e}")
            return {
                'limit_up': 0,
                'limit_down': 0,
                'strategy': 'error',
                'reason': f"计算失败: {str(e)}",
                'base_price': 0
            }
    
    def get_current_strategy_info(self, current_time: Optional[datetime] = None) -> Dict[str, Any]:
        """
        获取当前的价格策略信息
        
        Args:
            current_time: 当前时间
            
        Returns:
            策略信息字典
        """
        return price_strategy_decider.get_strategy_info(current_time)


# 全局价格服务实例工厂
def get_price_limit_service(storage: DataStorage) -> PriceLimitService:
    """获取价格限制服务实例"""
    return PriceLimitService(storage)
