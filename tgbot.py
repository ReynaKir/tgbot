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
    users = load_users()

    user_id = str(update.effective_user.id)

    if user_id in users:
        await update.message.reply_text(
            "Вы уже зарегистрированы."
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "Введите вашу почасовую ставку:"
    )

    return RATE

def load_users():
    try:
        with open("users.json", "r", encoding="utf-8") as file:
            return json.load(file)
    except:
        return {}
    
def save_users(data):
    with open("users.json", "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)





async def get_rate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rate = update.message.text

    try:
        rate = int(rate)
    except ValueError:
        await update.message.reply_text(
            "Введите ставку числом. Например: 350"
        )
        return RATE

    if rate < 100 or rate > 2000:
        await update.message.reply_text(
            "Введите корректную ставку (от 100 до 2000 рублей в час)."
        )
        return RATE

    context.user_data["rate"] = rate

    keyboard = [["Да", "Нет"]]

    await update.message.reply_text(
        "Получаете ЛВВ?",
        reply_markup=ReplyKeyboardMarkup(
            keyboard,
            resize_keyboard=True
        )
    )

    return LVV


conv_handler = ConversationHandler(
    entry_points=[
        CommandHandler("start", start)
    ],

    states={
        RATE: [
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                get_rate
            )
        ]
    },

    fallbacks=[]
)


telegram_app.add_handler(conv_handler)

@app.on_event("startup")
async def on_startup():
    await telegram_app.initialize()


@app.post("/")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return {"ok": True}