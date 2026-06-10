
from teamsleech.models.domain import Recording, SubjectConfig
from teamsleech.tg_bot.keyboards import (
    build_checklist_keyboard,
    build_subject_keyboard,
)


def test_build_subject_keyboard():
    subjects = [
        SubjectConfig(name="Math", short="M", doctor="Dr. Smith"),
        SubjectConfig(name="Physics", short="Phy", doctor="Dr. Jones"),
    ]
    kb = build_subject_keyboard(subjects)
    
    assert kb is not None
    # 2 subjects + 1 "Check All" button row. However subjects might be grouped by 3.
    # Total rows = 1 (for the 2 subjects) + 1 (for Check All) = 2
    assert len(kb.inline_keyboard) == 2
    assert kb.inline_keyboard[0][0].text == "M"
    assert kb.inline_keyboard[0][1].text == "Phy"
    assert kb.inline_keyboard[1][0].callback_data == "subj:__ALL__"

def test_build_checklist_keyboard():
    recs = [
        Recording(
            id="1", name="Vid1", url="http", 
            is_video=True, size_mb=10.0, 
            created="2026-01-01", team_name="T1",
            drive_id="d1", item_id="i1", subject_name="Math"
        ),
        Recording(
            id="2", name="Doc1", url="http", 
            is_video=False, size_mb=5.0, 
            created="2026-01-01", team_name="T1",
            drive_id="d2", item_id="i2", subject_name="Math"
        )
    ]
    selections = {0}
    kb = build_checklist_keyboard(recs, selections)
    
    assert kb is not None
    # toggle rows + upload button + filter row + action row
    # toggle rows: 1 row for 2 items (since TOGGLES_PER_ROW is 4)
    # total rows: 1 + 1 + 1 + 1 = 4
    assert len(kb.inline_keyboard) == 4
    
    # Check toggles
    assert kb.inline_keyboard[0][0].text == "✅ 1"
    assert kb.inline_keyboard[0][2].text == "⬛️ 2"
    
    # Check upload button
    assert "10 MB" in kb.inline_keyboard[1][0].text
    
    # Check filters
    # row 2
    assert "📄 PDFs" in kb.inline_keyboard[2][0].text
    assert "🎬 Videos" in kb.inline_keyboard[2][1].text
    
    # Check actions
    assert kb.inline_keyboard[3][0].callback_data == "date:change"
