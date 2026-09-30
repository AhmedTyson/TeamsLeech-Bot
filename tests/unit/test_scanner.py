import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from teamsleech.models.domain import Recording, SubjectConfig, Team
from teamsleech.services.graph import GraphAPIError
from teamsleech.services.scanner import ScannerService


@pytest.fixture
def scanner(graph_client):
    from unittest.mock import MagicMock

    state = MagicMock()
    state.get_last_run.return_value = datetime.min.replace(tzinfo=UTC)
    state.save_last_run = AsyncMock()
    return ScannerService(graph_client, state)


class TestLoadSubjects:
    def test_load_from_env(self, scanner, monkeypatch):
        data = json.dumps(
            {
                "subjects": [
                    {"name": "Math", "short": "MTH", "keywords": ["math"]},
                    {"name": "Physics", "keywords": ["physics"]},
                ]
            }
        )
        monkeypatch.setattr("teamsleech.services.scanner.settings.subjects_json", data)
        subjects = scanner.load_subjects()
        assert len(subjects) == 2
        assert subjects[0].name == "Math"
        assert subjects[1].name == "Physics"

    def test_load_from_env_parse_error(self, scanner, monkeypatch):
        monkeypatch.setattr(
            "teamsleech.services.scanner.settings.subjects_json",
            "invalid json",
        )
        subjects = scanner.load_subjects()
        assert subjects == []

    def test_load_subjects_no_env_no_file(self, scanner, monkeypatch):
        monkeypatch.setattr("teamsleech.services.scanner.settings.subjects_json", "")
        monkeypatch.setattr(
            "teamsleech.services.scanner.settings.subjects_path",
            "/nonexistent/path.json",
        )
        subjects = scanner.load_subjects()
        assert subjects == []

    def test_load_from_file_success(self, scanner, monkeypatch, tmp_path):
        monkeypatch.setattr("teamsleech.services.scanner.settings.subjects_json", "")
        f = tmp_path / "subjects.json"
        f.write_text(json.dumps({"subjects": [{"name": "Chem", "keywords": ["chemistry"]}]}))
        monkeypatch.setattr(
            "teamsleech.services.scanner.settings.subjects_path",
            str(f),
        )
        subjects = scanner.load_subjects()
        assert len(subjects) == 1
        assert subjects[0].name == "Chem"


class TestMatchTeams:
    def test_exact_keyword_match(self, scanner, sample_subject):
        teams = [
            Team(id="1", display_name="Algebra 101"),
            Team(id="2", display_name="World History"),
        ]
        matched = scanner._match_teams(teams, sample_subject)
        assert len(matched) == 1
        assert matched[0].display_name == "Algebra 101"

    def test_partial_keyword_match(self, scanner):
        subject = SubjectConfig(name="Test", keywords=["bio"])
        teams = [
            Team(id="1", display_name="Biology 101"),
            Team(id="2", display_name="Chemistry 101"),
        ]
        matched = scanner._match_teams(teams, subject)
        assert len(matched) == 1
        assert matched[0].display_name == "Biology 101"

    def test_no_match(self, scanner):
        subject = SubjectConfig(name="Test", keywords=["xyz"])
        teams = [Team(id="1", display_name="Math 101")]
        matched = scanner._match_teams(teams, subject)
        assert matched == []

    def test_non_alpha_keyword(self, scanner):
        subject = SubjectConfig(name="Test", keywords=["CS-101"])
        teams = [
            Team(id="1", display_name="CS-101 Introduction"),
        ]
        matched = scanner._match_teams(teams, subject)
        assert len(matched) == 1

    def test_case_insensitive(self, scanner):
        subject = SubjectConfig(name="Test", keywords=["algebra"])
        teams = [
            Team(id="1", display_name="ALGEBRA 101"),
            Team(id="2", display_name="algebra 202"),
        ]
        matched = scanner._match_teams(teams, subject)
        assert len(matched) == 2

    def test_multiple_keywords(self, scanner):
        subject = SubjectConfig(name="Test", keywords=["math", "algebra"])
        teams = [
            Team(id="1", display_name="Math 101"),
            Team(id="2", display_name="Algebra 101"),
            Team(id="3", display_name="Physics 101"),
        ]
        matched = scanner._match_teams(teams, subject)
        assert len(matched) == 2

    def test_short_keyword_requires_full_word(self, scanner):
        subject = SubjectConfig(name="Test", keywords=["cs"])
        teams = [
            Team(id="1", display_name="CS 101 Group"),
            Team(id="2", display_name="cs101 group"),
            Team(id="3", display_name="csgo fans"),
        ]
        matched = scanner._match_teams(teams, subject)
        assert [t.id for t in matched] == ["1"]

    def test_multiword_keyword(self, scanner):
        subject = SubjectConfig(name="Test", keywords=["CS 101"])
        teams = [Team(id="1", display_name="CS  101 - Lectures")]
        assert len(scanner._match_teams(teams, subject)) == 1


class TestProcessTeam:
    async def test_no_site_id_returns_empty(self, scanner, sample_subject, sample_team):
        scanner.graph.get = AsyncMock(return_value={})
        recordings = await scanner._process_team(
            sample_team,
            sample_subject,
            datetime.min.replace(tzinfo=UTC),
            None,
            None,
            set(),
        )
        assert recordings == []

    async def test_site_lookup_failure_returns_empty(self, scanner, sample_subject, sample_team):
        scanner.graph.get = AsyncMock(side_effect=GraphAPIError("Site not found"))
        recordings = await scanner._process_team(
            sample_team,
            sample_subject,
            datetime.min.replace(tzinfo=UTC),
            None,
            None,
            set(),
        )
        assert recordings == []

    async def test_drive_list_failure_returns_empty(self, scanner, sample_subject, sample_team):
        async def side_effect(endpoint, **kw):
            if "sites/root" in endpoint:
                return {"id": "site1"}
            msg = "Drives error"
            raise GraphAPIError(msg)

        scanner.graph.get = AsyncMock(side_effect=side_effect)
        recordings = await scanner._process_team(
            sample_team,
            sample_subject,
            datetime.min.replace(tzinfo=UTC),
            None,
            None,
            set(),
        )
        assert recordings == []

    async def test_with_date_start_filter(self, scanner, sample_subject, sample_team):
        scanner.graph.get = AsyncMock(
            side_effect=[
                {"id": "site1"},
                {"value": [{"id": "d1"}]},
            ]
        )
        scanner.graph.get_all_pages = AsyncMock(return_value=[])
        recordings = await scanner._process_team(
            sample_team,
            sample_subject,
            datetime.min.replace(tzinfo=UTC),
            "2024-06-01",
            "2024-06-30",
            set(),
        )
        assert recordings == []

    async def test_parses_offset_datetime(self, scanner, sample_subject, sample_team):
        async def side_effect(endpoint, **kw):
            if endpoint.endswith("/sites/root"):
                return {"id": "site1"}
            if endpoint.endswith("/drives"):
                return {"value": [{"id": "d1"}]}
            return {
                "value": [
                    {
                        "id": "i1",
                        "name": "lec.mp4",
                        "createdDateTime": "2024-06-15T10:30:00+03:00",
                        "size": 1024,
                    }
                ]
            }

        scanner.graph.get = AsyncMock(side_effect=side_effect)
        recordings = await scanner._process_team(
            sample_team,
            sample_subject,
            datetime.min.replace(tzinfo=UTC),
            None,
            None,
            set(),
        )
        assert len(recordings) == 1
        assert recordings[0].created == "2024-06-15"
        assert recordings[0].time == "10:30"

    async def test_none_size_kept_bad_date_skipped(self, scanner, sample_subject, sample_team):
        async def side_effect(endpoint, **kw):
            if endpoint.endswith("/sites/root"):
                return {"id": "site1"}
            if endpoint.endswith("/drives"):
                return {"value": [{"id": "d1"}]}
            return {
                "value": [
                    {
                        "id": "i1",
                        "name": "notes.pdf",
                        "createdDateTime": "2024-06-15T10:30:00Z",
                        "size": None,
                    },
                    {
                        "id": "i2",
                        "name": "broken.mp4",
                        "createdDateTime": "not-a-date",
                        "size": 10,
                    },
                ]
            }

        scanner.graph.get = AsyncMock(side_effect=side_effect)
        recordings = await scanner._process_team(
            sample_team,
            sample_subject,
            datetime.min.replace(tzinfo=UTC),
            None,
            None,
            set(),
        )
        assert len(recordings) == 1
        assert recordings[0].item_id == "i1"
        assert recordings[0].size_mb == 0.0

    async def test_ext_error_logged_others_survive(self, scanner, sample_subject, sample_team):
        async def side_effect(endpoint, **kw):
            if endpoint.endswith("/sites/root"):
                return {"id": "site1"}
            if endpoint.endswith("/drives"):
                return {"value": [{"id": "d1"}]}
            if "q='.mp4'" in endpoint:
                msg = "throttled"
                raise GraphAPIError(msg)
            return {
                "value": [
                    {
                        "id": "i1",
                        "name": "notes.pdf",
                        "createdDateTime": "2024-06-15T10:30:00Z",
                        "size": 2048,
                    }
                ]
            }

        scanner.graph.get = AsyncMock(side_effect=side_effect)
        recordings = await scanner._process_team(
            sample_team,
            sample_subject,
            datetime.min.replace(tzinfo=UTC),
            None,
            None,
            set(),
        )
        assert [r.item_id for r in recordings] == ["i1"]


class TestScanRecordings:
    async def test_scan_no_subjects(self, scanner, monkeypatch):
        monkeypatch.setattr(
            "teamsleech.services.scanner.settings.subjects_json",
            json.dumps({"subjects": []}),
        )
        with patch("teamsleech.services.discovery.DiscoveryService") as mock_disc:
            mock_disc.return_value.get_all_joined_teams = AsyncMock(return_value=[])
            result = await scanner.scan_recordings()
        assert result == {}

    async def test_scan_with_subject_filter_matches(self, scanner, monkeypatch):
        monkeypatch.setattr(
            "teamsleech.services.scanner.settings.subjects_json",
            json.dumps(
                {
                    "subjects": [
                        {"name": "Math", "short": "MTH", "keywords": ["math"]},
                        {"name": "Physics", "short": "PHY", "keywords": ["physics"]},
                    ]
                }
            ),
        )
        with patch("teamsleech.services.discovery.DiscoveryService") as mock_disc:
            mock_disc.return_value.get_all_joined_teams = AsyncMock(return_value=[])
            result = await scanner.scan_recordings(subject_filter="Math")
        assert "Math" in result
        assert "Physics" not in result

    async def test_scan_with_subject_filter_no_match(self, scanner, monkeypatch):
        monkeypatch.setattr(
            "teamsleech.services.scanner.settings.subjects_json",
            json.dumps(
                {
                    "subjects": [
                        {"name": "Math", "short": "MTH", "keywords": ["math"]},
                    ]
                }
            ),
        )
        with pytest.raises(ValueError, match="No subject matches"):
            await scanner.scan_recordings(subject_filter="Nonexistent")

    async def test_scan_handles_subject_error_gracefully(self, scanner, monkeypatch):
        monkeypatch.setattr(
            "teamsleech.services.scanner.settings.subjects_json",
            json.dumps(
                {
                    "subjects": [
                        {"name": "Math", "short": "MTH", "keywords": ["math"]},
                    ]
                }
            ),
        )
        with patch("teamsleech.services.discovery.DiscoveryService") as mock_disc:
            mock_disc.return_value.get_all_joined_teams = AsyncMock(
                side_effect=GraphAPIError("Teams fetch failed")
            )
            result = await scanner.scan_recordings()
        assert result == {"Math": []}

    async def test_scan_no_matched_teams_returns_empty(self, scanner, monkeypatch, mock_graph_api):
        monkeypatch.setattr(
            "teamsleech.services.scanner.settings.subjects_json",
            json.dumps(
                {
                    "subjects": [
                        {"name": "Math", "short": "MTH", "keywords": ["math"]},
                    ]
                }
            ),
        )
        with patch("teamsleech.services.discovery.DiscoveryService") as mock_disc:
            mock_disc.return_value.get_all_joined_teams = AsyncMock(return_value=[])
            scanner._match_teams = lambda teams, subject: []
            result = await scanner.scan_recordings()
        assert result == {"Math": []}

    async def test_scan_does_not_advance_last_run(self, scanner, monkeypatch):
        monkeypatch.setattr(
            "teamsleech.services.scanner.settings.subjects_json",
            json.dumps(
                {
                    "subjects": [
                        {"name": "Math", "short": "MTH", "keywords": ["math"]},
                    ]
                }
            ),
        )

        async def side_effect(endpoint, **kw):
            if endpoint.endswith("/sites/root"):
                return {"id": "site1"}
            if endpoint.endswith("/drives"):
                return {"value": [{"id": "d1"}]}
            return {
                "value": [
                    {
                        "id": "i1",
                        "name": "lec.mp4",
                        "createdDateTime": "2024-06-15T10:30:00Z",
                        "size": 1024,
                    }
                ]
            }

        scanner.graph.get = AsyncMock(side_effect=side_effect)
        with patch("teamsleech.services.discovery.DiscoveryService") as mock_disc:
            mock_disc.return_value.get_all_joined_teams = AsyncMock(
                return_value=[Team(id="t1", display_name="math group")]
            )
            result = await scanner.scan_recordings()
        assert len(result["Math"]) == 1
        scanner.state.save_last_run.assert_not_called()

    async def test_scan_dedups_across_teams(self, scanner, monkeypatch):
        monkeypatch.setattr(
            "teamsleech.services.scanner.settings.subjects_json",
            json.dumps(
                {
                    "subjects": [
                        {"name": "Math", "short": "MTH", "keywords": ["team"]},
                    ]
                }
            ),
        )

        def _rec(item_id):
            return Recording(
                name="a.mp4",
                size_mb=1.0,
                created="2024-01-02",
                time="10:00",
                duration_ms=0,
                drive_id="d",
                item_id=item_id,
                team_name="t",
                subject_name="Math",
                is_video=True,
            )

        teams = [
            Team(id="1", display_name="team A"),
            Team(id="2", display_name="team B"),
        ]
        with patch("teamsleech.services.discovery.DiscoveryService") as mock_disc:
            mock_disc.return_value.get_all_joined_teams = AsyncMock(return_value=teams)
            scanner._process_team = AsyncMock(side_effect=[[_rec("i1")], [_rec("i1"), _rec("i2")]])
            result = await scanner.scan_recordings()
        assert [r.item_id for r in result["Math"]] == ["i1", "i2"]
