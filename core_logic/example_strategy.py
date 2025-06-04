import pandas as pd
from .strategy_base import StrategyBase

class ExampleStrategy(StrategyBase):
    """
    An example trading strategy based on a simple moving average crossover.
    """

    def __init__(self, config: dict = None):
        super().__init__(strategy_name="ExampleMovingAverageCrossover", config=config)
        # Default configuration, can be overridden by the config dict
        self.default_config = {
            'short_window': 20,
            'long_window': 50,
            'ticker': 'SPY' # Default ticker, should be configurable
        }
        self.config = {**self.default_config, **self.config} # Merge default and provided config

    def generate_signals(self, market_data: pd.DataFrame) -> pd.DataFrame:
        """
        Generate trading signals based on a moving average crossover.

        Args:
            market_data (pd.DataFrame): DataFrame with a 'close' price column, indexed by timestamp.

        Returns:
            pd.DataFrame: DataFrame with 'signal' (1 for buy, -1 for sell, 0 for hold) and moving averages.
        """
        signals = pd.DataFrame(index=market_data.index)
        signals['signal'] = 0.0

        if 'close' not in market_data.columns:
            print("Error: 'close' column not found in market_data for ExampleStrategy")
            return signals # Return empty signals if data is not as expected

        # Calculate short and long moving averages
        short_mavg = market_data['close'].rolling(window=self.config['short_window'], min_periods=1, center=False).mean()
        long_mavg = market_data['close'].rolling(window=self.config['long_window'], min_periods=1, center=False).mean()

        signals['short_mavg'] = short_mavg
        signals['long_mavg'] = long_mavg

        # Generate signal: 1 when short_mavg > long_mavg, -1 when short_mavg < long_mavg
        # Taking the difference and then the sign handles the crossover
        signals['signal'][self.config['short_window']:] = \
            (short_mavg[self.config['short_window']:] > long_mavg[self.config['short_window':]]).astype(int) * 2 - 1
        
        # Create trading orders (buy/sell) based on the crossover points
        # A buy signal is generated when the short MA crosses above the long MA
        # A sell signal is generated when the short MA crosses below the long MA
        signals['positions'] = signals['signal'].diff()

        # For simplicity, we will just use the last signal to decide action
        # In a real scenario, you'd consider current holdings, risk management, etc.
        # print(f"Generated signals for {self.config['ticker']}:")
        # print(signals.tail())
        return signals

    def define_orders(self, signals: pd.DataFrame, current_positions: dict, account_balance: float) -> list:
        """
        Define orders based on the latest signal.
        This is a very simplistic implementation for demonstration.
        A real implementation would involve option selection, strike/expiry determination, risk management etc.
        """
        orders = []
        latest_signal = signals.iloc[-1]
        ticker_symbol = self.config['ticker'] # This would be the underlying for options

        # Example: if latest signal is a buy (positions == 1 or 2 for stronger signal)
        if latest_signal['positions'] > 0: # Buy signal
            # This is where you would construct an options order.
            # For now, let's simulate buying 1 contract of a call option.
            # We need to decide on strike, expiry, etc. based on the strategy.
            order = {
                'symbol': f"{ticker_symbol}_CALL_EXAMPLE", # Placeholder options symbol
                'type': 'market',
                'side': 'buy_to_open',
                'quantity': 1,
                'tag': self.strategy_name
            }
            orders.append(order)
            print(f"{self.strategy_name}: BUY signal for {ticker_symbol}. Order: {order}")

        elif latest_signal['positions'] < 0: # Sell signal
            # This could be selling a call (if held) or buying a put.
            # For simplicity, let's simulate selling 1 contract of a call option (if we had one).
            # Or, buying a put if the strategy dictates.
            # Example: Assuming we want to buy a put.
            order = {
                'symbol': f"{ticker_symbol}_PUT_EXAMPLE", # Placeholder options symbol
                'type': 'market',
                'side': 'buy_to_open',
                'quantity': 1,
                'tag': self.strategy_name
            }
            orders.append(order)
            print(f"{self.strategy_name}: SELL signal for {ticker_symbol} (interpreted as buy put). Order: {order}")
        else:
            print(f"{self.strategy_name}: HOLD signal for {ticker_symbol}.")

        # More sophisticated logic: check current_positions, account_balance, risk limits
        # Example: if current_positions.get(f"{ticker_symbol}_CALL_EXAMPLE", 0) > 0 and latest_signal['positions'] < 0:
        #    # We have a call and a sell signal, so create an order to sell the call
        #    pass 

        return orders

if __name__ == '__main__':
    # Example Usage (for testing)
    # Create dummy market data
    data = {
        'timestamp': pd.to_datetime([
            '2023-01-01 09:30:00', '2023-01-01 09:31:00', '2023-01-01 09:32:00', '2023-01-01 09:33:00', '2023-01-01 09:34:00',
            '2023-01-01 09:35:00', '2023-01-01 09:36:00', '2023-01-01 09:37:00', '2023-01-01 09:38:00', '2023-01-01 09:39:00',
            '2023-01-01 09:40:00', '2023-01-01 09:41:00', '2023-01-01 09:42:00', '2023-01-01 09:43:00', '2023-01-01 09:44:00',
            '2023-01-01 09:45:00', '2023-01-01 09:46:00', '2023-01-01 09:47:00', '2023-01-01 09:48:00', '2023-01-01 09:49:00',
            '2023-01-01 09:50:00', '2023-01-01 09:51:00', '2023-01-01 09:52:00', '2023-01-01 09:53:00', '2023-01-01 09:54:00',
            '2023-01-01 09:55:00', '2023-01-01 09:56:00', '2023-01-01 09:57:00', '2023-01-01 09:58:00', '2023-01-01 09:59:00',
            '2023-01-01 10:00:00', '2023-01-01 10:01:00', '2023-01-01 10:02:00', '2023-01-01 10:03:00', '2023-01-01 10:04:00',
            '2023-01-01 10:05:00', '2023-01-01 10:06:00', '2023-01-01 10:07:00', '2023-01-01 10:08:00', '2023-01-01 10:09:00',
            '2023-01-01 10:10:00', '2023-01-01 10:11:00', '2023-01-01 10:12:00', '2023-01-01 10:13:00', '2023-01-01 10:14:00',
            '2023-01-01 10:15:00', '2023-01-01 10:16:00', '2023-01-01 10:17:00', '2023-01-01 10:18:00', '2023-01-01 10:19:00',
            '2023-01-01 10:20:00' # Needs enough data points for long_window (50)
        ]),
        'close': [
            100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 
            110, 111, 112, 113, 114, 115, 116, 117, 118, 119, 
            120, 119, 118, 117, 116, 115, 114, 113, 112, 111,
            110, 109, 108, 107, 106, 105, 104, 103, 102, 101,
            100, 99, 98, 97, 96, 95, 94, 93, 92, 91,
            90 # Ensure this list matches the length of timestamp
        ]
    }
    market_df = pd.DataFrame(data).set_index('timestamp')

    # Initialize strategy
    # Example config for the strategy
    strategy_config = {
        'short_window': 5, # Shorter window for more signals with small data
        'long_window': 10,
        'ticker': 'XYZ'
    }
    example_strat = ExampleStrategy(config=strategy_config)
    print(f"Initialized strategy: {example_strat}")

    # Generate signals
    signals_df = example_strat.generate_signals(market_df)
    print("\nSignals DataFrame:")
    print(signals_df.tail())

    # Define orders
    current_pos = {} # No current positions
    balance = 100000.0 # Example balance
    orders_to_place = example_strat.define_orders(signals_df, current_pos, balance)
    print("\nOrders to place:")
    print(orders_to_place) 