from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from spark.core.database import Base


class Role(Base):
    __tablename__ = "roles"

    role_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role_code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(120))
    google_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    picture_url: Mapped[str | None] = mapped_column(String(512))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_super_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    token_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    privacy_policy_accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    privacy_policy_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("roles.role_id", ondelete="CASCADE"), primary_key=True
    )


class Factory(Base):
    __tablename__ = "factories"

    factory_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    factory_name: Mapped[str] = mapped_column(String(100), nullable=False)
    location: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    machines: Mapped[list["Machine"]] = relationship(back_populates="factory", lazy="select")


class UserFactoryAccess(Base):
    __tablename__ = "user_factory_access"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True
    )
    factory_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("factories.factory_id", ondelete="CASCADE"), primary_key=True
    )
    access_level: Mapped[str] = mapped_column(String(20), default="read")


class Machine(Base):
    __tablename__ = "machines"

    machine_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    factory_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("factories.factory_id"), nullable=False, index=True
    )
    machine_name: Mapped[str] = mapped_column(String(100), nullable=False)
    machine_type: Mapped[str | None] = mapped_column(String(50))
    manufacturer: Mapped[str | None] = mapped_column(String(100))
    model_number: Mapped[str | None] = mapped_column(String(100))
    install_date: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text)
    image_storage_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    factory: Mapped[Factory] = relationship(back_populates="machines", lazy="select")
    aliases: Mapped[list["MachineAlias"]] = relationship(back_populates="machine", lazy="select")
    components: Mapped[list["Component"]] = relationship(back_populates="machine", lazy="select")


class MachineAlias(Base):
    __tablename__ = "machine_aliases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    machine_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("machines.machine_id", ondelete="CASCADE"), nullable=False
    )
    alias: Mapped[str] = mapped_column(String(100), nullable=False)
    source: Mapped[str | None] = mapped_column(String(50))
    confidence: Mapped[float | None] = mapped_column(Numeric(3, 2), default=1.00)

    machine: Mapped[Machine] = relationship(back_populates="aliases", lazy="select")


class Component(Base):
    __tablename__ = "components"

    component_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    machine_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("machines.machine_id"), nullable=False, index=True
    )
    parent_component_id: Mapped[str | None] = mapped_column(
        String(30), ForeignKey("components.component_id"), index=True
    )
    component_name: Mapped[str] = mapped_column(String(100), nullable=False)
    component_type: Mapped[str | None] = mapped_column(String(50))
    manufacturer: Mapped[str | None] = mapped_column(String(100))
    part_number: Mapped[str | None] = mapped_column(String(100))
    install_date: Mapped[date | None] = mapped_column(Date)
    depth: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    machine: Mapped[Machine] = relationship(back_populates="components", lazy="select")
    parent: Mapped["Component | None"] = relationship(
        remote_side=[component_id], back_populates="children", lazy="select"
    )
    children: Mapped[list["Component"]] = relationship(back_populates="parent", lazy="select")
    aliases: Mapped[list["ComponentAlias"]] = relationship(back_populates="component", lazy="select")


class ComponentAlias(Base):
    __tablename__ = "component_aliases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    component_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("components.component_id", ondelete="CASCADE"), nullable=False
    )
    alias: Mapped[str] = mapped_column(String(100), nullable=False)
    source: Mapped[str | None] = mapped_column(String(50))

    component: Mapped[Component] = relationship(back_populates="aliases", lazy="select")
