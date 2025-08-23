"""股票数据服务 - 使用东方财富API重构版本"""
import time
from typing import Optional, Dict, Any
from datetime import datetime, time as dt_time
from astrbot.api import logger

from ..models.stock import StockInfo
from ..utils.validators import Validators
from ..utils.data_storage import DataStorage
from ..utils.market_time import is_trading_time, is_call_auction_time, can_place_order
from .eastmoney_api import EastMoneyAPIService


class StockDataService:
    """股票数据服务 - 基于东方财富API"""
    
    def __init__(self, storage: DataStorage):
        self.storage = storage
        self._cache_ttl = 30  # 缓存30秒
    
    async def get_stock_info(self, stock_code: str, use_cache: bool = True, skip_limit_calculation: bool = False) -> Optional[StockInfo]:
        """
        获取股票实时信息
        
        Args:
            stock_code: 股票代码
            use_cache: 是否使用缓存
            
        Returns:
            股票信息对象或None
        """
        # 标准化股票代码
        normalized_code = Validators.normalize_stock_code(stock_code)
        if not normalized_code:
            logger.error(f"无效的股票代码: {stock_code}")
            return None
        
        # 检查缓存
        if use_cache:
            cached_data = self.storage.get_market_cache(normalized_code)
            if cached_data and self._is_cache_valid(cached_data):
                return StockInfo.from_dict(cached_data)
        
        # 从东方财富API获取数据
        try:
            stock_data = await self._fetch_stock_data_from_eastmoney(normalized_code, skip_limit_calculation)
            if stock_data:
                # 保存到缓存
                self.storage.save_market_cache(normalized_code, stock_data.to_dict())
                return stock_data
                
        except Exception as e:
            logger.error(f"获取股票数据失败 {normalized_code}: {e}")
        
        return None
    
    async def _fetch_stock_data_from_eastmoney(self, stock_code: str, skip_limit_calculation: bool = False) -> Optional[StockInfo]:
        """
        从东方财富API获取股票数据
        
        Args:
            stock_code: 股票代码
            
        Returns:
            股票信息对象或None
        """
        try:
            async with EastMoneyAPIService() as api:
                raw_data = await api.get_stock_realtime_data(stock_code)
                
                if not raw_data:
                    logger.warning(f"未获取到股票数据: {stock_code}")
                    return None
                
                # 构造StockInfo对象
                return await self._build_stock_info(raw_data, skip_limit_calculation)
                
        except Exception as e:
            logger.error(f"从东方财富API获取数据失败 {stock_code}: {e}")
            return None
    
    async def _build_stock_info(self, raw_data: Dict[str, Any], skip_limit_calculation: bool = False) -> StockInfo:
        """
        从原始数据构建StockInfo对象
        
        Args:
            raw_data: 东方财富API返回的原始数据
            
        Returns:
            StockInfo对象
        """
        current_price = raw_data.get('current_price', 0)
        close_price = raw_data.get('close_price', current_price)
        stock_code = raw_data.get('code', '')
        stock_name = raw_data.get('name', '')
        
        # 设置买卖价格 - 统一使用当前价格，不再使用买1卖1
        # 模拟交易简化处理，所有交易都按当前价格进行
        trade_price = current_price if current_price > 0 else close_price
        
        # 检查股票是否停牌
        is_suspended = self._check_if_suspended(raw_data)
        
        # 获取涨跌停价格 - 根据交易时间选择不同的计算策略
        if skip_limit_calculation:
            # 跳过涨跌停计算，直接使用API数据（防止递归调用）
            limit_up = raw_data.get('limit_up', 0)
            limit_down = raw_data.get('limit_down', 0)
        else:
            limit_up, limit_down = await self._get_limit_prices(raw_data, stock_code, stock_name)
        
        # 构建StockInfo对象
        stock_info = StockInfo(
            code=stock_code,
            name=stock_name,
            current_price=current_price,
            open_price=raw_data.get('open_price', current_price),
            close_price=close_price,
            high_price=raw_data.get('high_price', current_price),
            low_price=raw_data.get('low_price', current_price),
            volume=raw_data.get('volume', 0),
            turnover=raw_data.get('turnover', 0),
            bid1_price=trade_price,  # 统一使用当前价格
            ask1_price=trade_price,  # 统一使用当前价格
            change_percent=raw_data.get('change_percent', 0),
            change_amount=raw_data.get('change_amount', 0),
            limit_up=limit_up,
            limit_down=limit_down,
            is_suspended=is_suspended,
            update_time=int(time.time())
        )
        
        return stock_info
    
    def _check_if_suspended(self, raw_data: Dict[str, Any]) -> bool:
        """
        检查股票是否停牌
        
        Args:
            raw_data: 原始数据
            
        Returns:
            是否停牌
        """
        # 简单判断：如果当前价格为0或者成交量为0且涨跌幅为0，可能是停牌
        current_price = raw_data.get('current_price', 0)
        volume = raw_data.get('volume', 0)
        change_percent = raw_data.get('change_percent', 0)
        
        # 如果当前价格为0，肯定是停牌
        if current_price <= 0:
            return True
        
        # 如果在交易时间内，成交量为0且价格没有变化，可能是停牌
        if is_trading_time():
            return volume == 0 and change_percent == 0
        
        return False
    
    async def _get_limit_prices(self, raw_data: Dict[str, Any], stock_code: str, stock_name: str) -> tuple[float, float]:
        """
        获取涨跌停价格 - 根据交易时间选择不同策略
        
        Args:
            raw_data: API返回的原始数据
            stock_code: 股票代码
            stock_name: 股票名称
            
        Returns:
            (涨停价, 跌停价)
        """
        current_time = datetime.now()
        
        # 判断是否在交易时间内（包括午休时间）
        is_market_hours = self._is_market_hours(current_time)
        
        # 如果是交易时间（包括午休），使用API返回的涨跌停价格
        if is_market_hours:
            api_limit_up = raw_data.get('limit_up', 0)
            api_limit_down = raw_data.get('limit_down', 0)
            
            # 如果API返回的涨跌停价格有效，直接使用
            if api_limit_up > 0 and api_limit_down > 0:
                logger.debug(f"交易时间，使用API涨跌停价格: 涨停 {api_limit_up}, 跌停 {api_limit_down}")
                return api_limit_up, api_limit_down
        
        # 非交易时间或API数据无效时，使用PriceCalculator计算
        logger.debug(f"非交易时间或API数据无效，使用PriceCalculator计算涨跌停价格")
        try:
            from ..utils.price_calculator import get_price_calculator
            price_calc = get_price_calculator(self.storage)
            
            price_limits = await price_calc.calculate_price_limits(stock_code, stock_name, current_time)
            calculated_limit_up = price_limits.get('limit_up', 0)
            calculated_limit_down = price_limits.get('limit_down', 0)
            
            if calculated_limit_up > 0 and calculated_limit_down > 0:
                logger.debug(f"计算得到涨跌停价格: 涨停 {calculated_limit_up}, 跌停 {calculated_limit_down}")
                return calculated_limit_up, calculated_limit_down
            else:
                logger.warning(f"涨跌停价格计算失败，使用API原值")
                
        except Exception as e:
            logger.error(f"计算涨跌停价格时出错: {e}")
        
        # 兜底：使用API原值
        api_limit_up = raw_data.get('limit_up', 0)
        api_limit_down = raw_data.get('limit_down', 0)
        return api_limit_up, api_limit_down
    
    def _is_lunch_break(self, current_time: datetime) -> bool:
        """
        判断是否为中午休市时间 (11:30-13:00)
        """
        from ..utils.market_time import market_time_manager
        if not market_time_manager.is_trading_day(current_time.date()):
            return False
            
        current_time_only = current_time.time()
        lunch_start = dt_time(11, 30)
        lunch_end = dt_time(13, 0)
        
        return lunch_start <= current_time_only <= lunch_end
    
    def _is_market_hours(self, current_time: datetime) -> bool:
        """
        判断是否在市场开放时间内（交易时间 + 午休时间）
        包括：
        - 9:30-11:30 (上午交易)
        - 11:30-13:00 (午休)
        - 13:00-15:00 (下午交易)
        """
        # 首先检查是否为交易日
        from ..utils.market_time import market_time_manager
        if not market_time_manager.is_trading_day(current_time.date()):
            return False
        
        current_time_only = current_time.time()
        
        # 市场时间范围：9:30-15:00 (包含午休时间)
        market_start = dt_time(9, 30)
        market_end = dt_time(15, 0)
        
        return market_start <= current_time_only <= market_end
    
    def _is_cache_valid(self, cache_data: Dict) -> bool:
        """
        检查缓存是否有效
        
        Args:
            cache_data: 缓存数据
            
        Returns:
            缓存是否有效
        """
        if 'update_time' not in cache_data:
            return False
        
        current_time = int(time.time())
        cache_time = cache_data['update_time']
        
        return (current_time - cache_time) <= self._cache_ttl
    
    def is_trading_time(self) -> bool:
        """
        检查是否在交易时间
        
        Returns:
            是否在交易时间
        """
        return is_trading_time()
    
    def is_call_auction_time(self) -> bool:
        """
        检查是否在集合竞价时间
        
        Returns:
            是否在集合竞价时间
        """
        return is_call_auction_time()
    
    def can_place_order(self) -> tuple[bool, str]:
        """
        检查是否可以下单
        
        Returns:
            (是否可以下单, 原因说明)
        """
        return can_place_order()
    
    async def search_stock(self, keyword: str) -> list:
        """
        搜索股票（保留原有方法）
        
        Args:
            keyword: 搜索关键词
            
        Returns:
            股票列表
        """
        try:
            async with EastMoneyAPIService() as api:
                # 尝试直接获取股票信息
                stock_info = await api.get_stock_realtime_data(keyword)
                if stock_info:
                    return [{
                        'code': stock_info['code'],
                        'name': stock_info['name'],
                        'price': stock_info['current_price']
                    }]
                
            return []
            
        except Exception as e:
            logger.error(f"搜索股票失败: {e}")
            return []
    
    async def search_stocks_fuzzy(self, keyword: str) -> list:
        """
        模糊搜索股票，支持中文、拼音、代码等
        
        Args:
            keyword: 搜索关键词
            
        Returns:
            股票候选列表: [{'code', 'name', 'market'}]
        """
        try:
            async with EastMoneyAPIService() as api:
                return await api.search_stocks_fuzzy(keyword)
        except Exception as e:
            logger.error(f"模糊搜索股票失败: {e}")
            return []
    
    async def batch_get_stocks(self, stock_codes: list) -> Dict[str, Optional[StockInfo]]:
        """
        批量获取股票信息
        
        Args:
            stock_codes: 股票代码列表
            
        Returns:
            {stock_code: StockInfo} 字典
        """
        results = {}
        
        try:
            async with EastMoneyAPIService() as api:
                raw_data_dict = await api.batch_get_stocks_data(stock_codes)
                
                for code, raw_data in raw_data_dict.items():
                    try:
                        stock_info = await self._build_stock_info(raw_data, skip_limit_calculation=False)
                        results[code] = stock_info
                        
                        # 保存到缓存
                        self.storage.save_market_cache(code, stock_info.to_dict())
                        
                    except Exception as e:
                        logger.error(f"构建股票信息失败 {code}: {e}")
                        results[code] = None
                        
        except Exception as e:
            logger.error(f"批量获取股票数据失败: {e}")
            
        return results
    
    def get_market_status(self) -> Dict[str, Any]:
        """
        获取市场状态信息
        
        Returns:
            市场状态字典
        """
        current_time = datetime.now()
        can_order, reason = can_place_order(current_time)
        
        return {
            'current_time': current_time.strftime('%Y-%m-%d %H:%M:%S'),
            'is_trading_time': is_trading_time(current_time),
            'is_call_auction_time': is_call_auction_time(current_time),
            'can_place_order': can_order,
            'reason': reason,
            'cache_ttl': self._cache_ttl
        }