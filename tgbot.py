import os
import json
from fastapi import FastAPI, Request
from telegram import (
    Update, 
    ReplyKeyboardMarkup
)
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters
)

TOKEN = os.getenv("BOT_TOKEN")
RATE, LVV, TRUCK, TRASH = range(4)

app = FastAPI()

telegram_app = Application.builder().token(TOKEN).build()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет, чмоня! Я твой новый телеграм-бот."
        )


telegram_app.add_handler(
    CommandHandler("start", start)
    )


@app.on_event("startup")
async def on_startup():
    await telegram_app.initialize()


@app.post("/")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return {"ok": True}