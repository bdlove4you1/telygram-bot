import os
import time
import random
import logging
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, ConversationHandler, filters
from twilio.rest import Client

# Load environment
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
TWILIO_SID = os.getenv("TWILIO_SID")
TWILIO_TOKEN = os.getenv("TWILIO_TOKEN")
TWILIO_FROM = os.getenv("TWILIO_FROM")

logging.basicConfig(level=logging.INFO)

otp_store = {}
twilio_client = Client(TWILIO_SID, TWILIO_TOKEN)

# Telegram Application
app_tg = Application.builder().token(BOT_TOKEN).build()

# States
CHOOSING, WAIT_CONTACT, WAIT_PHONE, WAIT_OTP = range(4)

def generate_otp():
    return f"{random.randint(100000, 999999)}"

# --- Start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [["Share Contact ✅"], ["Verify with OTP (SMS) 🔐"], ["Cancel ❌"]]
    await update.message.reply_text(
        "Welcome! Choose verification method:",
        reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True)
    )
    return CHOOSING

# --- Choice ---
async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    if "contact" in text:
        btn = KeyboardButton(text="Send my phone", request_contact=True)
        kb = ReplyKeyboardMarkup([[btn], ["Back ⬅️"]], one_time_keyboard=True, resize_keyboard=True)
        await update.message.reply_text("Tap the button to share your phone.", reply_markup=kb)
        return WAIT_CONTACT
    elif "otp" in text:
        await update.message.reply_text("Send your phone number (+8801XXXX).", reply_markup=ReplyKeyboardRemove())
        return WAIT_PHONE
    else:
        await update.message.reply_text("Cancelled.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

# --- Contact ---
async def contact_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.contact.phone_number
    context.user_data["verified_phone"] = phone
    await update.message.reply_text(f"✅ Verified by contact: {phone}", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# --- Phone for OTP ---
async def phone_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    if not phone.startswith("+") or not phone[1:].isdigit():
        await update.message.reply_text("❌ Invalid format. Example: +8801XXXXXXXXX")
        return WAIT_PHONE

    user_id = update.effective_user.id
    otp = generate_otp()
    otp_store[user_id] = {"phone": phone, "otp": otp, "expires": int(time.time()) + 300}

    try:
        twilio_client.messages.create(body=f"Your verification code is {otp}", from_=TWILIO_FROM, to=phone)
        await update.message.reply_text("📩 OTP sent. Enter the 6-digit code.")
    except Exception as e:
        await update.message.reply_text(f"SMS failed: {e}")
        return ConversationHandler.END
    return WAIT_OTP

# --- OTP Check ---
async def otp_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    record = otp_store.get(user_id)

    if not record:
        await update.message.reply_text("No OTP request. Send /start.")
        return ConversationHandler.END
    if int(time.time()) > record["expires"]:
        del otp_store[user_id]
        await update.message.reply_text("⏰ OTP expired. Restart with /start.")
        return ConversationHandler.END
    if text == record["otp"]:
        context.user_data["verified_phone"] = record["phone"]
        del otp_store[user_id]
        await update.message.reply_text(f"✅ Verified: {context.user_data['verified_phone']}")
        return ConversationHandler.END
    else:
        await update.message.reply_text("❌ Wrong OTP. Try again.")
        return WAIT_OTP

# --- Cancel ---
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# Conversation
conv = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        CHOOSING: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_choice)],
        WAIT_CONTACT: [MessageHandler(filters.CONTACT, contact_received)],
        WAIT_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, phone_received)],
        WAIT_OTP: [MessageHandler(filters.Regex(r"^\d{6}$"), otp_check)],
    },
    fallbacks=[CommandHandler("cancel", cancel)]
)
app_tg.add_handler(conv)

if __name__ == "__main__":
    app_tg.run_polling()
