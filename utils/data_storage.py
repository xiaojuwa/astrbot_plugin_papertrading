"""数据存储工具"""
import json
import os
from typing import Dict, Any, List, Optional
from pathlib import Path
from astrbot.api.star import StarTools
from astrbot.api import logger


class DataStorage:
    """数据存储管理器"""
    
    def __init__(self, plugin_name: str = "papertrading"):
        """初始化数据存储"""
        self.plugin_name = plugin_name
        self.data_dir = StarTools.get_data_dir(plugin_name)
        self._ensure_data_structure()
    
    def _ensure_data_structure(self):
        """确保数据目录结构存在"""
        # 创建必要的数据文件
        files = {
            'users.json': {},
            'orders.json': {},
            'positions.json': {},
            'market_data_cache.json': {},
            'config.json': {
                'initial_balance': 1000000,  # 初始资金100万
                'commission_rate': 0.0003,   # 手续费率0.03%
                'min_commission': 5,         # 最小手续费5元
                'market_hours': {
                    'morning': {'start': '09:30', 'end': '11:30'},
                    'afternoon': {'start': '13:00', 'end': '15:00'}
                },
                'monitor_interval': 15       # 监控间隔15秒
            }
        }
        
        for filename, default_data in files.items():
            file_path = self.data_dir / filename
            if not file_path.exists():
                self._save_json(filename, default_data)
    
    def _get_file_path(self, filename: str) -> Path:
        """获取文件路径"""
        return self.data_dir / filename
    
    def _load_json(self, filename: str) -> Dict[str, Any]:
        """加载JSON文件"""
        file_path = self._get_file_path(filename)
        try:
            if file_path.exists():
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.error(f"加载文件失败 {filename}: {e}")
            return {}
    
    def _save_json(self, filename: str, data: Dict[str, Any]):
        """保存JSON文件"""
        file_path = self._get_file_path(filename)
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存文件失败 {filename}: {e}")
    
    # 用户数据操作
    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """获取用户数据"""
        users = self._load_json('users.json')
        return users.get(user_id)
    
    def save_user(self, user_id: str, user_data: Dict[str, Any]):
        """保存用户数据"""
        users = self._load_json('users.json')
        users[user_id] = user_data
        self._save_json('users.json', users)
    
    def get_all_users(self) -> Dict[str, Any]:
        """获取所有用户数据"""
        return self._load_json('users.json')
    
    def delete_user(self, user_id: str):
        """删除用户数据"""
        users = self._load_json('users.json')
        if user_id in users:
            del users[user_id]
            self._save_json('users.json', users)
    
    # 订单数据操作
    def get_orders(self, user_id: str = None) -> List[Dict[str, Any]]:
        """获取订单数据"""
        orders = self._load_json('orders.json')
        if user_id:
            return [order for order in orders.values() if order.get('user_id') == user_id]
        return list(orders.values())
    
    def save_order(self, order_id: str, order_data: Dict[str, Any]):
        """保存订单数据"""
        orders = self._load_json('orders.json')
        orders[order_id] = order_data
        self._save_json('orders.json', orders)
    
    def get_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        """获取单个订单"""
        orders = self._load_json('orders.json')
        return orders.get(order_id)
    
    def delete_order(self, order_id: str):
        """删除订单"""
        orders = self._load_json('orders.json')
        if order_id in orders:
            del orders[order_id]
            self._save_json('orders.json', orders)
    
    def get_pending_orders(self) -> List[Dict[str, Any]]:
        """获取所有待成交订单"""
        orders = self._load_json('orders.json')
        return [order for order in orders.values() if order.get('status') == 'pending']
    
    # 持仓数据操作
    def get_positions(self, user_id: str) -> List[Dict[str, Any]]:
        """获取用户持仓"""
        positions = self._load_json('positions.json')
        user_positions = positions.get(user_id, {})
        return list(user_positions.values())
    
    def save_position(self, user_id: str, stock_code: str, position_data: Dict[str, Any]):
        """保存持仓数据"""
        positions = self._load_json('positions.json')
        if user_id not in positions:
            positions[user_id] = {}
        positions[user_id][stock_code] = position_data
        self._save_json('positions.json', positions)
    
    def get_position(self, user_id: str, stock_code: str) -> Optional[Dict[str, Any]]:
        """获取单个持仓"""
        positions = self._load_json('positions.json')
        return positions.get(user_id, {}).get(stock_code)
    
    def delete_position(self, user_id: str, stock_code: str):
        """删除持仓"""
        positions = self._load_json('positions.json')
        if user_id in positions and stock_code in positions[user_id]:
            del positions[user_id][stock_code]
            if not positions[user_id]:  # 如果用户没有任何持仓，删除用户条目
                del positions[user_id]
            self._save_json('positions.json', positions)
    
    # 市场数据缓存操作
    def get_market_cache(self, stock_code: str) -> Optional[Dict[str, Any]]:
        """获取市场数据缓存"""
        cache = self._load_json('market_data_cache.json')
        return cache.get(stock_code)
    
    def save_market_cache(self, stock_code: str, market_data: Dict[str, Any]):
        """保存市场数据缓存"""
        cache = self._load_json('market_data_cache.json')
        cache[stock_code] = market_data
        self._save_json('market_data_cache.json', cache)
    
    def clear_market_cache(self):
        """清空市场数据缓存"""
        self._save_json('market_data_cache.json', {})
    
    # 配置操作
    def get_config(self) -> Dict[str, Any]:
        """获取配置"""
        return self._load_json('config.json')
    
    def save_config(self, config: Dict[str, Any]):
        """保存配置"""
        self._save_json('config.json', config)
    
    def get_config_value(self, key: str, default=None):
        """获取配置值"""
        config = self.get_config()
        return config.get(key, default)
