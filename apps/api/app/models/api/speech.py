"""Request and response DTOs of `POST /speech/token`."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from app.config import SpeechLanguage, SpeechRegion
from app.models.api.base import ApiModel


class SpeechTokenRequest(ApiModel):
    company_id: uuid.UUID


class SpeechToken(ApiModel):
    """`aad#<resource id>#<access token>` for the Speech SDK; a secret while it lives."""

    token: str = Field(min_length=1, max_length=8192, repr=False)
    region: SpeechRegion
    expires_at: datetime
    language: SpeechLanguage
