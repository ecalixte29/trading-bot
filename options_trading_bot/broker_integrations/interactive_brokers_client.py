from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.order import Order
from ibapi.ticktype import TickTypeEnum # For decoding tick types
import threading
import time
from collections import defaultdict

class IBClient(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        self.nextOrderId = None
        
        # Data storage
        self.historical_data = defaultdict(list) # reqId: [bars]
        self.historical_data_end_flags = defaultdict(bool) # reqId: True if ended
        self.current_ticks = defaultdict(dict) # reqId: {tickType: value}
        
        # For managing requests and data
        self.active_requests = set() # Store active reqIds

    # ---- EWrapper methods ----
    def nextValidId(self, orderId: int):
        super().nextValidId(orderId)
        self.nextOrderId = orderId
        print(f"NextValidId: {orderId}")

    def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=""):
        super().error(reqId, errorCode, errorString, advancedOrderRejectJson)
        if reqId == -1 and errorCode == 2104: # Market data farm connection is OK
            return
        # Ignore common informational messages if they are not critical errors
        # 2104: "Market data farm connection is OK"
        # 2106: "HMDS data farm connection is OK"
        # 2158: "Sec-def data farm connection is OK"
        # 2103: "Market data farm connection is broken" - might be important
        # 2105: "HMDS data farm connection is broken" - might be important
        # 2108: "Market data farm connection is inactive but should be available upon demand"
        informational_codes = [2104, 2106, 2158, 2108]
        if errorCode in informational_codes and reqId == -1: # System messages often have reqId -1
            print(f"IB Info: {errorString}")
            return
            
        print(f"Error: reqId={reqId}, errorCode={errorCode}, errorString='{errorString}', advancedOrderRejectJson='{advancedOrderRejectJson}'")
        if reqId in self.active_requests:
            # Potentially mark this request as failed or handle specific errors
            if errorCode == 162: # "Historical Market Data Service error message:HMDS query returned no data"
                print(f"No historical data for reqId {reqId}. Likely incorrect contract or date range.")
                self.historical_data_end_flags[reqId] = True # Mark as ended to unblock any waiting logic
            elif errorCode == 200: # "No security definition has been found for the request"
                print(f"No security definition for reqId {reqId}. Contract details might be incorrect.")
                if reqId in self.historical_data_end_flags: # If it's a historical data request
                     self.historical_data_end_flags[reqId] = True

    def connectionClosed(self):
        print("Connection closed")

    def connectAck(self):
        print("Connected to IB")

    # ---- Custom methods ----
    def run_loop(self):
        self.run()

    def connect_to_ib(self, host="127.0.0.1", port=7497, clientId=1):
        """
        Connects to TWS or IB Gateway.
        Default port for TWS is 7497 (live/paper with recent TWS versions).
        Older TWS paper might be 7496.
        Default port for IB Gateway is 4001 (live) or 4002 (paper).
        """
        if self.isConnected():
            print("Already connected.")
            return

        print(f"Connecting to IB on {host}:{port} with clientId {clientId}...")
        self.connect(host, port, clientId)

        # Start the message processing loop in a separate thread
        api_thread = threading.Thread(target=self.run_loop, daemon=True)
        api_thread.start()

        # Wait for connection to be established and nextValidId to be received
        max_wait_time = 10  # seconds
        start_time = time.time()
        while self.nextOrderId is None and time.time() - start_time < max_wait_time:
            time.sleep(0.1)
        
        if self.nextOrderId is None:
            print("Failed to get nextValidId in time. Disconnecting.")
            self.disconnect_from_ib()
            raise ConnectionError("Could not connect to IB or retrieve nextValidId.")
        else:
            print("Successfully connected and received nextValidId.")

    def disconnect_from_ib(self):
        if self.isConnected():
            print("Disconnecting from IB...")
            # Cancel all active market data requests
            # Create a copy of the set for iteration, as cancelMktData might modify underlying structures
            # or EWrapper callbacks might trigger during this.
            active_req_ids_copy = list(self.active_requests)
            for req_id in active_req_ids_copy:
                print(f"Cancelling market data for reqId: {req_id}")
                self.cancelMktData(req_id) 
                # Also cancel historical data if separate tracking is implemented
                # self.cancelHistoricalData(req_id) # This would be for historical data specific reqIds
            
            self.active_requests.clear()

            self.disconnect()
            # Wait for the connection to actually close
            time.sleep(1) 
            if not self.isConnected():
                print("Successfully disconnected.")
            else:
                # This can happen if the disconnect call doesn't immediately terminate the socket.
                print("Disconnect command sent, but still appears connected. The socket might take a moment to fully close.")
        else:
            print("Already disconnected.")

    def get_forex_contract(self, symbol: str, currency: str = "USD"):
        """Creates a Forex contract object."""
        contract = Contract()
        contract.symbol = symbol  # e.g., EUR
        contract.secType = "CASH"
        contract.currency = currency # e.g., USD for EUR.USD
        contract.exchange = "IDEALPRO" # Forex ECN
        return contract

    def place_forex_order(self, contract: Contract, action: str, quantity: float, order_type: str = "MKT", limit_price: float = 0.0):
        """Places a Forex order."""
        if self.nextOrderId is None:
            print("Error: nextOrderId is not set. Cannot place order.")
            # Potentially request next valid ID again or handle error
            # self.reqIds(-1) # This might be needed if connection was reset or similar
            return

        order = Order()
        order.action = action  # "BUY" or "SELL"
        order.totalQuantity = quantity
        order.orderType = order_type  # "MKT", "LMT", etc.
        if order_type == "LMT":
            order.lmtPrice = limit_price
        
        # For Forex, typically no need for TIF or other complex attributes for MKT orders
        # order.tif = "GTC" # Good Till Cancelled

        print(f"Placing order for {contract.symbol}.{contract.currency}: {action} {quantity} @ {order_type} {limit_price if order_type == 'LMT' else ''}")
        self.placeOrder(self.nextOrderId, contract, order)
        self.nextOrderId += 1 # Increment for the next order

    # Placeholder for market data handling
    def historicalData(self, reqId, bar):
        # print(f"HistoricalData: {reqId} - Date: {bar.date}, Open: {bar.open}, High: {bar.high}, Low: {bar.low}, Close: {bar.close}, Volume: {bar.volume}")
        self.historical_data[reqId].append({
            "date": bar.date,
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume
        })
        self.historical_data_end_flags[reqId] = False # Data is coming in

    def historicalDataEnd(self, reqId: int, start: str, end: str):
        super().historicalDataEnd(reqId, start, end)
        print(f"HistoricalDataEnd. ReqId: {reqId} from {start} to {end}. Bars received: {len(self.historical_data[reqId])}")
        self.historical_data_end_flags[reqId] = True
        if reqId in self.active_requests:
            self.active_requests.remove(reqId) # No longer active if historical data is done

    def tickPrice(self, reqId, tickType, price, attrib):
        super().tickPrice(reqId, tickType, price, attrib)
        tick_name = TickTypeEnum.idx2name.get(tickType, str(tickType))
        # print(f"TickPrice. ReqId: {reqId}, TickType: {tick_name}({tickType}), Price: {price}, Attribs: {attrib}")
        self.current_ticks[reqId][tickType] = price
        self.current_ticks[reqId][tick_name] = price # Store by name as well for convenience

    def tickSize(self, reqId, tickType, size):
        super().tickSize(reqId, tickType, size)
        tick_name = TickTypeEnum.idx2name.get(tickType, str(tickType))
        # print(f"TickSize. ReqId: {reqId}, TickType: {tick_name}({tickType}), Size: {size}")
        self.current_ticks[reqId][tickType] = size # Store size ticks as well
        self.current_ticks[reqId][f"{tick_name}_SIZE"] = size # e.g. BID_SIZE, ASK_SIZE

    def orderStatus(self, orderId, status, filled, remaining, avgFillPrice, permId, parentId, lastFillPrice, clientId, whyHeld, mktCapPrice):
        super().orderStatus(orderId, status, filled, remaining, avgFillPrice, permId, parentId, lastFillPrice, clientId, whyHeld, mktCapPrice)
        print(f"OrderStatus. Id: {orderId}, Status: {status}, Filled: {filled}, Remaining: {remaining}, AvgFillPrice: {avgFillPrice}")

    def openOrder(self, orderId, contract, order, orderState):
        super().openOrder(orderId, contract, order, orderState)
        print(f"OpenOrder. PermId: {order.permId} Id: {orderId}, Symbol: {contract.symbol}, SecType: {contract.secType}, Exchange: {contract.exchange}, Action: {order.action}, OrderType: {order.orderType}, TotalQuantity: {order.totalQuantity}, Status: {orderState.status}")

    def execDetails(self, reqId, contract, execution):
        super().execDetails(reqId, contract, execution)
        print(f"ExecDetails. ReqId: {reqId}, Symbol: {contract.symbol}, SecType: {contract.secType}, Currency: {contract.currency}, ExecId: {execution.execId}, OrderId: {execution.orderId}, Time: {execution.time}, Shares: {execution.shares}, Price: {execution.price}")

    # ---- New custom methods for data retrieval ----
    def request_historical_bars(self, reqId: int, contract: Contract, durationStr: str = "1 M", barSizeSetting: str = "1 day", whatToShow: str = "MIDPOINT", useRTH: int = 1):
        """
        Requests historical bar data.
        durationStr: e.g., "1 D", "1 W", "1 M", "1 Y"
        barSizeSetting: e.g., "1 min", "5 mins", "15 mins", "30 mins", "1 hour", "1 day"
        whatToShow: "TRADES", "MIDPOINT", "BID", "ASK"
        useRTH: 0 for all data, 1 for regular trading hours only.
        """
        if reqId in self.active_requests:
            print(f"Request ID {reqId} is already active. Please use a new ID or wait for completion.")
            return False
            
        print(f"Requesting historical data for {contract.symbol}.{contract.currency} with reqId {reqId}...")
        self.historical_data[reqId].clear() # Clear previous data for this reqId
        self.historical_data_end_flags[reqId] = False
        self.active_requests.add(reqId)

        # For Forex, endDate should be empty for current data
        # Format for endDate is "yyyymmdd hh:mm:ss TTT" where TTT is the optional timezone
        self.reqHistoricalData(reqId, contract, "", durationStr, barSizeSetting, whatToShow, useRTH, 1, False, [])
        return True

    def get_historical_bars(self, reqId: int, timeout:int = 10):
        """
        Retrieves historical bars after request_historical_bars has been called.
        Waits for historicalDataEnd signal or timeout.
        """
        start_time = time.time()
        while not self.historical_data_end_flags.get(reqId, False) and time.time() - start_time < timeout:
            time.sleep(0.1)
        
        if not self.historical_data_end_flags.get(reqId, False):
            print(f"Timeout waiting for historical data for reqId {reqId}.")
            if reqId in self.active_requests: # If it timed out but was considered active
                 self.cancelHistoricalData(reqId) # Attempt to cancel
                 self.active_requests.remove(reqId)
            return None
        
        return self.historical_data.get(reqId, [])

    def request_streaming_ticks(self, reqId: int, contract: Contract, genericTickList: str = "233", snapshot: bool = False, regulatorySnapshot: bool = False):
        """
        Requests streaming tick data.
        genericTickList: "233" for RTVolume, "" for Bid/Ask/Last. See IB docs for more.
                         For Forex, an empty string "" is often sufficient for Bid/Ask.
                         "100,101,104,106,165,221,225,233,236,258" for a wide range of general ticks.
                         For FX, often MIDPOINT (ticktype 87) if not using specific bid/ask.
                         Or use specific tick types like 1 (BID), 2 (ASK), 4 (LAST).
        """
        if reqId in self.active_requests:
            print(f"Request ID {reqId} is already active for streaming. Please use a new ID or cancel existing.")
            return False
        
        print(f"Requesting streaming market data for {contract.symbol}.{contract.currency} with reqId {reqId}")
        self.current_ticks[reqId].clear()
        self.active_requests.add(reqId)
        self.reqMktData(reqId, contract, genericTickList, snapshot, regulatorySnapshot, [])
        return True

    def get_last_tick_data(self, reqId: int):
        """Retrieves the most recent tick data for a given request ID."""
        return self.current_ticks.get(reqId, {})
        
    def cancel_market_data(self, reqId: int):
        print(f"Attempting to cancel market data for reqId: {reqId}")
        self.cancelMktData(reqId)
        if reqId in self.active_requests:
            self.active_requests.remove(reqId)
        # Clear stored data for this reqId
        if reqId in self.current_ticks:
            del self.current_ticks[reqId]
        if reqId in self.historical_data: # Also clear if it was a historical reqId being cancelled
            del self.historical_data[reqId]
            del self.historical_data_end_flags[reqId]


if __name__ == '__main__':
    # This is a simple example of how to use the client.
    # Ensure TWS or IB Gateway is running and API is enabled.
    # For TWS Paper: port 7497 (by default after recent updates, formerly 7496)
    # For IB Gateway Paper: port 4002
    
    client = IBClient()
    hist_req_id = 201
    stream_req_id = 101
    try:
        client.connect_to_ib(port=7497, clientId=1) # Adjust port/clientId as needed

        if client.isConnected() and client.nextOrderId is not None:
            eurusd_contract = client.get_forex_contract("EUR", "USD")
            
            print("\n--- Requesting Historical Data ---")
            if client.request_historical_bars(reqId=hist_req_id, contract=eurusd_contract, durationStr="5 D", barSizeSetting="1 hour", whatToShow="MIDPOINT"):
                bars = client.get_historical_bars(reqId=hist_req_id, timeout=15)
                if bars:
                    print(f"Received {len(bars)} historical bars for EUR.USD. First bar: {bars[0] if bars else 'N/A'}, Last bar: {bars[-1] if bars else 'N/A'}")
                else:
                    print("Could not retrieve historical bars for EUR.USD.")

            print("\n--- Requesting Streaming Market Data ---")
            # For Forex, an empty genericTickList often gives Bid/Ask. "233" is RTVolume.
            # TickTypes: 1 (BID), 2 (ASK), 4 (LAST), 6 (HIGH), 7 (LOW), 9 (CLOSE_PRICE)
            # Use empty string for genericTickList to get standard Bid/Ask/Last for FX.
            if client.request_streaming_ticks(reqId=stream_req_id, contract=eurusd_contract, genericTickList=""): # Empty for BID/ASK/LAST
                print(f"Requested streaming data for {eurusd_contract.symbol}.{eurusd_contract.currency}. Waiting for ticks...")
                # Let it stream for a bit
                for _ in range(10): # Show 10 updates
                    time.sleep(2)
                    ticks = client.get_last_tick_data(stream_req_id)
                    if ticks:
                        bid = ticks.get(TickTypeEnum.BID, "N/A") # or ticks.get(1, "N/A")
                        ask = ticks.get(TickTypeEnum.ASK, "N/A") # or ticks.get(2, "N/A")
                        last = ticks.get(TickTypeEnum.LAST, "N/A") # or ticks.get(4, "N/A")
                        print(f"EUR.USD Tick: Bid: {bid}, Ask: {ask}, Last: {last}")
                    else:
                        print("No new ticks received yet...")
            else:
                print(f"Failed to request streaming data for {eurusd_contract.symbol}.{eurusd_contract.currency}")


            # Example: Placing a test order (BUY EUR.USD)
            # print("\n--- Placing Test Order (ensure paper account!) ---")
            # client.place_forex_order(eurusd_contract, "BUY", 1000, "MKT") # Example: Buy 1000 EUR (check min size)
            
            print("\nBot is running. Press Ctrl+C to stop and disconnect.")
            # Keep the main thread alive to allow the API thread to process messages
            # In a real bot, this would be your main strategy loop.
            # For this example, we'll just wait if not running the tick loop above.
            if not client.get_last_tick_data(stream_req_id): # If tick loop didn't run
                 while True:
                    time.sleep(1)

    except ConnectionError as e:
        print(f"Connection failed: {e}")
    except KeyboardInterrupt:
        print("\nUser interrupt received.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if client.isConnected():
            print("Disconnecting before exit...")
            if hist_req_id in client.active_requests or client.historical_data_end_flags.get(hist_req_id, False) == False :
                 client.cancelHistoricalData(hist_req_id) # Ensure historical data request is cancelled if it was active or never finished
            if stream_req_id in client.active_requests:
                client.cancel_market_data(stream_req_id)
            client.disconnect_from_ib()
        else:
            print("Client was not connected or already disconnected.")
        print("Exiting.") 