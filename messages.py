# bot/messages.py
from datetime import datetime

def fmt_dt(dt: datetime | None) -> str:
    if not dt:
        return "—"
    return dt.strftime("%d.%m.%Y %H:%M")

def title_brand(brand: str) -> str:
    # Молнии по краям, как просили
    return f"⚡️ <b>{brand}</b> ⚡️"

def cabinet_text(brand: str, plan: str, expires_at: datetime | None,
                 trial_available: bool, bonus_balance: int,
                 devices_used: int, devices_limit: int, referral_link: str) -> str:
    parts = [title_brand(brand), ""]
    parts.append("🎯 <b>Личный кабинет</b>")
    parts.append(f"📦 Тариф: <b>{plan}</b>")
    parts.append(f"⏳ Действует до: <b>{fmt_dt(expires_at)}</b>")
    if trial_available:
        parts.append("🎁 Доступен пробный период <b>3 дня</b> — активируйте в один тап ниже.")
    parts.append(f"💳 Бонусный баланс: <b>{bonus_balance} ₽</b>")
    parts.append(f"📱 Устройства: <b>{devices_used}</b> / <b>{devices_limit}</b>")
    parts.append("")
    parts.append("🚀 <b>Поделись суперсилой VPN с друзьями</b> и получи <b>+100 ₽</b> на бонусный баланс:")
    parts.append(f"🔗 {referral_link}")
    return "\n".join(parts)

def vpnpower_text() -> str:
    return (
        "✨ <b>VPNpower — быстро и без лишней суеты</b>\n\n"
        "✅ Доступ к любимым сервисам: YouTube, ChatGPT, Telegram, Instagram и др.\n"
        "🔒 Шифрование трафика, без логов и регистрации действий.\n"
        "⚙️ Простой импорт конфигурации: один тап — и готово.\n"
        "🌍 Несколько гео‑узлов для стабильной скорости."
    )

def help_text() -> str:
    return (
        "🆘 <b>Помощь</b>\n\n"
        "— Частые вопросы (FAQ)\n"
        "— Инструкции по установке и импорту\n"
        "— Живая поддержка: нажмите «Написать в поддержку»"
    )

def renew_text() -> str:
    return (
        "💳 <b>Продлить подписку</b>\n\n"
        "Выберите подходящий вариант:"
    )

def connect_header() -> str:
    return (
        "🔌 <b>Подключить VPN</b>\n\n"
        "1) Скачайте приложение для вашей платформы\n"
        "2) Нажмите «Создать ключ и импортировать» — конфигурация откроется в клиенте автоматически"
    )
