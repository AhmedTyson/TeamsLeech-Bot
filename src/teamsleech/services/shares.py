"""Resolve shared recording links (SharePoint/OneDrive) into Recordings.

He drops a Teams/SharePoint recording link in the DM; Graph's /shares API
turns the URL into a drive item without any cookie or extra login.
"""

import base64
import logging
import re

from teamsleech.core.constants import VIDEO_EXTENSIONS
from teamsleech.models.domain import Recording

log = logging.getLogger("shares")

RECORDING_LINK_RE = re.compile(
    r"https?://[^\s]*?(?:sharepoint\.com|1drv\.ms|onedrive)[^\s]*", re.IGNORECASE
)


def extract_recording_link(text: str | None) -> str | None:
    """First SharePoint/OneDrive link in the message, or None."""
    if not text:
        return None
    m = RECORDING_LINK_RE.search(text)
    return m.group(0).rstrip(".,)]>\"'") if m else None


def share_token(url: str) -> str:
    """Graph /shares token: 'u!' + base64url(url) without padding."""
    return "u!" + base64.urlsafe_b64encode(url.encode()).decode().rstrip("=")


def recording_from_drive_item(item: dict, source_url: str = "") -> Recording:
    """Build a Recording from a Graph driveItem payload."""
    created_str = item.get("createdDateTime", "")
    name = item.get("name", "recording")
    return Recording(
        name=name,
        size_mb=round(item.get("size", 0) / (1024 * 1024), 1),
        created=created_str[:10],
        time=created_str[11:16] if len(created_str) >= 16 else "",
        duration_ms=(item.get("video") or {}).get("duration", 0),
        drive_id=(item.get("parentReference") or {}).get("driveId", ""),
        item_id=item.get("id", ""),
        team_name="🔗 shared link",
        subject_name="",
        is_video=name.lower().endswith(tuple(VIDEO_EXTENSIONS)),
    )


async def resolve_share_recording(graph, url: str) -> Recording:
    """Fetch the shared drive item via Graph and adapt it to a Recording."""
    item = await graph.get(
        f"/shares/{share_token(url)}/driveItem"
        "?$select=id,name,size,createdDateTime,video,parentReference,file"
    )
    rec = recording_from_drive_item(item, url)
    if not rec.drive_id or not rec.item_id:
        raise ValueError("Link did not resolve to a file.")
    return rec
