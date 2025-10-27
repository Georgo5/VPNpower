# backend/seed_node.py
from __future__ import annotations

from dotenv import load_dotenv, find_dotenv
from sqlalchemy.orm import Session

from .db import Base, engine, SessionLocal         # <-- корректный импорт
from .models import Node

load_dotenv(find_dotenv(), override=True)


def upsert_node(
    *,
    name: str | None,
    region: str | None,
    host: str,
    port: int,
    reality_public_key: str,
    short_id: str,
    sni: str | None = None,
    flow: str = "xtls-rprx-vision",
    fingerprint: str = "chrome",
    active: bool = True,
) -> None:
    """
    Создаёт или обновляет узел по уникальной паре host:port.
    Поля country_code/country_name/priority можно будет добавить позже.
    """
    # гарантируем наличие таблиц (подключение — из .env: DATABASE_URL=postgresql+psycopg2://...)
    Base.metadata.create_all(bind=engine)

    db: Session = SessionLocal()
    try:
        node = db.query(Node).filter(Node.host == host, Node.port == port).first()
        if node:
            # обновляем существующий
            node.name = name
            node.region = region
            node.reality_public_key = reality_public_key
            node.short_id = short_id
            node.sni = sni or host
            node.flow = flow
            node.fingerprint = fingerprint
            node.active = active
            db.commit()
            print(f"[UPDATE] {host}:{port}")
        else:
            # создаём новый
            node = Node(
                name=name,
                region=region,
                host=host,
                port=port,
                reality_public_key=reality_public_key,
                short_id=short_id,
                sni=sni or host,
                flow=flow,
                fingerprint=fingerprint,
                active=active,
            )
            db.add(node)
            db.commit()
            print(f"[CREATE] {host}:{port}")
    finally:
        db.close()


def main():
    # TODO: замени значениями твоего сервера Reality
    upsert_node(
        name="Finland-1",
        region="EU",
        host="your.server.com",         # домен/IPv4 реального узла
        port=443,
        reality_public_key="PBK_BASE64", # публичный ключ Reality (pbk)
        short_id="abcd1234",             # short_id из конфига Reality
        sni="www.cloudflare.com",        # либо свой домен; если не знаешь — ставь свой host
    )

    # При необходимости можно добавить ещё узлы:
    # upsert_node(
    #     name="Germany-1",
    #     region="EU",
    #     host="de1.your.server.com",
    #     port=443,
    #     reality_public_key="PBK_2",
    #     short_id="ef567890",
    #     sni="www.cloudflare.com",
    # )


if __name__ == "__main__":
    main()
