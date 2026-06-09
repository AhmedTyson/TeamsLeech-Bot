from teamsleech.tg_bot.views import format_duration, format_date_short, clean_filename

def test_clean_filename():
    assert clean_filename("Lecture 1-Meeting Recording.mp4") == "Lecture 1.mp4"
    assert clean_filename("Session-20260401_103000.mp4") == "Session.mp4"
    assert clean_filename("Normal File.pdf") == "Normal File.pdf"

def test_format_date_short():
    assert format_date_short("2026-04-01") == "Apr 01"
    assert format_date_short("invalid-date") == "invalid-date"

def test_format_duration():
    assert format_duration(0) == ""
    assert format_duration("invalid") == ""
    
    # 65000 ms = 65 seconds = 1m 05s
    assert format_duration(65000) == "1m 05s"
    
    # 3600000 ms = 3600 seconds = 1h 0m
    assert format_duration(3600000) == "1h 0m"
    
    # 3665000 ms = 3665 seconds = 1h 1m
    assert format_duration(3665000) == "1h 1m"
