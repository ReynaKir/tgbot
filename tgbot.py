import os
import json
from datetime import datetime
from fastapi import FastAPI, Request
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN не найден. Добавьте переменную окружения BOT_TOKEN.")

USERS_FILE = "users.json"

(
    MODE,
    RATE,
    LVV,
    TRUCK,
    TRASH,
    SHIFT_DATE,
    SHIFT_START,
    SHIFT_END,
    SHIFT_BREAK,
    SHIFT_TRUCK,
    SHIFT_TRASH,
) = range(11)

app = FastAPI()
telegram_app = Application.builder().token(TOKEN).concurrent_updates(False).build()

MODE_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["Только часы"],
        ["Часы + ставка"],
        ["Полный расчёт"],
    ],
    resize_keyboard=True,
)

YES_NO_KEYBOARD = ReplyKeyboardMarkup(
    [["Да", "Нет"]],
    resize_keyboard=True,
)

BREAKS_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["0 пятнашек"],
        ["1 пятнашка"],
        ["2 пятнашки"],
    ],
    resize_keyboard=True,
)


def load_users():
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}


def save_users(data):
    with open(USERS_FILE, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)


def make_features(mode: str) -> dict:
    if mode == "hours_only":
        return {
            "hours": True,
            "salary": False,
            "tax": False,
            "lvv": False,
            "hour_bonus": False,
            "truck": False,
            "trash": False,
            "advance_salary": False,
        }

    if mode == "salary_simple":
        return {
            "hours": True,
            "salary": True,
            "tax": True,
            "lvv": False,
            "hour_bonus": False,
            "truck": False,
            "trash": False,
            "advance_salary": False,
        }

    return {
        "hours": True,
        "salary": True,
        "tax": True,
        "lvv": True,
        "hour_bonus": True,
        "truck": True,
        "trash": True,
        "advance_salary": True,
    }


def get_mode_name(mode: str) -> str:
    names = {
        "hours_only": "Только часы",
        "salary_simple": "Часы + ставка",
        "full_salary": "Полный расчёт",
    }
    return names.get(mode, mode)


def is_valid_date(text: str) -> bool:
    try:
        datetime.strptime(text, "%d.%m.%Y")
        return True
    except ValueError:
        return False


def is_valid_time(text: str) -> bool:
    try:
        datetime.strptime(text, "%H:%M")
        return True
    except ValueError:
        return False


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "Действие отменено.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


async def finish_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    users = load_users()

    mode = context.user_data["mode"]
    features = context.user_data["features"]

    users[user_id] = {
        "mode": mode,
        "features": features,
        "rate": context.user_data.get("rate"),
        "lvv": context.user_data.get("lvv", False),
        "truck": context.user_data.get("truck", False),
        "trash": context.user_data.get("trash", False),
        "shifts": [],
    }

    save_users(users)
    context.user_data.clear()

    await update.message.reply_text(
        f"Регистрация завершена ✅\n\nРежим: {get_mode_name(mode)}",
        reply_markup=ReplyKeyboardRemove(),
    )

    return ConversationHandler.END


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = load_users()
    user_id = str(update.effective_user.id)

    if user_id in users:
        mode = users[user_id].get("mode", "не указан")
        await update.message.reply_text(
            f"Вы уже зарегистрированы.\nВаш режим: {get_mode_name(mode)}"
        )
        return ConversationHandler.END

    context.user_data.clear()

    await update.message.reply_text(
        "Выберите, что вы хотите считать:",
        reply_markup=MODE_KEYBOARD,
    )

    return MODE


async def get_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    modes = {
        "Только часы": "hours_only",
        "Часы + ставка": "salary_simple",
        "Полный расчёт": "full_salary",
    }

    if text not in modes:
        await update.message.reply_text(
            "Выберите режим кнопкой.",
            reply_markup=MODE_KEYBOARD,
        )
        return MODE

    mode = modes[text]
    context.user_data["mode"] = mode
    context.user_data["features"] = make_features(mode)

    if mode == "hours_only":
        return await finish_registration(update, context)

    await update.message.reply_text(
        "Введите вашу почасовую ставку:",
        reply_markup=ReplyKeyboardRemove(),
    )

    return RATE


async def get_rate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        rate = int(update.message.text)
    except ValueError:
        await update.message.reply_text("Введите ставку числом. Например: 350")
        return RATE

    if rate < 100 or rate > 2000:
        await update.message.reply_text(
            "Введите корректную ставку от 100 до 2000 рублей в час."
        )
        return RATE

    context.user_data["rate"] = rate

    features = context.user_data["features"]

    if not features.get("lvv", False):
        return await finish_registration(update, context)

    await update.message.reply_text(
        "Получаете ЛВВ?",
        reply_markup=YES_NO_KEYBOARD,
    )

    return LVV


async def get_lvv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()

    if text not in ["да", "нет"]:
        await update.message.reply_text("Ответьте: Да или Нет")
        return LVV

    context.user_data["lvv"] = text == "да"

    await update.message.reply_text(
        "Разгружаете машину?",
        reply_markup=YES_NO_KEYBOARD,
    )

    return TRUCK


async def get_truck(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()

    if text not in ["да", "нет"]:
        await update.message.reply_text("Ответьте: Да или Нет")
        return TRUCK

    context.user_data["truck"] = text == "да"

    await update.message.reply_text(
        "Сдаёте мусор?",
        reply_markup=YES_NO_KEYBOARD,
    )

    return TRASH


async def get_trash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()

    if text not in ["да", "нет"]:
        await update.message.reply_text("Ответьте: Да или Нет")
        return TRASH

    context.user_data["trash"] = text == "да"

    return await finish_registration(update, context)


async def add_shift(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    users = load_users()

    if user_id not in users:
        await update.message.reply_text("Сначала пройдите регистрацию через /start")
        return ConversationHandler.END

    context.user_data.clear()

    await update.message.reply_text(
        "Введите дату смены в формате ДД.ММ.ГГГГ. Например: 09.06.2026"
    )

    return SHIFT_DATE


async def get_shift_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    date_text = update.message.text

    if not is_valid_date(date_text):
        await update.message.reply_text(
            "Введите дату в формате ДД.ММ.ГГГГ. Например: 09.06.2026"
        )
        return SHIFT_DATE

    context.user_data["shift_date"] = date_text

    await update.message.reply_text(
        "Введите время начала смены в формате ЧЧ:ММ. Например: 08:57"
    )

    return SHIFT_START


async def get_shift_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    start_time = update.message.text

    if not is_valid_time(start_time):
        await update.message.reply_text(
            "Введите время в формате ЧЧ:ММ. Например: 08:57"
        )
        return SHIFT_START

    context.user_data["shift_start"] = start_time

    await update.message.reply_text(
        "Введите время окончания смены в формате ЧЧ:ММ. Например: 17:49"
    )

    return SHIFT_END


async def get_shift_end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    end_time = update.message.text

    if not is_valid_time(end_time):
        await update.message.reply_text(
            "Введите время в формате ЧЧ:ММ. Например: 17:49"
        )
        return SHIFT_END

    context.user_data["shift_end"] = end_time

    await update.message.reply_text(
        "Сколько пятнашек было за смену?",
        reply_markup=BREAKS_KEYBOARD,
    )

    return SHIFT_BREAK


async def get_shift_break(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text not in ["0 пятнашек", "1 пятнашка", "2 пятнашки"]:
        await update.message.reply_text(
            "Выберите вариант кнопкой.",
            reply_markup=BREAKS_KEYBOARD,
        )
        return SHIFT_BREAK

    if text == "0 пятнашек":
        breaks = 0
    elif text == "1 пятнашка":
        breaks = 1
    else:
        breaks = 2

    context.user_data["shift_breaks"] = breaks

    user_id = str(update.effective_user.id)
    users = load_users()
    user = users[user_id]

    if user.get("features", {}).get("truck", False) and user.get("truck", False):
        await update.message.reply_text(
            "Была разгрузка машины за эту смену?",
            reply_markup=YES_NO_KEYBOARD,
        )
        return SHIFT_TRUCK

    context.user_data["truck_done"] = False

    if user.get("features", {}).get("trash", False) and user.get("trash", False):
        await update.message.reply_text(
            "Была сдача мусора за эту смену?",
            reply_markup=YES_NO_KEYBOARD,
        )
        return SHIFT_TRASH

    context.user_data["trash_done"] = False

    return await save_shift(update, context)


async def get_shift_truck(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()

    if text not in ["да", "нет"]:
        await update.message.reply_text("Ответьте: Да или Нет")
        return SHIFT_TRUCK

    context.user_data["truck_done"] = text == "да"

    user_id = str(update.effective_user.id)
    users = load_users()
    user = users[user_id]

    if user.get("features", {}).get("trash", False) and user.get("trash", False):
        await update.message.reply_text(
            "Была сдача мусора за эту смену?",
            reply_markup=YES_NO_KEYBOARD,
        )
        return SHIFT_TRASH

    context.user_data["trash_done"] = False

    return await save_shift(update, context)


async def get_shift_trash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()

    if text not in ["да", "нет"]:
        await update.message.reply_text("Ответьте: Да или Нет")
        return SHIFT_TRASH

    context.user_data["trash_done"] = text == "да"

    return await save_shift(update, context)


async def save_shift(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    users = load_users()
    user = users[user_id]

    shift = {
        "date": context.user_data["shift_date"],
        "start": context.user_data["shift_start"],
        "end": context.user_data["shift_end"],
        "breaks": context.user_data["shift_breaks"],
        "truck_done": context.user_data.get("truck_done", False),
        "trash_done": context.user_data.get("trash_done", False),
    }

    if user.get("rate") is not None:
        shift["rate"] = user["rate"]

    users[user_id]["shifts"].append(shift)
    save_users(users)

    context.user_data.clear()

    text = (
        "Смена сохранена ✅\n\n"
        f"Дата: {shift['date']}\n"
        f"Начало: {shift['start']}\n"
        f"Конец: {shift['end']}\n"
        f"Пятнашек: {shift['breaks']}"
    )

    if user.get("features", {}).get("truck", False) and user.get("truck", False):
        text += f"\nРазгрузка машины: {'Да' if shift['truck_done'] else 'Нет'}"

    if user.get("features", {}).get("trash", False) and user.get("trash", False):
        text += f"\nСдача мусора: {'Да' if shift['trash_done'] else 'Нет'}"

    await update.message.reply_text(
        text,
        reply_markup=ReplyKeyboardRemove(),
    )

    return ConversationHandler.END


conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        MODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_mode)],
        RATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_rate)],
        LVV: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_lvv)],
        TRUCK: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_truck)],
        TRASH: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_trash)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)

shift_handler = ConversationHandler(
    entry_points=[CommandHandler("addshift", add_shift)],
    states={
        SHIFT_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_shift_date)],
        SHIFT_START: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_shift_start)],
        SHIFT_END: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_shift_end)],
        SHIFT_BREAK: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_shift_break)],
        SHIFT_TRUCK: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_shift_truck)],
        SHIFT_TRASH: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_shift_trash)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
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
