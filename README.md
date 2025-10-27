# VPN Subscription Starter (FastAPI + aiogram 3)

Базовый каркас для проекта: Telegram‑бот управляет подписками/ключами (**VLESS + REALITY/XTLS**), backend отдаёт **URL‑подписку** с профилями `vless://…` и одноразовые ссылки (QR).

## Что входит
- **backend/** (FastAPI, SQLAlchemy, JWT)
  - `GET /sub/vless?token=…` — отдаёт список `vless://…` (по одному на слот/устройство)
  - `GET /oneclick/{nonce}` — одноразовая страница QR + ссылка
  - `POST /users/register` — регистрация/активация триала (72 часа)
  - `POST /devices` — создать слот (при наличии свободных слотов)
  - `GET /debug/sub_token/{tg_id}` — (демо) получить токен подписки
- **bot/** (aiogram 3)
  - `/start`, меню, «Моя подписка», «Добавить устройство», «Инструкции»

> Это **минимальный скелет** — для продакшена добавьте платежи (Stars/ЮKassa/Т‑Касса/CloudPayments), XrayR‑интеграцию с `DeviceLimit/GlobalDeviceLimit`, роли/права, алерты и т.д.

## Запуск
1. Скопируйте `.env.example` → `.env` и заполните значения (секреты, токен бота).
2. `docker compose up --build`
3. Зайдите в контейнер `api` и выполните seed узла:
   ```bash
   docker compose exec api python seed_node.py
   ```
   Отредактируйте `seed_node.py`, подставьте **hostname/pbk/sid/sni** вашего REALITY‑узла.
4. В Telegram отправьте `/start` вашему боту. В меню «Моя подписка» появится ссылка вида:
   `http://localhost:8000/sub/vless?token=…` — используйте в клиентах **V2Box/v2rayNG/v2rayN**.

## Важно
- Подписка выдаёт `vless://` строки вида:
  `security=reality&flow=xtls-rprx-vision&fp=chrome&pbk=…&sid=…&sni=…&type=tcp` — клиенты их понимают.
- Реализация «1 слот = 1 активная сессия» предполагает **XrayR (DeviceLimit + GlobalDeviceLimit/Redis)** на ваших узлах.
- Панель 3x‑ui (если используете) **не публикуйте наружу**; доступ через SSH‑туннель.

## Дальше
- Добавьте платежи и фискализацию (если нужны рубли/чеки).
- Расширьте API: ротация ключа, перенос слота между узлами, подписки/акции, автопродление.
- Подключите Redis для одноразовых ссылок/кэширования.
