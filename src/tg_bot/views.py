from datetime import datetime
from typing import Dict, List, Optional
import re
from models.domain import Recording

DIVIDER_THIN = "───────────────────"
DIVIDER_THICK = "━━━━━━━━━━━━━━━━━━"

def num_label(n: int) -> str:
    return str(n)

def clean_filename(name: str) -> str:
    name = re.sub(r"-Meeting Recording", "", name)
    # Don't strip extensions here, we'll handle it during upload/formatting to ensure we keep track of .pdf vs .mp4
    return name

def format_date_short(date_str: str) -> str:
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        return d.strftime("%b %d")
    except ValueError:
        return date_str

def format_duration(duration_ms: int | float | str) -> str:
    try:
        d_ms = int(duration_ms)
        if d_ms <= 0: return ""
        s = d_ms // 1000
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        if h > 0: return f"{h}h {m}m"
        return f"{m}m {s}s"
    except (ValueError, TypeError):
        return ""

def build_checklist_text(
    results: Dict[str, List[Recording]],
    scan_label: str = "",
    rename_overrides: Optional[Dict[int, str]] = None,
) -> str:
    """Build the checklist message text with detailed output."""
    total = sum(len(recs) for recs in results.values())
    if total == 0:
        subjects_checked = ", ".join(results.keys()) if results else "all subjects"
        header = "📡 **Scan Results**"
        if scan_label: header += f"\n{scan_label}"
        return f"{header}\n{DIVIDER_THICK}\n\n✅ No new recordings found\n_{subjects_checked}_"

    overrides = rename_overrides or {}
    is_multi = len(results) > 1

    lines = ["📡 **Scan Results**"]
    if scan_label: lines.append(scan_label)
    lines.append(DIVIDER_THICK)

    idx = 0
    for subj_name, recs in results.items():
        if not recs:
            if is_multi: lines.append(f"\n📚 **{subj_name}** — ✅ No new recordings")
            continue

        if is_multi: lines.append(f"\n📚 **{subj_name}**")

        for rec in recs:
            display_name = clean_filename(overrides.get(idx, rec.name))
            num = num_label(idx + 1)
            date_short = format_date_short(rec.created)
            time_display = f" at {rec.time}" if rec.time else ""
            
            icon = "🎬" if rec.is_video else "📄"
            duration_str = f"  •  {format_duration(rec.duration_ms)}" if rec.is_video and rec.duration_ms else ""

            lines.append(
                f"\n{num}. 👥 **{rec.team_name}**\n"
                f"   {date_short}{time_display}  •  💾 {rec.size_mb} MB{duration_str}\n"
                f"   {icon} {display_name}\n{DIVIDER_THIN}"
            )
            idx += 1

    lines.append(f"\n📊 **{total}** recording(s) found")

    full_text = "\n".join(lines)
    if len(full_text) <= 4000:
        return full_text

    cutoff = full_text.rfind('\n', 0, 3900)
    return full_text[:cutoff if cutoff != -1 else 3900] + "\n\n_...list truncated due to Telegram limits._"
