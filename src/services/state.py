import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from pyrogram import Client
from pyrogram.types import Message
from models.domain import UserSession

log = logging.getLogger("state_manager")

class StateManager:
    """
    Manages both persistent (Telegram DB) and ephemeral (in-memory) state.
    - Persistent: Subject last_run and last_lecture timestamps (saved to pinned msg).
    - Ephemeral: User UI session (saved in memory per-chat).
    """
    def __init__(self, client: Client, chat_id: int):
        self.client = client
        self.chat_id = chat_id
        
        # Persistent State (Synced to Telegram)
        self._subject_cache: Dict[str, Dict[str, Any]] = {}
        self._msg_id: Optional[int] = None
        self._initialized = False
        
        # Ephemeral State (User FSM)
        self._sessions: Dict[int, UserSession] = {}

    # ─── Ephemeral FSM (UserSession) ───────────────────────────────────

    def get_session(self, user_id: int) -> UserSession:
        """Get or create the user's current UI session."""
        if user_id not in self._sessions:
            self._sessions[user_id] = UserSession()
        return self._sessions[user_id]

    def clear_session(self, user_id: int) -> None:
        """Clear the user's session state safely."""
        self._sessions.pop(user_id, None)

    # ─── Persistent DB (Telegram Pinned Message) ───────────────────────

    async def initialize(self) -> None:
        """Loads persistent subject state from the pinned Telegram message."""
        if self._initialized:
            return
            
        try:
            chat = await self.client.get_chat(self.chat_id)
            if chat.pinned_message and chat.pinned_message.text and "#TEAMSLEECH_STATE" in chat.pinned_message.text:
                await self._parse_and_load(chat.pinned_message)
                return

            log.info("No pinned #TEAMSLEECH_STATE message found. Creating new empty database.")
            self._initialized = True
        except Exception as e:
            log.error(f"Failed to fetch telegram state: {e}")

    async def _parse_and_load(self, msg: Message) -> None:
        """Extracts JSON safely from the state message."""
        self._msg_id = msg.id
        text = msg.text or ""
        try:
            if "=====JSON_START=====" in text:
                json_str = text.split("=====JSON_START=====\n")[1].split("\n=====JSON_END=====")[0]
            elif "```json" in text:
                json_str = text.split("```json\n")[1].split("\n```")[0]
            else:
                json_str = text.split("#TEAMSLEECH_STATE\n")[1].replace("⚠️ DO NOT DELETE THIS MESSAGE\nThis acts as the database for the bot.\n", "").strip()
            self._subject_cache = json.loads(json_str)
        except Exception as e:
            log.warning("Failed to parse state JSON. Resetting cache and rewriting.")
            self._subject_cache = {}
            await self._push_to_telegram()
        self._initialized = True
        log.info("StateManager initialized. Loaded %d subjects.", len(self._subject_cache))

    async def _push_to_telegram(self) -> None:
        """Writes the subject_cache to Telegram."""
        text = (
            "#TEAMSLEECH_STATE\n"
            "**⚠️ DO NOT DELETE THIS MESSAGE**\n"
            "_This acts as the database for the bot._\n\n"
            "=====JSON_START=====\n"
            f"{json.dumps(self._subject_cache, indent=2)}\n"
            "=====JSON_END====="
        )
        try:
            if self._msg_id:
                await self.client.edit_message_text(self.chat_id, self._msg_id, text)
            else:
                msg = await self.client.send_message(self.chat_id, text)
                await msg.pin(both_sides=True)
                self._msg_id = msg.id
            log.info("Successfully pushed updated state to Telegram DB.")
        except Exception as e:
            log.error(f"Failed to push state to Telegram: {e}")

    def get_last_run(self, subject_name: str) -> datetime:
        """Gets the last_run timestamp for a subject natively from memory cache."""
        safe_name = subject_name.replace(" ", "_").lower()
        raw = self._subject_cache.get(safe_name)
        if not raw:
            return datetime.min.replace(tzinfo=timezone.utc)
            
        try:
            if isinstance(raw, dict):
                return datetime.fromisoformat(raw.get("last_run", ""))
            return datetime.fromisoformat(raw)
        except ValueError:
            return datetime.min.replace(tzinfo=timezone.utc)

    def get_last_lecture(self, subject_name: str) -> int:
        """Gets the last_lecture number for a subject from memory cache."""
        safe_name = subject_name.replace(" ", "_").lower()
        raw = self._subject_cache.get(safe_name)
        if isinstance(raw, dict):
            return raw.get("last_lecture", 0)
        return 0

    async def save_last_run(self, subject_name: str, timestamp: Optional[datetime] = None) -> None:
        """Updates the memory cache and immediately pushes to Telegram."""
        if not self._initialized:
            await self.initialize()
            
        safe_name = subject_name.replace(" ", "_").lower()
        ts = timestamp or datetime.now(timezone.utc)
        
        raw = self._subject_cache.get(safe_name)
        if isinstance(raw, dict):
            raw["last_run"] = ts.isoformat()
            self._subject_cache[safe_name] = raw
        else:
            self._subject_cache[safe_name] = {"last_run": ts.isoformat(), "last_lecture": 0}
            
        await self._push_to_telegram()

    async def save_last_lecture(self, subject_name: str, lecture_num: int) -> None:
        """Updates the last_lecture number in memory cache and pushes to Telegram."""
        if not self._initialized:
            await self.initialize()
            
        safe_name = subject_name.replace(" ", "_").lower()
        
        raw = self._subject_cache.get(safe_name)
        if isinstance(raw, dict):
            raw["last_lecture"] = lecture_num
            self._subject_cache[safe_name] = raw
        else:
            last_run = raw if isinstance(raw, str) else datetime.now(timezone.utc).isoformat()
            self._subject_cache[safe_name] = {"last_run": last_run, "last_lecture": lecture_num}
            
        await self._push_to_telegram()
