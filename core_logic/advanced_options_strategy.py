import pandas as pd
from .strategy_base import StrategyBase
from datetime import datetime, timedelta

class AdvancedOptionsStrategy(StrategyBase):
    """
    An advanced options trading strategy that selects contracts based on
    delta, DTE, liquidity, and various Implied Volatility (IV) filtering modes.
    """

    def __init__(self, config: dict = None):
        super().__init__(strategy_name="AdvancedOptionsStrategy", config=config)
        self.default_config = {
            'short_window': 20,
            'long_window': 50,
            'ticker': 'SPY',
            'target_dte_min': 30,
            'target_dte_max': 60,
            'target_delta_min': 0.30,  # Absolute delta
            'target_delta_max': 0.50,  # Absolute delta
            
            'iv_filter_mode': 'fixed_range', # Options: 'fixed_range', 'percentile', 'vs_underlying_hv', 'none'
            
            # For 'fixed_range' mode
            'target_iv_min': 0.15,      # Minimum Implied Volatility (e.g., 15%)
            'target_iv_max': 0.60,      # Maximum Implied Volatility (e.g., 60%)

            # For 'percentile' mode (assumes 'iv_percentile' is in contract data)
            'target_iv_percentile_min': 20, # E.g., IV should be above the 20th percentile
            'target_iv_percentile_max': 80, # E.g., IV should be below the 80th percentile

            # For 'vs_underlying_hv' mode (assumes 'underlying_hv' is passed to define_orders)
            'iv_to_hv_ratio_min': 1.0,   # E.g., IV should be at least 1.0x HV
            'iv_to_hv_ratio_max': 2.5,   # E.g., IV should be at most 2.5x HV
            
            'min_open_interest': 100,
            'min_volume': 50,
            'max_bid_ask_spread_pct': 0.1, # Max 10% spread of ask price
            'risk_per_trade_pct': 0.01    # Risk 1% of account balance per trade
        }
        self.config = {**self.default_config, **self.config}
        self._validate_config()

    def _validate_config(self):
        mode = self.config.get('iv_filter_mode')
        if mode not in ['fixed_range', 'percentile', 'vs_underlying_hv', 'none']:
            raise ValueError(f"Invalid iv_filter_mode: {mode}")

    def generate_signals(self, market_data: pd.DataFrame) -> pd.DataFrame:
        """
        Generates trading signals based on the provided market data (e.g., historical prices for the underlying).
        This example uses a simple moving average crossover.
        
        Args:
            market_data (pd.DataFrame): DataFrame with historical market data. 
                                        Must contain a 'close' column and be indexed by timestamp.

        Returns:
            pd.DataFrame: DataFrame with 'signal' (buy/sell/hold) and 'positions' (long/short/neutral) columns.
        """
        if 'close' not in market_data.columns:
            print("Error: 'close' column not found in market_data for signal generation.")
            return pd.DataFrame() # Return empty DataFrame on error

        signals = pd.DataFrame(index=market_data.index)
        signals['signal'] = 0.0 # Default to no signal
        signals['ticker'] = self.config.get('ticker', 'underlying')

        short_window = self.config.get('short_window', 20)
        long_window = self.config.get('long_window', 50)

        if len(market_data) < long_window:
            print(f"Warning: Not enough data for long window ({long_window} days). Need {long_window}, got {len(market_data)}.")
            # Still create the 'positions' column for consistency, even if no signals generated
            signals['positions'] = 0.0 
            return signals[['ticker', 'signal', 'positions']]

        # Calculate moving averages
        signals['short_mavg'] = market_data['close'].rolling(window=short_window, min_periods=1, center=False).mean()
        signals['long_mavg'] = market_data['close'].rolling(window=long_window, min_periods=1, center=False).mean()

        # Generate signal when short MA crosses long MA
        # Using .loc for assignment to avoid SettingWithCopyWarning and for future compatibility
        signals.loc[signals['short_mavg'] > signals['long_mavg'], 'signal'] = 1.0  # Buy signal
        signals.loc[signals['short_mavg'] < signals['long_mavg'], 'signal'] = -1.0 # Sell signal

        # Generate trading positions (1 for long, -1 for short, 0 for neutral)
        # This creates a position on the day *after* the signal
        signals['positions'] = signals['signal'].diff().fillna(0)
        # Ensure positions are 0, 1, or -1. Taking np.sign of diff can result in -2, 0, 2. 
        # So if signal was 1 and becomes -1, diff is -2. We want position to be -1 (short).
        # If signal was -1 and becomes 1, diff is 2. We want position to be 1 (long).
        # This logic might need refinement based on how positions are meant to be interpreted.
        # A common way: position is the state (long/short) after the signal.
        # signals['positions'] = signals['signal'] # Simpler: position is the signal itself

        # Correcting the position calculation based on the signal at that point.
        # We are interested in the state (long/short/neutral)
        signals.loc[signals['signal'] == 1.0, 'positions'] = 1.0
        signals.loc[signals['signal'] == -1.0, 'positions'] = -1.0
        signals.loc[signals['signal'] == 0.0, 'positions'] = 0.0
        signals['positions'] = signals['positions'].fillna(0) # Ensure no NaNs if any signal is NaN

        # For the warning related to: signals['signal'][self.config['short_window']:]
        # The original intent of that line (if it existed and was similar to below) was likely related to only taking signals after the initial window.
        # The current MA calculation already handles initial periods with min_periods=1.
        # The .diff() for positions also handles the start naturally.
        # If a specific offset was intended for signals (e.g. only start signals after long_window days), 
        # it should be applied carefully. For now, the above logic seems standard.

        # print("Debug Signals DF:")
        # print(signals.tail())
        return signals[['ticker', 'signal', 'positions']]

    def _calculate_dte(self, expiration_date_str: str) -> int:
        """Calculates Days To Expiration (DTE)."""
        expiration_date = datetime.strptime(expiration_date_str, '%Y-%m-%d')
        return (expiration_date - datetime.now()).days

    def _passes_iv_filter(self, contract: dict, underlying_hv: float = None) -> bool:
        """Checks if the contract passes the configured IV filter."""
        mode = self.config['iv_filter_mode']
        iv = contract.get('implied_volatility')

        if iv is None:
            # print(f"Warning: Contract {contract.get('symbol')} missing 'implied_volatility'. Skipping IV filter.")
            return True # Or False, depending on strictness. Let's be lenient for now if data is missing.
        try:
            iv = float(iv)
        except (ValueError, TypeError):
            # print(f"Warning: Contract {contract.get('symbol')} has invalid IV {iv}. Skipping IV filter.")
            return False # Invalid IV should fail the filter.

        if mode == 'none':
            return True
        elif mode == 'fixed_range':
            return self.config['target_iv_min'] <= iv <= self.config['target_iv_max']
        elif mode == 'percentile':
            percentile = contract.get('iv_percentile')
            if percentile is None:
                # print(f"Warning: Contract {contract.get('symbol')} missing 'iv_percentile' for percentile mode. Skipping IV filter for this contract.")
                return False # Require percentile data for this mode
            try:
                percentile = float(percentile)
            except (ValueError, TypeError):
                # print(f"Warning: Contract {contract.get('symbol')} has invalid iv_percentile {percentile}. Skipping IV filter for this contract.")
                return False
            return self.config['target_iv_percentile_min'] <= percentile <= self.config['target_iv_percentile_max']
        elif mode == 'vs_underlying_hv':
            if underlying_hv is None or underlying_hv <= 0:
                # print(f"Warning: 'underlying_hv' not provided or invalid for 'vs_underlying_hv' mode. Skipping IV filter.")
                return False # Require HV data for this mode
            ratio = iv / underlying_hv
            return self.config['iv_to_hv_ratio_min'] <= ratio <= self.config['iv_to_hv_ratio_max']
        return True # Default to pass if mode is unrecognized (though _validate_config should prevent this)

    def define_orders(self, signals: pd.DataFrame, current_positions: dict, account_balance: float, **kwargs) -> list:
        """
        Define options orders based on signals and contract selection criteria.
        Args:
            ...
            **kwargs: Must contain 'options_chain' (list of dicts) for the underlying.
                      Each contract dict should have: {'symbol', 'strike_price', 'expiration_date',
                                  'type', 'delta', 'bid', 'ask', 'volume', 'open_interest', 'implied_volatility'}
                      Optionally, 'iv_percentile' if using 'percentile' IV filter mode.
                      Must also contain 'underlying_price' (float).
                      Optionally, 'underlying_hv' (float) if using 'vs_underlying_hv' IV filter mode.
        """
        orders = []
        latest_signal_info = signals.iloc[-1]
        trade_signal = latest_signal_info['positions']

        options_chain = kwargs.get('options_chain')
        underlying_price = kwargs.get('underlying_price')
        underlying_hv = kwargs.get('underlying_hv') # Used for 'vs_underlying_hv' mode

        if not options_chain or underlying_price is None:
            print(f"{self.strategy_name}: Missing options_chain or underlying_price. Cannot select options.")
            return orders

        if trade_signal == 0: 
            return orders

        desired_option_type = 'call' if trade_signal > 0 else 'put'
        
        eligible_contracts = []
        for contract in options_chain:
            if contract['type'] != desired_option_type:
                continue

            dte = self._calculate_dte(contract['expiration_date'])
            if not (self.config['target_dte_min'] <= dte <= self.config['target_dte_max']):
                continue
            
            try:
                delta_val = float(contract.get('delta', 0))
            except (ValueError, TypeError):
                continue
            abs_delta = abs(delta_val)
            if not (self.config['target_delta_min'] <= abs_delta <= self.config['target_delta_max']):
                continue

            # Centralized IV Filter Check
            if not self._passes_iv_filter(contract, underlying_hv):
                # print(f"Contract {contract.get('symbol')} failed IV filter mode {self.config['iv_filter_mode']}.")
                continue

            if contract.get('open_interest', 0) < self.config['min_open_interest']:
                continue
            if contract.get('volume', 0) < self.config['min_volume']:
                continue

            bid = contract.get('bid', 0.0)
            ask = contract.get('ask', 0.0)
            if ask <= 0 or bid <= 0:
                continue
            if (ask - bid) / ask > self.config['max_bid_ask_spread_pct']:
                continue
            
            contract['dte'] = dte 
            eligible_contracts.append(contract)

        if not eligible_contracts:
            print(f"{self.strategy_name}: No eligible {desired_option_type} contracts found for {self.config['ticker']} matching all criteria (IV Mode: {self.config['iv_filter_mode']}).")
            return orders
        
        eligible_contracts.sort(key=lambda x: (
            abs(abs(float(x.get('delta',0))) - (self.config['target_delta_min'] + self.config['target_delta_max']) / 2),
            -x.get('open_interest',0) 
        ))
        
        selected_contract = eligible_contracts[0]

        option_price_to_use = selected_contract['ask']
        if option_price_to_use <= 0:
             print(f"{self.strategy_name}: Selected contract {selected_contract['symbol']} has invalid price {option_price_to_use}.")
             return orders

        max_loss_per_contract = option_price_to_use * 100 
        trade_risk_amount = account_balance * self.config['risk_per_trade_pct']
        quantity = int(trade_risk_amount // max_loss_per_contract)

        if quantity == 0:
            return orders

        order = {
            'symbol': selected_contract['symbol'],
            'type': 'market', 
            'side': 'buy_to_open',
            'quantity': quantity,
            'price_at_decision': selected_contract['ask'], 
            'estimated_cost': selected_contract['ask'] * quantity * 100,
            'tag': f"{self.strategy_name}_{desired_option_type}"
        }
        orders.append(order)
        iv_display = selected_contract.get('implied_volatility', 'N/A')
        iv_perc_display = selected_contract.get('iv_percentile', 'N/A')
        print(f"{self.strategy_name}: {('BULLISH' if trade_signal > 0 else 'BEARISH')} signal for {self.config['ticker']}. "
              f"Selected: {selected_contract['symbol']} (IV: {iv_display:.2f} / IV Perc: {iv_perc_display}, Delta: {selected_contract.get('delta', 'N/A'):.2f}, DTE: {selected_contract['dte']}). "
              f"Order: {order['side']} {order['quantity']} @ MKT (Est. Cost: ${order['estimated_cost']:.2f}) IV Mode: {self.config['iv_filter_mode']}")
        return orders

if __name__ == '__main__':
    base_strategy_params = {
        'short_window': 5,
        'long_window': 10,
        'ticker': 'XYZ',
        'target_dte_min': 25,
        'target_dte_max': 45,
        'target_delta_min': 0.30, 
        'target_delta_max': 0.60,
        'min_open_interest': 10,
        'min_volume': 5,
        'risk_per_trade_pct': 0.02 
    }

    # --- Test Config 1: Fixed IV Range ---
    config_fixed_iv = {**base_strategy_params,
        'iv_filter_mode': 'fixed_range',
        'target_iv_min': 0.20, 
        'target_iv_max': 0.35, 
    }
    adv_strat_fixed = AdvancedOptionsStrategy(config=config_fixed_iv)
    print(f"\nInitialized strategy (Fixed IV): {adv_strat_fixed.strategy_name} with config: {adv_strat_fixed.config['iv_filter_mode']}")

    # --- Test Config 2: IV Percentile Range ---
    config_percentile_iv = {**base_strategy_params,
        'iv_filter_mode': 'percentile',
        'target_iv_percentile_min': 30, 
        'target_iv_percentile_max': 70, 
    }
    adv_strat_percentile = AdvancedOptionsStrategy(config=config_percentile_iv)
    print(f"Initialized strategy (IV Percentile): {adv_strat_percentile.strategy_name} with config: {adv_strat_percentile.config['iv_filter_mode']}")

    # --- Test Config 3: IV vs Underlying HV Ratio ---
    config_hv_ratio_iv = {**base_strategy_params,
        'iv_filter_mode': 'vs_underlying_hv',
        'iv_to_hv_ratio_min': 1.1, 
        'iv_to_hv_ratio_max': 1.8, 
    }
    adv_strat_hv_ratio = AdvancedOptionsStrategy(config=config_hv_ratio_iv)
    print(f"Initialized strategy (IV vs HV Ratio): {adv_strat_hv_ratio.strategy_name} with config: {adv_strat_hv_ratio.config['iv_filter_mode']}")

    market_data_list = [
        {'timestamp': '2023-01-01 09:30:00', 'close': 100}, {'timestamp': '2023-01-01 09:31:00', 'close': 101},
        {'timestamp': '2023-01-01 09:32:00', 'close': 102}, {'timestamp': '2023-01-01 09:33:00', 'close': 103},
        {'timestamp': '2023-01-01 09:34:00', 'close': 104}, {'timestamp': '2023-01-01 09:35:00', 'close': 105}, 
        {'timestamp': '2023-01-01 09:36:00', 'close': 106}, {'timestamp': '2023-01-01 09:37:00', 'close': 107},
        {'timestamp': '2023-01-01 09:38:00', 'close': 108}, {'timestamp': '2023-01-01 09:39:00', 'close': 109},
        {'timestamp': '2023-01-01 09:40:00', 'close': 110}, {'timestamp': '2023-01-01 09:41:00', 'close': 109}, 
        {'timestamp': '2023-01-01 09:42:00', 'close': 108}, {'timestamp': '2023-01-01 09:43:00', 'close': 107},
        {'timestamp': '2023-01-01 09:44:00', 'close': 106},
    ]
    market_df = pd.DataFrame(market_data_list)
    market_df['timestamp'] = pd.to_datetime(market_df['timestamp'])
    market_df = market_df.set_index('timestamp')
    
    current_underlying_price = market_df['close'].iloc[-1]
    # Simulate an underlying historical volatility for testing 'vs_underlying_hv' mode
    simulated_underlying_hv = 0.22 # e.g., 22% annualized HV

    signals_df = adv_strat_fixed.generate_signals(market_df) # Signals are same for all

    exp_date_in_range = (datetime.now() + timedelta(days=base_strategy_params['target_dte_min'] + 5)).strftime('%Y-%m-%d')

    dummy_options_chain = [
        # Calls
        {'symbol': 'XYZ_C_PASS_ALL', 'strike_price': 105, 'expiration_date': exp_date_in_range, 'type': 'call', 'delta': 0.55, 'implied_volatility': 0.25, 'iv_percentile': 50, 'bid': 1.50, 'ask': 1.60, 'volume': 150, 'open_interest': 250},
        {'symbol': 'XYZ_C_FAIL_IVFIX', 'strike_price': 108, 'expiration_date': exp_date_in_range, 'type': 'call', 'delta': 0.45, 'implied_volatility': 0.40, 'iv_percentile': 75, 'bid': 1.00, 'ask': 1.10, 'volume': 80, 'open_interest': 180}, # IV 0.40 fails fixed range (0.20-0.35)
        {'symbol': 'XYZ_C_FAIL_IVPERC','strike_price': 110, 'expiration_date': exp_date_in_range, 'type': 'call', 'delta': 0.35, 'implied_volatility': 0.28, 'iv_percentile': 15, 'bid': 0.80, 'ask': 0.85, 'volume': 120, 'open_interest': 300},# IV Perc 15 fails (30-70)
        {'symbol': 'XYZ_C_FAIL_HVRA', 'strike_price': 106, 'expiration_date': exp_date_in_range, 'type': 'call', 'delta': 0.50, 'implied_volatility': 0.45, 'iv_percentile': 80, 'bid': 1.30, 'ask': 1.33, 'volume': 200, 'open_interest': 400}, # IV 0.45 / HV 0.22 = 2.04, fails ratio (1.1-1.8)
        # Puts
        {'symbol': 'XYZ_P_PASS_ALL', 'strike_price': 105, 'expiration_date': exp_date_in_range, 'type': 'put', 'delta': -0.53, 'implied_volatility': 0.28, 'iv_percentile': 60, 'bid': 1.80, 'ask': 1.90, 'volume': 130, 'open_interest': 220},
        {'symbol': 'XYZ_P_FAIL_IVFIX', 'strike_price': 100, 'expiration_date': exp_date_in_range, 'type': 'put', 'delta': -0.40, 'implied_volatility': 0.15, 'iv_percentile': 25, 'bid': 1.20, 'ask': 1.30, 'volume': 70, 'open_interest': 170}, # IV 0.15 fails fixed range (0.20-0.35)
        {'symbol': 'XYZ_P_FAIL_IVPERC','strike_price': 98,  'expiration_date': exp_date_in_range, 'type': 'put', 'delta': -0.33, 'implied_volatility': 0.30, 'iv_percentile': 85, 'bid': 0.90, 'ask': 0.95, 'volume': 110, 'open_interest': 280},# IV Perc 85 fails (30-70)
        {'symbol': 'XYZ_P_FAIL_HVRA', 'strike_price': 102, 'expiration_date': exp_date_in_range, 'type': 'put', 'delta': -0.48, 'implied_volatility': 0.18, 'iv_percentile': 40, 'bid': 1.50, 'ask': 1.55, 'volume': 180, 'open_interest': 350}, # IV 0.18 / HV 0.22 = 0.81, fails ratio (1.1-1.8)
    ]

    current_pos = {} 
    balance = 10000.0 
    
    test_scenarios = [
        (adv_strat_fixed, "Fixed IV Range"),
        (adv_strat_percentile, "IV Percentile"),
        (adv_strat_hv_ratio, "IV vs HV Ratio")
    ]

    for strategy_instance, name in test_scenarios:
        print(f"\n--- TESTING SCENARIO: {name.upper()} ---")
        # Bullish
        print(f"--- Simulating Bullish Scenario (BUY signal) for {name} ---")
        signals_df.iloc[-1, signals_df.columns.get_loc('positions')] = 1 
        orders_call = strategy_instance.define_orders(signals_df, current_pos, balance, 
                                                    options_chain=dummy_options_chain, 
                                                    underlying_price=current_underlying_price,
                                                    underlying_hv=simulated_underlying_hv)
        if not orders_call:
            print(f"No call orders generated for {name}.")
        
        # Bearish
        print(f"\n--- Simulating Bearish Scenario (SELL signal) for {name} ---")
        signals_df.iloc[-1, signals_df.columns.get_loc('positions')] = -1
        orders_put = strategy_instance.define_orders(signals_df, current_pos, balance, 
                                                   options_chain=dummy_options_chain, 
                                                   underlying_price=current_underlying_price,
                                                   underlying_hv=simulated_underlying_hv)
        if not orders_put:
            print(f"No put orders generated for {name}.") 