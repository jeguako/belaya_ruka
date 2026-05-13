from __future__ import annotations

import base64
import calendar
import json
import logging
import os
import random
import subprocess
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    MenuButtonCommands,
    MenuButtonWebApp,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
    WebAppInfo,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    JobQueue,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("belaya-ruka-bot")

LITERS_PER_BOTTLE = 19
GIFT_BOTTLES = 50

RU_MONTH_NAMES = (
    "",
    "Январь",
    "Февраль",
    "Март",
    "Апрель",
    "Май",
    "Июнь",
    "Июль",
    "Август",
    "Сентябрь",
    "Октябрь",
    "Ноябрь",
    "Декабрь",
)

CALLBACK_NOOP = "order:xnoop"

PARTNER_FOLLOWUP_TEXT = (
    "Дополнительно предлагаем формат партнёрства для самозанятых и частных лиц.\n\n"
    "Вы можете организовать небольшую точку выдачи бутилированной воды во дворе, подъезде "
    "или жилом комплексе: мы поставляем продукт большими партиями, вы реализуете его "
    "жильцам по розничной цене. Это может стать дополнительным источником дохода без "
    "существенных затрат времени.\n\n"
    "Если формат интересен — оставьте заявку в разделе B2B мини-приложения или сообщите "
    "менеджеру при звонке: мы свяжемся и подробно расскажем об условиях."
)

TIME_WINDOW_DISCLAIMER = (
    "Выберите ориентировочный интервал доставки.\n\n"
    "Время указано приблизительно и может быть скорректировано оператором или курьером "
    "в зависимости от загрузки маршрута."
)

WELCOME_PHOTO_URL = os.getenv(
    "WELCOME_PHOTO_URL",
    "https://images.unsplash.com/photo-1548839140-29a749e1cf4d?auto=format&fit=crop&w=1200&q=80",
).strip()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
USERS_FILE = DATA_DIR / "users.json"
ORDERS_FILE = DATA_DIR / "orders.json"
CATALOG_FILE = DATA_DIR / "catalog.json"

REG_TYPE = "reg_type"
REG_B2C_PHONE = "reg_b2c_phone"
REG_B2C_NAME = "reg_b2c_name"
REG_B2C_ADDRESS = "reg_b2c_address"
REG_B2C_FLOOR = "reg_b2c_floor"
REG_B2C_INTERCOM = "reg_b2c_intercom"
REG_B2C_NOTES = "reg_b2c_notes"

REG_B2B_NAME = "reg_b2b_name"
REG_B2B_PHONE = "reg_b2b_phone"
REG_B2B_INN = "reg_b2b_inn"
REG_B2B_VOLUME = "reg_b2b_volume"
REG_B2B_POINTS = "reg_b2b_points"

ORDER_COMMENT = "order_comment"
ORDER_DATE = "order_date"
ORDER_TIME = "order_time"
ORDER_MANUAL_QTY = "order_manual_qty"

BIRD_NAMES = [
    "Сокол", "Филин", "Колибри", "Чайка", "Ласточка",
    "Синица", "Иволга", "Аист", "Дятел", "Щегол",
]


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ensure_data_files() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not USERS_FILE.exists():
        USERS_FILE.write_text("{}", encoding="utf-8")
    if not ORDERS_FILE.exists():
        ORDERS_FILE.write_text("[]", encoding="utf-8")
    if not CATALOG_FILE.exists():
        CATALOG_FILE.write_text("[]", encoding="utf-8")


def load_users() -> dict[str, dict]:
    ensure_data_files()
    try:
        data = json.loads(USERS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_users(users: dict[str, dict]) -> None:
    USERS_FILE.write_text(
        json.dumps(users, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_orders() -> list[dict]:
    ensure_data_files()
    try:
        data = json.loads(ORDERS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_orders(orders: list[dict]) -> None:
    ORDERS_FILE.write_text(
        json.dumps(orders, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_catalog() -> list[dict]:
    ensure_data_files()
    try:
        data = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_catalog(products: list[dict]) -> None:
    ensure_data_files()
    CATALOG_FILE.write_text(
        json.dumps(products, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def upload_catalog_via_ftp_if_configured() -> None:
    host = os.getenv("FTP_HOST", "").strip()
    user = os.getenv("FTP_USER", "").strip()
    password = os.getenv("FTP_PASSWORD", "").strip()
    remote_raw = os.getenv("FTP_REMOTE_DIR", "").strip()
    rp = remote_raw.rstrip("/")
    if not remote_raw:
        rp = "/public_html"
    elif rp.lower() in (".", "-", "cwd", "~"):
        rp = ""

    path = ("catalog.json" if not rp else f"{rp}/catalog.json").replace("//", "/")
    if not (host and user and password):
        return
    if not CATALOG_FILE.exists():
        return
    tls_raw = os.getenv("FTP_TLS", "").strip().lower()
    if tls_raw in ("reqd", "required", "strict"):
        tls_mode = "reqd"
    elif tls_raw in ("insecure", "insec"):
        tls_mode = "insecure"
    elif tls_raw in ("1", "true", "yes", "on"):
        tls_mode = "yes"
    else:
        tls_mode = ""
    if path.startswith("/"):
        url = f"ftp://{host}//{path.lstrip('/')}"
    else:
        url = f"ftp://{host}/{path}"
    cmd = [
        "curl",
        "-sS",
        "--ipv4",
        "--connect-timeout",
        "30",
        "--max-time",
        "180",
        "--ftp-pasv",
        "--ftp-skip-pasv-ip",
        "-T",
        str(CATALOG_FILE),
        url,
        "--user",
        f"{user}:{password}",
    ]
    if tls_mode == "reqd":
        cmd.insert(1, "--ssl-reqd")
    elif tls_mode == "insecure":
        cmd.insert(1, "--ftp-ssl-control")
        cmd.insert(2, "--insecure")
    elif tls_mode == "yes":
        cmd.insert(1, "--ftp-ssl-control")
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            logger.warning(
                "catalog FTP upload exit %s: %s",
                proc.returncode,
                (proc.stderr or proc.stdout or "").strip(),
            )
    except Exception as exc:
        logger.warning("catalog FTP upload failed: %s", exc)


def webapp_url() -> str:
    return os.getenv("WEBAPP_URL", "").strip()


def webapp_available() -> bool:
    return webapp_url().startswith("https://")


def webapp_url_for(profile: dict, tab: str | None = None) -> str:
    base = webapp_url().split("#")[0].strip()
    if not base:
        return base
    liters = int(profile.get("liters_total", 0) or 0)
    bottles = liters // LITERS_PER_BOTTLE
    payload = {
        "name": profile.get("name", "") or "",
        "phone": profile.get("phone", "") or "",
        "mainAddress": profile.get("main_address", "") or "",
        "floor": profile.get("floor", "") or "",
        "intercom": profile.get("intercom", "") or "",
        "notes": profile.get("notes", "") or "",
        "userType": profile.get("user_type", "") or "",
        "litersTotal": liters,
        "bottlesTotal": bottles,
        "giftBottles": GIFT_BOTTLES,
    }
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    enc = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    frag_parts = [f"u={enc}"]
    if tab:
        frag_parts.append(f"tab={tab}")
    return f"{base}#{'&'.join(frag_parts)}"


def webapp_button(
    profile: dict,
    label: str = "Открыть магазин",
    tab: str | None = None,
) -> InlineKeyboardButton:
    return InlineKeyboardButton(label, web_app=WebAppInfo(url=webapp_url_for(profile, tab=tab)))


def user_key(update: Update) -> str:
    return str(update.effective_user.id if update.effective_user else 0)


def get_or_create_profile(update: Update) -> dict:
    users = load_users()
    key = user_key(update)
    username = update.effective_user.username if update.effective_user else ""
    profile = users.get(key) or {}
    profile.setdefault("username", username)
    profile.setdefault("liters_total", 0)
    profile.setdefault("registered", False)
    profile.setdefault("user_type", "")
    if username and not profile.get("username"):
        profile["username"] = username
    users[key] = profile
    save_users(users)
    return profile


def update_profile(update: Update, **fields) -> dict:
    users = load_users()
    key = user_key(update)
    profile = users.get(key) or {}
    profile.update(fields)
    users[key] = profile
    save_users(users)
    return profile


def get_display_name(profile: dict) -> str:
    name = str(profile.get("name", "")).strip()
    if name:
        return name
    username = str(profile.get("username", "")).strip()
    if username:
        return f"@{username}"
    return f"{random.choice(BIRD_NAMES)}-{random.randint(100, 999)}"


def is_registered(profile: dict) -> bool:
    return bool(profile.get("registered"))


def role_select_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Физическое лицо",
                    callback_data="reg:type:b2c",
                )
            ],
            [
                InlineKeyboardButton(
                    "Юридическое лицо / B2B",
                    callback_data="reg:type:b2b",
                )
            ],
        ]
    )


def begin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Начать", callback_data="reg:begin")]]
    )


def b2c_floor_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("1–5 этаж", callback_data="reg:b2c:floor:1-5"),
                InlineKeyboardButton("6+ этаж", callback_data="reg:b2c:floor:6+"),
            ],
            [InlineKeyboardButton("Частный дом / коттедж", callback_data="reg:b2c:floor:house")],
            [InlineKeyboardButton("Другое — напишу текстом", callback_data="reg:b2c:floor:manual")],
        ]
    )


def b2c_intercom_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Домофона нет", callback_data="reg:b2c:intercom:none")],
            [InlineKeyboardButton("Указать код — напишу текстом", callback_data="reg:b2c:intercom:manual")],
        ]
    )


def b2c_notes_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Без особых пожеланий", callback_data="reg:b2c:notes:none")],
            [InlineKeyboardButton("Напишу текстом", callback_data="reg:b2c:notes:manual")],
        ]
    )


def b2b_inn_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Пропустить ИНН", callback_data="reg:b2b:inn:skip")]]
    )


def b2b_volume_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("до 50 бут.", callback_data="reg:b2b:vol:s"),
                InlineKeyboardButton("50–200 бут.", callback_data="reg:b2b:vol:m"),
            ],
            [
                InlineKeyboardButton("200+ бут.", callback_data="reg:b2b:vol:l"),
            ],
            [InlineKeyboardButton("Указать текстом", callback_data="reg:b2b:vol:manual")],
        ]
    )


def b2b_points_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("1 точка", callback_data="reg:b2b:pts:1"),
                InlineKeyboardButton("2–5 точек", callback_data="reg:b2b:pts:few"),
            ],
            [InlineKeyboardButton("Указать текстом", callback_data="reg:b2b:pts:manual")],
        ]
    )


def order_comment_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Без комментария", callback_data="order:comment:none")]]
    )


def order_quantity_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("3 шт", callback_data="order:qty:3"),
                InlineKeyboardButton("4 шт", callback_data="order:qty:4"),
                InlineKeyboardButton("5 шт", callback_data="order:qty:5"),
            ],
            [
                InlineKeyboardButton("6 шт", callback_data="order:qty:6"),
                InlineKeyboardButton("8 шт", callback_data="order:qty:8"),
                InlineKeyboardButton("10 шт", callback_data="order:qty:10"),
            ],
            [
                InlineKeyboardButton(
                    "Другое количество",
                    callback_data="order:qty:manual",
                )
            ],
        ]
    )


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    month += delta
    while month > 12:
        month -= 12
        year += 1
    while month < 1:
        month += 12
        year -= 1
    return year, month


def calendar_markup(year: int, month: int, selected: str | None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    py, pm = _shift_month(year, month, -1)
    ny, nm = _shift_month(year, month, 1)
    rows.append(
        [
            InlineKeyboardButton(
                "◀",
                callback_data=f"order:calm:{py}-{pm:02d}",
            ),
            InlineKeyboardButton(
                f"{RU_MONTH_NAMES[month]} {year}",
                callback_data=CALLBACK_NOOP,
            ),
            InlineKeyboardButton(
                "▶",
                callback_data=f"order:calm:{ny}-{nm:02d}",
            ),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton("Пн", callback_data=CALLBACK_NOOP),
            InlineKeyboardButton("Вт", callback_data=CALLBACK_NOOP),
            InlineKeyboardButton("Ср", callback_data=CALLBACK_NOOP),
            InlineKeyboardButton("Чт", callback_data=CALLBACK_NOOP),
            InlineKeyboardButton("Пт", callback_data=CALLBACK_NOOP),
            InlineKeyboardButton("Сб", callback_data=CALLBACK_NOOP),
            InlineKeyboardButton("Вс", callback_data=CALLBACK_NOOP),
        ]
    )
    today = datetime.now().date()
    weeks = calendar.Calendar(firstweekday=calendar.MONDAY).monthdayscalendar(year, month)
    for week in weeks:
        row_btn: list[InlineKeyboardButton] = []
        for day in week:
            if day == 0:
                row_btn.append(InlineKeyboardButton(" ", callback_data=CALLBACK_NOOP))
                continue
            try:
                cell = datetime(year, month, day).date()
            except ValueError:
                row_btn.append(InlineKeyboardButton(" ", callback_data=CALLBACK_NOOP))
                continue
            ds = f"{day:02d}.{month:02d}.{year}"
            if cell < today:
                row_btn.append(InlineKeyboardButton("·", callback_data=CALLBACK_NOOP))
                continue
            label = f"✓{day}" if selected == ds else str(day)
            row_btn.append(
                InlineKeyboardButton(label, callback_data=f"order:cald:{ds}")
            )
        rows.append(row_btn)
    return InlineKeyboardMarkup(rows)


def time_picker_keyboard() -> InlineKeyboardMarkup:
    slots = [
        "09:00–12:00",
        "12:00–15:00",
        "15:00–18:00",
        "18:00–21:00",
    ]
    rows = [[InlineKeyboardButton(s, callback_data=f"order:time:{s}")] for s in slots]
    rows.append([InlineKeyboardButton("Указать вручную", callback_data="order:time:manual")])
    return InlineKeyboardMarkup(rows)


async def partner_followup_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = context.job.chat_id
    if chat_id is None:
        return
    try:
        await context.bot.send_message(chat_id=chat_id, text=PARTNER_FOLLOWUP_TEXT)
    except Exception as exc:
        logger.warning("partner followup failed: %s", exc)


def welcome_photo_caption() -> str:
    return (
        "БЕЛАЯ РУКА — доставка бутилированной воды 19 л.\n\n"
        "Что умеет этот бот:\n"
        "• Мини-приложение: каталог, оформление заказа с выбором даты и интервала.\n"
        "• Профиль: адрес, контакты, программа «каждые 50 бутылей — одна в подарок».\n"
        "• Заказ прямо в чате по шагам (команда /order).\n"
        "• B2B: заявка для офисов и торговых точек.\n\n"
        "Откройте мини-приложение через кнопку меню «Заказать» слева от поля ввода "
        "или командой /shop после регистрации."
    )


def welcome_followup() -> str:
    return (
        "Для продолжения выберите тип клиента:\n"
        "• физическое лицо — доставка на дом или в офис;\n"
        "• юридическое лицо / B2B — оптовые условия и подключение для организаций."
    )


def b2c_done_text(profile: dict) -> str:
    name = profile.get("name") or "Клиент"
    return (
        f"{name}, регистрация завершена. Контактные данные и адрес доставки сохранены.\n\n"
        "Откройте мини-приложение кнопкой меню «Заказать» слева от поля ввода или командой /shop. "
        "Заказ в чате: /order."
    )


def b2b_done_text() -> str:
    return (
        "Спасибо. Заявка зарегистрирована.\n"
        "Специалист свяжется с вами для уточнения условий сотрудничества.\n\n"
        "Каталог и формы B2B доступны в мини-приложении (меню «Заказать» или /shop)."
    )


async def send_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if not chat:
        return
    caption = welcome_photo_caption()
    if WELCOME_PHOTO_URL:
        try:
            await chat.send_photo(photo=WELCOME_PHOTO_URL, caption=caption)
        except Exception as exc:
            logger.warning("welcome photo failed: %s", exc)
            await chat.send_message(caption)
    else:
        await chat.send_message(caption)
    await chat.send_message(
        "Когда будете готовы пройти короткую регистрацию, нажмите «Начать».",
        reply_markup=begin_keyboard(),
    )


async def schedule_partner_followup(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    jq = context.application.job_queue
    if not jq:
        return
    job_name = f"partner_follow_{chat_id}"
    for job in jq.get_jobs_by_name(job_name):
        job.schedule_removal()
    jq.run_once(
        partner_followup_job,
        when=60,
        chat_id=chat_id,
        name=job_name,
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    profile = get_or_create_profile(update)
    context.user_data.pop("state", None)
    context.user_data.pop("draft_order", None)
    context.user_data.pop("onboarding_started", None)

    if is_registered(profile):
        greeting = (
            f"Добро пожаловать, {profile.get('name') or 'клиент'}.\n"
            "Мини-приложение — кнопка меню «Заказать» слева от поля ввода. "
            "Команды: /order — заказ в чате, /profile — профиль, /edit — данные в приложении, /help."
        )
        await update.message.reply_text(greeting, reply_markup=ReplyKeyboardRemove())
        return

    await send_welcome(update, context)


async def edit_profile_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    profile = get_or_create_profile(update)
    if not webapp_available():
        await update.message.reply_text("Мини-приложение временно недоступно.")
        return
    await update.message.reply_text(
        "Изменение контактных данных и адреса выполняется в разделе «Профиль» мини-приложения.",
        reply_markup=InlineKeyboardMarkup(
            [[webapp_button(profile, "Открыть профиль", tab="profile")]],
        ),
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    await update.message.reply_text(
        "Доступные команды:\n"
        "/start — главное меню и регистрация\n"
        "/shop — открыть магазин\n"
        "/order — заказ в чате по шагам\n"
        "/profile — сводка профиля\n"
        "/edit — открыть редактирование данных в мини-приложении\n"
        "/help — эта справка\n\n"
        "Мини-приложение открывается кнопкой меню «Заказать» слева от поля ввода "
        "(если настроен HTTPS). Команду можно ввести вручную, начав с символа /."
    )


async def profile_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    profile = get_or_create_profile(update)
    if not is_registered(profile):
        await update.message.reply_text(
            "Профиль ещё не заполнен. Нажмите /start.",
        )
        return

    if profile.get("user_type") == "b2b":
        text = (
            "Профиль B2B:\n"
            f"— Контактное лицо: {profile.get('name', '-')}\n"
            f"— Телефон: {profile.get('phone', '-')}\n"
            f"— ИНН: {profile.get('inn', '-')}\n"
            f"— Объём в неделю: {profile.get('weekly_volume', '-')}\n"
            f"— Точек по городу/краю: {profile.get('points_count', '-')}"
        )
        await update.message.reply_text(text, reply_markup=ReplyKeyboardRemove())
        return

    liters = int(profile.get("liters_total", 0))
    bottles = liters // LITERS_PER_BOTTLE
    cycle = bottles % GIFT_BOTTLES
    bottles_left = GIFT_BOTTLES - cycle if bottles else GIFT_BOTTLES
    gifts_earned = bottles // GIFT_BOTTLES
    text = (
        f"Профиль:\n"
        f"— Имя: {profile.get('name', '-')}\n"
        f"— Telegram: @{profile.get('username', '-')}\n"
        f"— Телефон: {profile.get('phone', '-')}\n"
        f"— Адрес: {profile.get('main_address', '-')}\n"
        f"— Этаж: {profile.get('floor', '-')}\n"
        f"— Домофон: {profile.get('intercom', '-')}\n"
        f"— Заметки: {profile.get('notes', '-')}\n\n"
        f"Статистика:\n"
        f"— Заказано: {bottles} бутылей ({liters} л)\n"
        f"— До бесплатной бутыли: {bottles_left} шт\n"
        f"— Получено бутылей в подарок: {gifts_earned}"
    )
    await update.message.reply_text(text, reply_markup=ReplyKeyboardRemove())


async def order_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    profile = get_or_create_profile(update)
    if not is_registered(profile):
        await update.message.reply_text(
            "Сначала пройдём мини-регистрацию. Нажмите /start.",
        )
        return
    if profile.get("user_type") == "b2b":
        await update.message.reply_text(
            "Заказы для юридических лиц и корпоративных клиентов оформляются через менеджера "
            "после согласования условий. Оставьте заявку в разделе B2B мини-приложения "
            "или дождитесь обратной связи по ранее отправленным данным.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return
    await update.message.reply_text(
        "Оформление заказа в чате.\n\n"
        "Шаг 1 из 4: укажите количество бутылей (не менее 3):",
        reply_markup=order_quantity_keyboard(),
    )


async def shop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    profile = get_or_create_profile(update)
    if not is_registered(profile):
        await update.message.reply_text(
            "Чтобы открыть мини-магазин, давайте сначала познакомимся. Нажмите /start.",
        )
        return
    if not webapp_available():
        await update.message.reply_text("Мини-магазин временно недоступен.")
        return
    await update.message.reply_text(
        "Мини-приложение:",
        reply_markup=InlineKeyboardMarkup([[webapp_button(profile, "Открыть магазин")]]),
    )


async def b2b_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await shop_cmd(update, context)


def create_order(
    update: Update,
    quantity: int,
    comment: str,
    date: str,
    time: str,
) -> str:
    profile = get_or_create_profile(update)
    orders = load_orders()
    display_name = get_display_name(profile)
    address = profile.get("main_address", "не указан")
    phone = profile.get("phone", "не указан")
    floor = profile.get("floor", "")
    intercom = profile.get("intercom", "")

    order = {
        "ts": now_str(),
        "chat_id": update.effective_chat.id if update.effective_chat else 0,
        "name": display_name,
        "username": profile.get("username", ""),
        "phone": phone,
        "quantity": quantity,
        "date": date,
        "time": time,
        "comment": comment or "без комментария",
        "address": address,
        "floor": floor,
        "intercom": intercom,
        "source": "inline",
    }
    orders.append(order)
    save_orders(orders)

    liters = int(profile.get("liters_total", 0)) + quantity * LITERS_PER_BOTTLE
    update_profile(update, liters_total=liters)

    return (
        "Заказ\n"
        f"Клиент: {display_name}\n"
        f"Телефон: {phone}\n"
        f"Адрес: {address}\n"
        f"Этаж: {floor or '-'}\n"
        f"Домофон: {intercom or '-'}\n"
        f"Количество: {quantity}\n"
        f"Дата: {date}\n"
        f"Время: {time}\n"
        f"Комментарий: {comment or 'без комментария'}"
    )


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    data = query.data or ""
    profile = get_or_create_profile(update)

    async def ack(note: str | None = None) -> None:
        try:
            await query.answer(note)
        except Exception:
            pass

    if data == CALLBACK_NOOP:
        await ack()
        return

    if data == "reg:begin":
        await ack()
        context.user_data["onboarding_started"] = True
        if query.message:
            await query.message.reply_text(welcome_followup(), reply_markup=role_select_keyboard())
            await schedule_partner_followup(context, query.message.chat_id)
        return

    if data.startswith("reg:type:"):
        if not context.user_data.get("onboarding_started"):
            await ack("Сначала нажмите «Начать»")
            if query.message:
                await query.message.reply_text(
                    "Чтобы зарегистрироваться, нажмите «Начать» в приветственном сообщении."
                )
            return
        kind = data.split(":")[-1]
        if kind not in {"b2c", "b2b"}:
            await ack()
            return
        update_profile(update, user_type=kind)
        if kind == "b2c":
            context.user_data["state"] = REG_B2C_PHONE
            phone_kb = ReplyKeyboardMarkup(
                [[KeyboardButton("Поделиться номером", request_contact=True)]],
                resize_keyboard=True,
            )
            await query.message.reply_text(
                "Регистрация физического лица.\n\n"
                "Шаг 1 из 6: номер телефона для связи и передачи курьеру.\n"
                "Нажмите «Поделиться номером» или введите номер сообщением.",
                reply_markup=phone_kb,
            )
        else:
            context.user_data["state"] = REG_B2B_NAME
            await query.message.reply_text(
                "Регистрация для юридического лица (B2B).\n\n"
                "Шаг 1 из 5: ФИО контактного лица.",
                reply_markup=ReplyKeyboardRemove(),
            )
        await ack()
        return

    if data.startswith("reg:b2c:floor:") and not is_registered(profile):
        if context.user_data.get("state") != REG_B2C_FLOOR:
            await ack()
            return
        key = data.split(":")[-1]
        if key == "manual":
            await query.message.reply_text(
                "Укажите этаж текстом (при необходимости упомяните лифт)."
            )
            await ack()
            return
        floor_map = {"1-5": "1–5 этаж", "6+": "6+ этаж", "house": "Частный дом / коттедж"}
        floor_val = floor_map.get(key)
        if not floor_val:
            await ack()
            return
        update_profile(update, floor=floor_val)
        context.user_data["state"] = REG_B2C_INTERCOM
        await query.message.reply_text(
            "Шаг 5 из 6: домофон.",
            reply_markup=b2c_intercom_keyboard(),
        )
        await ack()
        return

    if data.startswith("reg:b2c:intercom:") and not is_registered(profile):
        if context.user_data.get("state") != REG_B2C_INTERCOM:
            await ack()
            return
        suffix = data.split(":")[-1]
        if suffix == "manual":
            await query.message.reply_text(
                "Введите код домофона сообщением (или «-», если домофона нет)."
            )
            await ack()
            return
        if suffix == "none":
            update_profile(update, intercom="-")
            context.user_data["state"] = REG_B2C_NOTES
            await query.message.reply_text(
                "Шаг 6 из 6: дополнительные указания для курьера.",
                reply_markup=b2c_notes_keyboard(),
            )
            await ack()
            return
        await ack()
        return

    if data.startswith("reg:b2c:notes:") and not is_registered(profile):
        if context.user_data.get("state") != REG_B2C_NOTES:
            await ack()
            return
        suffix = data.split(":")[-1]
        if suffix == "manual":
            await query.message.reply_text("Введите заметки сообщением (или «-», если не нужны).")
            await ack()
            return
        if suffix == "none":
            update_profile(update, notes="-", registered=True)
            context.user_data.pop("state", None)
            context.user_data.pop("onboarding_started", None)
            profile = get_or_create_profile(update)
            await query.message.reply_text(
                b2c_done_text(profile),
                reply_markup=ReplyKeyboardRemove(),
            )
            await ack()
            return
        await ack()
        return

    if data == "reg:b2b:inn:skip" and not is_registered(profile):
        if context.user_data.get("state") != REG_B2B_INN:
            await ack()
            return
        update_profile(update, inn="-")
        context.user_data["state"] = REG_B2B_VOLUME
        await query.message.reply_text(
            "Шаг 4 из 5: ориентировочный объём поставок в неделю.",
            reply_markup=b2b_volume_keyboard(),
        )
        await ack()
        return

    if data.startswith("reg:b2b:vol:") and not is_registered(profile):
        if context.user_data.get("state") != REG_B2B_VOLUME:
            await ack()
            return
        suffix = data.split(":")[-1]
        if suffix == "manual":
            await query.message.reply_text(
                "Введите объём текстом (например, количество бутылей в неделю)."
            )
            await ack()
            return
        preset_vol = {
            "s": "до 50 бутылей в неделю",
            "m": "50–200 бутылей в неделю",
            "l": "более 200 бутылей в неделю",
        }.get(suffix)
        if not preset_vol:
            await ack()
            return
        update_profile(update, weekly_volume=preset_vol)
        context.user_data["state"] = REG_B2B_POINTS
        await query.message.reply_text(
            "Шаг 5 из 5: количество точек (адресов), по которым нужна доставка.",
            reply_markup=b2b_points_keyboard(),
        )
        await ack()
        return

    if data.startswith("reg:b2b:pts:") and not is_registered(profile):
        if context.user_data.get("state") != REG_B2B_POINTS:
            await ack()
            return
        suffix = data.split(":")[-1]
        if suffix == "manual":
            await query.message.reply_text("Введите количество точек текстом.")
            await ack()
            return
        points_val = "1" if suffix == "1" else "2–5"
        update_profile(update, points_count=points_val, registered=True)
        context.user_data.pop("state", None)
        context.user_data.pop("onboarding_started", None)
        await query.message.reply_text(b2b_done_text(), reply_markup=ReplyKeyboardRemove())
        await ack()
        return

    if not is_registered(profile):
        await ack("Требуется регистрация")
        await query.message.reply_text(
            "Чтобы оформить заказ, завершите регистрацию командой /start."
        )
        return

    if data == "order:comment:none":
        draft = context.user_data.setdefault("draft_order", {})
        draft["comment"] = "-"
        context.user_data["draft_order"] = draft
        context.user_data["state"] = ORDER_DATE
        await ack()
        now = datetime.now()
        await query.message.reply_text(
            "Шаг 3 из 4: дата доставки.\n"
            "Строка календаря: ◀ месяц ▶; затем выберите число (выбранный день отмечен галочкой ✓).",
            reply_markup=calendar_markup(now.year, now.month, None),
        )
        return

    if data.startswith("order:calm:"):
        ym = data.split(":")[2]
        ys, ms = ym.split("-")
        year, month = int(ys), int(ms)
        draft = context.user_data.get("draft_order", {})
        selected = draft.get("date")
        try:
            await query.edit_message_reply_markup(
                reply_markup=calendar_markup(year, month, selected),
            )
        except Exception:
            pass
        await ack()
        return

    if data.startswith("order:cald:"):
        date_value = data.split(":", 2)[2]
        parts = date_value.split(".")
        year_s, month_s = parts[2], parts[1]
        year, month = int(year_s), int(month_s)
        draft = context.user_data.setdefault("draft_order", {})
        draft["date"] = date_value
        context.user_data["draft_order"] = draft
        context.user_data["state"] = ORDER_TIME
        await ack("Дата выбрана")
        try:
            await query.edit_message_reply_markup(
                reply_markup=calendar_markup(year, month, date_value),
            )
        except Exception:
            pass
        await query.message.reply_text(
            TIME_WINDOW_DISCLAIMER + "\n\nВыберите интервал доставки:",
            reply_markup=time_picker_keyboard(),
        )
        return

    if data == "order:qty:manual":
        context.user_data["state"] = ORDER_MANUAL_QTY
        await ack()
        await query.message.reply_text(
            "Введите количество бутылей числом (не менее 3)."
        )
        return

    if data.startswith("order:qty:"):
        qty = int(data.split(":")[-1])
        context.user_data["draft_order"] = {"quantity": max(3, qty)}
        context.user_data["state"] = ORDER_COMMENT
        await ack()
        await query.message.reply_text(
            "Шаг 2 из 4: комментарий к заказу.\n"
            "Если комментарий не нужен — нажмите кнопку ниже или отправьте «-».",
            reply_markup=order_comment_keyboard(),
        )
        return

    if data == "order:time:manual":
        await ack()
        await query.message.reply_text(
            "Введите желаемый интервал времени текстом, например «17:00–20:00»."
        )
        return

    if data.startswith("order:time:"):
        time_value = data.split(":", 2)[-1]
        draft = context.user_data.get("draft_order", {})
        msg = create_order(
            update=update,
            quantity=int(draft.get("quantity", 3)),
            comment=str(draft.get("comment", "")),
            date=str(draft.get("date", "")),
            time=time_value,
        )
        context.user_data.pop("state", None)
        context.user_data.pop("draft_order", None)
        await ack("Готово")
        await query.message.reply_text(
            "Заказ принят. Спасибо за обращение.",
            reply_markup=ReplyKeyboardRemove(),
        )
        await query.message.reply_text(msg)
        return

    await ack()


async def handle_webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.web_app_data:
        return
    try:
        payload = json.loads(update.message.web_app_data.data or "{}")
    except Exception:
        await update.message.reply_text("Не удалось прочитать данные мини-аппа.")
        return

    event = str(payload.get("event", "")).strip()
    profile = get_or_create_profile(update)

    if event == "profile_update":
        update_profile(
            update,
            name=str(payload.get("name", "")).strip() or profile.get("name", ""),
            phone=str(payload.get("phone", "")).strip() or profile.get("phone", ""),
            main_address=str(payload.get("mainAddress", "")).strip() or profile.get("main_address", ""),
            floor=str(payload.get("floor", "")).strip() or profile.get("floor", ""),
            intercom=str(payload.get("intercom", "")).strip() or profile.get("intercom", ""),
            notes=str(payload.get("notes", "")).strip() or profile.get("notes", ""),
        )
        profile = get_or_create_profile(update)
        await update.message.reply_text(
            "Данные профиля сохранены.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    if event == "order":
        try:
            quantity = max(3, int(payload.get("quantity", 3)))
        except Exception:
            quantity = 3
        comment = str(payload.get("comment", "")).strip()
        order = {
            "ts": now_str(),
            "chat_id": update.effective_chat.id if update.effective_chat else 0,
            "name": get_display_name(profile),
            "phone": profile.get("phone", "не указан"),
            "quantity": quantity,
            "date": str(payload.get("date", "")).strip() or "не указана",
            "time": str(payload.get("time", "")).strip() or "не указано",
            "address": str(payload.get("selectedAddress", "")).strip()
            or profile.get("main_address", "не указан"),
            "comment": comment or "без комментария",
            "source": "miniapp",
            "product": str(payload.get("productTitle", "Вода 19л")).strip(),
        }
        orders = load_orders()
        orders.append(order)
        save_orders(orders)
        liters = int(profile.get("liters_total", 0)) + quantity * LITERS_PER_BOTTLE
        update_profile(update, liters_total=liters)
        await update.message.reply_text(
            "Заказ принят.\n"
            f"Товар: {order['product']}\n"
            f"Количество: {quantity}\n"
            f"Адрес: {order['address']}\n"
            f"Дата и интервал: {order['date']} {order['time']}",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    if event == "b2b":
        await update.message.reply_text(
            "Заявка зарегистрирована.\n"
            "Специалист свяжется для уточнения деталей.\n\n"
            f"Компания: {payload.get('company', '-')}\n"
            f"ИНН: {payload.get('inn', '-')}\n"
            f"Точек: {payload.get('pointsCount', '-')}\n"
            f"Объём: {payload.get('volume', '-')}\n"
            f"Контакт: {payload.get('contact', '-')}",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    if event == "rating":
        await update.message.reply_text("Спасибо за оценку 🙏")
        return

    if event in ("catalog_sync", "catalog_update"):
        products = payload.get("products")
        if isinstance(products, list):
            save_catalog(products)
            upload_catalog_via_ftp_if_configured()
            await update.message.reply_text(
                "Каталог обновлён и сохранён.",
                reply_markup=ReplyKeyboardRemove(),
            )
        else:
            await update.message.reply_text(
                "Карточка отмечена. Полный каталог приходит событием catalog_sync.",
                reply_markup=ReplyKeyboardRemove(),
            )
        return

    await update.message.reply_text("Данные мини-аппа получены.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_chat:
        return

    text = (update.message.text or "").strip()
    state = context.user_data.get("state")
    profile = get_or_create_profile(update)

    if state == REG_B2C_PHONE:
        phone = text
        if update.message.contact and update.message.contact.phone_number:
            phone = update.message.contact.phone_number
        if not phone:
            await update.message.reply_text(
                "Укажите номер телефона кнопкой «Поделиться номером» или введите его вручную."
            )
            return
        update_profile(update, phone=phone)
        context.user_data["state"] = REG_B2C_NAME
        await update.message.reply_text(
            "Шаг 2 из 6: как к вам обращаться? Укажите имя.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    if state == REG_B2C_NAME:
        if not text:
            await update.message.reply_text("Введите имя.")
            return
        update_profile(update, name=text)
        context.user_data["state"] = REG_B2C_ADDRESS
        await update.message.reply_text(
            "Шаг 3 из 6: полный адрес доставки (населённый пункт, улица, дом, квартира или офис)."
        )
        return

    if state == REG_B2C_ADDRESS:
        if not text:
            await update.message.reply_text("Укажите адрес доставки.")
            return
        update_profile(update, main_address=text)
        context.user_data["state"] = REG_B2C_FLOOR
        await update.message.reply_text(
            "Шаг 4 из 6: этаж. Выберите вариант или нажмите «Другое» и напишите текстом.",
            reply_markup=b2c_floor_keyboard(),
        )
        return

    if state == REG_B2C_FLOOR:
        update_profile(update, floor=text or "-")
        context.user_data["state"] = REG_B2C_INTERCOM
        await update.message.reply_text(
            "Шаг 5 из 6: домофон.",
            reply_markup=b2c_intercom_keyboard(),
        )
        return

    if state == REG_B2C_INTERCOM:
        update_profile(update, intercom=text or "-")
        context.user_data["state"] = REG_B2C_NOTES
        await update.message.reply_text(
            "Шаг 6 из 6: дополнительные указания для курьера.",
            reply_markup=b2c_notes_keyboard(),
        )
        return

    if state == REG_B2C_NOTES:
        update_profile(update, notes=text or "-", registered=True)
        context.user_data.pop("state", None)
        context.user_data.pop("onboarding_started", None)
        profile = get_or_create_profile(update)
        await update.message.reply_text(
            b2c_done_text(profile),
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    if state == REG_B2B_NAME:
        if not text:
            await update.message.reply_text("Укажите ФИО контактного лица.")
            return
        update_profile(update, name=text)
        context.user_data["state"] = REG_B2B_PHONE
        phone_kb = ReplyKeyboardMarkup(
            [[KeyboardButton("Поделиться номером", request_contact=True)]],
            resize_keyboard=True,
        )
        await update.message.reply_text(
            "Шаг 2 из 5: контактный телефон для обратной связи.",
            reply_markup=phone_kb,
        )
        return

    if state == REG_B2B_PHONE:
        phone = text
        if update.message.contact and update.message.contact.phone_number:
            phone = update.message.contact.phone_number
        if not phone:
            await update.message.reply_text(
                "Укажите номер телефона кнопкой «Поделиться номером» или введите его вручную."
            )
            return
        update_profile(update, phone=phone)
        context.user_data["state"] = REG_B2B_INN
        await update.message.reply_text(
            "Шаг 3 из 5: ИНН организации.",
            reply_markup=b2b_inn_keyboard(),
        )
        return

    if state == REG_B2B_INN:
        update_profile(update, inn=text or "-")
        context.user_data["state"] = REG_B2B_VOLUME
        await update.message.reply_text(
            "Шаг 4 из 5: ориентировочный объём поставок в неделю.",
            reply_markup=b2b_volume_keyboard(),
        )
        return

    if state == REG_B2B_VOLUME:
        update_profile(update, weekly_volume=text or "-")
        context.user_data["state"] = REG_B2B_POINTS
        await update.message.reply_text(
            "Шаг 5 из 5: количество точек (адресов), по которым нужна доставка.",
            reply_markup=b2b_points_keyboard(),
        )
        return

    if state == REG_B2B_POINTS:
        update_profile(update, points_count=text or "-", registered=True)
        context.user_data.pop("state", None)
        context.user_data.pop("onboarding_started", None)
        await update.message.reply_text(
            b2b_done_text(),
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    if not is_registered(profile):
        await update.message.reply_text(
            "Давайте сначала познакомимся. Нажмите /start.",
        )
        return

    if state == ORDER_MANUAL_QTY:
        try:
            qty = max(3, int(text))
        except Exception:
            await update.message.reply_text("Введите целое число не менее 3.")
            return
        context.user_data["draft_order"] = {"quantity": qty}
        context.user_data["state"] = ORDER_COMMENT
        await update.message.reply_text(
            "Шаг 2 из 4: комментарий к заказу.\n"
            "Если комментарий не нужен — нажмите кнопку ниже или отправьте «-».",
            reply_markup=order_comment_keyboard(),
        )
        return

    if state == ORDER_COMMENT:
        draft = context.user_data.get("draft_order", {})
        draft["comment"] = "" if text == "-" else text
        context.user_data["draft_order"] = draft
        context.user_data["state"] = ORDER_DATE
        now = datetime.now()
        await update.message.reply_text(
            "Шаг 3 из 4: дата доставки.\n"
            "Строка календаря: ◀ месяц ▶; затем выберите число (выбранный день отмечен галочкой ✓).",
            reply_markup=calendar_markup(now.year, now.month, None),
        )
        return

    if state == ORDER_DATE:
        draft = context.user_data.get("draft_order", {})
        draft["date"] = text
        context.user_data["draft_order"] = draft
        context.user_data["state"] = ORDER_TIME
        await update.message.reply_text(
            TIME_WINDOW_DISCLAIMER + "\n\nШаг 4 из 4: выберите интервал доставки:",
            reply_markup=time_picker_keyboard(),
        )
        return

    if state == ORDER_TIME:
        draft = context.user_data.get("draft_order", {})
        msg = create_order(
            update=update,
            quantity=int(draft.get("quantity", 3)),
            comment=str(draft.get("comment", "")),
            date=str(draft.get("date", "")),
            time=text,
        )
        context.user_data.pop("state", None)
        context.user_data.pop("draft_order", None)
        await update.message.reply_text(
            "Заказ принят. Спасибо за обращение.",
            reply_markup=ReplyKeyboardRemove(),
        )
        await update.message.reply_text(msg)
        return

    if text == "Заказать":
        await order_cmd(update, context)
        return

    await update.message.reply_text(
        "Откройте мини-приложение кнопкой меню «Заказать» или воспользуйтесь командами /order, /profile, /help.",
        reply_markup=ReplyKeyboardRemove(),
    )


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("handler error", exc_info=context.error)


async def post_init(app: Application) -> None:
    try:
        await app.bot.set_my_commands(
            [
                BotCommand("start", "Главное меню"),
                BotCommand("shop", "Магазин"),
                BotCommand("order", "Заказ в чате"),
                BotCommand("profile", "Профиль"),
                BotCommand("edit", "Данные в мини-апп"),
                BotCommand("help", "Справка"),
            ]
        )
        if webapp_available():
            base = webapp_url().split("#")[0].strip()
            await app.bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(
                    text="Заказать",
                    web_app=WebAppInfo(url=base),
                )
            )
        else:
            await app.bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    except Exception as exc:
        logger.warning("post_init failed: %s", exc)


def main() -> None:
    load_dotenv(dotenv_path=BASE_DIR / ".env", override=True)
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN in .env file")

    ensure_data_files()
    request = HTTPXRequest(
        connect_timeout=10.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=10.0,
        httpx_kwargs={"trust_env": False},
    )
    app = (
        Application.builder()
        .token(token)
        .job_queue(JobQueue())
        .request(request)
        .get_updates_request(request)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("order", order_cmd))
    app.add_handler(CommandHandler("shop", shop_cmd))
    app.add_handler(CommandHandler("b2b", b2b_cmd))
    app.add_handler(CommandHandler("profile", profile_cmd))
    app.add_handler(CommandHandler("edit", edit_profile_cmd))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_webapp_data))
    app.add_handler(
        MessageHandler((filters.TEXT | filters.CONTACT) & ~filters.COMMAND, handle_message)
    )
    app.add_error_handler(on_error)

    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
