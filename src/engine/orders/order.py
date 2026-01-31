from __future__ import annotations
from engine.enums import OrderType, Side, StrategyType


class Order:
    def __init__(self, order_dict: dict) :
        """
        Initialize an Order with a dictionary containing all order fields.

        Args:
            order_dict: Dictionary containing all order fields from the Orders table
        """
        self._order_dict = order_dict

        # Initialize executed_quantity if not present
        if "executed_quantity" not in self._order_dict:
            self._order_dict["executed_quantity"] = 0.0

        # Track fills for average price calculation
        self._fills = []  # List of (quantity, price) tuples

    def __getattr__(self, name: str):
        """Proxy attribute access to the underlying order dictionary."""
        if name.startswith("_"):
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

        # Map common attribute names to dictionary keys
        attr_map = {
            "id": "order_id",
            "user_id": "user_id",
            "strategy_type": "strategy_type",
            "order_type": "order_type",
            "side": "side",
            "quantity": "quantity",
            "executed_quantity": "executed_quantity",
            "price": "limit_price" if self._order_dict['order_type'] == OrderType.LIMIT else 'stop_price',
            "limit_price": "limit_price",
            "stop_price": "stop_price",
            "avg_fill_price": "avg_fill_price",
        }

        dict_key = attr_map.get(name, name)

        if dict_key in self._order_dict:
            value = self._order_dict[dict_key]

            if dict_key == "strategy_type":
                return StrategyType(value)
            elif dict_key == "order_type":
                return OrderType(value)
            elif dict_key == "side":
                return Side(value)
            return value

        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    def __setattr__(self, name: str, value):
        """Proxy attribute setting to the underlying order dictionary."""
        if name.startswith("_"):
            super().__setattr__(name, value)
            return

        # Map common attribute names to dictionary keys
        attr_map = {
            "id": "order_id",
            "executed_quantity": "executed_quantity",
            "avg_fill_price": "avg_fill_price",
        }

        dict_key = attr_map.get(name, name)
        self._order_dict[dict_key] = value

    @property
    def price(self) -> float:
        """Get the effective price based on order type."""
        order_type = self._order_dict['order_type']
        
        if order_type == OrderType.LIMIT:
            return self._order_dict.get("limit_price")
        elif order_type == OrderType.STOP:
            return self._order_dict.get("stop_price")
        
        raise NotImplementedError(f"Price field for order type '{order_type}' not implemented.")

    def add_fill(self, quantity: float, price: float):
        """Track a fill for average price calculation."""
        self._fills.append((quantity, price))
        self._order_dict["executed_quantity"] = self._order_dict.get("executed_quantity", 0.0) + quantity
        self._calculate_avg_fill_price()

    def _calculate_avg_fill_price(self):
        """Calculate weighted average fill price."""
        if not self._fills:
            self._order_dict["avg_fill_price"] = None
            return

        total_value = sum(qty * price for qty, price in self._fills)
        total_quantity = sum(qty for qty, _ in self._fills)

        if total_quantity > 0:
            self._order_dict["avg_fill_price"] = total_value / total_quantity
        else:
            self._order_dict["avg_fill_price"] = None

    def get_order_dict(self) -> dict:
        """Return the full order dictionary."""
        return self._order_dict.copy()

    def to_dict(self) -> dict:
        """Legacy method for compatibility."""
        result = {}
        result['order_dict'] = self._order_dict.copy()
        result["type"] = self.__class__.__name__
        return result

    @classmethod
    def from_dict(cls, data: dict) -> Order:
        """Create an Order from a dictionary."""
        return cls(order_dict=data['order_dict'])
