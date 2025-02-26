import os
import logging
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from flask_cors import CORS
from telegram import Bot, Update
from telegram.ext import CommandHandler, CallbackContext, MessageHandler, Filters, Updater, Dispatcher
from upstox_api.api import Upstox, Session

# Load environment variables
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("7762384377:AAGBv8XH8afYgIIN4BMj_nKOVsj-yqYbhVY")
UPSTOX_API_KEY = os.getenv("98b99c27-06d7-4ba0-b77b-2fd134469c3f")
UPSTOX_API_SECRET = os.getenv("vkygkh19pb")
REDIRECT_URI = os.getenv("https://automatedtrading.onrender.com/callback")

app = Flask(__name__)

@app.route("/")
def home():
    return "Hello, Flask is running!"
# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Store user authentication tokens
user_tokens = {}

# ✅ Start authentication process
def start(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    auth_url = f"https://api.upstox.com/login/authorization/dialog?response_type=code&client_id={UPSTOX_API_KEY}&redirect_uri={REDIRECT_URI}"
    update.message.reply_text(f"Click [here]({auth_url}) to authenticate Upstox.", parse_mode="Markdown")

# ✅ Handle Upstox authentication callback
@app.route("/callback")
def callback():
    code = request.args.get("code")
    if not code:
        return "❌ Authentication failed! No code received."

    try:
        session = Session(UPSTOX_API_KEY)
        session.set_redirect_uri(REDIRECT_URI)
        session.set_api_secret(UPSTOX_API_SECRET)
        session.set_code(code)
        access_token = session.retrieve_access_token()
        
        user_tokens["access_token"] = access_token
        return "✅ Upstox Authentication Successful! You can now use auto-trading."

    except Exception as e:
        logger.error(f"Authentication Error: {e}")
        return f"❌ Error: {str(e)}"

# ✅ Auto-trading function
def auto_trade(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    if "access_token" not in user_tokens:
        update.message.reply_text("⚠️ Please authenticate first using /start.")
        return

    upstox = Upstox(UPSTOX_API_KEY, user_tokens["access_token"])
    upstox.get_master_contract('NSE_EQ')

    # Fetch user's balance and allocate trade amount
    balance = upstox.get_balance()["available_margin"]
    trade_amount = min(balance * 0.4, 5000)  # 40% of balance or max ₹5000

    update.message.reply_text("🔍 Analyzing market... 📊")

    try:
        # Example: Buy 5 shares of RELIANCE
        order = upstox.place_order(
            transaction_type="BUY",
            exchange="NSE_EQ",
            symbol="RELIANCE",
            quantity=5,
            order_type="LIMIT",
            price=upstox.get_live_feed("RELIANCE")["ltp"],
            product="MIS"
        )
        update.message.reply_text("✅ Trade placed: 5 shares of RELIANCE bought successfully!")
    except Exception as e:
        update.message.reply_text(f"❌ Trade failed: {str(e)}")

# ✅ Portfolio check function
def portfolio(update: Update, context: CallbackContext):
    if "access_token" not in user_tokens:
        update.message.reply_text("⚠️ Please authenticate first using /start.")
        return

    upstox = Upstox(UPSTOX_API_KEY, user_tokens["access_token"])
    holdings = upstox.get_holdings()

    if not holdings:
        update.message.reply_text("📉 No stocks in your portfolio.")
        return

    message = "📊 *Your Portfolio:*\n"
    total_pnl = 0

    for stock in holdings:
        symbol = stock["symbol"]
        quantity = stock["quantity"]
        avg_price = stock["average_price"]
        current_price = stock["last_traded_price"]
        pnl = (current_price - avg_price) * quantity
        total_pnl += pnl
        message += f"\n📌 {symbol} - {quantity} shares\n   Avg: ₹{avg_price} | LTP: ₹{current_price} | P/L: ₹{pnl:.2f}"

    message += f"\n\n💰 *Total P/L:* ₹{total_pnl:.2f}"
    update.message.reply_text(message, parse_mode="Markdown")

# ✅ Set up Telegram Bot Handlers
updater = Updater(token=TELEGRAM_BOT_TOKEN, use_context=True)
dispatcher = updater.dispatcher
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("auto_trade", auto_trade))
dispatcher.add_handler(CommandHandler("portfolio", portfolio))
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, lambda update, context: update.message.reply_text("Use /start to begin!")))

# ✅ Telegram Webhook
@app.route(f"/{TELEGRAM_BOT_TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(), bot)
    dispatcher.process_update(update)
    return "OK"

# ✅ Start Flask Server
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
