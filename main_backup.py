"""A股模拟交易插件"""
import time
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.api.event.filter import command
from astrbot.api.star import Context, Star
from astrbot.api import logger, AstrBotConfig

# 导入本地模块
from .models.user import User
from .utils.data_storage import DataStorage
from .utils.validators import Validators
from .utils.formatters import Formatters
from .services.stock_data import StockDataService
from .services.trading_engine import TradingEngine
from .services.order_monitor import OrderMonitorService


class PaperTradingPlugin(Star):
    """A股模拟交易插件，支持实时买卖、挂单交易、持仓查询、群内排行等功能。"""
    
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config: AstrBotConfig = config
        
        # 初始化服务（使用依赖注入）
        self.storage = DataStorage("papertrading", self.config)
        self.stock_service = StockDataService(self.storage)
        self.trading_engine = TradingEngine(self.storage, self.stock_service)
        self.order_monitor = OrderMonitorService(self.storage)
        
        logger.info("A股模拟交易插件初始化完成")
    
    def _get_isolated_user_id(self, event: AstrMessageEvent) -> str:
        """
        获取隔离的用户ID，确保不同群聊中的数据隔离
        格式: platform:sender_id:session_id
        
        Args:
            event: 消息事件对象
            
        Returns:
            隔离的用户ID字符串
        """
        platform_name = event.get_platform_name()
        sender_id = event.get_sender_id()
        session_id = event.get_session_id()
        
        # 使用平台:发送者:会话的组合来确保数据隔离
        # 这样同一用户在不同群聊中会有不同的账户
        return f"{platform_name}:{sender_id}:{session_id}"
    
    async def _wait_for_stock_selection(self, event: AstrMessageEvent, candidates: list, action: str) -> dict:
        """
        等待用户选择股票
        
        Args:
            event: 原始事件
            candidates: 候选股票列表
            action: 操作描述（用于提示）
            
        Returns:
            选中的股票信息，或None
        """
        import asyncio
        
        try:
            # 简化版等待实现 - 在实际环境中需要使用事件监听机制
            # 这里返回第一个候选作为默认选择
            return candidates[0] if candidates else None
            
        except Exception as e:
            logger.error(f"等待用户选择失败: {e}")
            return None
    
    async def _wait_for_trade_confirmation(self, event: AstrMessageEvent, trade_info: dict) -> bool:
        """
        等待用户确认交易
        
        Args:
            event: 原始事件
            trade_info: 交易信息
            
        Returns:
            是否确认交易
        """
        try:
            # 简化版确认实现 - 在实际环境中需要使用事件监听机制
            # 这里默认确认交易
            return True
            
        except Exception as e:
            logger.error(f"等待交易确认失败: {e}")
            return False
    
    async def _search_and_select_stock(self, event: AstrMessageEvent, keyword: str) -> dict:
        """搜索并选择股票"""
        # 先尝试精确匹配（如果是6位数字代码）
        if keyword.isdigit() and len(keyword) == 6:
            stock_code = Validators.normalize_stock_code(keyword)
            if stock_code:
                try:
                    stock_info = await self.stock_service.get_stock_info(stock_code)
                    if stock_info:
                        return {
                            'code': stock_code,
                            'name': stock_info.name,
                            'market': '未知'  # 简化实现
                        }
                except Exception:
                    pass
        
        # 模糊搜索
        try:
            candidates = await self.stock_service.search_stocks_fuzzy(keyword)
            
            if not candidates:
                return None
            
            if len(candidates) == 1:
                return candidates[0]
            else:
                # 多个候选，让用户选择（简化实现）
                selection_text = f"🔍 找到多个相关股票:\n\n"
                for i, candidate in enumerate(candidates[:3], 1):  # 最多显示3个
                    selection_text += f"{i}. {candidate['name']} ({candidate['code']})\n"
                selection_text += f"\n💡 默认选择第一个: {candidates[0]['name']}"
                
                # 暂时直接返回第一个候选
                return candidates[0]  # 简化实现：返回第一个
                
        except Exception as e:
            logger.error(f"搜索股票失败: {e}")
            return None
    
    async def initialize(self):
        """插件初始化"""
        try:
            # 根据配置决定是否启动挂单监控服务
            monitor_interval = self.config.get("monitor_interval", 15)
            if monitor_interval > 0:
                await self.order_monitor.start_monitoring()
            else:
                logger.info("轮询间隔为0，挂单监控服务暂停")
            
            # 注册定时任务
            self.context.register_task(self._daily_maintenance(), "每日维护任务")
            
            logger.info("A股模拟交易插件启动成功")
        except Exception as e:
            logger.error(f"插件初始化失败: {e}")
    
    async def _daily_maintenance(self):
        """每日维护任务"""
        import asyncio
        from datetime import datetime, time as dt_time
        
        while True:
            try:
                # 每天凌晨2点执行维护
                now = datetime.now()
                target_time = datetime.combine(now.date(), dt_time(2, 0))
                
                if now > target_time:
                    target_time = target_time.replace(day=target_time.day + 1)
                
                sleep_seconds = (target_time - now).total_seconds()
                await asyncio.sleep(sleep_seconds)
                
                # 执行维护任务
                await self._perform_daily_maintenance()
                
            except Exception as e:
                logger.error(f"每日维护任务错误: {e}")
                await asyncio.sleep(3600)  # 出错后等待1小时
    
    async def _perform_daily_maintenance(self):
        """执行每日维护"""
        logger.info("开始执行每日维护任务")
        
        # 更新所有用户的T+1持仓状态
        all_users = self.storage.get_all_users()
        for user_id in all_users:
            try:
                from .services.market_rules import MarketRulesEngine
                market_rules = MarketRulesEngine(self.storage)
                market_rules.make_positions_available_for_next_day(user_id)
                
                # 更新用户总资产
                await self.trading_engine.update_user_assets(user_id)
            except Exception as e:
                logger.error(f"更新用户 {user_id} 数据失败: {e}")
        
        # 清理过期的市场数据缓存
        self.storage.clear_market_cache()
        
        logger.info("每日维护任务完成")

    # ==================== 用户注册相关 ====================
    
    @command("股票注册")
    async def register_user(self, event: AstrMessageEvent):
        """用户注册"""
        user_id = self._get_isolated_user_id(event)
        user_name = event.get_sender_name() or f"用户{user_id}"
        
        # 检查是否已注册
        existing_user = self.storage.get_user(user_id)
        if existing_user:
            yield MessageEventResult().message("您已经注册过了！使用 /股票账户 查看账户信息")
            return
        
        # 创建新用户，从插件配置获取初始资金
        initial_balance = self.config.get('initial_balance', 1000000)
        
        user = User(
            user_id=user_id,
            username=user_name,
            balance=initial_balance,
            total_assets=initial_balance,
            register_time=int(time.time()),
            last_login=int(time.time())
        )
        
        # 保存用户
        self.storage.save_user(user_id, user.to_dict())
        
        yield MessageEventResult().message(
            f"🎉 注册成功！\n"
            f"👤 用户名: {user_name}\n"
            f"💰 初始资金: {Formatters.format_currency(initial_balance)}元\n\n"
            f"📖 输入 /股票帮助 查看使用说明"
        )

    # ==================== 交易相关 ====================
    
    @command("买入")
    async def market_buy_stock(self, event: AstrMessageEvent):
        """市价买入股票"""
        user_id = self._get_isolated_user_id(event)
        
        # 检查用户是否注册
        if not self.storage.get_user(user_id):
            yield MessageEventResult().message("❌ 您还未注册，请先使用 /股票注册 注册账户")
            return
        
        # 解析参数
        params = event.message_str.strip().split()[1:]
        if len(params) < 2:
            yield MessageEventResult().message("❌ 参数不足\n\n格式: /买入 股票代码/名称 数量\n例: /买入 平安银行 1000")
            return
        
        keyword = params[0]
        try:
            volume = int(params[1])
            # 市价单无需价格参数
            price_text = None
        except (ValueError, IndexError):
            yield MessageEventResult().message("❌ 参数格式错误\n\n格式: /买入 股票代码/名称 数量\n例: /买入 平安银行 1000")
            return
        
        # 1. 股票搜索
        selected_stock = await self._search_and_select_stock(event, keyword)
        if not selected_stock:
            return
        
        stock_code = selected_stock['code']
        stock_name = selected_stock['name']
        
        # 2. 获取当前股价用于确认
        try:
            stock_info = await self.stock_service.get_stock_info(stock_code)
            if not stock_info:
                yield MessageEventResult().message(f"❌ 无法获取 {stock_name} 的实时数据")
                return
            
            # 3. 解析价格输入（支持涨停/跌停文本）
            price = None
            if price_text:
                from .utils.price_calculator import get_price_calculator
                price_calc = get_price_calculator(self.storage)
                
                # 计算当前时间的涨跌停价格
                price_limits = await price_calc.calculate_price_limits(stock_code, stock_name)
                if price_limits['limit_up'] > 0:
                    # 尝试解析价格文本
                    price = price_calc.parse_price_text(
                        price_text, 
                        price_limits['limit_up'], 
                        price_limits['limit_down']
                    )
                    if price is None:
                        yield MessageEventResult().message(f"❌ 无法解析价格参数: {price_text}\n支持格式: 数字价格、涨停、跌停")
                        return
                else:
                    # 如果无法计算涨跌停，尝试按数字解析
                    try:
                        price = float(price_text)
                    except ValueError:
                        yield MessageEventResult().message(f"❌ 无法解析价格参数: {price_text}")
                        return
            
            # 4. 交易确认（简化实现：默认确认）
            trade_type = "限价买入" if price else "市价买入"
            display_price = f"{price:.2f}元" if price else f"{stock_info.current_price:.2f}元(当前价)"
            
            confirmation_text = (
                f"📋 即将执行交易\n"
                f"股票: {stock_name} ({stock_code})\n"
                f"操作: {trade_type}\n" 
                f"数量: {volume}股\n"
                f"价格: {display_price}"
            )
            
            yield MessageEventResult().message(confirmation_text)
            
            # 4. 执行交易
            parsed = {
                'stock_code': stock_code,
                'volume': volume,
                'price': price,
                'error': None
            }
            
            success, message, order = await self.trading_engine.place_buy_order(
                user_id, 
                parsed['stock_code'], 
                parsed['volume'],
                parsed['price']
            )
            
            if success:
                yield MessageEventResult().message(f"✅ {message}")
            else:
                yield MessageEventResult().message(f"❌ {message}")
                
        except Exception as e:
            logger.error(f"买入操作失败: {e}")
            yield MessageEventResult().message("❌ 交易失败，请稍后重试")
    
    @command("限价买入")
    async def limit_buy_stock(self, event: AstrMessageEvent):
        """限价买入股票"""
        user_id = self._get_isolated_user_id(event)
        
        # 检查用户是否注册
        if not self.storage.get_user(user_id):
            yield MessageEventResult().message("❌ 您还未注册，请先使用 /股票注册 注册账户")
            return
        
        # 解析参数
        params = event.message_str.strip().split()[1:]
        if len(params) < 3:
            yield MessageEventResult().message("❌ 参数不足\n\n格式: /限价买入 股票代码/名称 数量 价格\n例: /限价买入 平安银行 1000 12.50\n    /限价买入 平安银行 1000 涨停")
            return
        
        keyword = params[0]
        try:
            volume = int(params[1])
            # 限价单必须提供价格参数，可能是数字或"涨停"/"跌停"文本
            price_text = params[2]
        except (ValueError, IndexError):
            yield MessageEventResult().message("❌ 参数格式错误\n\n格式: /限价买入 股票代码/名称 数量 价格\n例: /限价买入 平安银行 1000 12.50\n    /限价买入 平安银行 1000 涨停")
            return
        
        # 1. 股票搜索
        selected_stock = await self._search_and_select_stock(event, keyword)
        if not selected_stock:
            return
        
        stock_code = selected_stock['code']
        stock_name = selected_stock['name']
        
        # 2. 获取当前股价用于确认
        try:
            stock_info = await self.stock_service.get_stock_info(stock_code)
            if not stock_info:
                yield MessageEventResult().message(f"❌ 无法获取 {stock_name} 的实时数据")
                return
            
            # 3. 解析价格输入（支持涨停/跌停文本）
            from .utils.price_calculator import get_price_calculator
            price_calc = get_price_calculator(self.storage)
            
            # 计算当前时间的涨跌停价格
            price_limits = await price_calc.calculate_price_limits(stock_code, stock_name)
            if price_limits['limit_up'] > 0:
                # 尝试解析价格文本
                price = price_calc.parse_price_text(
                    price_text, 
                    price_limits['limit_up'], 
                    price_limits['limit_down']
                )
                if price is None:
                    yield MessageEventResult().message(f"❌ 无法解析价格参数: {price_text}\n支持格式: 数字价格、涨停、跌停")
                    return
            else:
                # 如果无法计算涨跌停，尝试按数字解析
                try:
                    price = float(price_text)
                except ValueError:
                    yield MessageEventResult().message(f"❌ 无法解析价格参数: {price_text}")
                    return
            
            # 4. 交易确认（简化实现：默认确认）
            trade_type = "限价买入"
            display_price = f"{price:.2f}元"
            
            confirmation_text = (
                f"📋 即将执行交易\n"
                f"股票: {stock_name} ({stock_code})\n"
                f"操作: {trade_type}\n" 
                f"数量: {volume}股\n"
                f"价格: {display_price}"
            )
            
            yield MessageEventResult().message(confirmation_text)
            
            # 5. 执行交易
            success, message, order = await self.trading_engine.place_buy_order(
                user_id, 
                stock_code, 
                volume,
                price
            )
            
            if success:
                yield MessageEventResult().message(f"✅ {message}")
            else:
                yield MessageEventResult().message(f"❌ {message}")
                
        except Exception as e:
            logger.error(f"买入操作失败: {e}")
            yield MessageEventResult().message("❌ 交易失败，请稍后重试")
    
    @command("卖出")
    async def market_sell_stock(self, event: AstrMessageEvent):
        """市价卖出股票"""
        user_id = self._get_isolated_user_id(event)
        
        # 检查用户是否注册
        if not self.storage.get_user(user_id):
            yield MessageEventResult().message("❌ 您还未注册，请先使用 /股票注册 注册账户")
            return
        
        # 解析参数
        params = event.message_str.strip().split()[1:]
        if len(params) < 2:
            yield MessageEventResult().message("❌ 参数不足\n\n格式: /卖出 股票代码/名称 数量\n例: /卖出 平安银行 500")
            return
        
        keyword = params[0]
        try:
            volume = int(params[1])
            # 市价单无需价格参数
            price_text = None
        except (ValueError, IndexError):
            yield MessageEventResult().message("❌ 参数格式错误\n\n格式: /卖出 股票代码/名称 数量\n例: /卖出 平安银行 500")
            return
        
        # 1. 股票搜索
        selected_stock = await self._search_and_select_stock(event, keyword)
        if not selected_stock:
            yield MessageEventResult().message(f"❌ 未找到相关股票: {keyword}")
            return
        
        stock_code = selected_stock['code']
        stock_name = selected_stock['name']
        
        # 2. 获取当前股价用于确认
        try:
            stock_info = await self.stock_service.get_stock_info(stock_code)
            if not stock_info:
                yield MessageEventResult().message(f"❌ 无法获取 {stock_name} 的实时数据")
                return
            
            # 3. 解析价格输入（支持涨停/跌停文本）
            price = None
            if price_text:
                from .utils.price_calculator import get_price_calculator
                price_calc = get_price_calculator(self.storage)
                
                # 计算当前时间的涨跌停价格
                price_limits = await price_calc.calculate_price_limits(stock_code, stock_name)
                if price_limits['limit_up'] > 0:
                    # 尝试解析价格文本
                    price = price_calc.parse_price_text(
                        price_text, 
                        price_limits['limit_up'], 
                        price_limits['limit_down']
                    )
                    if price is None:
                        yield MessageEventResult().message(f"❌ 无法解析价格参数: {price_text}\n支持格式: 数字价格、涨停、跌停")
                        return
                else:
                    # 如果无法计算涨跌停，尝试按数字解析
                    try:
                        price = float(price_text)
                    except ValueError:
                        yield MessageEventResult().message(f"❌ 无法解析价格参数: {price_text}")
                        return
            
            # 4. 交易确认（简化实现：默认确认）
            trade_type = "限价卖出" if price else "市价卖出"
            display_price = f"{price:.2f}元" if price else f"{stock_info.current_price:.2f}元(当前价)"
            
            confirmation_text = (
                f"📋 即将执行交易\n"
                f"股票: {stock_name} ({stock_code})\n"
                f"操作: {trade_type}\n"
                f"数量: {volume}股\n"
                f"价格: {display_price}"
            )
            
            yield MessageEventResult().message(confirmation_text)
            
            # 4. 执行交易
            parsed = {
                'stock_code': stock_code,
                'volume': volume,
                'price': price,
                'error': None
            }
            
            success, message, order = await self.trading_engine.place_sell_order(
                user_id,
                parsed['stock_code'],
                parsed['volume'],
                parsed['price']
            )
            
            if success:
                yield MessageEventResult().message(f"✅ {message}")
            else:
                yield MessageEventResult().message(f"❌ {message}")
                
        except Exception as e:
            logger.error(f"卖出操作失败: {e}")
            yield MessageEventResult().message("❌ 交易失败，请稍后重试")
    
    @command("限价卖出")
    async def limit_sell_stock(self, event: AstrMessageEvent):
        """限价卖出股票"""
        user_id = self._get_isolated_user_id(event)
        
        # 检查用户是否注册
        if not self.storage.get_user(user_id):
            yield MessageEventResult().message("❌ 您还未注册，请先使用 /股票注册 注册账户")
            return
        
        # 解析参数
        params = event.message_str.strip().split()[1:]
        if len(params) < 3:
            yield MessageEventResult().message("❌ 参数不足\n\n格式: /限价卖出 股票代码/名称 数量 价格\n例: /限价卖出 平安银行 500 13.00\n    /限价卖出 平安银行 500 跌停")
            return
        
        keyword = params[0]
        try:
            volume = int(params[1])
            # 限价单必须提供价格参数，可能是数字或"涨停"/"跌停"文本
            price_text = params[2]
        except (ValueError, IndexError):
            yield MessageEventResult().message("❌ 参数格式错误\n\n格式: /限价卖出 股票代码/名称 数量 价格\n例: /限价卖出 平安银行 500 13.00\n    /限价卖出 平安银行 500 跌停")
            return
        
        # 1. 股票搜索
        selected_stock = await self._search_and_select_stock(event, keyword)
        if not selected_stock:
            yield MessageEventResult().message(f"❌ 未找到相关股票: {keyword}")
            return
        
        stock_code = selected_stock['code']
        stock_name = selected_stock['name']
        
        # 2. 获取当前股价用于确认
        try:
            stock_info = await self.stock_service.get_stock_info(stock_code)
            if not stock_info:
                yield MessageEventResult().message(f"❌ 无法获取 {stock_name} 的实时数据")
                return
            
            # 3. 解析价格输入（支持涨停/跌停文本）
            from .utils.price_calculator import get_price_calculator
            price_calc = get_price_calculator(self.storage)
            
            # 计算当前时间的涨跌停价格
            price_limits = await price_calc.calculate_price_limits(stock_code, stock_name)
            if price_limits['limit_up'] > 0:
                # 尝试解析价格文本
                price = price_calc.parse_price_text(
                    price_text, 
                    price_limits['limit_up'], 
                    price_limits['limit_down']
                )
                if price is None:
                    yield MessageEventResult().message(f"❌ 无法解析价格参数: {price_text}\n支持格式: 数字价格、涨停、跌停")
                    return
            else:
                # 如果无法计算涨跌停，尝试按数字解析
                try:
                    price = float(price_text)
                except ValueError:
                    yield MessageEventResult().message(f"❌ 无法解析价格参数: {price_text}")
                    return
            
            # 4. 交易确认（简化实现：默认确认）
            trade_type = "限价卖出"
            display_price = f"{price:.2f}元"
            
            confirmation_text = (
                f"📋 即将执行交易\n"
                f"股票: {stock_name} ({stock_code})\n"
                f"操作: {trade_type}\n"
                f"数量: {volume}股\n"
                f"价格: {display_price}"
            )
            
            yield MessageEventResult().message(confirmation_text)
            
            # 5. 执行交易
            success, message, order = await self.trading_engine.place_sell_order(
                user_id,
                stock_code,
                volume,
                price
            )
            
            if success:
                yield MessageEventResult().message(f"✅ {message}")
            else:
                yield MessageEventResult().message(f"❌ {message}")
                
        except Exception as e:
            logger.error(f"卖出操作失败: {e}")
            yield MessageEventResult().message("❌ 交易失败，请稍后重试")
    
    @command("股票撤单")
    async def cancel_order(self, event: AstrMessageEvent):
        """撤销订单"""
        user_id = self._get_isolated_user_id(event)
        params = event.message_str.strip().split()[1:]
        
        if not params:
            yield MessageEventResult().message("❌ 请提供订单号\n格式: /股票撤单 订单号")
            return
        
        order_id = params[0]
        
        try:
            success, message = await self.trading_engine.cancel_order(user_id, order_id)
            
            if success:
                yield MessageEventResult().message(f"✅ {message}")
            else:
                yield MessageEventResult().message(f"❌ {message}")
                
        except Exception as e:
            logger.error(f"撤单操作失败: {e}")
            yield MessageEventResult().message("❌ 撤单失败，请稍后重试")

    # ==================== 查询相关 ====================
    
    @command("股票账户")
    async def show_account_info(self, event: AstrMessageEvent):
        """显示账户信息（合并持仓、余额、订单查询）"""
        user_id = self._get_isolated_user_id(event)
        
        # 检查用户是否注册
        user_data = self.storage.get_user(user_id)
        if not user_data:
            yield MessageEventResult().message("❌ 您还未注册，请先使用 /股票注册 注册账户")
            return
        
        try:
            # 更新用户总资产
            await self.trading_engine.update_user_assets(user_id)
            
            # 获取最新用户数据
            user_data = self.storage.get_user(user_id)
            user = User.from_dict(user_data)
            
            # 获取持仓数据
            positions = self.storage.get_positions(user_id)
            
            # 更新持仓市值
            for pos_data in positions:
                if pos_data['total_volume'] > 0:
                    stock_info = await self.stock_service.get_stock_info(pos_data['stock_code'])
                    if stock_info:
                        from .models.position import Position
                        position = Position.from_dict(pos_data)
                        position.update_market_data(stock_info.current_price)
                        self.storage.save_position(user_id, position.stock_code, position.to_dict())
                        pos_data.update(position.to_dict())
            
            # 获取冻结资金
            frozen_funds = self.storage.calculate_frozen_funds(user_id)
            
            # 格式化输出
            info_text = Formatters.format_user_info(user.to_dict(), positions, frozen_funds)
            
            # 添加待成交订单信息
            pending_orders = [order for order in self.storage.get_orders(user_id) if order.get('status') == 'pending']
            if pending_orders:
                info_text += "\n\n" + Formatters.format_pending_orders(pending_orders)
            
            yield MessageEventResult().message(info_text)
            
        except Exception as e:
            logger.error(f"查询账户信息失败: {e}")
            yield MessageEventResult().message("❌ 查询失败，请稍后重试")
    
    @command("股价")
    async def show_stock_price(self, event: AstrMessageEvent):
        """查询股价（支持模糊搜索）"""
        params = event.message_str.strip().split()[1:]
        
        if not params:
            yield MessageEventResult().message("❌ 请提供股票代码或名称\n格式: /股价 股票代码/名称\n例: /股价 000001 或 /股价 平安银行")
            return
        
        keyword = params[0]
        
        # 先尝试精确匹配（如果是6位数字代码）
        if keyword.isdigit() and len(keyword) == 6:
            stock_code = Validators.normalize_stock_code(keyword)
            if stock_code:
                try:
                    stock_info = await self.stock_service.get_stock_info(stock_code)
                    if stock_info:
                        info_text = Formatters.format_stock_info(stock_info.to_dict())
                        yield MessageEventResult().message(info_text)
                        return
                except Exception:
                    pass
        
        # 模糊搜索
        try:
            candidates = await self.stock_service.search_stocks_fuzzy(keyword)
            
            if not candidates:
                yield MessageEventResult().message(f"❌ 未找到相关股票: {keyword}\n请尝试使用股票代码或准确的股票名称")
                return
            
            if len(candidates) == 1:
                # 只有一个候选，直接查询
                stock_code = candidates[0]['code']
                stock_info = await self.stock_service.get_stock_info(stock_code)
                if stock_info:
                    info_text = Formatters.format_stock_info(stock_info.to_dict())
                    yield MessageEventResult().message(info_text)
                else:
                    yield MessageEventResult().message(f"❌ 无法获取股票信息")
            else:
                # 多个候选，让用户选择
                selection_text = f"🔍 找到多个相关股票，请选择:\n\n"
                for i, candidate in enumerate(candidates, 1):
                    selection_text += f"{i}. {candidate['name']} ({candidate['code']}) [{candidate['market']}]\n"
                selection_text += f"\n💡 请回复数字 1-{len(candidates)} 选择股票"
                
                yield MessageEventResult().message(selection_text)
                
                # 等待用户选择
                selected_stock = await self._wait_for_stock_selection(event, candidates, "股价查询")
                if selected_stock:
                    stock_info = await self.stock_service.get_stock_info(selected_stock['code'])
                    if stock_info:
                        info_text = Formatters.format_stock_info(stock_info.to_dict())
                        yield MessageEventResult().message(info_text)
                    else:
                        yield MessageEventResult().message(f"❌ 无法获取股票信息")
                        
        except Exception as e:
            logger.error(f"查询股价失败: {e}")
            yield MessageEventResult().message("❌ 查询失败，请稍后重试")
    
    @command("股票排行")
    async def show_ranking(self, event: AstrMessageEvent):
        """显示群内排行榜"""
        try:
            # 获取当前会话的标识，用于过滤同群用户
            platform_name = event.get_platform_name()
            session_id = event.get_session_id()
            session_prefix = f"{platform_name}:"
            session_suffix = f":{session_id}"
            
            all_users_data = self.storage.get_all_users()
            users_list = []
            
            for user_id, user_data in all_users_data.items():
                # 只包含相同会话（群聊）的用户
                if user_id.startswith(session_prefix) and user_id.endswith(session_suffix):
                    # 更新用户总资产
                    await self.trading_engine.update_user_assets(user_id)
                    updated_user_data = self.storage.get_user(user_id)
                    if updated_user_data:
                        users_list.append(updated_user_data)
            
            current_user_id = self._get_isolated_user_id(event)
            
            if not users_list:
                yield MessageEventResult().message("📊 当前群聊暂无用户排行数据\n请先使用 /股票注册 注册账户")
                return
            
            ranking_text = Formatters.format_ranking(users_list, current_user_id)
            yield MessageEventResult().message(ranking_text)
            
        except Exception as e:
            logger.error(f"查询排行榜失败: {e}")
            yield MessageEventResult().message("❌ 查询失败，请稍后重试")
    
    @command("历史订单")
    async def show_order_history(self, event: AstrMessageEvent):
        """显示历史订单"""
        user_id = self._get_isolated_user_id(event)
        
        # 检查用户是否注册
        if not self.storage.get_user(user_id):
            yield MessageEventResult().message("❌ 您还未注册，请先使用 /股票注册 注册账户")
            return
        
        # 解析页码参数
        params = event.message_str.strip().split()[1:]
        page = 1
        if params:
            try:
                page = int(params[0])
                if page < 1:
                    page = 1
            except ValueError:
                yield MessageEventResult().message("❌ 页码格式错误\n\n格式: /历史订单 [页码]\n例: /历史订单 1")
                return
        
        try:
            # 获取历史订单
            history_data = self.storage.get_user_order_history(user_id, page)
            
            # 格式化输出
            history_text = Formatters.format_order_history(history_data)
            yield MessageEventResult().message(history_text)
            
        except Exception as e:
            logger.error(f"查询历史订单失败: {e}")
            yield MessageEventResult().message("❌ 查询失败，请稍后重试")

    # ==================== 帮助信息 ====================
    
    @command("股票帮助")
    async def show_help(self, event: AstrMessageEvent):
        """显示帮助信息"""
        help_text = Formatters.format_help_message()
        yield MessageEventResult().message(help_text)

    # ==================== 插件生命周期 ====================
    
    async def terminate(self):
        """插件销毁"""
        try:
            # 停止挂单监控
            await self.order_monitor.stop_monitoring()
            logger.info("A股模拟交易插件已停止")
        except Exception as e:
            logger.error(f"插件停止时出错: {e}")
