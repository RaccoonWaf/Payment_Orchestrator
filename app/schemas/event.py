from datetime import datetime

from pydantic import BaseModel


class EventResponse(BaseModel):
    eventId: int
    type: str
    fromStatus: str | None
    toStatus: str
    message: str
    occurredAt: datetime
