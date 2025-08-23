"""格式化工具"""
from typing import List, Dict, Any
from datetime import datetime
import time


class Formatters:
    """格式化工具类"""
    
    @staticmethod
    def format_currency(amount: float, precision: int = 2) -> str:
        """格式化货币金额"""
        if amount >= 100000000:  # 1亿
            return f"{amount/100000000:.2f}亿"
        elif amount >= 10000:     # 1万
            return f"{amount/10000:.2f}万"
        else:
            return f"{amount:.{precision}f}"
    
    @staticmethod
    def format_percentage(value: float, precision: int = 2) -> str:
        """格式化百分比"""
        return f"{value:.{precision}f}%"
    
    @staticmethod
    def format_timestamp(timestamp: int) -> str:
        """格式化时间戳"""
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
    
    @staticmethod
    def format_stock_info(stock_info: Dict[str, Any]) -> str:
        """格式化股票信息"""
        lines = [
            f"📈 {stock_info['name']} ({stock_info['code']})",
            f"💰 当前价: {stock_info['current_price']:.2f}元",
            f"📊 涨跌: {stock_info['change_amount']:+.2f} ({stock_info['change_percent']:+.2f}%)",
            f"📈 最高: {stock_info['high_price']:.2f} 📉 最低: {stock_info['low_price']:.2f}",
            f"💰 成交额: {Formatters.format_currency(stock_info['turnover'])}元"
        ]
        
        if stock_info.get('is_suspended'):
            lines.append("⏸️ 状态: 停牌")
        
        return "\n".join(lines)
    
    @staticmethod
    def format_user_info(user: Dict[str, Any], positions: List[Dict[str, Any]]) -> str:
        """格式化用户信息（合并持仓、余额、订单查询）"""
        lines = [
            f"👤 账户信息",
            f"💰 可用余额: {Formatters.format_currency(user['balance'])}元",
            f"💎 总资产: {Formatters.format_currency(user['total_assets'])}元"
        ]
        
        if positions:
            lines.append("\n📊 持仓详情:")
            total_market_value = 0
            total_profit_loss = 0
            
            for pos in positions:
                if pos['total_volume'] > 0:
                    profit_color = "🟢" if pos['profit_loss'] >= 0 else "🔴"
                    lines.append(
                        f"{profit_color} {pos['stock_name']}({pos['stock_code']})\n"
                        f"   数量: {pos['total_volume']}股 (可卖: {pos['available_volume']}股)\n"
                        f"   成本: {pos['avg_cost']:.2f}元 现价: {pos['last_price']:.2f}元\n"
                        f"   市值: {Formatters.format_currency(pos['market_value'])}元\n"
                        f"   盈亏: {pos['profit_loss']:+.2f}元 ({pos['profit_loss_percent']:+.2f}%)"
                    )
                    total_market_value += pos['market_value']
                    total_profit_loss += pos['profit_loss']
            
            lines.append(f"\n💼 持仓市值: {Formatters.format_currency(total_market_value)}元")
            profit_color = "🟢" if total_profit_loss >= 0 else "🔴"
            lines.append(f"{profit_color} 总盈亏: {total_profit_loss:+.2f}元")
        else:
            lines.append("\n📊 暂无持仓")
        
        return "\n".join(lines)
    
    @staticmethod
    def format_order_info(order: Dict[str, Any]) -> str:
        """格式化订单信息"""
        order_type_icon = "🟢" if order['order_type'] == 'buy' else "🔴"
        status_icons = {
            'pending': '⏳',
            'filled': '✅',
            'cancelled': '❌',
            'partial': '🔄'
        }
        status_icon = status_icons.get(order['status'], '❓')
        
        lines = [
            f"{order_type_icon} {order['stock_name']}({order['stock_code']})",
            f"{status_icon} 状态: {order['status']}",
            f"💰 价格: {order['order_price']:.2f}元",
            f"📊 数量: {order['order_volume']}股"
        ]
        
        if order['filled_volume'] > 0:
            lines.append(f"✅ 已成交: {order['filled_volume']}股")
        
        lines.append(f"⏰ 时间: {Formatters.format_timestamp(order['create_time'])}")
        
        return "\n".join(lines)
    
    @staticmethod
    def format_pending_orders(orders: List[Dict[str, Any]]) -> str:
        """格式化待成交订单列表"""
        if not orders:
            return "📋 暂无待成交订单"
        
        lines = ["📋 待成交订单:"]
        for i, order in enumerate(orders, 1):
            order_type_icon = "🟢买入" if order['order_type'] == 'buy' else "🔴卖出"
            lines.append(
                f"{i}. {order_type_icon} {order['stock_name']}({order['stock_code']})\n"
                f"   价格: {order['order_price']:.2f}元 数量: {order['order_volume']}股\n"
                f"   订单号: {order['order_id'][:8]}..."
            )
        
        return "\n".join(lines)
    
    @staticmethod
    def format_ranking(users_data: List[Dict[str, Any]], current_user_id: str = None) -> str:
        """格式化排行榜"""
        if not users_data:
            return "📊 暂无排行数据"
        
        # 按总资产排序
        sorted_users = sorted(users_data, key=lambda x: x.get('total_assets', 0), reverse=True)
        
        lines = ["🏆 群内排行榜 (按总资产):"]
        
        for i, user in enumerate(sorted_users[:10], 1):  # 显示前10名
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            profit_loss = user.get('total_assets', 0) - 1000000  # 减去初始资金
            profit_color = "🟢" if profit_loss >= 0 else "🔴"
            
            # 标记当前用户
            name_marker = "👑" if user.get('user_id') == current_user_id else ""
            
            lines.append(
                f"{medal} {user.get('username', '匿名用户')}{name_marker}\n"
                f"   💎 总资产: {Formatters.format_currency(user.get('total_assets', 0))}元\n"
                f"   {profit_color} 盈亏: {profit_loss:+.2f}元"
            )
        
        return "\n".join(lines)
    
    @staticmethod
    def format_help_message() -> str:
        """格式化帮助信息"""
        return """📖 papertrading 插件说明

🎯 基础指令:
/股票注册 - 注册交易账户(初始资金100万)
/股价 代码 - 查询股票实时价格

💰 交易指令:
/股票买入 代码 数量 [价格] - 买入股票
  例: /股票买入 000001 1000 (市价买入)
  例: /股票买入 000001 1000 12.50 (限价买入)

/股票卖出 代码 数量 [价格] - 卖出股票
  例: /股票卖出 000001 500 (市价卖出)
  例: /股票卖出 000001 500 13.00 (限价卖出)

/股票撤单 订单号 - 撤销挂单

📊 查询指令:
/股票账户 - 查看余额、持仓、订单
/股票排行 - 查看群内排行榜

⚠️ 交易规则:
• 最小交易单位: 100股（1手）
• T+1制度: 当日买入次日才能卖出
• 涨跌停限制
• 停牌股票无法交易
• 手续费: 0.03%(最低5元)"""
