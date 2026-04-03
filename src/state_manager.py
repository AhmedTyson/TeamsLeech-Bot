"""
State Manager - Stores persistent JSON data via Telegram messages.
Removes dependency on ephemeral local disk caching.
"""
import json
import logging
from datetime import datetime, timezone

from pyrogram import Client

log = logging.getLogger("state_manager")

class TelegramStateManager:
    """Uses a pinned Telegram message in a specific chat as a free NoSQL Database."""
    
    def __init__(self, client: Client, chat_id: int):
        self.client = client
        self.chat_id = chat_id
        self._state_cache: dict[str, str] = {}
        self._msg_id: int | None = None
        self._initialized = False

    async def initialize(self) -> None:
        """Finds the #TEAMSLEECH_STATE message in the chat."""
        if self._initialized:
            return
            
        try:
            # 1. First, check if it's the currently pinned message (optimization)
            chat = await self.client.get_chat(self.chat_id)
            if chat.pinned_message and chat.pinned_message.text and "#TEAMSLEECH_STATE" in chat.pinned_message.text:
                await self._parse_and_load(chat.pinned_message)
                return

            # 2. If not pinned (or not the latest pin), scan recent history (bots cannot use search_messages)
            log.info("Scanning recent chat history for state message...")
            async for msg in self.client.get_chat_history(self.chat_id, limit=1000):
                if msg.text and "#TEAMSLEECH_STATE" in msg.text:
                    await self._parse_and_load(msg)
                    return
                
            log.info("No #TEAMSLEECH_STATE message found globally. Creating a new one.")
            self._initialized = True
        except Exception as e:
            log.error(f"Failed to fetch telegram state: {e}")

    async def _parse_and_load(self, msg: 'Message') -> None:
        """Helper to extract JSON from the state message."""
        self._msg_id = msg.id
        text = msg.text or ""
        try:
            # Parse between JSON markdown blocks if possible
            if "```json" in text:
                json_str = text.split("```json\n")[1].split("\n```")[0]
            else:
                json_str = text.split("#TEAMSLEECH_STATE\n")[1]
            self._state_cache = json.loads(json_str)
        except (IndexError, json.JSONDecodeError) as e:
            log.warning("Found state message but failed to parse JSON: %s. Resetting cache.", e)
            self._state_cache = {}
        self._initialized = True
        log.info("TelegramStateManager initialized. Loaded %d subjects.", len(self._state_cache))

    async def _push_to_telegram(self) -> None:
        """Writes the state_cache to Telegram."""
        text = (
            "#TEAMSLEECH_STATE\n"
            "**⚠️ DO NOT DELETE THIS MESSAGE**\n"
            "_This acts as the database for the bot._\n"
            f"```json\n{json.dumps(self._state_cache, indent=2)}\n```"
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
        raw = self._state_cache.get(safe_name)
        if not raw:
            return datetime.min.replace(tzinfo=timezone.utc)
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return datetime.min.replace(tzinfo=timezone.utc)

    async def save_last_run(self, subject_name: str, timestamp: datetime | None = None) -> None:
        """Updates the memory cache and immediately pushes strictly to Telegram."""
        if not self._initialized:
            await self.initialize()
            
        safe_name = subject_name.replace(" ", "_").lower()
        ts = timestamp or datetime.now(timezone.utc)
        self._state_cache[safe_name] = ts.isoformat()
        await self._push_to_telegram()
