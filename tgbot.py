import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = os.getenv("BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я финансовый бот.")

app = Application.builder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))

print("Бот запущен...")

app.run_polling()