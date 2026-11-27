"""Shared-link downloads: URL extraction, Graph share token, item mapping."""

from teamsleech.models.domain import SubjectConfig, UploadedItem
from teamsleech.services.shares import (
    extract_recording_link,
    recording_from_drive_item,
    share_token,
)
from teamsleech.tg_bot.handlers.link_download import (
    assign_subject_to_upload,
    build_link_subject_keyboard,
)


def test_extract_sharepoint_link():
    text = "شوف ده https://uni.sharepoint.com/:v:/s/team/abc123?e=xyz لو سمحت"
    assert extract_recording_link(text) == "https://uni.sharepoint.com/:v:/s/team/abc123?e=xyz"


def test_extract_onedrive_link_strips_trailing_punct():
    url = extract_recording_link("https://company-my.sharepoint.com/:v:/p/user/abc.")
    assert url == "https://company-my.sharepoint.com/:v:/p/user/abc"


def test_extract_ignores_plain_text_and_other_links():
    assert extract_recording_link("no link here") is None
    assert extract_recording_link("https://google.com/search?q=x") is None


def test_share_token_format():
    tok = share_token("https://a.sharepoint.com/x")
    assert tok.startswith("u!")
    assert "=" not in tok
    import base64
    assert base64.urlsafe_b64decode(tok[2:] + "==").decode() == "https://a.sharepoint.com/x"


def _item():
    return {
        "id": "item-1",
        "name": "Lecture 12.mp4",
        "size": 250 * 1024 * 1024,
        "createdDateTime": "2026-11-20T10:30:00Z",
        "video": {"duration": 3_600_000},
        "parentReference": {"driveId": "drive-9"},
        "file": {},
    }


def test_recording_from_drive_item():
    rec = recording_from_drive_item(_item())
    assert rec.name == "Lecture 12.mp4"
    assert rec.size_mb == 250.0
    assert rec.created == "2026-11-20"
    assert rec.time == "10:30"
    assert rec.duration_ms == 3_600_000
    assert rec.drive_id == "drive-9"
    assert rec.item_id == "item-1"
    assert rec.is_video is True
    assert rec.subject_name == ""


def test_recording_from_audio_item_is_video_true():
    item = _item()
    item["name"] = "Section 3.m4a"
    item.pop("video")
    rec = recording_from_drive_item(item)
    assert rec.is_video is True
    assert rec.duration_ms == 0


def test_assign_subject_names_and_numbers():
    subj = SubjectConfig(
        name="FT course", short="FT", doctor="Azza Hegazy",
        keywords=["x"], kind="lecture", next_no=8,
    )
    item = UploadedItem(
        name="Lecture 12.mp4", message_id=1, chat_id=2, subject_name=""
    )
    assign_subject_to_upload(item, subj)
    assert item.subject_name == "FT"
    assert item.assigned_no == 8
    assert item.name == "FT - L08 - Dr. Azza Hegazy.mp4"


def test_assign_subject_keeps_audio_extension():
    subj = SubjectConfig(
        name="CN course", short="CN", doctor="", keywords=["x"],
        kind="section", next_no=3,
    )
    item = UploadedItem(name="old.m4a", message_id=1, chat_id=2, subject_name="")
    assign_subject_to_upload(item, subj)
    assert item.name == "CN - Sec03.m4a"


def test_subject_keyboard_has_skip():
    subj = SubjectConfig(name="FT course", short="FT", keywords=["x"])
    kb = build_link_subject_keyboard([subj])
    callbacks = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert "linksubj:FT" in callbacks
    assert "linksubj:__skip__" in callbacks
