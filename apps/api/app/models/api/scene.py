"""The one-call canvas snapshot."""

from __future__ import annotations

from datetime import datetime

from app.models.api.base import ApiModel
from app.models.api.binding import Binding
from app.models.api.company import Company
from app.models.api.concept import Concept
from app.models.api.connector import ConnectorType
from app.models.api.proposal import Proposal
from app.models.api.relation import Relation
from app.models.api.settings import Appearance, Settings
from app.models.api.view_state import ViewState


class Scene(ApiModel):
    sequence: int
    server_time: datetime
    companies: list[Company]
    nodes: list[Concept]
    links: list[Relation | Binding]
    proposals: list[Proposal]
    settings: Settings
    appearance: Appearance
    view_state: ViewState
    connectors: list[ConnectorType]
