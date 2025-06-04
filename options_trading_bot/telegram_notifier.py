import telegram
import os # Import os to access environment variables

class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str):
        if not bot_token or not chat_id:
            self.bot = None
            self.chat_id = None
            print("TelegramNotifier: Bot token or Chat ID is missing. Notifications will be disabled.")
            return
        try:
            self.bot = telegram.Bot(token=bot_token)
            self.chat_id = chat_id
            print(f"TelegramNotifier initialized for chat ID: {chat_id}")
        except Exception as e:
            self.bot = None
            self.chat_id = None
            print(f"TelegramNotifier: Error initializing Telegram Bot: {e}. Notifications will be disabled.")

    def send_message(self, message: str):
        if self.bot and self.chat_id:
            try:
                self.bot.send_message(chat_id=self.chat_id, text=message, parse_mode=telegram.ParseMode.MARKDOWN)
                print(f"Telegram message sent: {message}")
            except Exception as e:
                print(f"TelegramNotifier: Error sending message: {e}")
        else:
            # print(f"TelegramNotifier: Bot not initialized or Chat ID missing. Message not sent: {message}")
            pass # Silently fail if not configured, or log if preferred

    def format_prediction_message(self, asset: str, signal: str, entry_price: float, stop_loss: float, take_profit: float, strategy_name: str = "Strategy"):
        """Formats a trading prediction message in Markdown."""
        direction = "Long" if signal.upper() == "BUY" else "Short" if signal.upper() == "SELL" else signal.upper()
        
        message = (f"*Trading Prediction ({strategy_name})*\n\n"
                   f"*Asset:* `{asset}`\n"
                   f"*Signal:* *{direction}* ({signal.upper()})\n"
                   f"*Entry Price:* `{entry_price:.5f}`\n"
                   f"*Stop Loss:* `{stop_loss:.5f}`\n"
                   f"*Take Profit:* `{take_profit:.5f}`\n\n"
                   f"_Disclaimer: This is an automated prediction. Trade responsibly._")
        return message

# Example Usage (for testing purposes)
if __name__ == '__main__':
    # Replace with your actual bot token and chat ID
    # IMPORTANT: Do not commit your actual token and chat_id to version control.
    # Use environment variables or a config file for real applications.
    
    # Load from environment variables
    TEST_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
    TEST_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

    if not TEST_BOT_TOKEN or not TEST_CHAT_ID:
        print("Please ensure TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID environment variables are set to test.")
    else:
        print(f"Attempting to use Bot Token: ...{TEST_BOT_TOKEN[-4:] if TEST_BOT_TOKEN else 'N/A'} and Chat ID: {TEST_CHAT_ID}") # Print last 4 chars of token for verification
        notifier = TelegramNotifier(bot_token=TEST_BOT_TOKEN, chat_id=TEST_CHAT_ID)
        
        # Test basic message
        # print("Sending a basic test message...")
        # notifier.send_message("Hello from the Trading Bot! This is a *test* message using Markdown from an environment variable setup.")
        
        # Test prediction format
        print("Sending a formatted prediction test message...")
        prediction_msg = notifier.format_prediction_message(
            asset="EUR/USD (Test Env Var)",
            signal="BUY",
            entry_price=1.08550,
            stop_loss=1.08050,
            take_profit=1.09550,
            strategy_name="MA Crossover FX (Test Env Var)"
        )
        notifier.send_message(prediction_msg)
        
        print("Test message(s) sent (if configured correctly, environment variables are set, and bot has permissions for the chat).") 