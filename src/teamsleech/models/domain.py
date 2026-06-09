from datetime import datetime
from pydantic import BaseModel, Field

class Recording(BaseModel):
    name: str
    size_mb: float
    created: str
    time: str = ""
    duration_ms: int | float = 0
    drive_id: str
    item_id: str
    team_name: str
    subject_name: str
    is_video: bool = False

    model_config = {"extra": "ignore"}

class SubjectConfig(BaseModel):
    name: str
    short: str = ""
    doctor: str = ""
    keywords: list[str] = Field(default_factory=list)

    model_config = {"extra": "ignore"}

class Team(BaseModel):
    id: str
    display_name: str = Field(alias="displayName")

    model_config = {"populate_by_name": True, "extra": "ignore"}

class UserSession(BaseModel):
    is_searching_teams: bool = False
    pending_add_step: str = ""
    pending_add_team: Team | None = None
    pending_add_data: dict[str, str] = Field(default_factory=dict)

    pending_rename_idx: int | None = None
    pending_suggestion: str | None = None

    date_input_pending: bool = False
    subject_filter: str | None = None
    scan_label: str = ""

    pending_recordings: list[Recording] = Field(default_factory=list)
    selected_indices: set[int] = Field(default_factory=set)
    rename_overrides: dict[int, str] = Field(default_factory=dict)
