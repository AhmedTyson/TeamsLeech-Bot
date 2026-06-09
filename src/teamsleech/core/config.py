from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class AppConfig(BaseSettings):
    """
    Centralized configuration for TeamsLeech Bot.
    Reads from environment variables or a local .env file.
    Throws a validation error immediately on boot if a required variable is missing.
    """
    # Microsoft / Auth
    teams_refresh_token: str = Field(..., alias="TEAMS_REFRESH_TOKEN")
    teams_client_id: str = Field("04b07795-8ddb-461a-bbee-02f9e1bf7b46", alias="TEAMS_CLIENT_ID")
    
    # Telegram Bot
    telegram_api_id: int = Field(..., alias="TELEGRAM_API_ID")
    telegram_api_hash: str = Field(..., alias="TELEGRAM_API_HASH")
    telegram_bot_token: str = Field(..., alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: int = Field(..., alias="TELEGRAM_CHAT_ID")
    
    # GitHub (Optional but recommended for secret rotation)
    gh_pat: str = Field("", alias="GH_PAT")
    github_repository: str = Field("", alias="GITHUB_REPOSITORY")
    
    # Internal Config
    subjects_json: str = Field("", alias="SUBJECTS_JSON")
    subjects_path: str = Field("subjects_config.json", alias="SUBJECTS_PATH")
    state_dir: str = Field(".state", alias="STATE_DIR")
    
    # Execution Flags
    auto_check: str = Field("0", alias="AUTO_CHECK")
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

# Global singleton configuration object to be imported by other modules
settings = AppConfig()
