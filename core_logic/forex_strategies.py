from collections import deque
import pandas as pd
import time

class MovingAverageCrossoverStrategy:
    def __init__(self, short_window: int, long_window: int, forex_pair: str):
        self.short_window = short_window
        self.long_window = long_window
        self.forex_pair = forex_pair # e.g., "EUR.USD"
        
        self.prices = deque(maxlen=long_window + 5) # Store recent close prices for MA calculation
        self.short_ma = None
        self.long_ma = None
        
        self.historical_bars_df = None
        self.data_initialized = False
        self.position = 0 # -1 for short, 0 for flat, 1 for long

    def initialize_with_historical_data(self, bars: list):
        """
        Initialize the strategy with historical bar data.
        bars: A list of dictionaries, e.g., from IBClient.get_historical_bars()
              Each dict should have at least 'close' and 'date' keys.
        """
        if not bars or len(bars) < self.long_window:
            print(f"Strategy Error ({self.forex_pair}): Not enough historical data to initialize. Need {self.long_window}, got {len(bars)}.")
            return False

        self.historical_bars_df = pd.DataFrame(bars)
        if 'close' not in self.historical_bars_df.columns:
            print(f"Strategy Error ({self.forex_pair}): 'close' column missing in historical bars.")
            return False
        
        # Ensure data is sorted by date if not already (though IB usually sends it sorted)
        if 'date' in self.historical_bars_df.columns:
            try:
                self.historical_bars_df['date'] = pd.to_datetime(self.historical_bars_df['date'])
                self.historical_bars_df = self.historical_bars_df.sort_values(by='date')
            except Exception as e:
                print(f"Strategy Warning ({self.forex_pair}): Could not parse or sort by date in historical data - {e}")

        # Calculate initial MAs
        self.historical_bars_df[f'short_ma'] = self.historical_bars_df['close'].rolling(window=self.short_window).mean()
        self.historical_bars_df[f'long_ma'] = self.historical_bars_df['close'].rolling(window=self.long_window).mean()
        
        # Populate recent prices for subsequent tick updates
        for price in self.historical_bars_df['close'].tail(self.long_window).tolist():
            self.prices.append(price)
            
        self.short_ma = self.historical_bars_df[f'short_ma'].iloc[-1]
        self.long_ma = self.historical_bars_df[f'long_ma'].iloc[-1]
        
        if pd.isna(self.short_ma) or pd.isna(self.long_ma):
            print(f"Strategy Error ({self.forex_pair}): Initial MAs are NaN. Check data and window sizes.")
            self.data_initialized = False
            return False
            
        self.data_initialized = True
        print(f"Strategy ({self.forex_pair}): Initialized. Last Short MA: {self.short_ma:.5f}, Long MA: {self.long_ma:.5f}")
        return True

    def on_new_tick(self, current_price: float):
        """
        Process a new tick (e.g., last price) to update MAs and generate signals.
        Returns a signal: "BUY", "SELL", or "HOLD".
        """
        if not self.data_initialized:
            # print(f"Strategy ({self.forex_pair}): Not initialized. Holding.")
            return "HOLD" # Or raise an error, or wait

        if current_price <= 0:
            # print(f"Strategy ({self.forex_pair}): Invalid current price ({current_price}). Holding.")
            return "HOLD"

        # This is a simplified update for tick data.
        # For strategies that rely on bar close, you'd typically update on bar close, not every tick.
        # Here, we append the current price and recalculate MAs on the fly from the deque.
        # This is more like an EMA-like behavior with a fixed-size deque for SMA.

        previous_short_ma = self.short_ma
        previous_long_ma = self.long_ma
        
        self.prices.append(current_price)
        
        if len(self.prices) >= self.short_window:
            self.short_ma = sum(list(self.prices)[-self.short_window:]) / self.short_window
        else:
            # Not enough data yet for short MA with new tick, should ideally not happen if initialized
            return "HOLD" 
            
        if len(self.prices) >= self.long_window:
            self.long_ma = sum(list(self.prices)[-self.long_window:]) / self.long_window
        else:
            # Not enough data yet for long MA with new tick
            return "HOLD"

        if previous_short_ma is None or previous_long_ma is None: # First tick after initialization
            # print(f"Strategy ({self.forex_pair}): Updated MAs. Short MA: {self.short_ma:.5f}, Long MA: {self.long_ma:.5f}")
            return "HOLD" # No crossover on the very first update post-initialization

        signal = "HOLD"
        # Check for BUY signal (short MA crosses above long MA)
        if previous_short_ma <= previous_long_ma and self.short_ma > self.long_ma:
            if self.position <= 0: # If flat or short, consider buying
                signal = "BUY"
                self.position = 1
                print(f"Strategy ({self.forex_pair}): BUY signal. Short MA ({self.short_ma:.5f}) crossed above Long MA ({self.long_ma:.5f})")
            else:
                # print(f"Strategy ({self.forex_pair}): Crossover BUY, but already long. Holding.")
                pass # Already long

        # Check for SELL signal (short MA crosses below long MA)
        elif previous_short_ma >= previous_long_ma and self.short_ma < self.long_ma:
            if self.position >= 0: # If flat or long, consider selling
                signal = "SELL"
                self.position = -1
                print(f"Strategy ({self.forex_pair}): SELL signal. Short MA ({self.short_ma:.5f}) crossed below Long MA ({self.long_ma:.5f})")
            else:
                # print(f"Strategy ({self.forex_pair}): Crossover SELL, but already short. Holding.")
                pass # Already short
        
        # Optional: print MAs on each tick for debugging
        # else:
            # print(f"Strategy ({self.forex_pair}): Holding. Short MA: {self.short_ma:.5f}, Long MA: {self.long_ma:.5f}")

        return signal

    def get_current_position(self):
        return self.position

    def update_position(self, new_position: int):
        """Allows external updates to position, e.g., after an order is confirmed filled."""
        # Validate new_position if necessary, e.g., -1, 0, 1
        self.position = new_position

# Example usage (conceptual, would be driven by the main bot)
if __name__ == '__main__':
    # 1. Simulate fetching historical data (replace with actual IBClient calls)
    dummy_historical_data = [
        {'date': f'2023-01-{i:02d}', 'close': 1.05 + i*0.001 + ( (i%5-2)*0.0005 )} for i in range(1, 51) # 50 bars
    ]
    for i in range(51, 60):
        dummy_historical_data.append({'date': f'2023-01-{i-20:02d}', 'close': dummy_historical_data[-1]['close'] - 0.0002 + ((i%3-1)*0.0001)})


    strategy = MovingAverageCrossoverStrategy(short_window=5, long_window=10, forex_pair="EUR.USD_SIM")
    initialized = strategy.initialize_with_historical_data(dummy_historical_data)

    if initialized:
        print(f"Initial position: {strategy.get_current_position()}")
        # 2. Simulate receiving new ticks
        simulated_ticks = [
            strategy.historical_bars_df['close'].iloc[-1] + 0.0001, # price goes up
            strategy.historical_bars_df['close'].iloc[-1] + 0.0003, # price goes up further (potential BUY)
            strategy.historical_bars_df['close'].iloc[-1] + 0.0002,
            strategy.historical_bars_df['close'].iloc[-1] - 0.0001,
            strategy.historical_bars_df['close'].iloc[-1] - 0.0004, # price goes down
            strategy.historical_bars_df['close'].iloc[-1] - 0.0006, # price goes down further (potential SELL)
            strategy.historical_bars_df['close'].iloc[-1] - 0.0005,
        ]
        
        print("\n--- Simulating Ticks ---")
        for i, tick_price in enumerate(simulated_ticks):
            print(f"\nTick {i+1}: Price = {tick_price:.5f}")
            signal = strategy.on_new_tick(tick_price)
            print(f" -> Signal: {signal}, Current Position: {strategy.get_current_position()}")
            # In a real bot, if signal is BUY or SELL, you would place an order.
            # After order confirmation, you might call strategy.update_position().
            time.sleep(0.1) # Simulate time between ticks

        # Example: Manually update position after a fill
        # strategy.update_position(1) # if a buy order was filled
        # print(f"Position after manual update: {strategy.get_current_position()}")
    else:
        print("Strategy could not be initialized.") 