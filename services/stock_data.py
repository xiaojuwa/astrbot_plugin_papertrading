"""股票数据服务"""
import asyncio
import time
from typing import Optional, Dict, Any
from datetime import datetime, time as dt_time

try:
    import akshare as ak
except ImportError:
    ak = None

from ..models.stock import StockInfo
from ..utils.validators import Validators
from ..utils.data_storage import DataStorage


class StockDataService:
    """股票数据服务"""
    
    def __init__(self, storage: DataStorage):
        self.storage = storage
        self._cache_ttl = 30  # 缓存30秒
        
        if ak is None:
            print("警告: akshare库未安装，股票数据功能将不可用")
    
    async def get_stock_info(self, stock_code: str, use_cache: bool = True) -> Optional[StockInfo]:
        """获取股票实时信息"""
        if ak is None:
            return None
        
        # 标准化股票代码
        normalized_code = Validators.normalize_stock_code(stock_code)
        if not normalized_code:
            return None
        
        # 检查缓存
        if use_cache:
            cached_data = self.storage.get_market_cache(normalized_code)
            if cached_data and self._is_cache_valid(cached_data):
                return StockInfo.from_dict(cached_data)
        
        # 从akshare获取数据
        try:
            stock_data = await self._fetch_stock_data(normalized_code)
            if stock_data:
                # 保存到缓存
                self.storage.save_market_cache(normalized_code, stock_data.to_dict())
                return stock_data
        except Exception as e:
            print(f"获取股票数据失败 {normalized_code}: {e}")
        
        return None
    
    async def _fetch_stock_data(self, stock_code: str) -> Optional[StockInfo]:
        """从akshare获取股票数据"""
        try:
            # 添加交易所前缀
            ak_code = Validators.format_stock_code_with_exchange(stock_code)
            if not ak_code:
                return None
            
            # 在线程池中执行同步的akshare调用
            loop = asyncio.get_event_loop()
            
            # 获取实时行情数据
            real_time_data = await loop.run_in_executor(
                None, self._get_realtime_data, ak_code
            )
            
            if not real_time_data:
                return None
            
            # 获取股票基本信息
            stock_info = await loop.run_in_executor(
                None, self._get_stock_info, stock_code
            )
            
            # 构造StockInfo对象
            return self._build_stock_info(stock_code, real_time_data, stock_info)
        
        except Exception as e:
            print(f"从akshare获取数据失败: {e}")
            return None
    
    def _get_realtime_data(self, ak_code: str) -> Optional[Dict]:
        """获取实时行情数据（同步方法）"""
        try:
            # 使用akshare获取实时数据
            df = ak.stock_zh_a_spot_em()
            
            # 查找对应股票
            stock_data = df[df['代码'] == ak_code[2:]]  # 去掉sh/sz前缀
            
            if stock_data.empty:
                return None
            
            data = stock_data.iloc[0]
            
            return {
                'name': data.get('名称', ''),
                'current_price': float(data.get('最新价', 0)),
                'open_price': float(data.get('今开', 0)),
                'close_price': float(data.get('昨收', 0)),
                'high_price': float(data.get('最高', 0)),
                'low_price': float(data.get('最低', 0)),
                'volume': int(data.get('成交量', 0)),
                'turnover': float(data.get('成交额', 0)),
                'change_percent': float(data.get('涨跌幅', 0)),
                'change_amount': float(data.get('涨跌额', 0)),
            }
        
        except Exception as e:
            print(f"获取实时数据失败: {e}")
            return None
    
    def _get_stock_info(self, stock_code: str) -> Optional[Dict]:
        """获取股票基本信息（同步方法）"""
        try:
            # 获取股票基本信息，包括涨跌停价格
            ak_code = Validators.format_stock_code_with_exchange(stock_code)
            if not ak_code:
                return None
            
            # 尝试获取涨跌停信息
            try:
                df_limit = ak.stock_zh_a_daily(symbol=ak_code, period="daily", start_date="20240101", adjust="")
                if not df_limit.empty:
                    latest = df_limit.iloc[-1]
                    close_price = float(latest.get('close', 0))
                    
                    # 计算涨跌停价格（10%）
                    limit_up = round(close_price * 1.1, 2)
                    limit_down = round(close_price * 0.9, 2)
                    
                    return {
                        'limit_up': limit_up,
                        'limit_down': limit_down
                    }
            except:
                pass
            
            # 如果无法获取历史数据，使用默认计算
            return {}
        
        except Exception as e:
            print(f"获取股票基本信息失败: {e}")
            return {}
    
    def _build_stock_info(self, stock_code: str, real_time_data: Dict, stock_info: Dict) -> StockInfo:
        """构建StockInfo对象"""
        current_price = real_time_data.get('current_price', 0)
        close_price = real_time_data.get('close_price', current_price)
        
        # 计算涨跌停价格
        limit_up = stock_info.get('limit_up', round(close_price * 1.1, 2))
        limit_down = stock_info.get('limit_down', round(close_price * 0.9, 2))
        
        # 估算买一卖一价格（如果没有真实数据）
        bid1_price = current_price - 0.01
        ask1_price = current_price + 0.01
        
        return StockInfo(
            code=stock_code,
            name=real_time_data.get('name', ''),
            current_price=current_price,
            open_price=real_time_data.get('open_price', current_price),
            close_price=close_price,
            high_price=real_time_data.get('high_price', current_price),
            low_price=real_time_data.get('low_price', current_price),
            volume=real_time_data.get('volume', 0),
            turnover=real_time_data.get('turnover', 0),
            bid1_price=bid1_price,
            ask1_price=ask1_price,
            change_percent=real_time_data.get('change_percent', 0),
            change_amount=real_time_data.get('change_amount', 0),
            limit_up=limit_up,
            limit_down=limit_down,
            is_suspended=self._check_if_suspended(real_time_data),
            update_time=int(time.time())
        )
    
    def _check_if_suspended(self, real_time_data: Dict) -> bool:
        """检查股票是否停牌"""
        # 简单判断：如果成交量为0且价格没有变化，可能是停牌
        volume = real_time_data.get('volume', 0)
        change_amount = real_time_data.get('change_amount', 0)
        
        return volume == 0 and change_amount == 0
    
    def _is_cache_valid(self, cache_data: Dict) -> bool:
        """检查缓存是否有效"""
        if 'update_time' not in cache_data:
            return False
        
        current_time = int(time.time())
        cache_time = cache_data['update_time']
        
        return (current_time - cache_time) <= self._cache_ttl
    
    def is_trading_time(self) -> bool:
        """检查是否在交易时间"""
        now = datetime.now()
        current_time = now.time()
        
        # 获取配置的交易时间
        config = self.storage.get_config()
        market_hours = config.get('market_hours', {})
        
        morning = market_hours.get('morning', {'start': '09:30', 'end': '11:30'})
        afternoon = market_hours.get('afternoon', {'start': '13:00', 'end': '15:00'})
        
        # 解析时间
        morning_start = dt_time.fromisoformat(morning['start'])
        morning_end = dt_time.fromisoformat(morning['end'])
        afternoon_start = dt_time.fromisoformat(afternoon['start'])
        afternoon_end = dt_time.fromisoformat(afternoon['end'])
        
        # 检查是否在交易时间段内
        is_morning_session = morning_start <= current_time <= morning_end
        is_afternoon_session = afternoon_start <= current_time <= afternoon_end
        
        # 还要检查是否是工作日
        is_weekday = now.weekday() < 5  # 0-4是周一到周五
        
        return is_weekday and (is_morning_session or is_afternoon_session)
    
    def is_call_auction_time(self) -> bool:
        """检查是否在集合竞价时间"""
        now = datetime.now()
        current_time = now.time()
        
        # 开盘集合竞价：9:15-9:25
        morning_auction_start = dt_time(9, 15)
        morning_auction_end = dt_time(9, 25)
        
        # 收盘集合竞价：14:57-15:00
        afternoon_auction_start = dt_time(14, 57)
        afternoon_auction_end = dt_time(15, 0)
        
        is_morning_auction = morning_auction_start <= current_time <= morning_auction_end
        is_afternoon_auction = afternoon_auction_start <= current_time <= afternoon_auction_end
        
        # 还要检查是否是工作日
        is_weekday = now.weekday() < 5
        
        return is_weekday and (is_morning_auction or is_afternoon_auction)
    
    async def search_stock(self, keyword: str) -> list:
        """搜索股票"""
        if ak is None:
            return []
        
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, self._search_stock_sync, keyword
            )
            return result or []
        except Exception as e:
            print(f"搜索股票失败: {e}")
            return []
    
    def _search_stock_sync(self, keyword: str) -> list:
        """同步搜索股票"""
        try:
            # 获取股票列表
            df = ak.stock_zh_a_spot_em()
            
            # 搜索名称或代码包含关键字的股票
            filtered = df[
                (df['名称'].str.contains(keyword, na=False)) |
                (df['代码'].str.contains(keyword, na=False))
            ]
            
            results = []
            for _, row in filtered.head(10).iterrows():  # 最多返回10个结果
                results.append({
                    'code': row['代码'],
                    'name': row['名称'],
                    'price': float(row.get('最新价', 0))
                })
            
            return results
        
        except Exception as e:
            print(f"同步搜索股票失败: {e}")
            return []
