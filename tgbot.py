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
RATE, LVV, TRUCK, TRASH, SHIFT_DATE, SHIFT_START, SHIFT_END, SHIFT_BREAK = range(8)

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

async def get_lvv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()

    if text not in ["да", "нет"]:
        await update.message.reply_text("Ответьте: Да или Нет")
        return LVV

    context.user_data["lvv"] = (text == "да")

    keyboard = [["Да", "Нет"]]

    await update.message.reply_text(
        "Разгружаете машину?",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

    return TRUCK

async def get_truck(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()

    if text not in ["да", "нет"]:
        await update.message.reply_text("Ответьте: Да или Нет")
        return TRUCK

    context.user_data["truck"] = (text == "да")

    keyboard = [["Да", "Нет"]]

    await update.message.reply_text(
        "Сдаёте мусор?",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

    return TRASH

async def get_trash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()

    if text not in ["да", "нет"]:
        await update.message.reply_text("Ответьте: Да или Нет")
        return TRASH

    user_id = str(update.effective_user.id)
    users = load_users()

    users[user_id] = {
        "rate": context.user_data["rate"],
        "lvv": context.user_data["lvv"],
        "truck": context.user_data["truck"],
        "trash": (text == "да"),
        "shifts": []
    }

    save_users(users)

    await update.message.reply_text("Регистрация завершена ✅")
    return ConversationHandler.END

async def add_shift(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    users = load_users()

    if user_id not in users:
        await update.message.reply_text(
            "Сначала пройдите регистрацию через /start"
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "Введите дату смены (например: 07.06.2026)"
    )

    return SHIFT_DATE

async def get_shift_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    date = update.message.text

    context.user_data["shift_date"] = date

    await update.message.reply_text(
        "Введите время начала смены (например: 08:57)"
    )

    return SHIFT_START

async def get_shift_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    start_time = update.message.text

    context.user_data["shift_start"] = start_time

    await update.message.reply_text(
        "Введите время окончания смены (например: 17:49)"
    )

    return SHIFT_END

async def get_shift_end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    end_time = update.message.text

    context.user_data["shift_end"] = end_time

    keyboard = [
        ["0 пятнашек"],
        ["1 пятнашка"],
        ["2 пятнашки"]
    ]

    await update.message.reply_text(
        "Сколько пятнашек было за смену?",
        reply_markup=ReplyKeyboardMarkup(
            keyboard,
            resize_keyboard=True
        )
    )

    return SHIFT_BREAK

async def get_shift_break(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text not in ["0 пятнашек", "1 пятнашка", "2 пятнашки"]:
        await update.message.reply_text(
            "Выберите вариант кнопкой."
        )
        return SHIFT_BREAK

    if text == "0 пятнашек":
        breaks = 0
    elif text == "1 пятнашка":
        breaks = 1
    else:
        breaks = 2

    user_id = str(update.effective_user.id)

    users = load_users()

    shift = {
        "date": context.user_data["shift_date"],
        "start": context.user_data["shift_start"],
        "end": context.user_data["shift_end"],
        "breaks": breaks
    }

    users[user_id]["shifts"].append(shift)

    save_users(users)

    await update.message.reply_text(
        "Смена сохранена ✅"
    )

    return ConversationHandler.END

conv_handler = ConversationHandler(
    entry_points=[
        CommandHandler("start", start)
    ],
    states={
        RATE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_rate)
        ],
        LVV: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_lvv)
        ],
        TRUCK: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_truck)
        ],
        TRASH: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_trash)
        ],
        SHIFT_DATE: [
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                get_shift_date
            )
        ],
        SHIFT_START: [
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                get_shift_start
            )
        ],
        SHIFT_END: [
    MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        get_shift_end
            )
        ],
        SHIFT_BREAK: [
    MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        get_shift_break
            )
        ],
    },
    fallbacks=[]
)

shift_handler = ConversationHandler(
    entry_points=[
        CommandHandler("addshift", add_shift)
    ],

    states={
        SHIFT_DATE: [
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                get_shift_date
            )
        ],

        SHIFT_START: [
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                get_shift_start
            )
        ],

        SHIFT_END: [
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                get_shift_end
            )
        ],

        SHIFT_BREAK: [
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                get_shift_break
            )
        ]
    },

    fallbacks=[]
)

telegram_app.add_handler(conv_handler)
telegram_app.add_handler(shift_handler)

@app.on_event("startup")
async def on_startup():
    await telegram_app.initialize()


@app.post("/")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return {"ok": True}