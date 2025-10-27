# bot/bot.py
from __future__ import annotations

import asyncio
import logging
import io
import time, jwt
import secrets
from datetime import datetime, timedelta
from contextlib import suppress
from typing import Any
from urllib.parse import quote

import qrcode
import aiohttp
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, User
from aiogram.client.default import DefaultBotProperties
from aiogram.types.input_file import FSInputFile
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, BufferedInputFile
from aiogram.exceptions import TelegramBadRequest

from .config import (
    BOT_TOKEN,
    BACKEND_URL,
    REQUEST_TIMEOUT,
    BANNER_FILE_ID,
    BANNER_FILE_PATH,
    SUPPORT_USERNAME,
    FAQ_URL,
)
from .config import SUB_BASE_URL, BRAND_NAME, JWT_SECRET

# ⬇️ NEW: пробуем импортировать секрет линковки TG (если его нет — просто пропустим авто‑линк)
try:
    from .config import TG_LINK_SECRET  # str | None
except Exception:
    TG_LINK_SECRET = None  # type: ignore

from . import texts
from .keyboards import (
    kb_main,
    kb_devices,
    kb_device_detail,
    kb_about,
    kb_help,
    kb_invite,
    kb_tariffs,
)
from .deeplink import build_import_link, build_subscription_url

router = Router()
_bot_username_cache: str | None = None

# ========== helpers ==========

def link_for_user_id(uid: int, name: str | None) -> str:
    first = (name or "Пользователь").strip()
    return f'<a href="tg://user?id={uid}">{first}</a>'

def link_for_message_author(msg: Message) -> str:
    return link_for_user_id(msg.from_user.id, msg.from_user.full_name or msg.from_user.first_name)

def link_for_callback_user(c: CallbackQuery) -> str:
    return link_for_user_id(c.from_user.id, c.from_user.full_name or c.from_user.first_name)

async def get_me_username(bot: Bot) -> str:
    global _bot_username_cache
    if _bot_username_cache:
        return _bot_username_cache
    me = await bot.get_me()
    _bot_username_cache = me.username
    return _bot_username_cache

# ========== NEW: «естественная» привязка TG‑профиля к пользователю ==========
_last_link_push: dict[int, float] = {}  # антиспам на случай частых нажатий

async def _push_tg_link(user: User) -> None:
    """
    Отправляем на бэкенд профиль Telegram для сохранения в таблицу users:
    tg_id, tg_username, first_name, last_name.

    Безопасность: секрет передаётся в заголовке X-TG-Link-Secret (или в ?secret=... как запасной путь).
    Любая ошибка/отказ не ломает UX — мы молча продолжаем дальше.
    """
    if not BACKEND_URL or not TG_LINK_SECRET:
        return  # не настроено — просто выходим

    payload = {
        "telegram_id": int(user.id),
        "telegram_username": user.username or None,
        "first_name": user.first_name or None,
        "last_name": user.last_name or None,
    }
    headers = {"X-TG-Link-Secret": TG_LINK_SECRET, "Content-Type": "application/json"}
    timeout = aiohttp.ClientTimeout(total=min(REQUEST_TIMEOUT or 10, 15))

    # Несколько совместимых маршрутов — чтобы работать с вашим tg_link.py независимо от префикса.
    candidates = [
        f"{BACKEND_URL}/tg/link",           # ваш актуальный маршрут
        f"{BACKEND_URL}/api/tg/link",
        f"{BACKEND_URL}/api/users/tg/link",
    ]

    async with aiohttp.ClientSession(timeout=timeout) as sess:
        for url in candidates:
            # 1) с заголовком
            with suppress(Exception):
                async with sess.post(url, json=payload, headers=headers) as r:
                    if r.status in (200, 201, 204):
                        return
            # 2) как query (?secret=...)
            with suppress(Exception):
                async with sess.post(f"{url}?secret={quote(TG_LINK_SECRET)}", json=payload) as r:
                    if r.status in (200, 201, 204):
                        return
    # Если сюда дошли — просто залогируем в DEBUG и пойдём дальше
    logging.debug("TG link push failed (user_id=%s)", user.id)

async def ensure_linked(user: User, force: bool = False) -> None:
    """Делаем «мягкую» привязку не чаще раза в час (или сразу, если force=True)."""
    now = time.time()
    last = _last_link_push.get(user.id, 0)
    if not force and (now - last) < 3600:
        return
    _last_link_push[user.id] = now
    await _push_tg_link(user)

# ========== one‑click / подписка ==========

async def fetch_oneclick(telegram_id: int, platform: str) -> str | None:
    """
    Получаем ссылку/ключ для подключения с бэкенда.
    Поддерживаем JSON (link/url/token) и text/plain.
    Сервисные сообщения («# …») возвращаем как есть — бот покажет пользователю.
    """
    paths = [
        f"{BACKEND_URL}/oneclick?telegram_id={telegram_id}&platform={platform}",
        f"{BACKEND_URL}/api/oneclick?telegram_id={telegram_id}&platform={platform}",
        f"{BACKEND_URL}/oneclick/{telegram_id}?platform={platform}",
    ]
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
    async with aiohttp.ClientSession(timeout=timeout) as sess:
        for url in paths:
            with suppress(Exception):
                async with sess.get(url) as r:
                    if r.status == 200:
                        with suppress(Exception):
                            data = await r.json()
                            link = (data.get("link") or data.get("url") or "").strip()
                            if link:
                                return link
                            token = (data.get("token") or "").strip()
                            if token:
                                device_key = secrets.token_hex(4)
                                return build_subscription_url(token, device_key)
                        text = (await r.text()).strip()
                        if text.startswith(("vless://", "vmess://", "hysteria://", "https://")):
                            return text
                        if text.startswith("#"):
                            return text
                        if text and "/" not in text and " " not in text:
                            device_key = secrets.token_hex(4)
                            return build_subscription_url(text, device_key)
                    if r.status in (403, 409):
                        text = (await r.text()).strip()
                        if text:
                            return text
    return None

# --- безопасные утилиты для колбэков/редактирования ---

async def ack(c: CallbackQuery, text: str | None = None, alert: bool = False) -> None:
    with suppress(TelegramBadRequest):
        await c.answer(text=text, show_alert=alert)

async def safe_edit(message: Message, text: str, reply_markup=None) -> None:
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            return
        raise

# ========== Личный кабинет (fetch + форматирование) ==========

async def fetch_me(telegram_id: int) -> dict[str, Any] | None:
    paths = [
        f"{BACKEND_URL}/api/me?telegram_id={telegram_id}",
        f"{BACKEND_URL}/me?telegram_id={telegram_id}",
    ]
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
    async with aiohttp.ClientSession(timeout=timeout) as sess:
        for url in paths:
            with suppress(Exception):
                async with sess.get(url) as r:
                    if r.status == 200:
                        data = await r.json()
                        return {
                            "active": bool(data.get("active", False)),
                            "plan": str(data.get("plan", "expired")),
                            "days_left": int(data.get("days_left", 0)),
                            "devices": int(data.get("devices", 0)),
                            "max_devices": int(data.get("max_devices", 1)),
                            "trial_days": int(data.get("trial_days", 3)),
                            "bonus": int(data.get("bonus", 0)),
                        }
    return None

def _plural_ru(n: int, one: str, few: str, many: str) -> str:
    n_abs = abs(n) % 100
    n1 = n_abs % 10
    if 11 <= n_abs <= 19:
        return many
    if 2 <= n1 <= 4:
        return few
    if n1 == 1:
        return one
    return many

def _format_days(n: int) -> str:
    word = _plural_ru(n, "день", "дня", "дней")
    return f"{n} {word}"

def _tariff_name(me: dict[str, Any]) -> str:
    plan = (me.get("plan") or "expired").lower()
    max_dev = int(me.get("max_devices") or 1)
    if plan == "trial":
        return "Мощь (Пробный)"
    if plan == "pro":
        return "Абсолютная мощь" if max_dev >= 5 else "Мощь"
    return "Нет подписки"

def _approx_until_by_days(days_left: int) -> str:
    dt = datetime.now() + timedelta(days=max(0, days_left))
    dt = dt.replace(hour=23, minute=59, second=0, microsecond=0)
    return dt.strftime("%d.%m.%Y %H:%M")

def render_me_text(user_link: str, me: dict[str, Any]) -> str:
    top = "⚡ <b>VPNpower</b> ⚡ — безопасность и скорость для твоих любимых сервисов.\n\n"
    header = f"👑 {user_link}, <b>Ваш аккаунт:</b>"
    active = bool(me.get("active"))
    days_left = max(0, int(me.get("days_left") or 0))
    tariff = _tariff_name(me)
    bonus = int(me.get("bonus") or 0)

    if active:
        until = _approx_until_by_days(days_left)
        line1 = f"├ ✅ <b>Активен!</b> До: <b>{until}</b>"
        line2 = f"├ 🕒 Осталось дней: <b>{days_left}</b>"
    else:
        line1 = "├ 🔴 <b>Неактивен</b>"
        line2 = "├ 🕒 Осталось дней: <b>0</b>"

    line3 = f"├ 💼Тариф: <b>{tariff}</b>"
    line4 = f"└ 💎Бонусный баланс: <b>{bonus} ₽</b>"

    tips = (
        '<blockquote>🎁 Получай 100Р за каждого приглашённого друга. '
        'Подробнее — по кнопке "Пригласить"</blockquote>\n'
        '<blockquote>🆘 Наша поддержка работает 24/7. Если у Вас возникнут вопросы — '
        'переходи по кнопке "Помощь"</blockquote>'
    )
    return "\n".join([top, header, line1, line2, line3, line4, "", tips]).strip()

# ========== banner ==========

async def send_banner(bot: Bot, chat_id: int):
    try:
        if BANNER_FILE_ID:
            await bot.send_video(chat_id, BANNER_FILE_ID)
            return
        with suppress(Exception):
            await bot.send_video(chat_id, FSInputFile(BANNER_FILE_PATH))
            return
        logging.warning("Banner file not found or not sent: %s", BANNER_FILE_PATH)
        await bot.send_message(chat_id, "⚠️ Баннер временно недоступен. Продолжаем настройку…")
    except Exception:
        logging.exception("Failed to send banner")
        with suppress(Exception):
            await bot.send_message(chat_id, "⚠️ Баннер временно недоступен. Продолжаем настройку…")

# ========== handlers ==========

@router.message(CommandStart())
async def on_start(msg: Message, bot: Bot):
    # ⬇️ NEW: мягко отправим профиль в бэкенд
    await ensure_linked(msg.from_user, force=True)

    # баннер
    await send_banner(bot, msg.chat.id)
    # личный кабинет (динамический), при ошибке — старый текст
    me = await fetch_me(msg.from_user.id)
    text = render_me_text(link_for_message_author(msg), me) if me else texts.home_header(link_for_message_author(msg))
    await msg.answer(text, reply_markup=kb_main())

@router.callback_query(F.data == "home")
async def cb_home(c: CallbackQuery):
    await ack(c)
    await ensure_linked(c.from_user)  # ⬅️ NEW
    me = await fetch_me(c.from_user.id)
    text = render_me_text(link_for_callback_user(c), me) if me else texts.home_header(link_for_callback_user(c))
    await safe_edit(c.message, text, reply_markup=kb_main())

# --- About ---
@router.callback_query(F.data == "about")
async def cb_about(c: CallbackQuery):
    await ack(c)
    await ensure_linked(c.from_user)  # ⬅️ NEW
    await safe_edit(c.message, texts.about_text(), reply_markup=kb_about())

# --- Help ---
@router.callback_query(F.data == "help")
async def cb_help(c: CallbackQuery):
    await ack(c)
    await ensure_linked(c.from_user)  # ⬅️ NEW
    await safe_edit(c.message, texts.help_text(SUPPORT_USERNAME, FAQ_URL), reply_markup=kb_help())

# --- Invite (referrals) ---
@router.callback_query(F.data == "invite")
async def cb_invite(c: CallbackQuery, bot: Bot):
    await ack(c)
    await ensure_linked(c.from_user)  # ⬅️ NEW
    username = await get_me_username(bot)
    ref = f"https://t.me/{username}?start=ref_{c.from_user.id}"
    await safe_edit(c.message, texts.invite_text(ref), reply_markup=kb_invite())

# --- Tariffs screen ---
@router.callback_query(F.data == "renew")
async def cb_tariffs(c: CallbackQuery):
    await ack(c)
    await ensure_linked(c.from_user)  # ⬅️ NEW
    await safe_edit(c.message, texts.tariffs_text(), reply_markup=kb_tariffs())

# --- Connect flow ---
@router.callback_query(F.data == "connect")
async def cb_connect(c: CallbackQuery):
    await ack(c)
    await ensure_linked(c.from_user)  # ⬅️ NEW
    await safe_edit(c.message, texts.choose_device_text(), reply_markup=kb_devices())

@router.callback_query(F.data.in_({"dev_ios", "dev_android", "dev_windows", "dev_mac", "dev_tv"}))
async def cb_device(c: CallbackQuery):
    await ack(c)
    await ensure_linked(c.from_user)  # ⬅️ NEW
    mapping = {
        "dev_ios": ("🍏", "iOS", "ios"),
        "dev_android": ("🤖", "Android", "android"),
        "dev_windows": ("🪟", "Windows", "windows"),
        "dev_mac": ("💻", "Mac", "mac"),
        "dev_tv": ("📺", "Телевизор", "tv"),
    }
    em, title, key = mapping[c.data]
    await safe_edit(
        c.message,
        texts.device_instructions_title(em, title),
        reply_markup=kb_device_detail(key, has_store_link=(key in {"ios", "android"}))
    )

# === Подключение: редактируем текущее сообщение, без нового ===
@router.callback_query(F.data.in_({"go_ios", "go_android", "go_windows", "go_mac", "go_tv"}))
async def cb_go_platform(c: CallbackQuery):
    await ack(c, text="Готовим ключ…")
    await ensure_linked(c.from_user)  # ⬅️ NEW

    platform = c.data.replace("go_", "")
    platform_titles = {"ios": "iOS", "android": "Android", "windows": "Windows", "mac": "Mac", "tv": "TV"}
    title = platform_titles.get(platform, platform.upper())

    link_or_msg = await fetch_oneclick(c.from_user.id, platform)
    if not link_or_msg or link_or_msg.startswith("#"):
        human = link_or_msg or "Не удалось получить ключ. Попробуйте позже."
        await safe_edit(c.message, f"⚠️ {human}", reply_markup=kb_main())
        return

    link = link_or_msg
    can_autoinstall = platform in {"ios", "android"}
    if can_autoinstall:
        deep = build_import_link(platform, link, redirect=True, tg_id=int(c.from_user.id))
        connect_line = f"• ▶️ <a href=\"{deep}\"><b>Подключить автоматически</b></a>"
    else:
        connect_line = "• ▶️ Импортируйте ключ в приложении — смотрите видеоинструкцию ниже."

    app_map = {
        "ios": "https://vpnpower.ru/ios",
        "android": "https://vpnpower.ru/android",
        "windows": "https://vpnpower.ru/windows",
        "mac": "https://vpnpower.ru/mac",
        "tv": "https://vpnpower.ru/tv",
    }
    app_url = app_map.get(platform, "https://vpnpower.ru")
    video_url = FAQ_URL or "https://t.me/vpnpower_help/1"

    sub_link = build_subscription_url(tg_id=int(c.from_user.id))
    txt = (
        "<i>Сервисное сообщение: ключ будет привязан к этому устройству. "
        "Вы всегда сможете переустановить конфигурацию повторно.</i>\n\n"
        f"🔌 <b>Подключение — {title}</b>\n\n"
        f"{connect_line}\n"
        f"• 📲 Скачать приложение: <a href=\"{app_url}\">{app_url}</a>\n"
        f"• 🎬 Видео‑инструкция: <a href=\"{video_url}\">{video_url}</a>\n\n"
        "• 🔑 Ключ (для ручного копирования):\n"
        f"<code>{ sub_link or link }</code>\n\n"
        "При необходимости можете получить QR‑код ключа кнопкой ниже."
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧾 Показать QR‑код", callback_data=f"qr:{platform}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="connect")]
    ])
    await safe_edit(c.message, txt, reply_markup=kb)

# Показ QR (отдельным сообщением с фото)
@router.callback_query(F.data.startswith("qr:"))
async def cb_show_qr(c: CallbackQuery):
    await ack(c)
    await ensure_linked(c.from_user)  # ⬅️ NEW
    platform = c.data.split(":", 1)[1] if ":" in c.data else "ios"
    link_or_msg = await fetch_oneclick(c.from_user.id, platform)
    if not link_or_msg or link_or_msg.startswith("#"):
        await c.message.answer("⚠️ Не удалось получить ключ для QR. Попробуйте позже.")
        return

    img = qrcode.make(link_or_msg)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    photo = BufferedInputFile(buf.getvalue(), filename="vpnpower_qr.png")

    cap = (
        "🧾 <b>QR‑код ключа</b>\n"
        "Отсканируйте в приложении.\n\n"
        "Если не сканируется — откройте ссылку вручную:\n"
        f"<code>{link_or_msg}</code>"
    )
    await c.message.answer_photo(photo, caption=cap)

# --- Личный кабинет (колбэк и команда) ---

@router.callback_query(F.data.in_({"me", "cabinet", "lk", "status"}))
async def cb_me(c: CallbackQuery):
    await ack(c)
    await ensure_linked(c.from_user)  # ⬅️ NEW
    me = await fetch_me(c.from_user.id)
    if not me:
        await safe_edit(
            c.message,
            "⚠️ Не удалось получить статус. Попробуйте позже или напишите в поддержку.",
            reply_markup=kb_main(),
        )
        return
    text = render_me_text(link_for_callback_user(c), me)
    await safe_edit(c.message, text, reply_markup=kb_main())

@router.message(Command("me"))
async def cmd_me(msg: Message):
    await ensure_linked(msg.from_user)  # ⬅️ NEW
    me = await fetch_me(msg.from_user.id)
    if not me:
        await msg.answer("⚠️ Не удалось получить статус. Попробуйте позже или напишите в поддержку.", reply_markup=kb_main())
        return
    text = render_me_text(link_for_message_author(msg), me)
    await msg.answer(text, reply_markup=kb_main())

# ========= Fallbacks for /vless (auto) =========
try:
    SUB_BASE_URL  # type: ignore[name-defined]
    JWT_SECRET    # type: ignore[name-defined]
    BRAND_NAME    # type: ignore[name-defined]
except Exception:
    from .config import SUB_BASE_URL, JWT_SECRET, BRAND_NAME  # type: ignore

def _first_vless_line(body: str) -> str | None:
    for line in (body or '').splitlines():
        s = line.strip()
        if s.startswith(('vless://','vmess://','hysteria://')):
            return s
    return None

def _me_from_vless_header(body: str):
    if not body:
        return None
    first = (body.splitlines() or [''])[0]
    plan_raw = 'expired'
    days_left = 0
    if 'plan:' in first:
        plan_raw = first.split('plan:',1)[1].split(',')[0].strip().lower()
    if 'days_left:' in first:
        tail = first.split('days_left:',1)[1]
        digits = ''.join(ch for ch in tail if ch.isdigit())
        try: days_left = int(digits or '0')
        except Exception: days_left = 0
    plan = 'pro' if plan_raw in ('active','pro') else ('trial' if plan_raw=='trial' else 'expired')
    active = plan != 'expired' and (days_left > 0 or plan in ('trial','pro'))
    return {
        'active': active, 'plan': plan, 'days_left': days_left,
        'devices': 1, 'max_devices': 5, 'trial_days': 3, 'bonus': 0
    }

async def _get_vless_bundle_by_jwt(uid: int) -> str | None:
    if not JWT_SECRET:
        return None
    now = int(time.time())
    try:
        token = jwt.encode(
            {'iss': BRAND_NAME, 'sub': str(uid), 'tv': 0, 'iat': now, 'exp': now+3600, 'scope': 'subscription', 'uid': uid},
            JWT_SECRET, algorithm='HS256'
        )
    except Exception:
        return None
    url = SUB_BASE_URL.rstrip('/') + '/vless?token=' + token
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
    async with aiohttp.ClientSession(timeout=timeout) as sess:
        with suppress(Exception):
            async with sess.get(url) as r:
                if r.status == 200:
                    return (await r.text()).strip()
    return None

# Оборачиваем исходные функции, чтобы добавить фолбэк на /vless
_original_fetch_oneclick = fetch_oneclick  # type: ignore
async def fetch_oneclick(telegram_id: int, platform: str) -> str | None:  # type: ignore[override]
    link = await _original_fetch_oneclick(telegram_id, platform)
    if link and not str(link).startswith('#'):
        return link
    body = await _get_vless_bundle_by_jwt(telegram_id)
    if not body:
        return link
    v = _first_vless_line(body)
    return v or link

_original_fetch_me = fetch_me  # type: ignore
async def fetch_me(telegram_id: int):  # type: ignore[override]
    me = await _original_fetch_me(telegram_id)
    if me:
        return me
    body = await _get_vless_bundle_by_jwt(telegram_id)
    if not body:
        return None
    return _me_from_vless_header(body)

# ========= run =========

async def main():
    logging.basicConfig(level=logging.INFO)
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    with suppress(Exception):
        await bot.delete_webhook(drop_pending_updates=True)

    dp = Dispatcher()
    dp.include_router(router)

    logging.info("Bot started")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())
