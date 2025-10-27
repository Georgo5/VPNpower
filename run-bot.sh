#!/usr/bin/env bash
set -Eeuo pipefail

cd /srv/vpnpower/app/vpn-subscription-starter

# Запускаем бот как модуль пакета, чтобы сработали относительные импорты (.config и т.д.)
exec /srv/vpnpower/app/vpn-subscription-starter/.venv/bin/python -m bot.bot
