from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_serializer

from app.utils import to_iso


class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @field_serializer("*", when_used="json")
    @classmethod
    def _serialize_datetimes(cls, value, _info):
        if isinstance(value, datetime):
            return to_iso(value)
        return value


class ErrorResponse(BaseModel):
    error_code: str
    message: str
    details: dict


class MessageResponse(BaseModel):
    message: str
