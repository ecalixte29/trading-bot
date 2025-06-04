import openai
import json

class OpenAIAnalyzer:
    def __init__(self, api_key: str):
        if not api_key:
            print("OpenAIAnalyzer: API key not provided. Analyzer will be disabled.")
            self.client = None
            return
        try:
            self.client = openai.OpenAI(api_key=api_key)
            print("OpenAIAnalyzer initialized successfully.")
        except Exception as e:
            print(f"OpenAIAnalyzer: Error initializing OpenAI client: {e}")
            self.client = None

    def analyze_signals(self, signals_data: list, pair: str, model="gpt-3.5-turbo"):
        if not self.client:
            return "OpenAI Analyzer is not initialized (e.g., missing API key)."
        if not signals_data:
            return "No signals data provided for analysis."

        # Convert signals data to a more readable format for the prompt
        formatted_signals = []
        for s in signals_data:
            formatted_signals.append(
                f"- Time: {s.get('timestamp')}, Asset: {s.get('asset_symbol')}, Strategy: {s.get('strategy_name')}, "
                f"Signal: {s.get('signal_type')} at {s.get('entry_price')}, ShortMA: {s.get('short_ma_value')}, LongMA: {s.get('long_ma_value')}"
            )
        
        prompt_signals_data = "\n".join(formatted_signals)

        system_prompt = (
            "You are a trading analysis assistant. Based on the recent trading signals provided, "
            "offer a brief (1-2 sentences) market sentiment analysis or a confidence score for the upcoming period for the specified Forex pair. "
            "Consider the sequence, frequency, and type of signals. Do not give trading advice or specific predictions."
        )
        
        user_prompt = (
            f"Here are the recent trading signals for {pair}:\n"
            f"{prompt_signals_data}\n\n"
            f"Based on these signals, what is your brief market sentiment analysis or confidence assessment for {pair}?"
        )

        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=100,
                temperature=0.5 # Keep it somewhat factual but allow for a little variation
            )
            analysis = response.choices[0].message.content.strip()
            print(f"OpenAI Analysis for {pair}: {analysis}")
            return analysis
        except openai.APIError as e:
            print(f"OpenAI API Error: {e}")
            return f"Error analyzing signals: {e}"
        except Exception as e:
            print(f"An unexpected error occurred during OpenAI analysis: {e}")
            return "An unexpected error occurred during analysis."

if __name__ == '__main__':
    # This example requires your OPENAI_API_KEY to be set as an environment variable
    # or replace os.environ.get("OPENAI_API_KEY") with your actual key for testing.
    # IMPORTANT: Do not commit your API key directly into the code in a real scenario.
    import os
    api_key_from_env = os.environ.get("OPENAI_API_KEY")

    if not api_key_from_env:
        print("OPENAI_API_KEY environment variable not set. Cannot run OpenAIAnalyzer example.")
    else:
        analyzer = OpenAIAnalyzer(api_key=api_key_from_env)
        if analyzer.client:
            # Simulate some signal data (replace with data from DatabaseLogger in a real scenario)
            dummy_signals = [
                {'timestamp': '2023-10-26T10:00:00', 'asset_symbol': 'EUR.USD', 'strategy_name': 'MA Crossover', 'signal_type': 'BUY', 'entry_price': 1.0550, 'short_ma_value': 1.0548, 'long_ma_value': 1.0545},
                {'timestamp': '2023-10-26T10:15:00', 'asset_symbol': 'EUR.USD', 'strategy_name': 'MA Crossover', 'signal_type': 'BUY', 'entry_price': 1.0560, 'short_ma_value': 1.0558, 'long_ma_value': 1.0555},
                {'timestamp': '2023-10-26T10:30:00', 'asset_symbol': 'EUR.USD', 'strategy_name': 'MA Crossover', 'signal_type': 'SELL', 'entry_price': 1.0555, 'short_ma_value': 1.0556, 'long_ma_value': 1.0558},
            ]
            print("\n--- Testing OpenAI Signal Analysis --- ")
            ai_feedback = analyzer.analyze_signals(dummy_signals, pair="EUR.USD")
            print(f"\nAI Feedback received:\n{ai_feedback}")

            # Test with empty signals
            print("\n--- Testing OpenAI Signal Analysis (No Signals) --- ")
            ai_feedback_no_signals = analyzer.analyze_signals([], pair="EUR.USD")
            print(f"\nAI Feedback (No Signals) received:\n{ai_feedback_no_signals}")

            # Test with a different pair (if you want)
            # dummy_signals_gbp = [
            #     {'timestamp': '2023-10-26T11:00:00', 'asset_symbol': 'GBP.USD', 'strategy_name': 'MA Crossover', 'signal_type': 'SELL', 'entry_price': 1.2150, 'short_ma_value': 1.2152, 'long_ma_value': 1.2155},
            # ]
            # print("\n--- Testing OpenAI Signal Analysis (GBP.USD) --- ")
            # ai_feedback_gbp = analyzer.analyze_signals(dummy_signals_gbp, pair="GBP.USD")
            # print(f"\nAI Feedback (GBP.USD) received:\n{ai_feedback_gbp}") 