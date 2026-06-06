from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = "8901883272:AAHC0WyX_aUyzqw57Go1MuiQE1rSEJL_9qA"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я финансовый бот.")

app = Application.builder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))

print("Бот запущен...")

app.run_polling()