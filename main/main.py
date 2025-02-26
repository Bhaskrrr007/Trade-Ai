import os
import logging
import time
from dotenv import load_dotenv
from flask import Flask, request
from telegram import Bot, Update
from telegram.ext import Updater, CommandHandler, Dispatcher
from upstox_api.api import Upstox, Session
import numpy as np

# Load environment variables
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("7762384377:AAGBv8XH8afYgIIN4BMj_nKOVsj-yqYbhVY")
UPSTOX_API_KEY = os.getenv("98b99c27-06d7-4ba0-b77b-2fd134469c3f")
UPSTOX_API_SECRET = os.getenv("vkygkh19pb")
REDIRECT_URI = os.getenv("https://automatedtrading.onrender.com/callback")

# Initialize Flask app
app = Flask(__name__)
bot = Bot(token=TELEGRAM_BOT_TOKEN)

# Logging Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Store user tokens
user_tokens = {}

# Function to calculate Moving Average (MA) & Relative Strength Index (RSI)
def get_market_analysis(upstox, symbol):
    """Analyze stock trend using Moving Average & RSI"""
    historical_data = upstox.get_ohlc(symbol=symbol, interval="15minute", days=5)
    
    # Extract closing prices
    close_prices = [data["close"] for data in historical_data[-50:]]  # Last 50 candles
    
    # Calculate Moving Averages
    short_ma = np.mean(close_prices[-10:])  # 10-period MA
    long_ma = np.mean(close_prices[-30:])   # 30-period MA
    
    # Calculate RSI
    gains = [max(close_prices[i] - close_prices[i-1], 0) for i in range(1, len(close_prices))]
    losses = [max(close_prices[i-1] - close_prices[i], 0) for i in range(1, len(close_prices))]
    avg_gain = np.mean(gains[-14:])
    avg_loss = np.mean(losses[-14:])
    rsi = 100 - (100 / (1 + (avg_gain / avg_loss))) if avg_loss != 0 else 100
    
    return short_ma, long_ma, rsi

# Telegram Bot Command Handlers
def start(update: Update, context):
    """Send authentication link for Upstox"""
    chat_id = update.message.chat_id
    auth_url = f"https://api.upstox.com/login/authorization/dialog?response_type=code&client_id={UPSTOX_API_KEY}&redirect_uri={REDIRECT_URI}"
    update.message.reply_text(f"Click [here]({auth_url}) to authenticate Upstox.", parse_mode="Markdown")

def trade(update: Update, context):
    """Execute trade with smart analysis"""
    chat_id = update.message.chat_id
    if "access_token" not in user_tokens:
        update.message.reply_text("Please authenticate first using /start.")
        return

    upstox = Upstox(UPSTOX_API_KEY, user_tokens["access_token"])
    upstox.get_master_contract("NSE_EQ")

    symbol = "RELIANCE"  # Example trade
    short_ma, long_ma, rsi = get_market_analysis(upstox, symbol)
    
    # Smart Trade Conditions
    if short_ma > long_ma and rsi > 55:  # Bullish Trend Confirmation
        balance = upstox.get_balance()["available_margin"]
        trade_amount = min(balance * 0.5, 10000)  # Use 50% of balance, max ₹10K
        price = upstox.get_live_feed(symbol)["ltp"]
        quantity = int(trade_amount / price)  # Calculate position size

        update.message.reply_text(f"📊 Market Analysis:\nShort MA: {short_ma:.2f}, Long MA: {long_ma:.2f}, RSI: {rsi:.2f}")
        update.message.reply_text(f"🚀 Entering trade: Buying {quantity} shares of {symbol} at ₹{price:.2f}")

        try:
            order = upstox.place_order(
                transaction_type="BUY",
                exchange="NSE_EQ",
                symbol=symbol,
                quantity=quantity,
                order_type="LIMIT",
                price=price,
                product="MIS"
            )
            time.sleep(60)  # Wait for price movement (1 min)

            # Exit logic after profit (Trailing Stop-Loss)
            exit_price = upstox.get_live_feed(symbol)["ltp"]
            if exit_price > price * 1.02:  # 2% Profit Target
                upstox.place_order(
                    transaction_type="SELL",
                    exchange="NSE_EQ",
                    symbol=symbol,
                    quantity=quantity,
                    order_type="LIMIT",
                    price=exit_price,
                    product="MIS"
                )
                update.message.reply_text(f"✅ Trade Exited: Sold {quantity} shares at ₹{exit_price:.2f} (Profit!)")
            else:
                update.message.reply_text(f"⚠️ Holding Position... Current Price: ₹{exit_price:.2f}")

        except Exception as e:
            update.message.reply_text(f"❌ Trade Failed: {str(e)}")
    else:
        update.message.reply_text("📉 Market conditions are not favorable. No trade taken.")

# Telegram Bot Setup
updater = Updater(token=TELEGRAM_BOT_TOKEN, use_context=True)
dispatcher: Dispatcher = updater.dispatcher
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("trade", trade))

@app.route(f"/{TELEGRAM_BOT_TOKEN}", methods=["POST"])
def webhook():
    """Process Telegram updates"""
    update = Update.de_json(request.get_json(), bot)
    dispatcher.process_update(update)
    return "OK"

@app.route("/callback")
def callback():
    """Handle Upstox authentication callback"""
    code = request.args.get("code")
    if not code:
        return "Authentication failed! No code received."

    try:
        session = Session(UPSTOX_API_KEY)
        session.set_redirect_uri(REDIRECT_URI)
        session.set_api_secret(UPSTOX_API_SECRET)
        session.set_code(code)
        access_token = session.retrieve_access_token()
        
        user_tokens["access_token"] = access_token
        return "Upstox Authentication Successful! You can now use auto-trading."

    except Exception as e:
        return f"Error: {str(e)}"

# Gunicorn Entry Point
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
