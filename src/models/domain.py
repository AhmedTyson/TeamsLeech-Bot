from datetime import datetime
from typing import Optional, Dict, Set, List
from pydantic import BaseModel, Field

class SubjectConfig(BaseModel):
    """Represents a course/subject configuration."""
    name: str
    short: str = ""
    doctor: str = ""
    keywords: List[str] = Field(default_factory=list)

class Recording(BaseModel):
    """Strict schema for a Microsoft Graph video recording."""
    name: str
    size_mb: float
    created: str  # e.g., YYYY-MM-DD
    time: str = ""  # e.g., HH:MM
    duration_ms: int = 0
    drive_id: str
    item_id: str
    team_name: str
    subject_name: str

class Team(BaseModel):
    """Represents a Microsoft Team from the Graph API."""
    id: str
    display_name: str = Field(alias="displayName")

class UserSession(BaseModel):
    """
    Finite State Machine (FSM) schema.
    Tracks everything a user is doing in the Telegram UI.
    """
    # Active Search / Setup mode
    is_searching_teams: bool = False
    
    # Recording Selection State
    pending_recordings: List[Recording] = Field(default_factory=list)
    selected_indices: Set[int] = Field(default_factory=set)
    rename_overrides: Dict[int, str] = Field(default_factory=dict)
    
    # Active UI Prompts
    pending_rename_idx: Optional[int] = None
    pending_suggestion: Optional[str] = None
    date_input_pending: bool = False
    scan_label: str = ""
    subject_filter: Optional[str] = None
    
    # Subject Adding Flow
    pending_add_team: Optional[Team] = None
    pending_add_step: str = ""  # e.g., "ask_name", "ask_short", "ask_doctor"
    pending_add_data: Dict[str, str] = Field(default_factory=dict)

