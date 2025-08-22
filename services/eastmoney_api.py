"""东方财富API服务类"""
import json
import asyncio
from typing import Optional, Dict, Any, Tuple
from astrbot.api import logger

try:
    import aiohttp
except ImportError:
    aiohttp = None


class EastMoneyAPIService:
    """东方财富API服务"""
    
    def __init__(self):
        self.session = None
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive'
        }
        
        # 常用股票代码映射（从temp_sayustock借鉴）
        self.code_id_dict = {
            '上证综指': '1.000001',
            '上证指数': '1.000001', 
            '深证成指': '0.399001',
            '深证指数': '0.399001',
            '创业板指': '0.399006',
            '创业板': '0.399006',
            '沪深300': '1.000300',
            '上证50': '1.000016',
            '科创50': '1.000688',
            '中小100': '0.399005',
            '中小板': '0.399005'
        }
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        if aiohttp is None:
            raise ImportError("需要安装aiohttp: pip install aiohttp")
        
        connector = aiohttp.TCPConnector(verify_ssl=False)
        timeout = aiohttp.ClientTimeout(total=30)
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers=self.headers
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        if self.session:
            await self.session.close()
    
    async def get_code_id(self, code: str) -> Optional[Tuple[str, str]]:
        """
        获取东方财富股票专用的行情ID
        借鉴自temp_sayustock项目
        
        Args:
            code: 股票代码或简称
            
        Returns:
            (secid, name) 或 None
        """
        # 如果已经是完整的secid格式
        if '.' in code:
            return code, ''
        
        # 检查预定义映射
        if code in self.code_id_dict:
            return self.code_id_dict[code], code
        
        # 通过搜索API获取
        url = 'https://searchapi.eastmoney.com/api/suggest/get'
        params = {
            'input': code,
            'type': '14',
            'token': 'D43BF722C8E33BDC906FB84D85E326E8',
            'count': '4'
        }
        
        try:
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    text = await response.text()
                    data = json.loads(text)
                    
                    code_list = data.get('QuotationCodeTable', {}).get('Data', [])
                    if code_list:
                        # 排序：债券排到最后，股票优先
                        code_list.sort(
                            key=lambda x: x.get('SecurityTypeName') == '债券'
                        )
                        return code_list[0]['QuoteID'], code_list[0]['Name']
                        
        except Exception as e:
            logger.error(f"搜索股票代码失败 {code}: {e}")
        
        return None
    
    def _get_full_security_code(self, code: str) -> str:
        """
        获取完整的证券代码
        借鉴自temp_sayustock项目
        """
        if '.' not in code:
            # 根据代码前缀判断市场
            if code.startswith(('00', '30', '39')):  # 深市
                return f"0.{code}"
            elif code.startswith(('60', '68', '51')):  # 沪市
                return f"1.{code}"
            elif code.startswith('83') or code.startswith('43') or code.startswith('87'):  # 北交所
                return f"0.{code}"
        return code
    
    async def get_stock_realtime_data(self, stock_code: str) -> Optional[Dict[str, Any]]:
        """
        获取股票实时数据
        使用东方财富个股接口
        
        Args:
            stock_code: 股票代码
            
        Returns:
            股票实时数据字典或None
        """
        try:
            # 获取secid
            code_result = await self.get_code_id(stock_code)
            if not code_result:
                logger.error(f"无法找到股票代码: {stock_code}")
                return None
            
            secid, stock_name = code_result
            secid = self._get_full_security_code(secid)
            
            # 构建请求参数 - 只获取模拟交易必需的数据
            url = 'https://push2.eastmoney.com/api/qt/stock/get'
            fields = [
                'f58',  # 股票名称
                'f57',  # 股票代码  
                'f43',  # 最新价(元)
                'f44',  # 最高价(元)
                'f45',  # 最低价(元)
                'f46',  # 开盘价(元)
                'f60',  # 昨收价(元)
                'f47',  # 成交量(手)
                'f48',  # 成交额(元)
                'f169', # 涨跌额(元)
                'f170', # 涨跌幅(%)
                'f51',  # 涨停价(元)
                'f52',  # 跌停价(元)
                'f86',  # 时间戳
            ]
            
            params = {
                'fields': ','.join(fields),
                'secid': secid
            }
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if data.get('data') is None:
                        logger.error(f"获取股票数据失败，可能股票不存在: {stock_code}")
                        return None
                    
                    raw_data = data['data']
                    
                    # 解析数据 - 只返回模拟交易必需的字段
                    result = {
                        'code': stock_code,
                        'name': raw_data.get('f58', stock_name),
                        'current_price': float(raw_data.get('f43', 0) or 0),
                        'open_price': float(raw_data.get('f46', 0) or 0),
                        'close_price': float(raw_data.get('f60', 0) or 0),  # 昨收价
                        'high_price': float(raw_data.get('f44', 0) or 0),
                        'low_price': float(raw_data.get('f45', 0) or 0),
                        'volume': int(raw_data.get('f47', 0) or 0),
                        'turnover': float(raw_data.get('f48', 0) or 0),
                        'change_amount': float(raw_data.get('f169', 0) or 0),
                        'change_percent': float(raw_data.get('f170', 0) or 0),
                        'limit_up': float(raw_data.get('f51', 0) or 0),
                        'limit_down': float(raw_data.get('f52', 0) or 0),
                        'timestamp': raw_data.get('f86', ''),
                    }
                    
                    return result
                else:
                    logger.error(f"请求失败，状态码: {response.status}")
                    return None
                    
        except Exception as e:
            logger.error(f"获取股票实时数据失败 {stock_code}: {e}")
            return None
    
    async def batch_get_stocks_data(self, stock_codes: list) -> Dict[str, Dict[str, Any]]:
        """
        批量获取股票数据
        
        Args:
            stock_codes: 股票代码列表
            
        Returns:
            {stock_code: stock_data} 字典
        """
        results = {}
        
        # 创建并发任务
        tasks = []
        for code in stock_codes:
            task = self.get_stock_realtime_data(code)
            tasks.append((code, task))
        
        # 并发执行
        for code, task in tasks:
            try:
                data = await task
                if data:
                    results[code] = data
            except Exception as e:
                logger.error(f"获取股票数据失败 {code}: {e}")
        
        return results


# 全局API实例（单例模式）
_api_instance = None

async def get_eastmoney_api() -> EastMoneyAPIService:
    """获取东方财富API实例"""
    global _api_instance
    if _api_instance is None:
        _api_instance = EastMoneyAPIService()
    return _api_instance
