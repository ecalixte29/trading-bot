import httpx # Using httpx for potential async later, and it's used by polygon-api-python
from polygon import RESTClient # Corrected: RESTClient is directly under polygon
# from polygon.models import Aggregate as Aggs # Old incorrect path
# from polygon.models import OptionContract  # Old incorrect path
from polygon.rest.models import Agg as Aggs # Corrected: Agg is in polygon.rest.models
from polygon.rest.models import OptionsContract as OptionContract # Try plural 'OptionsContract' and alias
import pandas as pd
from datetime import date, datetime, timedelta
from typing import List, Dict, Optional, Any

from ..config import POLYGON_API_KEY

class PolygonDataClient:
    """
    Client for interacting with the Polygon.io API to fetch market data.
    """
    def __init__(self, api_key: str = POLYGON_API_KEY):
        if not api_key:
            raise ValueError("Polygon API key is required.")
        self.client = RESTClient(api_key)
        print("PolygonDataClient initialized.")

    def get_underlying_price(self, ticker: str) -> Optional[float]:
        """
        Fetches the last trade price for a given stock ticker.
        """
        try:
            resp = self.client.get_last_trade(ticker)
            return resp.price
        except Exception as e:
            print(f"Error fetching last trade for {ticker}: {e}")
            return None

    def get_historical_aggregates(self, 
                                  ticker: str, 
                                  from_date: str, # YYYY-MM-DD
                                  to_date: str,   # YYYY-MM-DD
                                  timespan: str = "day", 
                                  multiplier: int = 1,
                                  limit: int = 5000 # Max 50000, default 5000 for safety
                                 ) -> pd.DataFrame:
        """
        Fetches historical OHLCV aggregates for a ticker.
        Args:
            ticker (str): The ticker symbol.
            from_date (str): Start date in YYYY-MM-DD format.
            to_date (str): End date in YYYY-MM-DD format.
            timespan (str): Size of the time window (e.g., 'minute', 'hour', 'day', 'week', 'month', 'quarter', 'year').
            multiplier (int): Multiplier for the timespan (e.g., 1 day, 5 minutes).
            limit (int): Max number of base aggregates.
        Returns:
            pd.DataFrame: DataFrame with columns ['timestamp', 'open', 'high', 'low', 'close', 'volume'], 
                          indexed by timestamp (converted to datetime objects).
                          Returns an empty DataFrame on error or if no data.
        """
        try:
            aggs_list: List[Aggs] = []
            for a in self.client.list_aggs(
                ticker=ticker,
                multiplier=multiplier,
                timespan=timespan,
                from_=from_date,
                to=to_date,
                limit=limit,
                adjusted=True # Typically, you want adjusted prices
            ):
                aggs_list.append(a)
            
            if not aggs_list:
                print(f"No historical data found for {ticker} from {from_date} to {to_date}.")
                return pd.DataFrame()

            df = pd.DataFrame([{
                'timestamp': pd.to_datetime(agg.timestamp, unit='ms'), # Convert from ms to datetime
                'open': agg.open,
                'high': agg.high,
                'low': agg.low,
                'close': agg.close,
                'volume': agg.volume
            } for agg in aggs_list])
            
            if not df.empty:
                df = df.set_index('timestamp').sort_index()
            return df
        except Exception as e:
            print(f"Error fetching historical aggregates for {ticker}: {e}")
            return pd.DataFrame()

    def get_options_chain_snapshot(self, 
                                 underlying_ticker: str, 
                                 expiration_date_gte: Optional[str] = None, # YYYY-MM-DD
                                 expiration_date_lte: Optional[str] = None, # YYYY-MM-DD
                                 strike_price_gte: Optional[float] = None,
                                 strike_price_lte: Optional[float] = None,
                                 contract_type: Optional[str] = None, # 'call' or 'put'
                                 limit: int = 250 # Max per page is 250 for options contracts
                                 ) -> List[Dict[str, Any]]:
        """
        Fetches the options chain for an underlying ticker and attempts to get snapshot data
        including Greeks and IV for each contract.
        
        Note: The standard options contracts list might not have all Greeks/IV.
        This method tries to get snapshots which are more detailed.
        However, fetching snapshots for a full chain can be very API intensive.
        Consider filtering contracts extensively before fetching snapshots if performance is an issue.
        Polygon's snapshot endpoint for a *single* contract is /v3/snapshot/options/{underlyingAsset}/{optionContract}
        There isn't a direct "chain with all details" endpoint typically.
        This method will list contracts and then try to fetch their snapshots if necessary.
        For simplicity in this first pass, we'll try to use data available from list_options_contracts and see if it's enough.
        Often, Greeks like delta and IV are part of the snapshot, not the contract listing itself.

        The `list_options_contracts` endpoint can filter by various parameters.
        The `get_snapshot_ticker` for an option symbol (`O:TICKERYYMMDDP00000000`) provides greeks.
        """
        chain_data = []
        processed_contracts = 0
        try:
            for contract_item in self.client.list_options_contracts(
                underlying_ticker=underlying_ticker,
                expiration_date_gte=expiration_date_gte,
                expiration_date_lte=expiration_date_lte,
                strike_price_gte=strike_price_gte,
                strike_price_lte=strike_price_lte,
                contract_type=contract_type,
                limit=limit, 
                order="asc",
                sort="expiration_date",
                expired=False # Typically want unexpired contracts
            ):
                if processed_contracts >= limit: # Apply the limit to the number of contracts processed for snapshots
                    print(f"Reached processing limit of {limit} contracts for snapshot fetching.")
                    break
                
                if not hasattr(contract_item, 'ticker') or not contract_item.ticker:
                    continue

                try:
                    snapshot = self.client.get_snapshot_option(underlying_asset=underlying_ticker, option_contract=contract_item.ticker)
                    
                    if snapshot and snapshot.details and snapshot.greeks and snapshot.last_quote:
                        if not all([
                            hasattr(snapshot.details, 'strike_price'),
                            hasattr(snapshot.details, 'expiration_date'),
                            hasattr(snapshot.details, 'contract_type'),
                            hasattr(snapshot.greeks, 'delta'),
                            hasattr(snapshot, 'implied_volatility'),
                            hasattr(snapshot.last_quote, 'bid'),
                            hasattr(snapshot.last_quote, 'ask'),
                            hasattr(snapshot.day, 'volume'),
                            hasattr(snapshot.details, 'open_interest')
                        ]):
                            continue
                            
                        iv = snapshot.implied_volatility if hasattr(snapshot, 'implied_volatility') and snapshot.implied_volatility is not None else 0.0
                        delta = snapshot.greeks.delta if hasattr(snapshot.greeks, 'delta') and snapshot.greeks.delta is not None else 0.0
                        bid = snapshot.last_quote.bid if hasattr(snapshot.last_quote, 'bid') and snapshot.last_quote.bid is not None else 0.0
                        ask = snapshot.last_quote.ask if hasattr(snapshot.last_quote, 'ask') and snapshot.last_quote.ask is not None else 0.0
                        volume = snapshot.day.volume if hasattr(snapshot.day, 'volume') and snapshot.day.volume is not None else 0
                        open_interest = snapshot.details.open_interest if hasattr(snapshot.details, 'open_interest') and snapshot.details.open_interest is not None else 0
                        
                        # Add check for non-zero ask to prevent issues later
                        if ask <= 0: 
                            # print(f"Skipping {contract_item.ticker} due to zero or negative ask price: {ask}")
                            continue

                        contract_data = {
                            'symbol': contract_item.ticker, 
                            'strike_price': snapshot.details.strike_price,
                            'expiration_date': snapshot.details.expiration_date, 
                            'type': snapshot.details.contract_type, 
                            'delta': delta,
                            'implied_volatility': iv,
                            'bid': bid,
                            'ask': ask,
                            'volume': volume,
                            'open_interest': open_interest,
                        }
                        chain_data.append(contract_data)
                        processed_contracts += 1
                except Exception as snap_e:
                    # Log this error appropriately in a real system
                    # print(f"Error fetching snapshot for option {contract_item.ticker}: {type(snap_e).__name__} - {snap_e}")
                    continue # Continue to next contract
            
            return chain_data
        except Exception as e:
            print(f"Error listing options contracts for {underlying_ticker}: {type(e).__name__} - {e}")
            return []

# Example Usage (for testing this client directly)
if __name__ == '__main__':
    if not POLYGON_API_KEY:
        print("Skipping PolygonDataClient tests as POLYGON_API_KEY is not set.")
    else:
        print("Running PolygonDataClient direct tests...")
        client = PolygonDataClient()

        ticker = "AAPL"
        price = client.get_underlying_price(ticker)
        print(f"Last price for {ticker}: {price if price else 'Not found'}")

        print("\n--- Testing Historical Aggregates ---")
        to_d = date.today().strftime("%Y-%m-%d")
        from_d = (date.today() - timedelta(days=120)).strftime("%Y-%m-%d") # Approx 4 months of daily data
        print(f"Fetching historical daily data for {ticker} from {from_d} to {to_d}")
        historical_data = client.get_historical_aggregates(ticker, from_date=from_d, to_date=to_d)
        if not historical_data.empty:
            print(f"Fetched {len(historical_data)} days of historical data for {ticker}.")
            print("Last 5 days:")
            print(historical_data.tail())
        else:
            print(f"Could not fetch historical data for {ticker}.")

        print("\n--- Testing Options Chain Snapshot ---")
        underlying = "SPY"
        exp_gte = (date.today() + timedelta(days=28)).strftime("%Y-%m-%d")
        exp_lte = (date.today() + timedelta(days=35)).strftime("%Y-%m-%d")
        print(f"Fetching options chain for {underlying}, DTE: {exp_gte} to {exp_lte}, Type: call, Limit: 3 processed contracts")
        options = client.get_options_chain_snapshot(
            underlying_ticker=underlying,
            expiration_date_gte=exp_gte,
            expiration_date_lte=exp_lte,
            contract_type='call',
            limit=3 
        )
        if options:
            print(f"Successfully fetched {len(options)} option contracts for {underlying}:")
            for i, opt in enumerate(options):
                print(f"  {i+1}. Symbol: {opt['symbol']}, Strike: {opt['strike_price']}, Exp: {opt['expiration_date']}, Type: {opt['type']}")
                print(f"     Delta: {opt['delta']:.4f}, IV: {opt.get('implied_volatility', 'N/A')}, Bid: {opt['bid']}, Ask: {opt['ask']}, Vol: {opt['volume']}, OI: {opt['open_interest']}")
        else:
            print(f"No options found or error fetching chain for {underlying}.") 