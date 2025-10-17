"""交易表情包反应工具"""
import random


class TradingReactions:
    """交易表情包反应类"""
    
    # 盈利反应
    PROFIT_REACTIONS = {
        'huge_profit': [  # 大赚 >= 10%
            "🚀 哇！{stock_name} 让你大赚 {profit_amount:.2f}元！{profit_rate:.1%}的收益，你是股神吗？",
            "💰 太棒了！{stock_name} 大赚 {profit_amount:.2f}元！{profit_rate:.1%}的收益，继续加油！",
            "🎉 恭喜！{stock_name} 让你赚了 {profit_amount:.2f}元！{profit_rate:.1%}的收益，太厉害了！",
            "🔥 厉害！{stock_name} 大赚 {profit_amount:.2f}元！{profit_rate:.1%}的收益，股神附体！"
        ],
        'big_profit': [  # 大赚 >= 5%
            "💰 不错！{stock_name} 让你赚了 {profit_amount:.2f}元！{profit_rate:.1%}的收益，继续加油！",
            "😊 很好！{stock_name} 小赚 {profit_amount:.2f}元！{profit_rate:.1%}的收益，不错不错！",
            "👍 棒！{stock_name} 赚了 {profit_amount:.2f}元！{profit_rate:.1%}的收益，继续努力！",
            "💪 不错！{stock_name} 让你赚了 {profit_amount:.2f}元！{profit_rate:.1%}的收益，加油！"
        ],
        'small_profit': [  # 小赚 >= 0%
            "😊 小赚 {profit_amount:.2f}元！{profit_rate:.1%}的收益，积少成多！",
            "👍 不错！{stock_name} 小赚 {profit_amount:.2f}元！{profit_rate:.1%}的收益！",
            "💪 加油！{stock_name} 小赚 {profit_amount:.2f}元！{profit_rate:.1%}的收益！",
            "😄 小赚 {profit_amount:.2f}元！{profit_rate:.1%}的收益，慢慢来！"
        ],
        'small_loss': [  # 小亏 >= -5%
            "😅 小亏 {loss_amount:.2f}元，{loss_rate:.1%}的损失，下次会更好！",
            "🤷 没事！{stock_name} 小亏 {loss_amount:.2f}元，{loss_rate:.1%}的损失，继续加油！",
            "💭 小亏 {loss_amount:.2f}元，{loss_rate:.1%}的损失，总结经验！",
            "😊 小亏 {loss_amount:.2f}元，{loss_rate:.1%}的损失，下次会更好！"
        ],
        'medium_loss': [  # 中亏 >= -10%
            "😔 亏了 {loss_amount:.2f}元，{loss_rate:.1%}的损失，稳住！",
            "😢 没事！{stock_name} 亏了 {loss_amount:.2f}元，{loss_rate:.1%}的损失，继续努力！",
            "💔 亏了 {loss_amount:.2f}元，{loss_rate:.1%}的损失，总结经验！",
            "😞 亏了 {loss_amount:.2f}元，{loss_rate:.1%}的损失，下次会更好！"
        ],
        'big_loss': [  # 大亏 < -10%
            "😱 大亏 {loss_amount:.2f}元，{loss_rate:.1%}的损失，要冷静啊！",
            "😭 哎呀！{stock_name} 大亏 {loss_amount:.2f}元，{loss_rate:.1%}的损失，稳住！",
            "💸 大亏 {loss_amount:.2f}元，{loss_rate:.1%}的损失，要冷静！",
            "😵 大亏 {loss_amount:.2f}元，{loss_rate:.1%}的损失，总结经验！"
        ]
    }
    
    # 买入反应
    BUY_REACTIONS = [
        "🎯 买入 {stock_name} {volume}股，价格 {price:.2f}元，期待上涨！",
        "📈 买入 {stock_name} {volume}股，价格 {price:.2f}元，看好后市！",
        "💎 买入 {stock_name} {volume}股，价格 {price:.2f}元，价值投资！",
        "🚀 买入 {stock_name} {volume}股，价格 {price:.2f}元，冲冲冲！"
    ]
    
    # 卖出反应
    SELL_REACTIONS = [
        "💰 卖出 {stock_name} {volume}股，价格 {price:.2f}元，落袋为安！",
        "📉 卖出 {stock_name} {volume}股，价格 {price:.2f}元，及时止损！",
        "🎯 卖出 {stock_name} {volume}股，价格 {price:.2f}元，见好就收！",
        "💸 卖出 {stock_name} {volume}股，价格 {price:.2f}元，获利了结！"
    ]
    
    @staticmethod
    def get_profit_reaction(profit_rate: float, profit_amount: float, stock_name: str) -> str:
        """根据盈亏情况生成反应"""
        if profit_rate >= 0.1:
            reactions = TradingReactions.PROFIT_REACTIONS['huge_profit']
        elif profit_rate >= 0.05:
            reactions = TradingReactions.PROFIT_REACTIONS['big_profit']
        elif profit_rate >= 0:
            reactions = TradingReactions.PROFIT_REACTIONS['small_profit']
        elif profit_rate >= -0.05:
            reactions = TradingReactions.PROFIT_REACTIONS['small_loss']
        elif profit_rate >= -0.1:
            reactions = TradingReactions.PROFIT_REACTIONS['medium_loss']
        else:
            reactions = TradingReactions.PROFIT_REACTIONS['big_loss']
        
        # 随机选择一个反应
        template = random.choice(reactions)
        
        if profit_rate >= 0:
            return template.format(
                stock_name=stock_name,
                profit_amount=profit_amount,
                profit_rate=profit_rate
            )
        else:
            return template.format(
                stock_name=stock_name,
                loss_amount=abs(profit_amount),
                loss_rate=abs(profit_rate)
            )
    
    @staticmethod
    def get_buy_reaction(stock_name: str, volume: int, price: float) -> str:
        """获取买入反应"""
        template = random.choice(TradingReactions.BUY_REACTIONS)
        return template.format(
            stock_name=stock_name,
            volume=volume,
            price=price
        )
    
    @staticmethod
    def get_sell_reaction(stock_name: str, volume: int, price: float) -> str:
        """获取卖出反应"""
        template = random.choice(TradingReactions.SELL_REACTIONS)
        return template.format(
            stock_name=stock_name,
            volume=volume,
            price=price
        )
    
    @staticmethod
    def get_trading_emoji(profit_rate: float) -> str:
        """获取交易表情"""
        if profit_rate >= 0.1:
            return "🚀💰🎉"
        elif profit_rate >= 0.05:
            return "💰😊"
        elif profit_rate >= 0:
            return "😊👍"
        elif profit_rate >= -0.05:
            return "😅🤷"
        elif profit_rate >= -0.1:
            return "😔💔"
        else:
            return "😱💸"
