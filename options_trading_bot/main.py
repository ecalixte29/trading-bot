import pandas as pd
from datetime import datetime, timedelta
import json # For pretty printing dicts
import requests # For sending alerts to the API
import time # Added for Forex trading loop

from .config import (
    POLYGON_API_KEY, TRADIER_API_KEY, TRADIER_ACCOUNT_ID, 
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, OPENAI_API_KEY,
    IB_HOST, IB_PORT, IB_CLIENT_ID, # IB connection details
    SUBMIT_ORDERS_TO_BROKER, # Global control flag
    FOREX_TRADING_ENABLED, # Forex cycle flag
    # OPTIONS_TRADING_ENABLED, # If you add this to config.py and want to use it
    ALERT_API_URL,
    USE_SANDBOX as TRADIER_USE_SANDBOX # Keep this alias for Tradier specific use
)
from .data_feeds import PolygonDataClient
from .core_logic import AdvancedOptionsStrategy
from .broker_integrations import TradierClient

# --- New Imports for Forex Trading with Interactive Brokers ---
from .broker_integrations.interactive_brokers_client import IBClient, TickTypeEnum
from .core_logic.forex_strategies import MovingAverageCrossoverStrategy
from .telegram_notifier import TelegramNotifier # Added TelegramNotifier import
from .database_logger import DatabaseLogger # <<< ADDED IMPORT FOR DATABASELOGGER
from .openai_analyzer import OpenAIAnalyzer # <<< ADDED IMPORT FOR OPENAIANALYZER

# --- Configuration for the Main Bot --- 
# Most of these will now come from config.py
HARDCODED_UNDERLYING_TICKER = "SPY" # Default ticker to trade (can remain or be moved to config)
STRATEGY_CONFIG = {
    'short_window': 20,
    'long_window': 50,
    'ticker': HARDCODED_UNDERLYING_TICKER,
    'target_dte_min': 30, 
    'target_dte_max': 60,
    'target_delta_min': 0.30, 
    'target_delta_max': 0.50,
    'iv_filter_mode': 'vs_underlying_hv', # Temporarily set to test HV calculation
    'target_iv_min': 0.10, # 10% IV 
    'target_iv_max': 0.70, # 70% IV
    'iv_to_hv_ratio_min': 1.0, # For 'vs_underlying_hv' mode
    'iv_to_hv_ratio_max': 2.5,   # For 'vs_underlying_hv' mode
    'min_open_interest': 50, # Adjusted for potentially real data
    'min_volume': 20,        # Adjusted for potentially real data
    'max_bid_ask_spread_pct': 0.15, 
    'risk_per_trade_pct': 0.01 
}

# Options chain fetching parameters
CHAIN_EXPR_DATE_GTE_DAYS = 25  # Min DTE for options to fetch
CHAIN_EXPR_DATE_LTE_DAYS = 65  # Max DTE for options to fetch
CHAIN_CONTRACT_LIMIT = 200     # Limit number of contracts to fetch for the chain initially (max 250 per page from Polygon)
                               # Be mindful of API rate limits with snapshot fetching.

HISTORICAL_DATA_DAYS_FOR_SIGNALS = STRATEGY_CONFIG['long_window'] + 150

# --- Global Control Flags --- 
# MOVED TO CONFIG.PY and imported: SUBMIT_ORDERS_TO_BROKER, ALERT_API_URL

# --- Forex Trading Configuration ---
# MOVED TO CONFIG.PY and imported: FOREX_TRADING_ENABLED, IB_HOST, IB_PORT, IB_CLIENT_ID
# These can remain here if they are highly specific to main.py and not general config,
# or also be moved to .env and config.py if desired for full externalization.
FOREX_PAIR_SYMBOL = "EUR" 
FOREX_PAIR_CURRENCY = "USD"
FOREX_STRATEGY_SHORT_WINDOW = 10
FOREX_STRATEGY_LONG_WINDOW = 20
FOREX_ORDER_QUANTITY = 1000

# Request IDs for IBClient (These are runtime identifiers, okay to keep in main.py)
HIST_DATA_REQ_ID = 201
STREAM_DATA_REQ_ID = 101

# --- Telegram Configuration --- (Loaded from config.py)
# --- Placeholder SL/TP percentages --- (Okay to keep in main.py or move to config)
FOREX_DEFAULT_SL_PERCENT = 0.005
FOREX_DEFAULT_TP_PERCENT = 0.01

# --- Helper function to send alerts ---
def send_alert_to_api(message: str, level: str = "INFO"):
    """Sends an alert to the configured Alert API."""
    try:
        payload = {"message": message, "level": level}
        response = requests.post(ALERT_API_URL, json=payload, timeout=5) # 5 second timeout
        if response.status_code == 201:
            print(f"Alert API: Successfully sent '{level}' alert: {message}")
        else:
            print(f"Alert API: Failed to send alert. Status: {response.status_code}, Response: {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"Alert API: Error connecting to alert API at {ALERT_API_URL}: {e}")

def generate_dummy_market_data_for_signals(ticker: str, days=100) -> pd.DataFrame:
    """Generates dummy historical data for signal generation if real historical fetch isn't set up yet."""
    print(f"Warning: Using DUMMY historical data for {ticker} to generate signals.")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    dates = pd.date_range(start_date, end_date, freq='B') # Business days
    data_len = len(dates)
    # Create a simple sine wave + trend for close prices
    prices = 100 + pd.Series(range(data_len))/10 + 5 * pd.Series(index=dates, data=pd.np.sin(pd.np.arange(data_len) * 0.1))
    prices = prices.fillna(method='ffill').round(2)
    market_df = pd.DataFrame({'close': prices}, index=dates)
    market_df.index.name = 'timestamp'
    return market_df

def run_trading_cycle():
    db_stock_options_logger = DatabaseLogger(db_name="stock_options_signals.db")
    # Initialize variables that might be used in finally or for logging before full initialization
    underlying_ticker_for_logging = HARDCODED_UNDERLYING_TICKER 
    strategy_name_for_logging = "AdvancedOptionsStrategy" # Default name

    try:
        send_alert_to_api(f"Trading cycle started for {HARDCODED_UNDERLYING_TICKER}.", "INFO")
        print(f"\n[{datetime.now()}] --- Starting Trading Cycle ---")

        active_environment = "Sandbox" if TRADIER_USE_SANDBOX else "Production (LIVE MONEY)"
        print(f"Tradier Environment: {active_environment}")
        print(f"Order Submission to Broker: {'ENABLED' if SUBMIT_ORDERS_TO_BROKER else 'DISABLED'}")
        if SUBMIT_ORDERS_TO_BROKER and not TRADIER_USE_SANDBOX:
            warning_msg = "Order submission ENABLED in PRODUCTION (LIVE MONEY) mode! Proceed with EXTREME CAUTION!"
            print(f"\n{'!'*60}\nWARNING: {warning_msg}\n{'!'*60}\n")
            send_alert_to_api(warning_msg, "CRITICAL")

        if not POLYGON_API_KEY:
            err_msg = "POLYGON_API_KEY not set. Exiting trading cycle."
            print(err_msg)
            send_alert_to_api(err_msg, "ERROR")
            return # Exit early
        if SUBMIT_ORDERS_TO_BROKER and (not TRADIER_API_KEY or not TRADIER_ACCOUNT_ID):
            err_msg = "TRADIER_API_KEY or TRADIER_ACCOUNT_ID not set, but order submission is enabled. Exiting."
            print(err_msg)
            send_alert_to_api(err_msg, "ERROR")
            return # Exit early

        poly_client = PolygonDataClient()
        tradier_client = TradierClient()
        strategy = AdvancedOptionsStrategy(config=STRATEGY_CONFIG)
        underlying_ticker_for_logging = strategy.config.get('ticker', HARDCODED_UNDERLYING_TICKER)
        strategy_name_for_logging = strategy.strategy_name

        print(f"Trading for underlying: {underlying_ticker_for_logging} with strategy: {strategy_name_for_logging}")
        print(f"Strategy IV Filter Mode: {strategy.config.get('iv_filter_mode')}")
        send_alert_to_api(f"Strategy initialized: {strategy_name_for_logging} for {underlying_ticker_for_logging}. IV Filter: {strategy.config.get('iv_filter_mode')}", "INFO")

        # 2. Fetch Account Details (Balance, Positions) from Broker if submitting orders
        account_balance_val = 10000.0 # Default placeholder
        current_positions_val = {}    # Default placeholder

        if SUBMIT_ORDERS_TO_BROKER or not SUBMIT_ORDERS_TO_BROKER: # Always useful to get balance for strategy sizing
            print("Fetching account balance from Tradier...")
            balance_data = tradier_client.get_account_balance()
            if balance_data and 'option_buying_power' in balance_data : # Tradier often has 'option_buying_power'
                try:
                    account_balance_val = float(balance_data['option_buying_power'])
                    print(f"Fetched Option Buying Power: ${account_balance_val:.2f}")
                except ValueError:
                    print(f"Warning: Could not parse option_buying_power: {balance_data['option_buying_power']}. Using default.")
            elif balance_data and 'total_cash' in balance_data:
                 try:
                    account_balance_val = float(balance_data['total_cash'])
                    print(f"Fetched Total Cash (using as approx. buying power): ${account_balance_val:.2f}")
                 except ValueError:
                    print(f"Warning: Could not parse total_cash: {balance_data['total_cash']}. Using default.")
            else:
                print(f"Warning: Could not fetch account balance or relevant fields. Using default: ${account_balance_val:.2f}")
                # if SUBMIT_ORDERS_TO_BROKER: return # Critical if submitting real orders
        
            print("Fetching current positions from Tradier...")
            positions_data = tradier_client.get_account_positions()
            if positions_data:
                current_positions_val = {pos['symbol']: pos['quantity'] for pos in positions_data if 'symbol' in pos and 'quantity' in pos}
                print(f"Fetched {len(current_positions_val)} positions.")
                # print(json.dumps(positions_data, indent=2))
            else:
                print("No current positions found or error fetching them.")

        # 3. Fetch REAL Historical Market Data for Signals from Polygon.io
        print(f"Fetching historical data for {underlying_ticker_for_logging} for signal generation...")
        to_date_str = datetime.now().strftime("%Y-%m-%d")
        from_date_str = (datetime.now() - timedelta(days=HISTORICAL_DATA_DAYS_FOR_SIGNALS)).strftime("%Y-%m-%d")
        
        historical_market_data = poly_client.get_historical_aggregates(
            ticker=underlying_ticker_for_logging,
            from_date=from_date_str,
            to_date=to_date_str,
            timespan="day"
        )

        if historical_market_data.empty or len(historical_market_data) < strategy.config['long_window']:
            err_msg = f"Not enough historical market data for {underlying_ticker_for_logging} (need {strategy.config['long_window']}, got {len(historical_market_data)}). Exiting."
            print(err_msg)
            send_alert_to_api(err_msg, "ERROR")
            return
        print(f"Successfully fetched {len(historical_market_data)} days of historical data for {underlying_ticker_for_logging}.")

        # 4. Generate Trading Signals
        signals_df = strategy.generate_signals(historical_market_data)
        if signals_df.empty or 'positions' not in signals_df.columns:
            print("Failed to generate signals. Exiting.")
            send_alert_to_api("Failed to generate signals.", "ERROR")
            return
        
        latest_signal_info = signals_df.iloc[-1]
        trade_signal = latest_signal_info['positions'] 
        print(f"Latest signal for {underlying_ticker_for_logging}: {'BULLISH' if trade_signal > 0 else 'BEARISH' if trade_signal < 0 else 'HOLD'}")

        if trade_signal == 0:
            print("No new trade signal. Ending cycle.")
            send_alert_to_api(f"No new trade signal for {underlying_ticker_for_logging}. Ending cycle.", "INFO")
            return

        # 5. Fetch Current Data for Decision Making
        current_underlying_price = poly_client.get_underlying_price(underlying_ticker_for_logging)
        if current_underlying_price is None:
            err_msg = f"Could not fetch current price for {underlying_ticker_for_logging}. Exiting."
            print(err_msg)
            send_alert_to_api(err_msg, "ERROR")
            return
        print(f"Current underlying price for {underlying_ticker_for_logging}: {current_underlying_price}")

        # Determine contract type based on signal for fetching specific chain
        desired_option_type_for_chain = 'call' if trade_signal > 0 else 'put'

        # Define DTE range for fetching options chain
        today = datetime.now().date()
        exp_date_gte = (today + timedelta(days=CHAIN_EXPR_DATE_GTE_DAYS)).strftime("%Y-%m-%d")
        exp_date_lte = (today + timedelta(days=CHAIN_EXPR_DATE_LTE_DAYS)).strftime("%Y-%m-%d")
        
        print(f"Fetching {desired_option_type_for_chain} options chain for {underlying_ticker_for_logging}, DTE: {exp_date_gte} to {exp_date_lte}")
        options_chain_data = poly_client.get_options_chain_snapshot(
            underlying_ticker=underlying_ticker_for_logging,
            expiration_date_gte=exp_date_gte,
            expiration_date_lte=exp_date_lte,
            contract_type=desired_option_type_for_chain,
            # strike_price_gte=current_underlying_price * 0.8, # Example: Filter strikes around current price
            # strike_price_lte=current_underlying_price * 1.2,
            limit=CHAIN_CONTRACT_LIMIT 
        )

        if not options_chain_data:
            err_msg = f"No options chain data received for {underlying_ticker_for_logging} with specified criteria. Cannot define orders."
            print(err_msg)
            send_alert_to_api(err_msg, "WARNING")
            return
        print(f"Fetched {len(options_chain_data)} contracts for the options chain.")

        # Prepare kwargs for define_orders
        strategy_kwargs = {
            'options_chain': options_chain_data,
            'underlying_price': current_underlying_price
        }
        
        # Add underlying_hv if mode requires it
        if strategy.config.get('iv_filter_mode') == 'vs_underlying_hv':
            # TODO: Fetch/calculate actual underlying historical volatility (HV)
            # This would typically involve fetching more historical data and calculating std dev of log returns.
            print("Attempting to calculate Historical Volatility (HV)...")
            # For HV, use a period like 20 or 30 days from the historical_market_data already fetched
            hv_period = 20 
            if len(historical_market_data) >= hv_period:
                log_returns = pd.np.log(historical_market_data['close'] / historical_market_data['close'].shift(1))
                # Annualized HV: std_dev * sqrt(trading_days_in_year)
                # Assuming approx 252 trading days in a year
                calculated_hv = log_returns.rolling(window=hv_period).std().iloc[-1] * pd.np.sqrt(252)
                if pd.notna(calculated_hv) and calculated_hv > 0:
                    strategy_kwargs['underlying_hv'] = calculated_hv
                    print(f"Calculated Underlying HV ({hv_period}-day annualized): {calculated_hv:.4f} for IV filter mode.")
                else:
                    print(f"Warning: Could not calculate valid HV. Check historical data. Using placeholder.")
                    strategy_kwargs['underlying_hv'] = 0.20 # Fallback placeholder
            else:
                print(f"Warning: Not enough data ({len(historical_market_data)}) to calculate {hv_period}-day HV. Using placeholder.")
                strategy_kwargs['underlying_hv'] = 0.20 # Fallback placeholder

        # 6. Define Orders using the strategy
        orders_to_place = strategy.define_orders(
            signals=signals_df, 
            current_positions=current_positions_val,
            account_balance=account_balance_val,
            **strategy_kwargs
        )

        # 7. Submit Orders to Broker (Tradier in this case)
        if SUBMIT_ORDERS_TO_BROKER and orders_to_place:
            print(f"Submitting {len(orders_to_place)} orders to Tradier...")
            # Safety check: Ensure we are not submitting too many orders or too large orders
            # This is a basic check, more sophisticated risk management would be needed for live trading
            if len(orders_to_place) > 5: # Arbitrary limit
                print("Warning: Attempting to place more than 5 orders. SKIPPING for safety.")
                send_alert_to_api(f"Attempted to place {len(orders_to_place)} orders. Skipped for safety.", "CRITICAL")
            else:
                submitted_order_ids = tradier_client.submit_bulk_orders(orders_to_place)
                if submitted_order_ids:
                    print(f"Successfully submitted orders. IDs: {submitted_order_ids}")
                    send_alert_to_api(f"Successfully submitted {len(submitted_order_ids)} orders to Tradier. IDs: {submitted_order_ids}", "CRITICAL")
                    # TODO: Further logic to track these orders, confirm fills, etc.
                else:
                    print("Failed to submit orders or no orders were submitted.")
                    send_alert_to_api(f"Failed to submit orders to Tradier.", "ERROR")
        elif not orders_to_place:
            print("No orders defined by the strategy.")
            send_alert_to_api(f"No orders defined by strategy for {underlying_ticker_for_logging}.", "INFO")
        else:
            print("Order submission is DISABLED. No orders sent to broker.")
            # Log the orders that would have been placed
            if orders_to_place:
                print("Orders that would have been placed:")
                for order_detail in orders_to_place:
                    print(f"  - {order_detail.get('class','N/A')} {order_detail.get('symbol','N/A')} {order_detail.get('side','N/A')} Qty: {order_detail.get('quantity','N/A')} Type: {order_detail.get('type','N/A')} Price: {order_detail.get('price','N/A')}")
                    
                    # <<< LOG OPTION ORDER TO DATABASE >>>
                    signal_type_mapped = None
                    if order_detail.get('side') == 'buy_to_open':
                        signal_type_mapped = 'BUY'
                    elif order_detail.get('side') == 'sell_to_open':
                        signal_type_mapped = 'SELL'
                    
                    if signal_type_mapped: # Only log if it's an opening trade we've mapped
                        db_stock_options_logger.log_signal(
                            asset_symbol=order_detail.get('symbol'),
                            strategy_name=strategy.strategy_name, # strategy object is in scope here
                            signal_type=signal_type_mapped,
                            entry_price=order_detail.get('price'),
                            stop_loss_price=None, # Not directly available per leg here
                            take_profit_price=None, # Not directly available per leg here
                            short_ma=None, # Not applicable for this strategy
                            long_ma=None, # Not applicable for this strategy
                            telegram_status='NOT_ATTEMPTED' # Options cycle doesn't have detailed Telegram signal notifications
                        )

                send_alert_to_api(f"{len(orders_to_place)} orders defined but not submitted for {underlying_ticker_for_logging} (submission disabled).", "WARNING")

    except Exception as e:
        err_msg = f"CRITICAL ERROR in trading cycle for {underlying_ticker_for_logging} with {strategy_name_for_logging}: {e}"
        print(err_msg)
        import traceback
        traceback.print_exc()
        send_alert_to_api(err_msg, "CRITICAL")
    finally:
        if db_stock_options_logger:
            db_stock_options_logger.close_connection()
        print(f"--- Trading Cycle Ended for {underlying_ticker_for_logging} (in finally) ---")
        # Final alert already sent before this or in case of no new trade signal
        # If an exception occurred, it's logged above.
        # Consider if a generic "cycle finished" alert is needed here on top of specific ones.

# --- New Forex Trading Cycle with Interactive Brokers ---
def run_forex_trading_cycle():
    forex_pair_str = f"{FOREX_PAIR_SYMBOL}.{FOREX_PAIR_CURRENCY}"
    strategy_name = f"MA Crossover ({FOREX_STRATEGY_SHORT_WINDOW}/{FOREX_STRATEGY_LONG_WINDOW})"
    
    telegram_bot = TelegramNotifier(bot_token=TELEGRAM_BOT_TOKEN, chat_id=TELEGRAM_CHAT_ID)
    # <<< USE SPECIFIC DB NAME FOR FOREX >>>
    db_logger = DatabaseLogger(db_name="forex_signals.db") 
    openai_analyzer = OpenAIAnalyzer(api_key=OPENAI_API_KEY)

    alert_message_start = f"Forex trading cycle started for {forex_pair_str} with {strategy_name}."
    send_alert_to_api(alert_message_start, "INFO")
    telegram_bot.send_message(f"🤖 {alert_message_start}") # Also send to Telegram
    
    print(f"\n[{datetime.now()}] --- Starting Forex Trading Cycle for {forex_pair_str} ---")
    print(f"Order Submission to Broker: {'ENABLED' if SUBMIT_ORDERS_TO_BROKER else 'DISABLED'}")
    if SUBMIT_ORDERS_TO_BROKER:
        warning_msg = f"Order submission ENABLED for Forex trading with Interactive Brokers! Ensure you are on a PAPER account if testing."
        print(f"\n{'!'*60}\nWARNING: {warning_msg}\n{'!'*60}\n")
        send_alert_to_api(warning_msg, "CRITICAL")
        # time.sleep(5) # Give time to read warning

    # 1. Initialize IBClient and Strategy
    ib_client = IBClient()
    forex_strategy = MovingAverageCrossoverStrategy(
        short_window=FOREX_STRATEGY_SHORT_WINDOW,
        long_window=FOREX_STRATEGY_LONG_WINDOW,
        forex_pair=forex_pair_str
    )

    try:
        # 2. Connect to Interactive Brokers
        print(f"Connecting to Interactive Brokers at {IB_HOST}:{IB_PORT} with Client ID {IB_CLIENT_ID}...")
        ib_client.connect_to_ib(host=IB_HOST, port=IB_PORT, clientId=IB_CLIENT_ID)
        # Connection success is checked within connect_to_ib which raises ConnectionError on failure
        print("Successfully connected to Interactive Brokers.")
        send_alert_to_api("Successfully connected to Interactive Brokers for Forex trading.", "INFO")

        # 3. Get Forex Contract
        forex_contract = ib_client.get_forex_contract(symbol=FOREX_PAIR_SYMBOL, currency=FOREX_PAIR_CURRENCY)
        if not forex_contract:
            err_msg = "Could not create Forex contract. Exiting."
            print(err_msg)
            send_alert_to_api(err_msg, "CRITICAL")
            return

        # 4. Fetch Historical Data for Strategy Initialization
        # Duration and bar size for MAs. E.g., for 10/20 MA on 1-hour bars, need at least 20 hours + buffer.
        # If long_window is 20 on 1-hour bars, "1 D" (1 day) might be too short if it means 1 trading day (e.g. 8 bars).
        # "2 D" for 2 days, or specify hours e.g. "48 H" if API supports. Let's use days for simplicity.
        # For a 20-period MA, we need at least 20 bars. Let's get 50 bars to be safe.
        # If barSizeSetting is "1 hour", durationStr="2 D" might be too short for 50 bars depending on trading hours.
        # Let's try durationStr="5 D" barSizeSetting="1 hour" for FOREX_STRATEGY_LONG_WINDOW=20
        # Or, adjust bar size, e.g., "15 mins" for duration "1 D"
        # Choose appropriate duration and bar size for your strategy window.
        # Example: For a 20-period MA on 1 hour bars, fetch ~50 hours of data.
        # Using 1 day bars for initialization here for simplicity, adjust as needed.
        # For MA(10), MA(20) on hourly bars: fetch e.g., "3 D" of "1 hour" bars.
        hist_duration = f"{FOREX_STRATEGY_LONG_WINDOW + 30} D" # Get more than long_window days of daily data
        hist_bar_size = "1 day"
        print(f"Fetching historical data for {forex_pair_str}: {hist_duration} of {hist_bar_size} bars.")
        send_alert_to_api(f"Fetching historical data for {forex_pair_str} ({hist_duration} of {hist_bar_size}).", "INFO")
        
        if ib_client.request_historical_bars(reqId=HIST_DATA_REQ_ID, contract=forex_contract, durationStr=hist_duration, barSizeSetting=hist_bar_size, whatToShow="MIDPOINT"):
            historical_bars = ib_client.get_historical_bars(reqId=HIST_DATA_REQ_ID, timeout=20) # Increased timeout
            if historical_bars and len(historical_bars) >= forex_strategy.long_window:
                print(f"Successfully fetched {len(historical_bars)} historical bars.")
                send_alert_to_api(f"Fetched {len(historical_bars)} historical bars for {forex_pair_str}.", "INFO")
                if not forex_strategy.initialize_with_historical_data(historical_bars):
                    err_msg = "Failed to initialize Forex strategy with historical data. Exiting."
                    print(err_msg)
                    send_alert_to_api(err_msg, "ERROR")
                    return # Exit if strategy cannot be initialized
            else:
                err_msg = f"Failed to fetch sufficient historical data for {forex_pair_str} (need {forex_strategy.long_window}, got {len(historical_bars) if historical_bars else 0}). Exiting."
                print(err_msg)
                send_alert_to_api(err_msg, "ERROR")
                return
        else:
            err_msg = f"Failed to request historical data for {forex_pair_str}. Exiting."
            print(err_msg)
            send_alert_to_api(err_msg, "ERROR")
            return

        # 5. Request Streaming Tick Data
        # For Forex, empty genericTickList ("" or None) usually gives BID, ASK, LAST.
        # TickTypeEnum.BID (1), TickTypeEnum.ASK (2), TickTypeEnum.LAST (4)
        print(f"Requesting streaming market data for {forex_pair_str}...")
        if not ib_client.request_streaming_ticks(reqId=STREAM_DATA_REQ_ID, contract=forex_contract, genericTickList=""):
            err_msg = f"Failed to request streaming market data for {forex_pair_str}. Exiting."
            print(err_msg)
            send_alert_to_api(err_msg, "ERROR")
            return
        print("Streaming data request sent. Waiting for ticks...")
        send_alert_to_api(f"Streaming ticks for {forex_pair_str}. Bot is live.", "INFO")

        # 6. Main Trading Loop
        last_tick_processed_time = time.time()
        while True:
            current_ticks = ib_client.get_last_tick_data(STREAM_DATA_REQ_ID)
            
            # Use LAST price if available, otherwise MIDPOINT from BID/ASK
            # TickTypeEnum.LAST == 4, TickTypeEnum.BID == 1, TickTypeEnum.ASK == 2
            last_price = current_ticks.get(TickTypeEnum.LAST) 
            bid_price = current_ticks.get(TickTypeEnum.BID)
            ask_price = current_ticks.get(TickTypeEnum.ASK)

            current_price_for_signal = None
            if last_price is not None and last_price > 0:
                current_price_for_signal = last_price
            elif bid_price is not None and ask_price is not None and bid_price > 0 and ask_price > 0:
                current_price_for_signal = (bid_price + ask_price) / 2.0
            
            if current_price_for_signal:
                # Optional: check if this is a new tick (e.g. by comparing to previous or timestamp if available)
                # For simplicity, process if price is available.
                # In IB, tickPrice callback is triggered on new ticks. Here we are polling.
                print(f"[{datetime.now()}] {forex_pair_str} - Bid: {bid_price:.5f}, Ask: {ask_price:.5f}, Last: {last_price if last_price else 'N/A'}, SignalPrice: {current_price_for_signal:.5f}")
                
                signal = forex_strategy.on_new_tick(current_price_for_signal)
                
                if signal != "HOLD":
                    entry_price = current_price_for_signal
                    if signal.upper() == "BUY":
                        stop_loss = entry_price * (1 - FOREX_DEFAULT_SL_PERCENT)
                        take_profit = entry_price * (1 + FOREX_DEFAULT_TP_PERCENT)
                    elif signal.upper() == "SELL":
                        stop_loss = entry_price * (1 + FOREX_DEFAULT_SL_PERCENT)
                        take_profit = entry_price * (1 - FOREX_DEFAULT_TP_PERCENT)
                    else:
                        stop_loss = 0.0
                        take_profit = 0.0

                    prediction_details = (
                        f"Asset: {forex_pair_str}, Signal: {signal}, Entry: {entry_price:.5f}, "
                        f"SL: {stop_loss:.5f}, TP: {take_profit:.5f}"
                    )
                    send_alert_to_api(f"Forex Signal for {forex_pair_str}: {signal} at price {entry_price:.5f}", "WARNING")
                    print(f"--- FOREX SIGNAL: {signal} for {forex_pair_str} at {entry_price:.5f} ---")
                    
                    telegram_notified_status = "FAILED" # Default to FAILED
                    try:
                        telegram_prediction_message = telegram_bot.format_prediction_message(
                            asset=forex_pair_str,
                            signal=signal,
                            entry_price=entry_price,
                            stop_loss=stop_loss,
                            take_profit=take_profit,
                            strategy_name=strategy_name
                        )
                        if telegram_bot.send_message(telegram_prediction_message):
                            telegram_notified_status = "SUCCESS"
                    except Exception as e:
                        print(f"Error sending Telegram message during signal processing: {e}")
                        # telegram_notified_status remains "FAILED"

                    # Log the signal to the database
                    db_logger.log_signal(
                        asset_symbol=forex_pair_str,
                        strategy_name=strategy_name,
                        signal_type=signal,
                        entry_price=entry_price,
                        stop_loss_price=stop_loss,
                        take_profit_price=take_profit,
                        short_ma=forex_strategy.short_ma, # Get current MAs from strategy
                        long_ma=forex_strategy.long_ma,
                        telegram_status=telegram_notified_status
                    ) # <<< LOG SIGNAL TO DATABASE

                    # Get OpenAI Analysis (after logging the current signal)
                    if openai_analyzer.client: # Check if analyzer is active
                        recent_signals_for_ai = db_logger.get_recent_signals(limit=5)
                        if recent_signals_for_ai:
                            print(f"Sending {len(recent_signals_for_ai)} recent signals to OpenAI for analysis...")
                            ai_analysis = openai_analyzer.analyze_signals(recent_signals_for_ai, pair=forex_pair_str)
                            if ai_analysis:
                                print(f"AI Analysis for {forex_pair_str}: {ai_analysis}")
                                telegram_bot.send_message(f"🧠 *AI Analysis for {forex_pair_str}:*\n{ai_analysis}")
                            else:
                                print("No analysis returned from OpenAI.")
                        else:
                            print("Not enough recent signals in DB for AI analysis yet.")
                    else:
                        print("OpenAI Analyzer not active, skipping analysis.")

                    if SUBMIT_ORDERS_TO_BROKER:
                        print(f"Attempting to place {signal} order for {FOREX_ORDER_QUANTITY} units of {FOREX_PAIR_SYMBOL}.")
                        # Ensure order parameters are correct for your IB account and the specific Forex pair
                        # e.g., minimum quantity, price precision etc.
                        ib_client.place_forex_order(
                            contract=forex_contract, 
                            action=signal, # "BUY" or "SELL"
                            quantity=FOREX_ORDER_QUANTITY, 
                            order_type="MKT"
                        )
                        # Note: After placing an order, you'd typically wait for orderStatus and execDetails
                        # callbacks to confirm the fill and then update strategy.position.
                        # For this example, the strategy updates its internal position optimistically.
                        # A more robust system would handle partial fills, rejections, etc.
                        send_alert_to_api(f"Placed {signal} order for {FOREX_ORDER_QUANTITY} {forex_pair_str}. Check broker platform.", "CRITICAL")
                    else:
                        print(f"Order submission DISABLED. Signal {signal} not sent to broker.")
            else:
                # No new usable price tick since last check, or no tick data yet.
                if time.time() - last_tick_processed_time > 30: # Log if no ticks for a while
                    print(f"No new ticks for {forex_pair_str} in the last 30s. Current tick data: {current_ticks}")
                    send_alert_to_api(f"No new ticks for {forex_pair_str} in the last 30s.", "WARNING")
                    last_tick_processed_time = time.time()

            time.sleep(5) # Check for new ticks every 5 seconds. Adjust as needed.

    except ConnectionError as e:
        err_msg = f"IB Connection failed: {e}"
        print(err_msg)
        send_alert_to_api(err_msg, "CRITICAL")
    except KeyboardInterrupt:
        print("\nUser interrupt received for Forex cycle. Shutting down...")
        send_alert_to_api("Forex bot user interrupt. Shutting down.", "CRITICAL")
    except Exception as e:
        err_msg = f"An unexpected error occurred in Forex cycle: {e}"
        print(err_msg)
        import traceback
        traceback.print_exc()
        send_alert_to_api(f"{err_msg} - {traceback.format_exc()}", "CRITICAL")
    finally:
        if ib_client and ib_client.isConnected():
            print("Disconnecting from Interactive Brokers...")
            # Ensure specific request IDs used in this function are cancelled if active
            if ib_client.historical_data_end_flags.get(HIST_DATA_REQ_ID, False) == False and HIST_DATA_REQ_ID in ib_client.active_requests:
                 ib_client.cancelHistoricalData(HIST_DATA_REQ_ID)
                 if HIST_DATA_REQ_ID in ib_client.active_requests: ib_client.active_requests.remove(HIST_DATA_REQ_ID)
            if STREAM_DATA_REQ_ID in ib_client.active_requests:
                ib_client.cancel_market_data(STREAM_DATA_REQ_ID)
            ib_client.disconnect_from_ib()
            disconnect_msg = "Disconnected from Interactive Brokers."
            send_alert_to_api(disconnect_msg, "INFO")
            if telegram_bot and telegram_bot.bot: # Check if telegram_bot was initialized
                telegram_bot.send_message(f"🤖 {disconnect_msg} Bot shutting down Forex cycle.")
        else:
            print("IBClient was not connected or already disconnected at exit.")
        
        if db_logger: # <<< CLOSE DATABASE CONNECTION
            db_logger.close_connection()

        final_msg = "Forex trading cycle finished."
        print(final_msg)
        if 'telegram_bot' in locals() and telegram_bot.bot: # Check if telegram_bot was initialized before trying to send a message
            telegram_bot.send_message(f"🤖 {final_msg}")

# --- Main Execution --- 
if __name__ == "__main__":
    print("Starting Trading Bot...")
    # You can choose which cycle to run, or run them based on a flag/argument

    if FOREX_TRADING_ENABLED:
        print("Forex trading is ENABLED. Starting Forex cycle.")
        # Ensure all necessary configurations (FOREX_PAIR_SYMBOL, IB_PORT, etc.) are defined above.
        run_forex_trading_cycle()
    else:
        print("Forex trading is DISABLED. Attempting to start Options trading cycle.")
        # run_trading_cycle() # Uncomment to run the existing options cycle
        print("To run the options trading cycle, set FOREX_TRADING_ENABLED = False and uncomment run_trading_cycle() call.")

    print("Trading Bot finished or was interrupted.") 
