import sqlite3
from datetime import datetime

class DatabaseLogger:
    def __init__(self, db_name="trading_signals.db"):
        self.db_name = db_name
        self.conn = None
        self.cursor = None
        self._connect()
        self._create_tables()

    def _connect(self):
        try:
            self.conn = sqlite3.connect(self.db_name)
            self.cursor = self.conn.cursor()
            print(f"Successfully connected to database: {self.db_name}")
        except sqlite3.Error as e:
            print(f"Error connecting to database {self.db_name}: {e}")
            # Potentially raise the error or handle it more gracefully
            # For now, if connection fails, methods will likely fail.

    def _create_tables(self):
        if not self.conn:
            print("Cannot create tables, no database connection.")
            return
        try:
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS trading_signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    asset_symbol TEXT NOT NULL,
                    strategy_name TEXT NOT NULL,
                    signal_type TEXT NOT NULL, -- 'BUY' or 'SELL'
                    entry_price REAL NOT NULL,
                    stop_loss_price REAL,
                    take_profit_price REAL,
                    short_ma_value REAL, -- Specific to MA Crossover, could be JSON for more generic data
                    long_ma_value REAL,  -- Specific to MA Crossover
                    telegram_notified_status TEXT -- e.g., 'SUCCESS', 'FAILED', 'NOT_ATTEMPTED'
                )
            """)
            self.conn.commit()
            print("Table 'trading_signals' checked/created successfully.")
        except sqlite3.Error as e:
            print(f"Error creating/checking 'trading_signals' table: {e}")

    def log_signal(self, asset_symbol: str, strategy_name: str, signal_type: str,
                   entry_price: float, stop_loss_price: float = None, take_profit_price: float = None,
                   short_ma: float = None, long_ma: float = None, telegram_status: str = "NOT_ATTEMPTED"):
        if not self.conn:
            print("Cannot log signal, no database connection.")
            return False
            
        timestamp_str = datetime.now().isoformat()
        try:
            self.cursor.execute("""
                INSERT INTO trading_signals (
                    timestamp, asset_symbol, strategy_name, signal_type, entry_price, 
                    stop_loss_price, take_profit_price, short_ma_value, long_ma_value, telegram_notified_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (timestamp_str, asset_symbol, strategy_name, signal_type, entry_price,
                  stop_loss_price, take_profit_price, short_ma, long_ma, telegram_status))
            self.conn.commit()
            print(f"Successfully logged signal for {asset_symbol}: {signal_type} at {entry_price}")
            return True
        except sqlite3.Error as e:
            print(f"Error logging signal: {e}")
            return False

    def get_recent_signals(self, limit: int = 10):
        if not self.conn:
            print("Cannot get recent signals, no database connection.")
            return []
        try:
            self.cursor.execute("""
                SELECT timestamp, asset_symbol, strategy_name, signal_type, entry_price, 
                       stop_loss_price, take_profit_price, short_ma_value, long_ma_value, telegram_notified_status
                FROM trading_signals
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,))
            signals = self.cursor.fetchall()
            # Convert list of tuples to list of dicts for easier use
            columns = [col[0] for col in self.cursor.description]
            return [dict(zip(columns, row)) for row in signals]
        except sqlite3.Error as e:
            print(f"Error fetching recent signals: {e}")
            return []

    def close_connection(self):
        if self.conn:
            self.conn.close()
            print(f"Database connection closed for {self.db_name}.")

    def __del__(self):
        # Ensure connection is closed when the object is destroyed
        self.close_connection()

if __name__ == '__main__':
    # Example Usage:
    db_logger = DatabaseLogger(db_name="test_trading_signals.db") # Use a test DB

    # Test logging a signal
    print("\nLogging a BUY signal...")
    db_logger.log_signal(
        asset_symbol="EUR.USD",
        strategy_name="MA Crossover (10/20)",
        signal_type="BUY",
        entry_price=1.08500,
        stop_loss_price=1.08000,
        take_profit_price=1.09500,
        short_ma=1.08450,
        long_ma=1.08400,
        telegram_status="SUCCESS"
    )

    print("\nLogging a SELL signal (minimal)...")
    db_logger.log_signal(
        asset_symbol="GBP.JPY",
        strategy_name="MA Crossover (5/15)",
        signal_type="SELL",
        entry_price=190.55,
        short_ma=190.60, # SL/TP/Telegram status omitted
        long_ma=190.65
    )
    
    # Test fetching recent signals
    print("\nFetching recent signals...")
    recent_signals = db_logger.get_recent_signals(limit=5)
    if recent_signals:
        print(f"Fetched {len(recent_signals)} recent signals:")
        for signal in recent_signals:
            print(signal)
    else:
        print("No recent signals found or error fetching.")
    
    # To verify, you would typically use an SQLite browser to check test_trading_signals.db
    # or add a query method to the class.
    print("\nExample usage complete. Check 'test_trading_signals.db'.")
    
    # Explicitly close (though __del__ handles it too)
    db_logger.close_connection() 