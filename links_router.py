from aiogram import Router, types
from aiogram.filters import Command
import os, time, jwt, httpx, asyncio
from sqlalchemy import create_engine, text
from .config import SUB_BASE_URL, BRAND_NAME, JWT_SECRET, REQUEST_TIMEOUT

router = Router()
_engine = create_engine(os.environ['DATABASE_URL'], pool_pre_ping=True, future=True)

def _uid_by_tg(tg_id: int) -> int | None:
    with _engine.begin() as c:
        row = c.execute(text('select id from users where tg_id=:tg'), {'tg': tg_id}).one_or_none()
        return row[0] if row else None

@router.message(Command('links'))
async def links_handler(m: types.Message):
    uid = await asyncio.to_thread(_uid_by_tg, m.from_user.id)
    if not uid:
        await m.answer('⚠️ В базе не найден ваш профиль по tg_id. Напишите в поддержку.')
        return
    now = int(time.time())
    token = jwt.encode(
        {'iss': BRAND_NAME, 'sub': str(uid), 'tv': 0, 'iat': now, 'exp': now+3600, 'scope': 'subscription', 'uid': uid},
        JWT_SECRET, algorithm='HS256'
    )
    url = SUB_BASE_URL.rstrip('/') + '/vless?token=' + token
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            r = await client.get(url)
        txt = (r.text or '').strip()
        if r.status_code == 200 and txt:
            await m.answer(txt)
        else:
            await m.answer(f'⚠️ Backend ответил {r.status_code}. Не удалось получить ключ.')
    except Exception:
        await m.answer('⚠️ Не удалось получить ключ. Попробуйте позже.')
