"""每日一猜服务"""
import random
import time
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List
from astrbot.api import logger

from ..models.daily_guess import DailyGuess, GuessRecord
from ..utils.data_storage import DataStorage
from .stock_data import StockDataService


class DailyGuessService:
    """每日一猜服务"""
    
    def __init__(self, storage: DataStorage, stock_service: StockDataService):
        self.storage = storage
        self.stock_service = stock_service
        
        # 热门股票池 - 按板块分类，更丰富多样
        self.popular_stocks = {
            '银行': [
                {'code': '000001', 'name': '平安银行'},
                {'code': '600036', 'name': '招商银行'},
                {'code': '600000', 'name': '浦发银行'},
                {'code': '601166', 'name': '兴业银行'},
                {'code': '600016', 'name': '民生银行'},
                {'code': '601398', 'name': '工商银行'},
                {'code': '601939', 'name': '建设银行'},
                {'code': '601288', 'name': '农业银行'}
            ],
            '白酒': [
                {'code': '600519', 'name': '贵州茅台'},
                {'code': '000858', 'name': '五粮液'},
                {'code': '000568', 'name': '泸州老窖'},
                {'code': '000596', 'name': '古井贡酒'},
                {'code': '600809', 'name': '山西汾酒'},
                {'code': '000799', 'name': '酒鬼酒'},
                {'code': '603369', 'name': '今世缘'},
                {'code': '000860', 'name': '顺鑫农业'}
            ],
            '科技': [
                {'code': '000063', 'name': '中兴通讯'},
                {'code': '002415', 'name': '海康威视'},
                {'code': '300059', 'name': '东方财富'},
                {'code': '000725', 'name': '京东方A'},
                {'code': '002594', 'name': '比亚迪'},
                {'code': '300750', 'name': '宁德时代'},
                {'code': '688981', 'name': '中芯国际'},
                {'code': '002230', 'name': '科大讯飞'},
                {'code': '300760', 'name': '迈瑞医疗'},
                {'code': '688111', 'name': '金山办公'}
            ],
            '地产': [
                {'code': '000002', 'name': '万科A'},
                {'code': '600048', 'name': '保利发展'},
                {'code': '001979', 'name': '招商蛇口'},
                {'code': '600383', 'name': '金地集团'},
                {'code': '000069', 'name': '华侨城A'},
                {'code': '600606', 'name': '绿地控股'},
                {'code': '000656', 'name': '金科股份'},
                {'code': '600340', 'name': '华夏幸福'}
            ],
            '医药': [
                {'code': '600276', 'name': '恒瑞医药'},
                {'code': '000661', 'name': '长春高新'},
                {'code': '300015', 'name': '爱尔眼科'},
                {'code': '600521', 'name': '华海药业'},
                {'code': '002007', 'name': '华兰生物'},
                {'code': '300347', 'name': '泰格医药'},
                {'code': '600196', 'name': '复星医药'},
                {'code': '000963', 'name': '华东医药'}
            ],
            '消费': [
                {'code': '600887', 'name': '伊利股份'},
                {'code': '000858', 'name': '五粮液'},
                {'code': '600519', 'name': '贵州茅台'},
                {'code': '000568', 'name': '泸州老窖'},
                {'code': '600031', 'name': '三一重工'},
                {'code': '000858', 'name': '五粮液'},
                {'code': '600276', 'name': '恒瑞医药'},
                {'code': '600887', 'name': '伊利股份'},
                {'code': '000596', 'name': '古井贡酒'},
                {'code': '600809', 'name': '山西汾酒'}
            ],
            '新能源': [
                {'code': '300750', 'name': '宁德时代'},
                {'code': '002594', 'name': '比亚迪'},
                {'code': '300274', 'name': '阳光电源'},
                {'code': '002460', 'name': '赣锋锂业'},
                {'code': '300014', 'name': '亿纬锂能'},
                {'code': '002812', 'name': '恩捷股份'},
                {'code': '300207', 'name': '欣旺达'},
                {'code': '688223', 'name': '晶科能源'}
            ],
            '军工': [
                {'code': '000768', 'name': '中航飞机'},
                {'code': '600893', 'name': '航发动力'},
                {'code': '002179', 'name': '中航光电'},
                {'code': '600372', 'name': '中航电子'},
                {'code': '000547', 'name': '航天发展'},
                {'code': '600879', 'name': '航天电子'},
                {'code': '002013', 'name': '中航机电'},
                {'code': '600967', 'name': '内蒙一机'}
            ]
        }
    
    async def create_daily_guess(self, date: str = None) -> DailyGuess:
        """创建每日猜股"""
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')
        
        # 检查是否已存在今日猜股
        existing = self.storage.get_daily_guess(date)
        if existing:
            return DailyGuess.from_dict(existing)
        
        # 随机选择一只股票
        stock = await self._select_random_stock()
        
        # 创建猜股记录
        daily_guess = DailyGuess(
            date=date,
            stock_code=stock['code'],
            stock_name=stock['name'],
            open_price=stock['open_price'],
            create_time=int(time.time())
        )
        
        self.storage.save_daily_guess(daily_guess)
        logger.info(f"创建每日猜股: {date} - {stock['name']}({stock['code']})")
        return daily_guess
    
    async def submit_guess(self, user_id: str, guess_price: float) -> Tuple[bool, str]:
        """提交猜测"""
        today = datetime.now().strftime('%Y-%m-%d')
        daily_guess = self.storage.get_daily_guess(today)
        
        if not daily_guess:
            return False, "今日猜股活动未开始"
        
        daily_guess = DailyGuess.from_dict(daily_guess)
        
        if daily_guess.is_finished:
            return False, "今日猜股活动已结束"
        
        # 检查是否在猜股时间内 (9:35-15:05)
        now = datetime.now()
        guess_start = now.replace(hour=9, minute=35, second=0, microsecond=0)
        guess_end = now.replace(hour=15, minute=5, second=0, microsecond=0)
        
        if now < guess_start:
            return False, f"猜股活动还未开始，开始时间：09:35"
        elif now > guess_end:
            return False, f"猜股活动已结束，结束时间：15:05"
        
        # 检查是否已猜测过
        if user_id in daily_guess.guesses:
            return False, "您已经猜测过了"
        
        # 验证价格
        if guess_price <= 0:
            return False, "猜测价格必须大于0"
        
        # 保存猜测
        daily_guess.add_guess(user_id, guess_price)
        self.storage.save_daily_guess(daily_guess)
        
        return True, f"猜测成功！您猜测 {daily_guess.stock_name} 收盘价为 {guess_price:.2f}元"
    
    async def finish_daily_guess(self, date: str = None) -> Tuple[bool, str]:
        """结束每日猜股并确定获胜者"""
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')
        
        daily_guess = self.storage.get_daily_guess(date)
        if not daily_guess:
            return False, "未找到今日猜股记录"
        
        daily_guess = DailyGuess.from_dict(daily_guess)
        
        if daily_guess.is_finished:
            return False, "今日猜股已结束"
        
        # 获取收盘价
        stock_info = await self.stock_service.get_stock_info(daily_guess.stock_code)
        if not stock_info:
            return False, "无法获取股票收盘价"
        
        close_price = stock_info.close_price
        daily_guess.finish_guess(close_price)
        
        # 给获胜者发放奖励
        if daily_guess.winner:
            await self._give_prize(daily_guess.winner, daily_guess.prize_amount)
            winner_accuracy = daily_guess.get_winner_accuracy()
            message = f"猜股结束！收盘价：{close_price:.2f}元，获胜者：{daily_guess.winner}，误差：{winner_accuracy:.2f}元"
        else:
            message = f"猜股结束！收盘价：{close_price:.2f}元，无人参与"
        
        self.storage.save_daily_guess(daily_guess)
        logger.info(f"每日猜股结束: {date} - 收盘价:{close_price:.2f}元, 获胜者:{daily_guess.winner}")
        return True, message
    
    async def get_daily_guess_status(self, date: str = None) -> Optional[DailyGuess]:
        """获取每日猜股状态"""
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')
        
        daily_guess = self.storage.get_daily_guess(date)
        if not daily_guess:
            return None
        
        return DailyGuess.from_dict(daily_guess)
    
    async def get_guess_ranking(self, date: str = None) -> List[Dict[str, Any]]:
        """获取猜测排行榜"""
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')
        
        daily_guess = self.storage.get_daily_guess(date)
        if not daily_guess:
            return []
        
        daily_guess = DailyGuess.from_dict(daily_guess)
        
        if not daily_guess.guesses:
            return []
        
        # 计算准确度
        rankings = []
        for user_id, guess_price in daily_guess.guesses.items():
            if daily_guess.close_price:
                accuracy = abs(guess_price - daily_guess.close_price)
            else:
                accuracy = None
            
            rankings.append({
                'user_id': user_id,
                'guess_price': guess_price,
                'accuracy': accuracy,
                'is_winner': user_id == daily_guess.winner
            })
        
        # 按准确度排序（误差越小越好）
        if daily_guess.close_price:
            rankings.sort(key=lambda x: x['accuracy'] or float('inf'))
        
        return rankings
    
    async def _select_random_stock(self) -> Dict[str, Any]:
        """随机选择一只股票"""
        # 1. 完全随机选择板块
        sectors = list(self.popular_stocks.keys())
        selected_sector = random.choice(sectors)
        
        # 2. 从该板块中随机选择一只股票
        sector_stocks = self.popular_stocks[selected_sector]
        selected = random.choice(sector_stocks)
        
        # 3. 添加板块信息
        selected['sector'] = selected_sector
        
        # 4. 获取开盘价
        try:
            stock_info = await self.stock_service.get_stock_info(selected['code'])
            if stock_info:
                selected['open_price'] = stock_info.open_price
            else:
                selected['open_price'] = 0.0
        except Exception as e:
            logger.error(f"获取股票 {selected['code']} 信息失败: {e}")
            selected['open_price'] = 0.0
        
        logger.info(f"选择猜股股票: {selected['name']}({selected['code']}) - {selected_sector}板块")
        return selected
    
    async def _give_prize(self, user_id: str, amount: float):
        """发放奖励"""
        try:
            user_data = self.storage.get_user(user_id)
            if user_data:
                from ..models.user import User
                user = User.from_dict(user_data)
                user.add_balance(amount)
                self.storage.save_user(user_id, user.to_dict())
                logger.info(f"发放猜股奖励: {user_id} +{amount:.2f}元")
        except Exception as e:
            logger.error(f"发放奖励失败: {e}")
    
    def get_stock_pool_info(self) -> Dict[str, Any]:
        """获取股票池信息"""
        total_stocks = sum(len(stocks) for stocks in self.popular_stocks.values())
        sectors = list(self.popular_stocks.keys())
        
        return {
            'total_stocks': total_stocks,
            'sectors': sectors,
            'sector_counts': {sector: len(stocks) for sector, stocks in self.popular_stocks.items()},
            'all_stocks': self.popular_stocks
        }
    
    def get_sector_stocks(self, sector: str) -> List[Dict[str, str]]:
        """获取指定板块的股票列表"""
        return self.popular_stocks.get(sector, [])
