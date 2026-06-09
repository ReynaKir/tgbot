import os
import json
from datetime import datetime, timedelta

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
    SETTINGS_CHOICE,
    SETTINGS_RATE,
    SETTINGS_LVV,
    SETTINGS_TRUCK,
    SETTINGS_TRASH,
    SETTINGS_MODE,
) = range(17)


app = FastAPI()
telegram_app = Application.builder().token(TOKEN).build()


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

MAIN_MENU_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["➕ Добавить смену"],
        ["📊 Статистика", "💰 Зарплата"],
        ["👤 Профиль", "⚙️ Настройки"],
    ],
    resize_keyboard=True,
)

SETTINGS_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["Изменить режим"],
        ["Изменить ставку"],
        ["Изменить ЛВВ"],
        ["Изменить машину"],
        ["Изменить мусор"],
        ["⬅️ Назад"],
    ],
    resize_keyboard=True,
)


TAX_RATE = 0.13
TRUCK_PAY = 1150
TRASH_PAY = 100
LVV_BONUS = 16000


# ---------- Работа с users.json ----------


def load_users():
    try:
        with open("users.json", "r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}


def save_users(data):
    with open("users.json", "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)


# ---------- Режимы и настройки ----------


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


def yes_no_text(value: bool) -> str:
    if value:
        return "Да"
    return "Нет"


def build_settings_text(user: dict) -> str:
    mode = user.get("mode", "не указан")
    features = user.get("features", {})
    rate = user.get("rate")

    if rate is None:
        rate_text = "не указана"
    else:
        rate_text = f"{rate} ₽/час"

    if not features.get("salary", False):
        rate_text += " (не используется в режиме только часов)"

    if features.get("lvv", False):
        lvv_text = yes_no_text(user.get("lvv", False))
    else:
        lvv_text = "не используется в этом режиме"

    if features.get("truck", False):
        truck_text = yes_no_text(user.get("truck", False))
    else:
        truck_text = "не используется в этом режиме"

    if features.get("trash", False):
        trash_text = yes_no_text(user.get("trash", False))
    else:
        trash_text = "не используется в этом режиме"

    text = (
        "⚙️ Настройки\n\n"
        f"Режим: {get_mode_name(mode)}\n"
        f"Ставка: {rate_text}\n"
        f"ЛВВ: {lvv_text}\n"
        f"Разгрузка машины: {truck_text}\n"
        f"Сдача мусора: {trash_text}\n\n"
        "Что хотите изменить?"
    )

    return text


# ---------- Проверка даты и времени ----------


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


# ---------- Расчёт времени ----------


def parse_shift_datetime(date_text: str, time_text: str):
    return datetime.strptime(
        f"{date_text} {time_text}",
        "%d.%m.%Y %H:%M",
    )


def get_shift_datetimes(shift: dict):
    start = parse_shift_datetime(shift["date"], shift["start"])
    end = parse_shift_datetime(shift["date"], shift["end"])

    if end <= start:
        end += timedelta(days=1)

    return start, end


def get_shift_paid_minutes(shift: dict) -> int:
    start, end = get_shift_datetimes(shift)

    total_minutes = int((end - start).total_seconds() // 60)

    break_minutes = 30
    fifteen_minutes = int(shift.get("breaks", 0)) * 15

    paid_minutes = total_minutes - break_minutes - fifteen_minutes

    return max(0, paid_minutes)


def format_minutes(minutes: int) -> str:
    hours = minutes // 60
    mins = minutes % 60

    return f"{hours} ч {mins:02d} мин"


def get_next_bonus_text(total_minutes: int) -> str:
    total_hours = total_minutes / 60

    if total_hours < 50:
        left_minutes = 50 * 60 - total_minutes
        return f"До премии 50 ₽/час осталось: {format_minutes(left_minutes)}"

    if total_hours < 80:
        left_minutes = 80 * 60 - total_minutes
        return f"До премии 100 ₽/час осталось: {format_minutes(left_minutes)}"

    if total_hours < 120:
        left_minutes = 120 * 60 - total_minutes
        return f"До премии 150 ₽/час осталось: {format_minutes(left_minutes)}"

    return "Максимальный этап премии уже достигнут ✅"


def get_month_from_stats_command(text: str):
    parts = text.split()
    today = datetime.now()

    if not text.startswith("/stats"):
        return today.month, today.year

    if len(parts) == 1:
        return today.month, today.year

    try:
        month_text = parts[1]
        month, year = month_text.split(".")
        month = int(month)
        year = int(year)

        if month < 1 or month > 12:
            return None

        return month, year

    except ValueError:
        return None


def shift_belongs_to_month(shift: dict, month: int, year: int) -> bool:
    shift_date = datetime.strptime(shift["date"], "%d.%m.%Y")

    return shift_date.month == month and shift_date.year == year


# ---------- Расчёт зарплаты ----------


def get_hours_bonus_rate(total_minutes: int) -> int:
    total_hours = total_minutes / 60

    if total_hours >= 120:
        return 150

    if total_hours >= 80:
        return 100

    if total_hours >= 50:
        return 50

    return 0


def get_shift_base_money(shift: dict, user: dict) -> float:
    paid_minutes = get_shift_paid_minutes(shift)
    rate = shift.get("rate", user.get("rate"))

    if rate is None:
        return 0

    return paid_minutes / 60 * rate


def get_shift_day(shift: dict) -> int:
    shift_date = datetime.strptime(shift["date"], "%d.%m.%Y")
    return shift_date.day


def get_month_shifts(user: dict, month: int, year: int) -> list:
    result = []

    for shift in user.get("shifts", []):
        if shift_belongs_to_month(shift, month, year):
            result.append(shift)

    return result


def get_salary_month_from_command(text: str):
    parts = text.split()
    today = datetime.now()

    if not text.startswith("/salary"):
        return today.month, today.year

    if len(parts) == 1:
        return today.month, today.year

    try:
        month_text = parts[1]
        month, year = month_text.split(".")
        month = int(month)
        year = int(year)

        if month < 1 or month > 12:
            return None

        return month, year

    except ValueError:
        return None


def calculate_salary(user: dict, month: int, year: int) -> dict:
    features = user.get("features", {})
    month_shifts = get_month_shifts(user, month, year)

    first_half_shifts = []
    second_half_shifts = []

    for shift in month_shifts:
        day = get_shift_day(shift)

        if day <= 15:
            first_half_shifts.append(shift)
        else:
            second_half_shifts.append(shift)

    total_minutes = 0
    for shift in month_shifts:
        total_minutes += get_shift_paid_minutes(shift)

    first_half_base = 0
    for shift in first_half_shifts:
        first_half_base += get_shift_base_money(shift, user)

    second_half_base = 0
    for shift in second_half_shifts:
        second_half_base += get_shift_base_money(shift, user)

    hours_bonus = 0
    hours_bonus_rate = 0

    if features.get("hour_bonus", False):
        hours_bonus_rate = get_hours_bonus_rate(total_minutes)
        hours_bonus = total_minutes / 60 * hours_bonus_rate

    lvv_bonus = 0
    if features.get("lvv", False) and user.get("lvv", False):
        lvv_bonus = LVV_BONUS

    truck_money = 0
    trash_money = 0

    if features.get("truck", False):
        for shift in month_shifts:
            if shift.get("truck_done", False):
                truck_money += TRUCK_PAY

    if features.get("trash", False):
        for shift in month_shifts:
            if shift.get("trash_done", False):
                trash_money += TRASH_PAY

    advance_gross = first_half_base

    salary_gross = (
        second_half_base
        + hours_bonus
        + lvv_bonus
        + truck_money
        + trash_money
    )

    total_gross = advance_gross + salary_gross

    if features.get("tax", False):
        advance_tax = advance_gross * TAX_RATE
        salary_tax = salary_gross * TAX_RATE
        total_tax = total_gross * TAX_RATE
    else:
        advance_tax = 0
        salary_tax = 0
        total_tax = 0

    advance_net = advance_gross - advance_tax
    salary_net = salary_gross - salary_tax
    total_net = total_gross - total_tax

    return {
        "month": month,
        "year": year,
        "shifts_count": len(month_shifts),
        "total_minutes": total_minutes,
        "first_half_base": first_half_base,
        "second_half_base": second_half_base,
        "hours_bonus_rate": hours_bonus_rate,
        "hours_bonus": hours_bonus,
        "lvv_bonus": lvv_bonus,
        "truck_money": truck_money,
        "trash_money": trash_money,
        "advance_gross": advance_gross,
        "advance_tax": advance_tax,
        "advance_net": advance_net,
        "salary_gross": salary_gross,
        "salary_tax": salary_tax,
        "salary_net": salary_net,
        "total_gross": total_gross,
        "total_tax": total_tax,
        "total_net": total_net,
    }


def money_text(value: float) -> str:
    return f"{round(value)} ₽"


# ---------- Общие команды ----------


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()

    await update.message.reply_text(
        "Действие отменено.",
        reply_markup=MAIN_MENU_KEYBOARD,
    )

    return ConversationHandler.END


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    users = load_users()

    if user_id not in users:
        await update.message.reply_text(
            "Сначала пройдите регистрацию через /start"
        )
        return

    await update.message.reply_text(
        "Главное меню:",
        reply_markup=MAIN_MENU_KEYBOARD,
    )


async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    users = load_users()

    if user_id not in users:
        await update.message.reply_text(
            "Сначала пройдите регистрацию через /start"
        )
        return

    user = users[user_id]

    mode = user.get("mode", "не указан")
    rate = user.get("rate")
    shifts_count = len(user.get("shifts", []))

    text = (
        "👤 Ваш профиль\n\n"
        f"Режим: {get_mode_name(mode)}\n"
        f"Ставка: {rate if rate is not None else 'не используется'} ₽/час\n"
        f"ЛВВ: {'Да' if user.get('lvv', False) else 'Нет'}\n"
        f"Разгрузка машины: {'Да' if user.get('truck', False) else 'Нет'}\n"
        f"Сдача мусора: {'Да' if user.get('trash', False) else 'Нет'}\n"
        f"Смен сохранено: {shifts_count}"
    )

    await update.message.reply_text(
        text,
        reply_markup=MAIN_MENU_KEYBOARD,
    )


# ---------- Регистрация ----------


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
        f"Регистрация завершена ✅\n\n"
        f"Режим: {get_mode_name(mode)}",
        reply_markup=MAIN_MENU_KEYBOARD,
    )

    return ConversationHandler.END


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = load_users()
    user_id = str(update.effective_user.id)

    if user_id in users:
        mode = users[user_id].get("mode", "не указан")

        await update.message.reply_text(
            f"Вы уже зарегистрированы.\n"
            f"Ваш режим: {get_mode_name(mode)}",
            reply_markup=MAIN_MENU_KEYBOARD,
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


# ---------- Добавление смены ----------


async def add_shift(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    users = load_users()

    if user_id not in users:
        await update.message.reply_text(
            "Сначала пройдите регистрацию через /start"
        )
        return ConversationHandler.END

    context.user_data.clear()

    await update.message.reply_text(
        "Введите дату смены (например: 09.06.2026)",
        reply_markup=ReplyKeyboardRemove(),
    )

    return SHIFT_DATE


async def get_shift_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    date = update.message.text

    if not is_valid_date(date):
        await update.message.reply_text(
            "Введите дату в формате ДД.ММ.ГГГГ. Например: 09.06.2026"
        )
        return SHIFT_DATE

    context.user_data["shift_date"] = date

    await update.message.reply_text(
        "Введите время начала смены (например: 08:57)"
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
        "Введите время окончания смены (например: 17:49)"
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

    if shift.get("truck_done", False):
        text += "\nРазгрузка машины: Да"

    if shift.get("trash_done", False):
        text += "\nСдача мусора: Да"

    await update.message.reply_text(
        text,
        reply_markup=MAIN_MENU_KEYBOARD,
    )

    return ConversationHandler.END


# ---------- Статистика ----------


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    users = load_users()

    if user_id not in users:
        await update.message.reply_text(
            "Сначала пройдите регистрацию через /start"
        )
        return

    month_info = get_month_from_stats_command(update.message.text)

    if month_info is None:
        await update.message.reply_text(
            "Введите команду так:\n"
            "/stats\n"
            "или\n"
            "/stats 06.2026"
        )
        return

    month, year = month_info
    user = users[user_id]

    month_shifts = []
    for shift in user.get("shifts", []):
        if shift_belongs_to_month(shift, month, year):
            month_shifts.append(shift)

    total_minutes = 0
    for shift in month_shifts:
        total_minutes += get_shift_paid_minutes(shift)

    next_bonus_text = get_next_bonus_text(total_minutes)

    text = (
        f"📊 Статистика за {month:02d}.{year}\n\n"
        f"Смен: {len(month_shifts)}\n"
        f"Отработано: {format_minutes(total_minutes)}\n\n"
        f"{next_bonus_text}"
    )

    await update.message.reply_text(
        text,
        reply_markup=MAIN_MENU_KEYBOARD,
    )


# ---------- Зарплата ----------


async def salary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    users = load_users()

    if user_id not in users:
        await update.message.reply_text(
            "Сначала пройдите регистрацию через /start"
        )
        return

    user = users[user_id]
    features = user.get("features", {})

    if not features.get("salary", False):
        await update.message.reply_text(
            "В вашем режиме зарплата не считается.\n\n"
            "Чтобы считать зарплату, откройте ⚙️ Настройки и измените режим.",
            reply_markup=MAIN_MENU_KEYBOARD,
        )
        return

    month_info = get_salary_month_from_command(update.message.text)

    if month_info is None:
        await update.message.reply_text(
            "Введите команду так:\n"
            "/salary\n"
            "или\n"
            "/salary 06.2026"
        )
        return

    month, year = month_info
    result = calculate_salary(user, month, year)

    mode = user.get("mode")

    if mode == "salary_simple":
        text = (
            f"💰 Зарплата за {month:02d}.{year}\n\n"
            f"Смен: {result['shifts_count']}\n"
            f"Отработано: {format_minutes(result['total_minutes'])}\n\n"
            f"Начислено до налога: {money_text(result['total_gross'])}\n"
            f"НДФЛ: {money_text(result['total_tax'])}\n"
            f"На руки: {money_text(result['total_net'])}"
        )

        await update.message.reply_text(
            text,
            reply_markup=MAIN_MENU_KEYBOARD,
        )
        return

    text = (
        f"💰 Зарплата за {month:02d}.{year}\n\n"
        f"Смен: {result['shifts_count']}\n"
        f"Отработано: {format_minutes(result['total_minutes'])}\n\n"
        f"🟦 Аванс, 1–15 число\n"
        f"До налога: {money_text(result['advance_gross'])}\n"
        f"НДФЛ: {money_text(result['advance_tax'])}\n"
        f"На руки: {money_text(result['advance_net'])}\n\n"
        f"🟩 Зарплата, 16–конец месяца\n"
        f"Оплата по ставке: {money_text(result['second_half_base'])}\n"
        f"Премия за часы: {money_text(result['hours_bonus'])} "
        f"({result['hours_bonus_rate']} ₽/час)\n"
        f"ЛВВ: {money_text(result['lvv_bonus'])}\n"
        f"Разгрузка машины: {money_text(result['truck_money'])}\n"
        f"Сдача мусора: {money_text(result['trash_money'])}\n"
        f"До налога: {money_text(result['salary_gross'])}\n"
        f"НДФЛ: {money_text(result['salary_tax'])}\n"
        f"На руки: {money_text(result['salary_net'])}\n\n"
        f"📌 Итого за месяц\n"
        f"До налога: {money_text(result['total_gross'])}\n"
        f"НДФЛ: {money_text(result['total_tax'])}\n"
        f"На руки: {money_text(result['total_net'])}"
    )

    await update.message.reply_text(
        text,
        reply_markup=MAIN_MENU_KEYBOARD,
    )


# ---------- Настройки ----------


async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    users = load_users()

    if user_id not in users:
        await update.message.reply_text(
            "Сначала пройдите регистрацию через /start"
        )
        return ConversationHandler.END

    user = users[user_id]

    await update.message.reply_text(
        build_settings_text(user),
        reply_markup=SETTINGS_KEYBOARD,
    )

    return SETTINGS_CHOICE


async def settings_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = str(update.effective_user.id)

    users = load_users()
    user = users[user_id]
    features = user.get("features", {})

    if text == "⬅️ Назад":
        await update.message.reply_text(
            "Главное меню:",
            reply_markup=MAIN_MENU_KEYBOARD,
        )
        return ConversationHandler.END

    if text == "Изменить режим":
        await update.message.reply_text(
            "Выберите новый режим:",
            reply_markup=MODE_KEYBOARD,
        )
        return SETTINGS_MODE

    if text == "Изменить ставку":
        if not features.get("salary", False):
            await update.message.reply_text(
                "В вашем режиме ставка не используется.\n"
                "Сейчас у вас режим: Только часы.",
                reply_markup=SETTINGS_KEYBOARD,
            )
            return SETTINGS_CHOICE

        await update.message.reply_text(
            "Введите новую почасовую ставку:",
            reply_markup=ReplyKeyboardRemove(),
        )
        return SETTINGS_RATE

    if text == "Изменить ЛВВ":
        if not features.get("lvv", False):
            await update.message.reply_text(
                "ЛВВ используется только в режиме полного расчёта.",
                reply_markup=SETTINGS_KEYBOARD,
            )
            return SETTINGS_CHOICE

        await update.message.reply_text(
            "Получаете ЛВВ?",
            reply_markup=YES_NO_KEYBOARD,
        )
        return SETTINGS_LVV

    if text == "Изменить машину":
        if not features.get("truck", False):
            await update.message.reply_text(
                "Разгрузка машины используется только в режиме полного расчёта.",
                reply_markup=SETTINGS_KEYBOARD,
            )
            return SETTINGS_CHOICE

        await update.message.reply_text(
            "Разгружаете машину?",
            reply_markup=YES_NO_KEYBOARD,
        )
        return SETTINGS_TRUCK

    if text == "Изменить мусор":
        if not features.get("trash", False):
            await update.message.reply_text(
                "Сдача мусора используется только в режиме полного расчёта.",
                reply_markup=SETTINGS_KEYBOARD,
            )
            return SETTINGS_CHOICE

        await update.message.reply_text(
            "Сдаёте мусор?",
            reply_markup=YES_NO_KEYBOARD,
        )
        return SETTINGS_TRASH

    await update.message.reply_text(
        "Выберите действие кнопкой.",
        reply_markup=SETTINGS_KEYBOARD,
    )

    return SETTINGS_CHOICE


async def settings_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        return SETTINGS_MODE

    user_id = str(update.effective_user.id)

    users = load_users()
    user = users[user_id]

    new_mode = modes[text]
    user["mode"] = new_mode
    user["features"] = make_features(new_mode)

    user.setdefault("lvv", False)
    user.setdefault("truck", False)
    user.setdefault("trash", False)
    user.setdefault("shifts", [])

    save_users(users)

    if new_mode == "hours_only":
        await update.message.reply_text(
            "Режим изменён на: Только часы ✅\n\n"
            "История смен сохранена.",
            reply_markup=MAIN_MENU_KEYBOARD,
        )
        return ConversationHandler.END

    if user.get("rate") is None:
        context.user_data["return_to_settings_after_rate"] = True

        await update.message.reply_text(
            "Режим изменён ✅\n\n"
            "Для этого режима нужна почасовая ставка.\n"
            "Введите вашу ставку:",
            reply_markup=ReplyKeyboardRemove(),
        )

        return SETTINGS_RATE

    await update.message.reply_text(
        f"Режим изменён на: {get_mode_name(new_mode)} ✅\n\n"
        "История смен сохранена.",
        reply_markup=MAIN_MENU_KEYBOARD,
    )

    return ConversationHandler.END


async def settings_rate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    try:
        rate = int(text)
    except ValueError:
        await update.message.reply_text(
            "Введите ставку числом. Например: 350"
        )
        return SETTINGS_RATE

    if rate < 100 or rate > 2000:
        await update.message.reply_text(
            "Введите корректную ставку от 100 до 2000 рублей в час."
        )
        return SETTINGS_RATE

    user_id = str(update.effective_user.id)

    users = load_users()
    users[user_id]["rate"] = rate
    save_users(users)

    if context.user_data.get("return_to_settings_after_rate", False):
        context.user_data.pop("return_to_settings_after_rate", None)

        await update.message.reply_text(
            f"Ставка сохранена: {rate} ₽/час ✅\n\n"
            "История смен сохранена.",
            reply_markup=MAIN_MENU_KEYBOARD,
        )

        return ConversationHandler.END

    await update.message.reply_text(
        f"Ставка изменена на {rate} ₽/час ✅\n\n"
        "Важно: старые смены не изменятся. Новая ставка будет применяться к новым сменам.",
        reply_markup=SETTINGS_KEYBOARD,
    )

    return SETTINGS_CHOICE


async def settings_lvv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()

    if text not in ["да", "нет"]:
        await update.message.reply_text("Ответьте: Да или Нет")
        return SETTINGS_LVV

    user_id = str(update.effective_user.id)

    users = load_users()
    users[user_id]["lvv"] = text == "да"
    save_users(users)

    await update.message.reply_text(
        "Настройка ЛВВ обновлена ✅",
        reply_markup=SETTINGS_KEYBOARD,
    )

    return SETTINGS_CHOICE


async def settings_truck(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()

    if text not in ["да", "нет"]:
        await update.message.reply_text("Ответьте: Да или Нет")
        return SETTINGS_TRUCK

    user_id = str(update.effective_user.id)

    users = load_users()
    users[user_id]["truck"] = text == "да"
    save_users(users)

    await update.message.reply_text(
        "Настройка разгрузки машины обновлена ✅",
        reply_markup=SETTINGS_KEYBOARD,
    )

    return SETTINGS_CHOICE


async def settings_trash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()

    if text not in ["да", "нет"]:
        await update.message.reply_text("Ответьте: Да или Нет")
        return SETTINGS_TRASH

    user_id = str(update.effective_user.id)

    users = load_users()
    users[user_id]["trash"] = text == "да"
    save_users(users)

    await update.message.reply_text(
        "Настройка сдачи мусора обновлена ✅",
        reply_markup=SETTINGS_KEYBOARD,
    )

    return SETTINGS_CHOICE


async def cancel_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Настройки закрыты.",
        reply_markup=MAIN_MENU_KEYBOARD,
    )

    return ConversationHandler.END


# ---------- ConversationHandler ----------


conv_handler = ConversationHandler(
    entry_points=[
        CommandHandler("start", start),
    ],
    states={
        MODE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_mode),
        ],
        RATE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_rate),
        ],
        LVV: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_lvv),
        ],
        TRUCK: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_truck),
        ],
        TRASH: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_trash),
        ],
    },
    fallbacks=[
        CommandHandler("cancel", cancel),
    ],
)


shift_handler = ConversationHandler(
    entry_points=[
        CommandHandler("addshift", add_shift),
        MessageHandler(filters.Regex("^➕ Добавить смену$"), add_shift),
    ],
    states={
        SHIFT_DATE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_shift_date),
        ],
        SHIFT_START: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_shift_start),
        ],
        SHIFT_END: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_shift_end),
        ],
        SHIFT_BREAK: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_shift_break),
        ],
        SHIFT_TRUCK: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_shift_truck),
        ],
        SHIFT_TRASH: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_shift_trash),
        ],
    },
    fallbacks=[
        CommandHandler("cancel", cancel),
    ],
)


settings_handler = ConversationHandler(
    entry_points=[
        CommandHandler("settings", settings),
        MessageHandler(filters.Regex("^⚙️ Настройки$"), settings),
    ],
    states={
        SETTINGS_CHOICE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, settings_choice),
        ],
        SETTINGS_MODE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, settings_mode),
        ],
        SETTINGS_RATE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, settings_rate),
        ],
        SETTINGS_LVV: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, settings_lvv),
        ],
        SETTINGS_TRUCK: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, settings_truck),
        ],
        SETTINGS_TRASH: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, settings_trash),
        ],
    },
    fallbacks=[
        CommandHandler("cancel", cancel_settings),
    ],
)


telegram_app.add_handler(conv_handler)
telegram_app.add_handler(shift_handler)
telegram_app.add_handler(settings_handler)

telegram_app.add_handler(CommandHandler("stats", stats))
telegram_app.add_handler(CommandHandler("salary", salary))
telegram_app.add_handler(CommandHandler("menu", menu))
telegram_app.add_handler(CommandHandler("profile", profile))

telegram_app.add_handler(MessageHandler(filters.Regex("^📊 Статистика$"), stats))
telegram_app.add_handler(MessageHandler(filters.Regex("^💰 Зарплата$"), salary))
telegram_app.add_handler(MessageHandler(filters.Regex("^👤 Профиль$"), profile))


# ---------- FastAPI / Webhook ----------


@app.on_event("startup")
async def on_startup():
    await telegram_app.initialize()


@app.on_event("shutdown")
async def on_shutdown():
    await telegram_app.shutdown()


@app.get("/")
async def health_check():
    return {"ok": True}


@app.post("/")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return {"ok": True}
