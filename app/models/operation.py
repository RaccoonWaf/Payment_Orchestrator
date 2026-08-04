from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, func, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.enums import OperationStatus
from app.models.base import Base


if TYPE_CHECKING:
    from app.models.event import Event


class Operation(Base):
    __tablename__ = "operations"

    operation_id: Mapped[str] = mapped_column(
        String(255),
        primary_key=True
        )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        )
    currency: Mapped[str] = mapped_column(
        String(8),
        nullable=False
        )
    description: Mapped[str] = mapped_column(
        String(512),
        nullable=False
        )

    status: Mapped[OperationStatus] = mapped_column(
        String(32),
        nullable=False,
        default=OperationStatus.CREATED,
        index=True,
    )
    provider_payment_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        unique=True,
        )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    submit_intent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    events: Mapped[list[Event]] = relationship(
        back_populates="operation",
        order_by="Event.event_id",
        cascade="all, delete-orphan",
    )
