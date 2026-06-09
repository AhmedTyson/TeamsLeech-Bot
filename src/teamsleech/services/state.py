import json
import logging
from datetime import datetime, timezone
from pyrogram import Client
from pyrogram.types import Message
from teamsleech.models.domain import UserSession

log = logging.getLogger("state_manager")

class StateManager:
    def __init__(self, client: Client, chat_id: int):
        self.client = client
        self.chat_id = chat_id
        self._subject_cache: dict[str, dict[str, object]] = {}
        self._msg_id: int | None = None
        self._initialized = False
        self._sessions: dict[int, UserSession] = {}

    def get_session(self, user_id: int) -> UserSession:
        if user_id not in self._sessions:
            self._sessions[user_id] = UserSession()
        return self._sessions[user_id]

    def clear_session(self, user_id: int) -> None:
        self._sessions.pop(user_id, None)

    async def initialize(self) -> None:
        if self._initialized:
            return

        try:
            chat = await self.client.get_chat(self.chat_id)
            if (
                chat.pinned_message
                and chat.pinned_message.text
                and "#TEAMSLEECH_STATE" in chat.pinned_message.text
            ):
                await self._parse_and_load(chat.pinned_message)
                return

            log.info(
                "No pinned #TEAMSLEECH_STATE message found."
                " Creating new empty database."
            )
            self._initialized = True
        except Exception as e:
            log.error("Failed to fetch telegram state: %s", e)

    async def _parse_and_load(self, msg: Message) -> None:
        self._msg_id = msg.id
        text = msg.text or ""
        try:
            if "=====JSON_START=====" in text:
                json_str = text.split("=====JSON_START=====\n")[1].split(
                    "\n=====JSON_END====="
                )[0]
            elif "```json" in text:
                json_str = text.split("```json\n")[1].split("\n```")[0]
            else:
                json_str = (
                    text.split("#TEAMSLEECH_STATE\n")[1]
                    .replace(
                        "⚠️ DO NOT DELETE THIS MESSAGE\n"
                        "This acts as the database for the bot.\n",
                        "",
                    )
                    .strip()
                )
            self._subject_cache = json.loads(json_str)
        except Exception as e:
            log.warning(
                "Failed to parse state JSON. Resetting cache and rewriting: %s",
                e,
            )
            self._subject_cache = {}
            await self._push_to_telegram()
        self._initialized = True
        log.info(
            "StateManager initialized. Loaded %d subjects.",
            len(self._subject_cache),
        )

    async def _push_to_telegram(self) -> None:
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
                await self.client.edit_message_text(
                    self.chat_id, self._msg_id, text
                )
            else:
                msg = await self.client.send_message(self.chat_id, text)
                await msg.pin(both_sides=True)
                self._msg_id = msg.id
            log.info("Successfully pushed updated state to Telegram DB.")
        except Exception as e:
            log.error("Failed to push state to Telegram: %s", e)

    def get_last_run(self, subject_name: str) -> datetime:
        safe_name = subject_name.replace(" ", "_").lower()
        raw = self._subject_cache.get(safe_name)
        if not raw:
            return datetime.min.replace(tzinfo=timezone.utc)

        try:
            if isinstance(raw, dict):
                return datetime.fromisoformat(raw.get("last_run", ""))
            return datetime.fromisoformat(raw)
        except (ValueError, TypeError):
            return datetime.min.replace(tzinfo=timezone.utc)

    def get_last_lecture(self, subject_name: str) -> int:
        safe_name = subject_name.replace(" ", "_").lower()
        raw = self._subject_cache.get(safe_name)
        if isinstance(raw, dict):
            return raw.get("last_lecture", 0)
        return 0

    async def save_last_run(
        self, subject_name: str, timestamp: datetime | None = None
    ) -> None:
        if not self._initialized:
            await self.initialize()

        safe_name = subject_name.replace(" ", "_").lower()
        ts = timestamp or datetime.now(timezone.utc)

        raw = self._subject_cache.get(safe_name)
        if isinstance(raw, dict):
            raw["last_run"] = ts.isoformat()
            self._subject_cache[safe_name] = raw
        else:
            self._subject_cache[safe_name] = {
                "last_run": ts.isoformat(),
                "last_lecture": 0,
            }

        await self._push_to_telegram()

    async def save_last_lecture(
        self, subject_name: str, lecture_num: int
    ) -> None:
        if not self._initialized:
            await self.initialize()

        safe_name = subject_name.replace(" ", "_").lower()

        raw = self._subject_cache.get(safe_name)
        if isinstance(raw, dict):
            raw["last_lecture"] = lecture_num
            self._subject_cache[safe_name] = raw
        else:
            last_run = (
                raw
                if isinstance(raw, str)
                else datetime.now(timezone.utc).isoformat()
            )
            self._subject_cache[safe_name] = {
                "last_run": last_run,
                "last_lecture": lecture_num,
            }

        await self._push_to_telegram()
