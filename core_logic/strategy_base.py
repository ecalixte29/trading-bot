from abc import ABC, abstractmethod
import pandas as pd

class StrategyBase(ABC):
    """
    Abstract base class for all trading strategies.
    """

    def __init__(self, strategy_name: str, config: dict = None):
        """
        Initialize the strategy.

        Args:
            strategy_name (str): Name of the strategy.
            config (dict, optional): Strategy-specific configuration. Defaults to None.
        """
        self.strategy_name = strategy_name
        self.config = config if config is not None else {}

    @abstractmethod
    def generate_signals(self, market_data: pd.DataFrame) -> pd.DataFrame:
        """
        Generate trading signals based on market data.

        Args:
            market_data (pd.DataFrame): DataFrame containing market data (e.g., OHLCV, indicators).
                                         The DataFrame should be indexed by timestamp.

        Returns:
            pd.DataFrame: DataFrame with signals (e.g., 'buy', 'sell', 'hold') and any other
                          relevant information for decision making. Should also be indexed by timestamp.
        """
        pass

    @abstractmethod
    def define_orders(self, signals: pd.DataFrame, current_positions: dict, account_balance: float, **kwargs) -> list:
        """
        Define orders to be placed based on generated signals and current account status.

        Args:
            signals (pd.DataFrame): DataFrame containing the latest signals from generate_signals.
            current_positions (dict): Dictionary representing current holdings.
                                      Example: {'AAPL_20231215_C150': 10, 'MSFT_20231215_P250': -5}
            account_balance (float): Current available cash in the trading account.
            **kwargs: Additional keyword arguments that strategies might need, e.g., options_chain_data.

        Returns:
            list: A list of order objects or dictionaries to be executed by the broker integration.
                  Each order should specify symbol, type (market, limit), side (buy, sell), quantity, etc.
        """
        pass

    def update_config(self, new_config: dict):
        """
        Update the strategy's configuration.
        """
        self.config.update(new_config)
        print(f"Strategy {self.strategy_name} config updated.")

    def __str__(self):
        return f"Strategy(name='{self.strategy_name}', config={self.config})" 