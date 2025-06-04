import os
from dotenv import load_dotenv

# Load .env file variables into environment
load_dotenv()

# --- API Keys ---
POLYGON_API_KEY = os.environ.get("POLYGON_API_KEY")
TRADIER_API_KEY = os.environ.get("TRADIER_API_KEY")
TRADIER_ACCOUNT_ID = os.environ.get("TRADIER_ACCOUNT_ID")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# --- Tradier Environment ---
# Default to "sandbox" if not specified in .env
TRADIER_ENVIRONMENT = os.environ.get("TRADIER_ENVIRONMENT", "sandbox")
USE_SANDBOX = TRADIER_ENVIRONMENT.lower() == "sandbox" # For TradierClient

# --- Interactive Brokers (IB) Connection Details ---
IB_HOST = os.environ.get("IB_HOST", "127.0.0.1")
# Choose which port to use based on your setup, or add more logic.
# For simplicity, let's assume TWS port is the default.
# You could also have separate variables in .env e.g. IB_ACTIVE_PORT
IB_PORT = int(os.environ.get("IB_PORT_TWS", 7497)) # Default to TWS port
IB_CLIENT_ID = int(os.environ.get("IB_CLIENT_ID_FOREX", 10)) # Default client ID

# --- Global Control Flags ---
# Convert string "True"/"False" from .env to boolean
SUBMIT_ORDERS_TO_BROKER_STR = os.environ.get("SUBMIT_ORDERS_TO_BROKER", "False")
SUBMIT_ORDERS_TO_BROKER = SUBMIT_ORDERS_TO_BROKER_STR.lower() in ['true', '1', 't', 'y', 'yes']

FOREX_TRADING_ENABLED_STR = os.environ.get("FOREX_TRADING_ENABLED", "True")
FOREX_TRADING_ENABLED = FOREX_TRADING_ENABLED_STR.lower() in ['true', '1', 't', 'y', 'yes']

# Optionally, add for options trading cycle if you want to control it via .env
# OPTIONS_TRADING_ENABLED_STR = os.environ.get("OPTIONS_TRADING_ENABLED", "False")
# OPTIONS_TRADING_ENABLED = OPTIONS_TRADING_ENABLED_STR.lower() in ['true', '1', 't', 'y', 'yes']


# --- Alert API URL ---
ALERT_API_URL = os.environ.get("ALERT_API_URL", "http://127.0.0.1:8001/alert")

# --- Forex Trading Configuration (can also be loaded from .env if preferred over main.py) ---
# These are still in main.py for now, but could be moved here if desired:
# FOREX_PAIR_SYMBOL, FOREX_PAIR_CURRENCY, FOREX_STRATEGY_SHORT_WINDOW, 
# FOREX_STRATEGY_LONG_WINDOW, FOREX_ORDER_QUANTITY, etc.
# Example:
# FOREX_PAIR_SYMBOL = os.environ.get("FOREX_PAIR_SYMBOL", "EUR")
# FOREX_ORDER_QUANTITY = int(os.environ.get("FOREX_ORDER_QUANTITY", 1000))

print("Configuration loaded:")
print(f"  Tradier Environment: {'Sandbox' if USE_SANDBOX else 'Production'}")
print(f"  Submit Orders: {SUBMIT_ORDERS_TO_BROKER}")
print(f"  Forex Trading Enabled: {FOREX_TRADING_ENABLED}")
# print(f"  Options Trading Enabled: {OPTIONS_TRADING_ENABLED}") # if you add it
print(f"  IB Host: {IB_HOST}, Port: {IB_PORT}, Client ID: {IB_CLIENT_ID}")

if POLYGON_API_KEY is None:
    print("Warning: POLYGON_API_KEY environment variable not set. Polygon.io functionality will be disabled.")

# You can add other global configurations here
# For example:
# DEFAULT_UNDERLYING_TICKER = "SPY" 