"""Guided setup wizard: DM, buttons only, one question at a time.

Design rule (standing): the owner's path must be as short as possible —
buttons not commands, one question at a time, plain Egyptian Arabic, no
jargon, and auto-detected defaults instead of asking. Three steps:
1. Topic linking checklist — per subject a copyable /link command to
   send inside its forum topic, with live ✅/❌ status and refresh.
2. Numbering — per subject a ➖/➕ picker for the next number, defaulting
   to the bot's own record (next_no), persisted when advancing.
3. Start — one button runs Scan Missing; review, upload and publish stay
   his taps in the normal checklist.
"""

import logging
import re

from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from teamsleech.tg_bot.filters import owner_only
from teamsleech.tg_bot.handlers import safe_answer, safe_edit_text

log = logging.getLogger("setup_wizard")

# In-progress numbering edits per chat: {chat_id: {subject_name: next_no}}.
# Flushed to the subjects store whenever a step advances.
_pending: dict[int, dict[str, int]] = {}


def _prefix(subj) -> str:
    return "Sec" if subj.kind == "section" else "L"


def _label(subj) -> str:
    return f"{subj.name} — {subj.doctor}" if subj.doctor else subj.name


def build_topics_text(subjects) -> str:
    lines = [
        "⚙️ **الإعداد — خطوة 1 من 3: ربط المواضيع**",
        "",
        "الطريقة الأسهل: افتح التوبيك، انسخ لينكه (Copy link)، وابعته هنا —",
        "هسألك المادة دي أنهي واحدة، وتدوس على اسمها وخلاص.",
        "",
        "(طريقة تانية لو حابب: ابعت الأمر اللي تحت المادة جوا التوبيك نفسه.)",
        "",
    ]
    for s in subjects:
        status = "✅ مربوط" if s.topic_id else "❌ لسه"
        lines.append(f"📚 **{_label(s)}** — {status}")
        lines.append(f"`/link {s.short or s.name}`")
        lines.append("")
    linked = sum(1 for s in subjects if s.topic_id)
    lines.append(f"مربوط {linked} من {len(subjects)}. لما تخلص دوس تحديث.")
    return "\n".join(lines)


def build_topics_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔄 تحديث", callback_data="wiz:refresh"),
                InlineKeyboardButton("التالي ▶️", callback_data="wiz:tonum:0"),
            ],
            [InlineKeyboardButton("❌ إلغاء", callback_data="wiz:cancel")],
        ]
    )


def _pending_value(chat_id: int, subj) -> int:
    return _pending.get(chat_id, {}).get(subj.name, subj.next_no)


def build_numbering_text(subj, value: int, idx: int, total: int) -> str:
    return (
        "⚙️ **الإعداد — خطوة 2 من 3: الترقيم**\n\n"
        f"📚 **{subj.name}** ({idx + 1} من {total})\n\n"
        "البوت هيكمل من رقم كام؟ يعني أول رقم **لسه متنشرش** في الموضوع.\n"
        "لو الموضوع فاضي، سيبه 1.\n\n"
        f"الرقم الحالي: **{_prefix(subj)}{value:02d}**"
    )


def build_numbering_keyboard(idx: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("➖", callback_data=f"wiz:dec:{idx}"),
                InlineKeyboardButton("من 1", callback_data=f"wiz:one:{idx}"),
                InlineKeyboardButton("➕", callback_data=f"wiz:inc:{idx}"),
            ],
            [InlineKeyboardButton("اللي بعده ▶️", callback_data=f"wiz:tonum:{idx + 1}")],
            [InlineKeyboardButton("❌ إلغاء", callback_data="wiz:cancel")],
        ]
    )


def build_ready_text() -> str:
    return (
        "⚙️ **الإعداد — خطوة 3 من 3: جاهزين 🚀**\n\n"
        "كله متظبط. دوس **ابدأ** وهو هيفحص كل المواد ويجهزلك قائمة الناقص"
        " بالأسماء مظبوطة.\n"
        "بعدها بزرارين من القائمة نفسها: **✅ Approve all & Upload** ثم"
        " **📤 Publish to group** — النشر دايماً بدستك انت."
    )


def build_ready_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🚀 ابدأ", callback_data="wiz:go")],
            [InlineKeyboardButton("❌ إلغاء", callback_data="wiz:cancel")],
        ]
    )


async def _flush_pending(chat_id: int, subjects) -> bool:
    """Write pending numbering edits into the subjects and persist once."""
    edits = _pending.pop(chat_id, {})
    if not edits:
        return True
    changed = False
    for s in subjects:
        if s.name in edits:
            s.next_no = max(1, edits[s.name])
            changed = True
    if not changed:
        return True
    from teamsleech.services.subjects_store import persist_subjects

    await persist_subjects(subjects)
    return True


# --- Link a topic by pasting its t.me/c link right here in the DM ---------

TOPIC_LINK_RE = re.compile(r"(?:https?://)?t\.me/c/(\d+)/(\d+)(?:/\d+)?")


def parse_topic_link(text: str) -> tuple[int, int] | None:
    """t.me/c/<g>/<topic>[/msg] -> (group chat id -100<g>, topic id)."""
    m = TOPIC_LINK_RE.search(text or "")
    if not m:
        return None
    return int(f"-100{m.group(1)}"), int(m.group(2))


def build_pick_subject_text() -> str:
    return "اللينك وصل ✅\n\nالموضوع ده بتاع أنهي مادة؟ دوس على اسمها:"


def build_pick_subject_keyboard(
    subjects, group_id: int, topic_id: int
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                f"📚 {_label(s)}{' ✅' if s.topic_id == topic_id else ''}",
                callback_data=f"wiz:linkto:{group_id}:{topic_id}:{i}",
            )
        ]
        for i, s in enumerate(subjects)
    ]
    rows.append([InlineKeyboardButton("❌ إلغاء", callback_data="wiz:cancel")])
    return InlineKeyboardMarkup(rows)


async def _write_status_note(client: Client, group_id: int) -> str:
    """Whether the bot can write in that group — membership/permissions
    only; no test message is ever sent to the group."""
    try:
        me = await client.get_chat_member(group_id, "me")
        status = str(getattr(me, "status", "")).lower()
    except Exception:
        return "⚠️ مش لاقي البوت جوا الجروب ده — ضيفه وخليه أدمن."
    if any(k in status for k in ("admin", "creator", "owner")):
        return "✅ البوت أدمن في الجروب — يقدر ينشر في الموضوع."
    try:
        chat = await client.get_chat(group_id)
        can = getattr(getattr(chat, "permissions", None), "can_send_messages", None)
    except Exception:
        can = None
    if can is False:
        return "⚠️ البوت عضو بس ممنوع يكتب — خليه أدمن عشان يقدر ينشر."
    return "✅ البوت جوا الجروب ويقدر يكتب."


def register_setup_wizard(app: Client, scanner, state):
    async def _show_topics(client: Client, message: Message):
        subjects = scanner.load_subjects()
        if not subjects:
            await message.reply("❌ مفيش مواد متظبطة لسه.")
            return
        await message.reply(
            build_topics_text(subjects), reply_markup=build_topics_keyboard()
        )

    @app.on_message(
        (filters.command("setup") | filters.regex("^⚙️ الإعداد$"))
        & filters.private
        & owner_only
    )
    async def handle_setup(client: Client, message: Message):
        await _show_topics(client, message)

    @app.on_callback_query(filters.regex(r"^wiz:(start|refresh)$") & owner_only)
    async def handle_wiz_topics(client: Client, cb: CallbackQuery):
        await safe_answer(cb)
        subjects = scanner.load_subjects()
        await safe_edit_text(
            cb.message,
            build_topics_text(subjects),
            reply_markup=build_topics_keyboard(),
        )

    @app.on_callback_query(filters.regex(r"^wiz:tonum:(\d+)$") & owner_only)
    async def handle_wiz_tonum(client: Client, cb: CallbackQuery):
        subjects = scanner.load_subjects()
        idx = int(cb.data.rsplit(":", 1)[1])
        chat_id = cb.message.chat.id
        if idx > 0:
            try:
                await _flush_pending(chat_id, subjects)
            except Exception as e:
                await safe_answer(cb, f"⚠️ الحفظ فشل: {e}", show_alert=True)
                return
        await safe_answer(cb)
        if idx >= len(subjects):
            await safe_edit_text(
                cb.message, build_ready_text(),
                reply_markup=build_ready_keyboard(),
            )
            return
        subj = subjects[idx]
        value = _pending_value(chat_id, subj)
        await safe_edit_text(
            cb.message,
            build_numbering_text(subj, value, idx, len(subjects)),
            reply_markup=build_numbering_keyboard(idx),
        )

    @app.on_callback_query(filters.regex(r"^wiz:(inc|dec|one):(\d+)$") & owner_only)
    async def handle_wiz_adjust(client: Client, cb: CallbackQuery):
        _, action, idx_s = cb.data.split(":")
        idx = int(idx_s)
        subjects = scanner.load_subjects()
        if idx >= len(subjects):
            await safe_answer(cb)
            return
        subj = subjects[idx]
        chat_id = cb.message.chat.id
        value = _pending_value(chat_id, subj)
        if action == "inc":
            value += 1
        elif action == "dec":
            value = max(1, value - 1)
        else:
            value = 1
        _pending.setdefault(chat_id, {})[subj.name] = value
        await safe_answer(cb, f"{_prefix(subj)}{value:02d}")
        await safe_edit_text(
            cb.message,
            build_numbering_text(subj, value, idx, len(subjects)),
            reply_markup=build_numbering_keyboard(idx),
        )

    @app.on_callback_query(filters.regex(r"^wiz:go$") & owner_only)
    async def handle_wiz_go(client: Client, cb: CallbackQuery):
        subjects = scanner.load_subjects()
        chat_id = cb.message.chat.id
        try:
            await _flush_pending(chat_id, subjects)
        except Exception as e:
            await safe_answer(cb, f"⚠️ الحفظ فشل: {e}", show_alert=True)
            return
        await safe_answer(cb, "🚀 بيفحص الناقص...")
        await safe_edit_text(
            cb.message,
            "✅ **الإعداد خلص.** جاري فحص الناقص في كل المواد...",
        )
        from teamsleech.tg_bot.handlers.scanner_ui import run_missing_scan

        await run_missing_scan(client, chat_id, scanner, state)
        await client.send_message(
            chat_id,
            "👆 راجع القايمة اللي فوق، وبعدها:\n"
            "1️⃣ دوس **✅ Approve all & Upload** عشان يرفعهم هنا.\n"
            "2️⃣ لما الرفع يخلص دوس **📤 Publish to group** عشان ينزلهم"
            " في المواضيع.",
        )

    @app.on_message(filters.private & owner_only & filters.regex(TOPIC_LINK_RE))
    async def handle_topic_link_paste(client: Client, message: Message):
        parsed = parse_topic_link(message.text or "")
        if not parsed:
            return
        group_id, topic_id = parsed
        subjects = scanner.load_subjects()
        if not subjects:
            await message.reply("❌ مفيش مواد متظبطة لسه.")
            return
        await message.reply(
            build_pick_subject_text(),
            reply_markup=build_pick_subject_keyboard(subjects, group_id, topic_id),
        )

    @app.on_callback_query(filters.regex(r"^wiz:linkto:-?\d+:\d+:\d+$") & owner_only)
    async def handle_wiz_linkto(client: Client, cb: CallbackQuery):
        _, _, group_s, topic_s, idx_s = cb.data.split(":")
        group_id, topic_id, idx = int(group_s), int(topic_s), int(idx_s)
        subjects = scanner.load_subjects()
        if idx >= len(subjects):
            await safe_answer(cb, "⚠️ المادة مش موجودة.", show_alert=True)
            return
        subj = subjects[idx]
        moved_from = next(
            (s for s in subjects if s.topic_id == topic_id and s is not subj), None
        )
        subj.topic_id = topic_id
        try:
            from teamsleech.services.subjects_store import persist_subjects

            await persist_subjects(subjects)
        except Exception as e:
            await safe_answer(cb, f"⚠️ الحفظ فشل: {e}", show_alert=True)
            return
        try:
            from teamsleech.tg_bot.handlers.commands import persist_target_chat_id

            await persist_target_chat_id(group_id)
        except Exception:
            pass
        note = await _write_status_note(client, group_id)
        await safe_answer(cb, "✅ اتربط")
        moved = f"\n(كان مربوط بـ **{moved_from.name}** — اتنقل هنا)" if moved_from else ""
        await safe_edit_text(
            cb.message,
            f"✅ **اتربط!**\n📚 **{_label(subj)}**\n🧵 الموضوع: `{topic_id}`{moved}\n{note}",
        )
        subjects = scanner.load_subjects()
        await client.send_message(
            cb.message.chat.id,
            build_topics_text(subjects),
            reply_markup=build_topics_keyboard(),
        )

    @app.on_callback_query(filters.regex(r"^wiz:cancel$") & owner_only)
    async def handle_wiz_cancel(client: Client, cb: CallbackQuery):
        _pending.pop(cb.message.chat.id, None)
        await safe_answer(cb)
        await safe_edit_text(
            cb.message,
            "تمام، الإعداد اتلغى. ابعت /setup أو دوس ⚙️ **الإعداد** أي وقت.",
        )
