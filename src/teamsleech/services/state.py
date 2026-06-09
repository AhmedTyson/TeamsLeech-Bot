import json
import logging
from datetime import UTC, datetime
from io import BytesIO

from pyrogram import Client
from pyrogram.types import Message

from teamsleech.core.retry import retry_tg
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

    @retry_tg
    async def _download_document(self, msg: Message) -> BytesIO:
        return await self.client.download_media(msg, in_memory=True)

    @retry_tg
    async def _send_state_doc(
        self, chat_id: int, document: BytesIO, file_name: str, caption: str
    ) -> Message:
        return await self.client.send_document(
            chat_id, document, file_name=file_name, caption=caption
        )

    async def initialize(self) -> None:
        if self._initialized:
            return

        try:
            chat = await self.client.get_chat(self.chat_id)
            pinned = chat.pinned_message

            if pinned and pinned.document and pinned.document.file_name == "teamsleech_state.json":
                self._msg_id = pinned.id
                await self._load_from_document(pinned)
                return

            if pinned and pinned.text and "#TEAMSLEECH_STATE" in pinned.text:
                self._msg_id = pinned.id
                await self._parse_and_load(pinned)
                return

            log.info(
                "No pinned state document found. Creating new empty database."
            )
            self._initialized = True
        except Exception as e:
            log.error("Failed to initialize state: %s", e)

    async def _load_from_document(self, msg: Message) -> None:
        self._msg_id = msg.id
        try:
            file_bytes = await self._download_document(msg)
            self._subject_cache = json.loads(file_bytes.getvalue())
        except Exception as e:
            log.warning("Failed to parse state document. Resetting: %s", e)
            self._subject_cache = {}
            await self._push_to_telegram()
        self._initialized = True
        log.info(
            "StateManager initialized. Loaded %d subjects from document.",
            len(self._subject_cache),
        )

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
                "Failed to parse legacy state text. Resetting cache: %s",
                e,
            )
            self._subject_cache = {}
        self._initialized = True
        log.info(
            "StateManager initialized (legacy text). Upgrading %d subjects to document format.",
            len(self._subject_cache),
        )
        await self._push_to_telegram()

    async def _push_to_telegram(self) -> None:
        data = json.dumps(self._subject_cache, indent=2).encode("utf-8")
        bio = BytesIO(data)
        bio.name = "teamsleech_state.json"
        try:
            old_msg_id = self._msg_id
            msg = await self._send_state_doc(
                self.chat_id,
                bio,
                file_name="teamsleech_state.json",
                caption="#TEAMSLEECH_STATE",
            )
            await msg.pin(both_sides=True)
            self._msg_id = msg.id
            if old_msg_id:
                try:
                    await self.client.delete_messages(self.chat_id, old_msg_id)
                except Exception as e:
                    log.warning("Failed to delete old state message: %s", e)
            log.info("Successfully pushed updated state as document.")
        except Exception as e:
            log.error("Failed to push state to Telegram: %s", e)

    def get_last_run(self, subject_name: str) -> datetime:
        safe_name = subject_name.replace(" ", "_").lower()
        raw = self._subject_cache.get(safe_name)
        if not raw:
            return datetime.min.replace(tzinfo=UTC)

        try:
            if isinstance(raw, dict):
                return datetime.fromisoformat(raw.get("last_run", ""))
            return datetime.fromisoformat(raw)
        except (ValueError, TypeError):
            return datetime.min.replace(tzinfo=UTC)

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
        ts = timestamp or datetime.now(UTC)

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
                else datetime.now(UTC).isoformat()
            )
            self._subject_cache[safe_name] = {
                "last_run": last_run,
                "last_lecture": lecture_num,
            }

        await self._push_to_telegram()
