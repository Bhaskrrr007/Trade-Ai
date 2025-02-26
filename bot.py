import os
import logging
import time
import numpy as np
from dotenv import load_dotenv
from flask import Flask, request
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from upstox_api.api import Upstox, Session

# Load environment variables
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("7762384377:AAGBv8XH8afYgIIN4BMj_nKOVsj-yqYbhVY")
UPSTOX_API_KEY = os.getenv("98b99c27-06d7-4ba0-b77b-2fd134469c3f")
UPSTOX_API_SECRET = os.getenv("vkygkh19pb")
REDIRECT_URI = os.getenv("https://automatedtrading.onrender.com")

# Initialize Flask app and Telegram bot
app = Flask(__name__)

# Logging Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Store user tokens securely with chat_id as key
user_tokens = {}

# Function to calculate Moving Average (MA) & Relative Strength Index (RSI)
def get_market_analysis(upstox, symbol):
    historical_data = upstox.get_ohlc(symbol=symbol, interval="15minute", days=5)
    close_prices = [data["close"] for data in historical_data[-50:]]

    # Calculate Moving Averages
    short_ma = np.mean(close_prices[-10:])
    long_ma = np.mean(close_prices[-30:])

    # Calculate RSI
    gains = [max(close_prices[i] - close_prices[i-1], 0) for i in range(1, len(close_prices))]
    losses = [max(close_prices[i-1] - close_prices[i], 0) for i in range(1, len(close_prices))]
    avg_gain = np.mean(gains[-14:])
    avg_loss = np.mean(losses[-14:])
    rsi = 100 - (100 / (1 + (avg_gain / avg_loss))) if avg_loss != 0 else 100

    return short_ma, long_ma, rsi

# Telegram Bot Command Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send authentication link for Upstox"""
    chat_id = update.message.chat_id
    auth_url = f"https://api.upstox.com/login/authorization/dialog?response_type=code&client_id={UPSTOX_API_KEY}&redirect_uri={REDIRECT_URI}"
    await context.bot.send_message(chat_id=chat_id, text=f"Click [here]({auth_url}) to authenticate Upstox.", parse_mode="Markdown")

async def trade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Execute trade with smart analysis"""
    chat_id = update.message.chat_id

    if chat_id not in user_tokens or "access_token" not in user_tokens[chat_id]:
        await context.bot.send_message(chat_id=chat_id, text="Please authenticate first using /start.")
        return

    upstox = Upstox(UPSTOX_API_KEY, user_tokens[chat_id]["access_token"])
    upstox.get_master_contract("NSE_EQ")

    symbol = "RELIANCE"
    short_ma, long_ma, rsi = get_market_analysis(upstox, symbol)

    if short_ma > long_ma and rsi > 55:
        try:
            balance = upstox.get_balance()["available_margin"]
            trade_amount = min(balance * 0.5, 10000)
            price = upstox.get_live_feed(symbol)["ltp"]
            quantity = int(trade_amount / price)

            await context.bot.send_message(chat_id=chat_id, text=f"📊 Market Analysis:\nShort MA: {short_ma:.2f}, Long MA: {long_ma:.2f}, RSI: {rsi:.2f}")
            await context.bot.send_message(chat_id=chat_id, text=f"🚀 Entering trade: Buying {quantity} shares of {symbol} at ₹{price:.2f}")

            order = upstox.place_order(
                transaction_type="BUY",
                exchange="NSE_EQ",
                symbol=symbol,
                quantity=quantity,
                order_type="LIMIT",
                price=price,
                product="MIS"
            )
            time.sleep(60)  # Wait for a minute

            exit_price = upstox.get_live_feed(symbol)["ltp"]
            if exit_price > price * 1.02:
                upstox.place_order(
                    transaction_type="SELL",
                    exchange="NSE_EQ",
                    symbol=symbol,
                    quantity=quantity,
                    order_type="LIMIT",
                    price=exit_price,
                    product="MIS"
                )
                await context.bot.send_message(chat_id=chat_id, text=f"✅ Trade Exited: Sold {quantity} shares at ₹{exit_price:.2f} (Profit!)")
            else:
                await context.bot.send_message(chat_id=chat_id, text=f"⚠️ Holding Position... Current Price: ₹{exit_price:.2f}")

        except Exception as e:
            logger.error(f"Trade execution failed: {str(e)}")
            await context.bot.send_message(chat_id=chat_id, text=f"❌ Trade Failed: {str(e)}")
    else:
        await context.bot.send_message(chat_id=chat_id, text="📉 Market conditions are not favorable. No trade taken.")

# Webhook Setup
async def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return "OK"

@app.route(f"/{TELEGRAM_BOT_TOKEN}", methods=["POST"])
def receive_update():
    update = Update.de_json(request.get_json(force=True), bot)
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

        user_tokens[code] = {"access_token": access_token}
        return "Upstox Authentication Successful! You can now use auto-trading."

    except Exception as e:
        logger.error(f"Authentication failed: {str(e)}")
        return f"Error: {str(e)}"

# Main entry point
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
