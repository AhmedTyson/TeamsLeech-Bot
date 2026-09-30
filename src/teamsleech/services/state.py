import asyncio
import json
import logging
import re
from datetime import UTC, datetime
from io import BytesIO
from typing import Any, cast

from pyrogram.client import Client
from pyrogram.types import Message

from teamsleech.core.retry import retry_tg
from teamsleech.models.domain import UserSession

log = logging.getLogger("state_manager")

BACKUP_PREFIX = "teamsleech_state.backup"


def _normalize_key(subject_name: str) -> str:
    base = re.sub(r"\s+", "_", subject_name.strip()).lower()
    return base or "subject"


class StateManager:
    def __init__(self, client: Client, chat_id: int):
        self.client = client
        self.chat_id = chat_id
        self._subject_cache: dict[str, dict[str, Any]] = {}
        self._msg_id: int | None = None
        self._initialized = False
        self._lock = asyncio.Lock()
        self._sessions: dict[int, UserSession] = {}
        # NOTE: UserSession objects are intentionally ephemeral in-memory
        # wizard state (pending scans, selections, renames). They do NOT
        # survive restarts — only the subject cursor cache above is
        # persisted to the pinned Telegram document.

    def get_session(self, user_id: int) -> UserSession:
        if user_id not in self._sessions:
            self._sessions[user_id] = UserSession()
        return self._sessions[user_id]

    def clear_session(self, user_id: int) -> None:
        self._sessions.pop(user_id, None)

    @retry_tg
    async def _download_document(self, msg: Message) -> BytesIO:
        return cast(BytesIO, await self.client.download_media(msg, in_memory=True))

    @retry_tg
    async def _send_state_doc(
        self, chat_id: int, document: BytesIO, file_name: str, caption: str
    ) -> Message:
        return cast(
            Message,
            await self.client.send_document(
                chat_id, document, file_name=file_name, caption=caption
            ),
        )

    async def _ensure_initialized(self) -> None:
        if not self._initialized:
            await self.initialize()
        if not self._initialized:
            msg = "StateManager not initialized — refusing to push state."
            raise RuntimeError(msg)

    def _resolve_key(self, subject_name: str) -> str:
        """Read path: canonical key, or suffixed key owning this display name."""
        base = _normalize_key(subject_name)
        raw = self._subject_cache.get(base)
        if raw is None:
            return base
        owner = raw.get("display_name") if isinstance(raw, dict) else None
        if owner in (None, subject_name):
            return base
        i = 2
        while True:
            key = f"{base}__{i}"
            raw = self._subject_cache.get(key)
            owner = raw.get("display_name") if isinstance(raw, dict) else None
            if raw is None or owner in (None, subject_name):
                return key
            i += 1

    def _write_key(self, subject_name: str) -> str:
        """Write path: claim canonical key, suffix + warn on collision."""
        key = self._resolve_key(subject_name)
        if key != _normalize_key(subject_name):
            log.warning(
                "Subject key collision: %r shares normalized key with another "
                "subject; using %r.",
                subject_name,
                key,
            )
        return key

    async def _backup_blob(self, payload: bytes, reason: str) -> None:
        try:
            bio = BytesIO(payload)
            bio.name = f"{BACKUP_PREFIX}.{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}.json"
            await self._send_state_doc(
                self.chat_id,
                bio,
                file_name=bio.name,
                caption=f"#TEAMSLEECH_STATE_BACKUP {reason}",
            )
            log.info("Backed up unreadable state (%s).", reason)
        except Exception:
            log.exception("Failed to back up corrupt state (%s)", reason)

    async def initialize(self) -> None:
        if self._initialized:
            return

        try:
            chat = await self.client.get_chat(self.chat_id)
            pinned = getattr(chat, "pinned_message", None)

            if pinned and pinned.document and pinned.document.file_name == "teamsleech_state.json":
                self._msg_id = pinned.id
                await self._load_from_document(pinned)
                return

            if pinned and pinned.text and "#TEAMSLEECH_STATE" in pinned.text:
                self._msg_id = pinned.id
                await self._parse_and_load(pinned)
                return

            log.info("No pinned state document found. Creating new empty database.")
            self._initialized = True
        except Exception:
            log.exception("Failed to initialize state")

    async def _load_from_document(self, msg: Message) -> None:
        self._msg_id = msg.id
        raw: bytes | None = None
        try:
            file_bytes = await self._download_document(msg)
            raw = file_bytes.getvalue()
            self._subject_cache = json.loads(raw)
        except Exception:
            log.exception("State document unreadable — backing up, starting fresh")
            if raw is not None:
                await self._backup_blob(raw, "unparseable-document")
            self._subject_cache = {}
            # NOTE: the corrupt pinned doc is deliberately left in place
            # (not deleted); the fresh push below pins a new doc.
            await self._push_to_telegram(delete_old=False)
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
                json_str = text.split("=====JSON_START=====\n")[1].split("\n=====JSON_END=====")[0]
            elif "```json" in text:
                json_str = text.split("```json\n")[1].split("\n```")[0]
            else:
                json_str = (
                    text.split("#TEAMSLEECH_STATE\n")[1]
                    .replace(
                        "⚠️ DO NOT DELETE THIS MESSAGE\n" "This acts as the database for the bot.\n",
                        "",
                    )
                    .strip()
                )
            self._subject_cache = json.loads(json_str)
        except Exception:
            log.exception("Legacy state text unreadable — backing up, starting fresh")
            await self._backup_blob(text.encode("utf-8"), "unparseable-legacy-text")
            self._subject_cache = {}
            await self._push_to_telegram(delete_old=False)
            self._initialized = True
            return
        self._initialized = True
        log.info(
            "StateManager initialized (legacy text). Upgrading %d subjects to document format.",
            len(self._subject_cache),
        )
        await self._push_to_telegram()

    async def _push_to_telegram(self, delete_old: bool = True) -> bool:
        async with self._lock:
            return await self._push_locked(delete_old=delete_old)

    async def _push_locked(self, delete_old: bool = True) -> bool:
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
            try:
                await msg.pin(both_sides=True)
            except Exception:
                log.exception("Failed to pin state doc — removing orphan")
                try:
                    await self.client.delete_messages(self.chat_id, msg.id)
                except Exception as cleanup_e:
                    log.debug("Orphan state doc cleanup failed: %s", cleanup_e)
                return False
            self._msg_id = msg.id
            if delete_old and old_msg_id:
                try:
                    await self.client.delete_messages(self.chat_id, old_msg_id)
                except Exception as e:
                    log.warning("Failed to delete old state message: %s", e)
        except Exception:
            log.exception("Failed to push state to Telegram")
            return False
        else:
            log.info("Successfully pushed updated state as document.")
            return True

    def get_last_run(self, subject_name: str) -> datetime:
        raw = self._subject_cache.get(self._resolve_key(subject_name))
        if not raw:
            return datetime.min.replace(tzinfo=UTC)

        try:
            if isinstance(raw, dict):
                return datetime.fromisoformat(raw.get("last_run", ""))
            return datetime.fromisoformat(raw)
        except (ValueError, TypeError):
            return datetime.min.replace(tzinfo=UTC)

    def get_last_lecture(self, subject_name: str) -> int:
        raw = self._subject_cache.get(self._resolve_key(subject_name))
        if isinstance(raw, dict):
            lecture = raw.get("last_lecture", 0)
            return lecture if isinstance(lecture, int) else 0
        return 0

    async def save_last_run(self, subject_name: str, timestamp: datetime | None = None) -> None:
        await self._ensure_initialized()

        async with self._lock:
            key = self._write_key(subject_name)
            ts = timestamp or datetime.now(UTC)

            raw = self._subject_cache.get(key)
            if isinstance(raw, dict):
                raw["last_run"] = ts.isoformat()
                raw["display_name"] = subject_name
                self._subject_cache[key] = raw
            else:
                self._subject_cache[key] = {
                    "last_run": ts.isoformat(),
                    "last_lecture": 0,
                    "display_name": subject_name,
                }

            await self._push_locked()

    async def save_last_lecture(self, subject_name: str, lecture_num: int) -> None:
        await self._ensure_initialized()

        async with self._lock:
            key = self._write_key(subject_name)

            raw = self._subject_cache.get(key)
            if isinstance(raw, dict):
                raw["last_lecture"] = lecture_num
                raw["display_name"] = subject_name
                self._subject_cache[key] = raw
            else:
                last_run = raw if isinstance(raw, str) else datetime.now(UTC).isoformat()
                self._subject_cache[key] = {
                    "last_run": last_run,
                    "last_lecture": lecture_num,
                    "display_name": subject_name,
                }

            await self._push_locked()

    async def save_subject_state(
        self,
        subject_name: str,
        last_run: datetime | None = None,
        lecture_increment: int = 0,
    ) -> None:
        """Batch cursor + lecture update with a single Telegram push.

        Accumulates the newest `last_run` (max-merge) and adds
        `lecture_increment` to the stored lecture count.
        """
        await self._ensure_initialized()

        async with self._lock:
            key = self._write_key(subject_name)
            raw = self._subject_cache.get(key)
            entry: dict[str, Any]
            if isinstance(raw, dict):
                entry = dict(raw)
            else:
                entry = {"last_run": "", "last_lecture": 0}
            if last_run is not None and last_run.isoformat() > entry.get("last_run", ""):
                entry["last_run"] = last_run.isoformat()
            if lecture_increment:
                entry["last_lecture"] = int(entry.get("last_lecture", 0)) + lecture_increment
            entry["display_name"] = subject_name
            self._subject_cache[key] = entry

            await self._push_locked()
