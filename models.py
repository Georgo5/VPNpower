# backend/models.py
from __future__ import annotations

from sqlalchemy import (
    Column, Integer, BigInteger, String, Boolean, DateTime,
    ForeignKey, UniqueConstraint, Index, text,
)
from sqlalchemy.orm import relationship, deferred, synonym
from .db import Base, utcnow
import uuid as _uuid


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    tg_id = Column(BigInteger, unique=True, index=True, nullable=False)
    tg_username = Column(String(64), nullable=True)
    first_name = Column(String(64), nullable=True)
    last_name = Column(String(64), nullable=True)

    plan_id = deferred(Column(String(32), nullable=True))
    # одно объявление достаточно; alias ниже сохранён
    plan_devices = Column("device_slots", Integer, nullable=False, server_default=text("1"))
    device_slots = synonym("plan_devices")  # алиас для обратной совместимости

    # служебные флаги
    trial_used = Column(Boolean, nullable=False, server_default=text("false"))
    autopay_enabled = Column(Boolean, nullable=False, server_default=text("false"))

    subscription_active = Column(Boolean, nullable=False, server_default=text("true"))
    is_admin = Column(Boolean, nullable=False, server_default=text("false"))
    token_version = Column(Integer, nullable=False, server_default=text("0"))

    vless_uuid = Column(String(36), nullable=True)
    subscription_end_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=True)

    devices = relationship("Device", back_populates="user", cascade="all, delete-orphan")
    oneclick_tokens = relationship("OneClickToken", back_populates="user", cascade="all, delete-orphan")

    def ensure_uuid(self):
        if not self.vless_uuid:
            self.vless_uuid = str(_uuid.uuid4())


class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # "Слот" устройства (передаётся как d=... в ссылке подписки)
    device_key = Column(String(128), nullable=False)

    # Новые поля для полноценной логики (помечены deferred, чтобы не падать до миграций)
    uuid = deferred(Column(String(36), nullable=True))            # пер‑устройство VLESS UUID
    platform = deferred(Column(String(16), nullable=True))        # ios|android|windows|mac|linux|other
    status = deferred(Column(String(16), nullable=False, server_default="active"))  # active|blocked|evicted
    last_seen_ip = deferred(Column(String(64), nullable=True))    # строкой, без PG‑специфичных типов
    last_seen_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    user = relationship("User", back_populates="devices")

    __table_args__ = (
        UniqueConstraint("user_id", "device_key", name="uq_user_device"),  # уникальность слота в рамках пользователя
        UniqueConstraint("uuid", name="uq_device_uuid"),
        Index("ix_devices_status", "status"),
    )

    def ensure_uuid(self):
        """Генерирует UUID для устройства при первом обращении."""
        if not self.uuid:
            self.uuid = str(_uuid.uuid4())


class Node(Base):
    __tablename__ = "nodes"

    id = Column(Integer, primary_key=True)

    # Отображаемое имя и краткая "региональная" метка
    name = Column(String(64), nullable=True)  # делаем мягким, на старых БД может не быть колонки
    region = Column(String(8), nullable=True)  # например, 'EU'

    # Параметры Reality (имеющиеся в текущей схеме)
    host = Column(String(128), nullable=False, index=True)
    port = Column(Integer, nullable=False)
    reality_public_key = Column(String(128), nullable=False)
    short_id = Column(String(32), nullable=False)
    sni = Column(String(128), nullable=False)
    flow = Column(String(64), nullable=False, server_default="xtls-rprx-vision")
    fingerprint = Column(String(32), nullable=False, server_default="chrome")

    # Флаг активности
    active = Column(Boolean, nullable=False, server_default=text("true"))

    # Новые мягкие поля для масштабирования по странам/приоритетам (deferred до миграций)
    country_code = deferred(Column(String(2), nullable=True))     # 'SE', 'FI', ...
    country_name = deferred(Column(String(64), nullable=True))    # 'Sweden', 'Finland', ...
    priority = deferred(Column(Integer, nullable=False, server_default="100"))

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("host", "port", name="uq_node_host_port"),
        Index("ix_nodes_active", "active"),
        Index("ix_nodes_country_code", "country_code"),
        Index("ix_nodes_priority", "priority"),
    )


class OneClickToken(Base):
    __tablename__ = "oneclick_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Сам подписочный токен (уникальный) и статусы
    token = deferred(Column(String(64), unique=True, nullable=True))
    expires_at = deferred(Column(DateTime(timezone=True), nullable=True))
    revoked_at = deferred(Column(DateTime(timezone=True), nullable=True))
    last_used_at = deferred(Column(DateTime(timezone=True), nullable=True))

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    user = relationship("User", back_populates="oneclick_tokens")

    __table_args__ = (
        # отдельная уникальная колонка уже помечена unique=True выше;
        # оставляем индексы для выборок:
        Index("ix_oneclick_user_id", "user_id"),
        Index("ix_oneclick_token", "token"),
    )
