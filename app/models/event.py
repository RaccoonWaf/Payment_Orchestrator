from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (DateTime,
                        ForeignKey,
                        Integer,
                        String,
                        UniqueConstraint,
                        func
                        )
from sqlalchemy.orm import (Mapped,
                            mapped_column,
                            relationship
                            )

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.operation import Operation


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
        )

    __table_args__ = (
        UniqueConstraint(
            "operation_id",
            "event_id",
            ),
    )

    event_id: Mapped[int] = mapped_column(Integer, nullable=False)
    operation_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("operations.operation_id"),
        nullable=False,
        index=True,
    )

    type: Mapped[str] = mapped_column(String(32), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[str] = mapped_column(String(512), nullable=False)

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    operation: Mapped[Operation] = relationship(back_populates="events")
