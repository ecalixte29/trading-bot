import yfinance as yf
import pandas as pd
from datetime import datetime

def fetch_historical_data_yfinance(ticker_symbol: str, start_date: str, end_date: str, interval: str = "1d") -> pd.DataFrame:
    """
    Fetches historical market data for a given ticker using yfinance.

    Args:
        ticker_symbol (str): The stock ticker symbol (e.g., 'AAPL', 'EURUSD=X' for Forex).
        start_date (str): The start date for historical data (YYYY-MM-DD).
        end_date (str): The end date for historical data (YYYY-MM-DD).
        interval (str): Data interval (e.g., '1m', '5m', '1h', '1d', '1wk').

    Returns:
        pd.DataFrame: A pandas DataFrame containing the historical data (OHLC, Volume, Dividends, Stock Splits).
                      Returns an empty DataFrame if an error occurs or no data is found.
    """
    try:
        ticker = yf.Ticker(ticker_symbol)
        # Note: yfinance end_date is exclusive for daily and higher intervals.
        # To make it inclusive for daily data, one might add 1 day to end_date if needed, 
        # but for API consistency, we'll use it as yfinance defines.
        hist_df = ticker.history(start=start_date, end=end_date, interval=interval)
        
        if hist_df.empty:
            print(f"yfinance: No data found for {ticker_symbol} from {start_date} to {end_date} with interval {interval}.")
            return pd.DataFrame()

        # Standardize column names slightly if needed (yfinance is usually lowercase: open, high, low, close, volume)
        hist_df.rename(columns={
            'Open': 'open',
            'High': 'high',
            'Low': 'low',
            'Close': 'close',
            'Volume': 'volume'
        }, inplace=True, errors='ignore') # errors='ignore' if some columns aren't present
        
        # Ensure the index is datetime type and timezone-naive for consistency, or handle timezone as needed.
        if not isinstance(hist_df.index, pd.DatetimeIndex):
            hist_df.index = pd.to_datetime(hist_df.index)
        hist_df.index = hist_df.index.tz_localize(None) # Make index timezone-naive

        print(f"yfinance: Successfully fetched {len(hist_df)} data points for {ticker_symbol}.")
        return hist_df

    except Exception as e:
        print(f"yfinance: Error fetching data for {ticker_symbol}: {e}")
        return pd.DataFrame()

if __name__ == '__main__':
    print("--- Testing yfinance data fetcher --- ")
    
    # Example 1: Stock data
    today = datetime.now()
    start_dt = (today - pd.Timedelta(days=90)).strftime("%Y-%m-%d")
    end_dt = today.strftime("%Y-%m-%d")
    
    print(f"\nFetching daily data for 'AAPL' from {start_dt} to {end_dt}...")
    aapl_data = fetch_historical_data_yfinance(ticker_symbol="AAPL", start_date=start_dt, end_date=end_dt, interval="1d")
    if not aapl_data.empty:
        print("AAPL Data (last 5 rows):")
        print(aapl_data.tail())
        print(f"Columns: {aapl_data.columns.tolist()}")
        print(f"Index type: {type(aapl_data.index)}")

    # Example 2: Forex data (EUR/USD)
    print(f"\nFetching hourly data for 'EURUSD=X' from 3 days ago to today...")
    forex_start_dt = (today - pd.Timedelta(days=3)).strftime("%Y-%m-%d") # yfinance might need more specific start for hourly
    # For intraday, yfinance typically has a limit on days back (e.g., 60 days for 1m-30m, 730 days for 1h)
    eurusd_data = fetch_historical_data_yfinance(ticker_symbol="EURUSD=X", start_date=forex_start_dt, end_date=end_dt, interval="1h")
    if not eurusd_data.empty:
        print("EURUSD=X Data (last 5 rows):")
        print(eurusd_data.tail())
    else:
        print("Could not fetch EURUSD=X data. Note: Intraday Forex data availability can vary.")

    # Example 3: Invalid ticker
    print(f"\nFetching data for 'INVALIDTICKER123'...")
    invalid_data = fetch_historical_data_yfinance(ticker_symbol="INVALIDTICKER123", start_date=start_dt, end_date=end_dt)
    if invalid_data.empty:
        print("Correctly returned empty DataFrame for invalid ticker.") 