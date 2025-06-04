import requests
import json
from typing import Optional, Dict, Any, List

from ..config import TRADIER_API_KEY, TRADIER_ACCOUNT_ID

# Configuration for Tradier API
TRADIER_API_BASE_URL_SANDBOX = "https://sandbox.tradier.com/v1/"
TRADIER_API_BASE_URL_PRODUCTION = "https://api.tradier.com/v1/"

# Set USE_SANDBOX to True for testing with Tradier's sandbox environment
# Set to False for live trading (USE WITH EXTREME CAUTION)
USE_SANDBOX = True 

TRADIER_BASE_URL = TRADIER_API_BASE_URL_SANDBOX if USE_SANDBOX else TRADIER_API_BASE_URL_PRODUCTION

class TradierClient:
    """
    Client for interacting with the Tradier brokerage API.
    """
    def __init__(self, api_key: str = TRADIER_API_KEY, account_id: str = TRADIER_ACCOUNT_ID):
        if not api_key:
            raise ValueError("Tradier API key is required.")
        if not account_id:
            raise ValueError("Tradier Account ID is required.")
        
        self.api_key = api_key
        self.account_id = account_id
        self.base_url = TRADIER_BASE_URL
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json"
        }
        env_type = "Sandbox" if USE_SANDBOX else "Production"
        print(f"TradierClient initialized for Account {self.account_id} using {env_type} environment.")

    def _make_request(self, method: str, endpoint: str, params: Optional[Dict] = None, data: Optional[Dict] = None) -> Optional[Dict[str, Any]]:
        """Helper function to make requests to Tradier API."""
        url = f"{self.base_url}{endpoint}"
        try:
            if method.upper() == 'GET':
                response = requests.get(url, headers=self.headers, params=params)
            elif method.upper() == 'POST':
                response = requests.post(url, headers=self.headers, params=params, data=data)
            elif method.upper() == 'DELETE':
                response = requests.delete(url, headers=self.headers, params=params)
            else:
                print(f"Unsupported HTTP method: {method}")
                return None

            response.raise_for_status() # Raise an exception for HTTP errors (4XX, 5XX)
            return response.json()
        except requests.exceptions.HTTPError as http_err:
            print(f"HTTP error occurred: {http_err} - {response.text}")
        except requests.exceptions.RequestException as req_err:
            print(f"Request exception occurred: {req_err}")
        except json.JSONDecodeError:
            print(f"Failed to decode JSON response: {response.text}")
        except Exception as e:
            print(f"An unexpected error occurred in _make_request: {e}")
        return None

    def get_account_balance(self) -> Optional[Dict[str, Any]]:
        """
        Retrieves the account balance.
        Endpoint: GET /accounts/{account_id}/balances
        """
        endpoint = f"accounts/{self.account_id}/balances"
        response_data = self._make_request("GET", endpoint)
        if response_data and 'balances' in response_data:
            return response_data['balances']
        elif response_data: # Handle cases where 'balances' might be top-level or nested differently
            return response_data 
        return None

    def get_account_positions(self) -> List[Dict[str, Any]]:
        """
        Retrieves the account's current positions.
        Endpoint: GET /accounts/{account_id}/positions
        """
        endpoint = f"accounts/{self.account_id}/positions"
        response_data = self._make_request("GET", endpoint)
        if response_data and 'positions' in response_data and isinstance(response_data['positions'], dict) and 'position' in response_data['positions']:
            # If 'position' is a list, return it. If it's a single dict (one position), wrap in a list.
            positions_data = response_data['positions']['position']
            if isinstance(positions_data, list):
                return positions_data
            elif isinstance(positions_data, dict):
                return [positions_data] 
            return [] # Should be list or dict
        elif response_data and response_data.get('positions') == 'null': # No positions
            return []
        return []

    def place_option_order(self, 
                             underlying_symbol: str, 
                             option_symbol: str, # OCC Format, e.g., AAPL231215C00175000
                             side: str,          # e.g., 'buy_to_open', 'sell_to_close'
                             quantity: int, 
                             order_type: str,    # e.g., 'market', 'limit', 'stop', 'stop_limit'
                             duration: str = 'day',  # 'day' or 'gtc'
                             price: Optional[float] = None, # Required for limit/stop_limit
                             stop: Optional[float] = None   # Required for stop/stop_limit
                            ) -> Optional[Dict[str, Any]]:
        """
        Places an option order.
        Endpoint: POST /accounts/{account_id}/orders

        Args:
            underlying_symbol (str): The underlying stock ticker (e.g., "AAPL").
            option_symbol (str): The OCC option symbol (e.g., "AAPL231215C00175000").
            side (str): Trade side: 'buy_to_open', 'sell_to_open', 'buy_to_close', 'sell_to_close'.
            quantity (int): Number of contracts.
            order_type (str): 'market', 'limit', 'stop', 'stop_limit'.
            duration (str): 'day' or 'gtc'.
            price (Optional[float]): Limit price for limit orders.
            stop (Optional[float]): Stop price for stop orders.
        """
        endpoint = f"accounts/{self.account_id}/orders"
        order_data = {
            'class': 'option',
            'symbol': underlying_symbol, # Tradier API often needs the underlying symbol here
            'option_symbol': option_symbol,
            'side': side,
            'quantity': quantity,
            'type': order_type,
            'duration': duration
        }

        if order_type.lower() in ['limit', 'stop_limit']:
            if price is None:
                print(f"Error: Price is required for {order_type} order.")
                return None
            order_data['price'] = price
        
        if order_type.lower() in ['stop', 'stop_limit']:
            if stop is None:
                print(f"Error: Stop price is required for {order_type} order.")
                return None
            order_data['stop'] = stop
        
        response = self._make_request("POST", endpoint, data=order_data)
        if response and 'order' in response:
            return response['order']
        elif response: # Error or unexpected format
            print(f"Order placement may have failed or returned unexpected format: {response}")
            return response 
        return None

    def get_order_status(self, order_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves the status of a specific order.
        Endpoint: GET /accounts/{account_id}/orders/{order_id}
        """
        endpoint = f"accounts/{self.account_id}/orders/{order_id}"
        response = self._make_request("GET", endpoint)
        if response and 'order' in response:
            return response['order']
        return response

    def cancel_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        """
        Cancels a pending order.
        Endpoint: DELETE /accounts/{account_id}/orders/{order_id}
        """
        endpoint = f"accounts/{self.account_id}/orders/{order_id}"
        response = self._make_request("DELETE", endpoint)
        if response and 'order' in response:
            return response['order'] # Successful cancellation usually returns order details
        return response


if __name__ == '__main__':
    if not TRADIER_API_KEY or not TRADIER_ACCOUNT_ID:
        print("Skipping TradierClient tests: TRADIER_API_KEY or TRADIER_ACCOUNT_ID not set in .env")
    else:
        print(f"Running TradierClient direct tests (Environment: {'Sandbox' if USE_SANDBOX else 'Production'})...")
        client = TradierClient()

        print("\n--- Testing Get Account Balance ---")
        balance = client.get_account_balance()
        if balance:
            print(f"Account Balance: {json.dumps(balance, indent=2)}")
            # Example: Accessing specific balance fields if structure is known
            if 'total_cash' in balance:
                print(f"Total Cash: {balance['total_cash']}")
            if 'option_bp' in balance:
                print(f"Option Buying Power: {balance['option_bp']}") 
        else:
            print("Could not retrieve account balance.")

        print("\n--- Testing Get Account Positions ---")
        positions = client.get_account_positions()
        if positions:
            print(f"Account Positions ({len(positions)}): {json.dumps(positions, indent=2)}")
        else:
            print("No positions found or error retrieving positions.")
        
        # --- Test Order Placement (Market Order - USE SANDBOX AND A CHEAP OPTION) ---
        # Note: To run this test, you need a valid underlying and option symbol for the Tradier sandbox.
        # The OCC option symbol format is TICKER<YYMMDD><C/P><StrikePrice*1000>
        # Example: SPY241220C00500000 (SPY Dec 20, 2024 $500 Call)
        # Ensure this option exists in the sandbox environment and your account can trade it.
        
        # --- Example Option Order (Buy to Open Market) --- 
        # THIS IS A LIVE ORDER IF NOT IN SANDBOX - BE CAREFUL
        # Only run if you are sure, and ideally in Sandbox with a dummy symbol/account
        test_order_placement = False # SET TO TRUE TO TEST - HIGHLY RECOMMENDED TO USE SANDBOX
        if test_order_placement and USE_SANDBOX:
            print("\n--- Testing Place Option Order (Market Buy to Open) ---")
            # Find a valid option symbol for testing in Tradier Sandbox. 
            # This might require looking at Tradier's documentation or using their option chain lookup.
            # For SPY, a very liquid underlying:
            underlying_sym_test = "SPY"
            # You would typically get this from an option chain lookup.
            # Placeholder: A near-term, slightly OTM call might be less risky for testing.
            # E.g., if SPY is 500, a 505 Call for next week.
            # The exact symbol will change daily/weekly.
            # It's best to use Tradier's API to look up a valid chain first if you need a dynamic test symbol.
            option_sym_test = "SPY240719C00550000" # EXAMPLE - THIS WILL EXPIRE/BECOME INVALID. REPLACE.
            
            print(f"Attempting to place order for 1 {option_sym_test} (BUY TO OPEN MARKET)")
            order_result = client.place_option_order(
                underlying_symbol=underlying_sym_test,
                option_symbol=option_sym_test, 
                side='buy_to_open',
                quantity=1,
                order_type='market',
                duration='day'
            )
            if order_result and order_result.get('id'):
                order_id = order_result['id']
                print(f"Order placed successfully. Order ID: {order_id}")
                print(f"Order details: {json.dumps(order_result, indent=2)}")
                
                # Test Get Order Status
                print("\n--- Testing Get Order Status ---")
                status = client.get_order_status(order_id)
                if status:
                    print(f"Status for order {order_id}: {json.dumps(status, indent=2)}")
                else:
                    print(f"Could not get status for order {order_id}.")

                # Test Cancel Order (only if it's likely still open, e.g. for GTCor DAY limit not filled)
                # For a market order, it might fill too quickly to cancel.
                # if status and status.get('status') == 'pending' or status.get('status') == 'open': 
                # print("\n--- Testing Cancel Order ---")
                # cancel_result = client.cancel_order(order_id)
                # if cancel_result:
                #     print(f"Cancel request for order {order_id} processed: {json.dumps(cancel_result, indent=2)}")
                # else:
                #     print(f"Could not cancel order {order_id}.")

            elif order_result: # Order placement failed but got some response
                 print(f"Order placement failed. Response: {json.dumps(order_result, indent=2)}")
            else:
                print("Order placement failed. No response or error in request.")
        elif test_order_placement and not USE_SANDBOX:
            print("\nWARNING: Skipping order placement test because USE_SANDBOX is False. Set to True to test in sandbox.")
        else:
            print("\nSkipping order placement test (test_order_placement is False).") 