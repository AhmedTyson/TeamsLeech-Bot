from teamsleech.tg_bot.views import format_duration, format_date_short, clean_filename

def test_clean_filename():
    assert clean_filename("Lecture -Meeting Recording") == "Lecture"
    assert clean_filename("Video-20240115_123456") == "Video"
    assert clean_filename("Normal File.mp4") == "Normal File.mp4"

def test_format_date_short():
    assert format_date_short("2024-01-15") == "Jan 15"
    assert format_date_short("invalid") == "invalid"

def test_format_duration():
    assert format_duration(0) == ""
    assert format_duration(5000) == "5s"
    assert format_duration(65000) == "1m 05s"
    assert format_duration(3661000) == "1h 1m"
    assert format_duration("invalid") == ""
