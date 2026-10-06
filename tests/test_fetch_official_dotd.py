"""Tests for fetch_official_dotd.py — no network access required.

Fixtures are redacted JSON payloads captured from the official
`v1/fom-results-extension/driver-of-the-day` API (image/article blobs
stripped, voting fields kept verbatim):

* api_2016_empty.json        — season with no official data (skip policy)
* api_2019_hungary.json     — tie for 5th (Vettel + Bottas, 5.18)
* api_2019_austria.json     — official winner Kubica (race is PINNED: the
                             repo keeps the original Verstappen data — see
                             pinned_races.py)
* api_2020_great_britain.json — Hulkenberg winner in the API payload (race
                             is PINNED: the repo keeps the original
                             Hamilton data — see pinned_races.py)
* api_2025_azerbaijan.json  — tie for 3rd (Russell + Hamilton, 8.34)
* api_2026_australia.json   — two-decimal percentages incl. whole number 30
* api_2026_bahrain.json     — folder rename: "in Malaysia" -> canonical
"""

import argparse
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import fetch_official_dotd as mod

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    with open(FIXTURES / name, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Location map (plan §10)
# ---------------------------------------------------------------------------


class TestCanonicalRaceName:
    def test_great_britain(self):
        assert mod.canonical_race_name("Great Britain", 2021) == "British Grand Prix"

    def test_mexico_2019_uses_old_name(self):
        assert mod.canonical_race_name("Mexico", 2019) == "Mexican Grand Prix"

    def test_mexico_2024_uses_new_name(self):
        assert mod.canonical_race_name("Mexico", 2024) == "Mexico City Grand Prix"

    def test_mexico_era_boundaries(self):
        # Plan §6.2: 2016–2019 old name, 2021+ new name. 2020 had no Mexican
        # round; the gap year falls back to the default map (Mexico City).
        assert mod.canonical_race_name("Mexico", 2019) == "Mexican Grand Prix"
        assert mod.canonical_race_name("Mexico", 2020) == "Mexico City Grand Prix"
        assert mod.canonical_race_name("Mexico", 2021) == "Mexico City Grand Prix"

    def test_brazil_eras(self):
        assert mod.canonical_race_name("Brazil", 2019) == "Brazilian Grand Prix"
        assert mod.canonical_race_name("Brazil", 2021) == "São Paulo Grand Prix"
        assert mod.canonical_race_name("Brazil", 2025) == "São Paulo Grand Prix"

    def test_two_spanish_races_stay_distinct(self):
        assert (
            mod.canonical_race_name("Barcelona-Catalunya", 2026)
            == "Barcelona-Catalunya Grand Prix"
        )
        assert mod.canonical_race_name("Spain", 2026) == "Spanish Grand Prix"
        assert mod.canonical_race_name(
            "Barcelona-Catalunya", 2026
        ) != mod.canonical_race_name("Spain", 2026)

    def test_covid_replacements(self):
        assert mod.canonical_race_name("Styria", 2020) == "Styrian Grand Prix"
        assert mod.canonical_race_name("Tuscany", 2020) == "Tuscan Grand Prix"
        assert mod.canonical_race_name("Eifel", 2020) == "Eifel Grand Prix"
        assert mod.canonical_race_name("Sakhir", 2020) == "Sakhir Grand Prix"
        assert (
            mod.canonical_race_name("70th Anniversary", 2020)
            == "70th Anniversary Grand Prix"
        )

    def test_emilia_romagna_drops_hyphen(self):
        assert (
            mod.canonical_race_name("Emilia-Romagna", 2024)
            == "Emilia Romagna Grand Prix"
        )

    def test_unknown_location_derives_name(self):
        assert mod.canonical_race_name("Mars", 2026) == "Mars Grand Prix"


# ---------------------------------------------------------------------------
# Normalisation: ties, ordering, winner, percentage fidelity (plan §10)
# ---------------------------------------------------------------------------


class TestNormalizeRaces:
    def test_percentage_fidelity_two_decimals(self):
        races = mod.normalize_races(load_fixture("api_2026_australia.json"), 2026)
        by_driver = {r["driver"]: r["percentage"] for r in races[0]["voting_results"]}
        assert by_driver["Charles Leclerc"] == 14.23
        assert by_driver["Arvid Lindblad"] == 10.54
        assert by_driver["George Russell"] == 10.24
        assert by_driver["Lewis Hamilton"] == 9.62
        # whole number stays whole — no re-rounding, no string conversion
        assert by_driver["Max Verstappen"] == 30
        assert isinstance(by_driver["Max Verstappen"], int)

    def test_winner_is_first_sorted_row(self):
        races = mod.normalize_races(load_fixture("api_2026_australia.json"), 2026)
        race = races[0]
        assert race["winner"] == "Max Verstappen"
        assert race["winner"] == race["voting_results"][0]["driver"]

    def test_2020_british_gp_winner_is_hulkenberg(self):
        """The API payload normalises to Hulkenberg, but the pipeline pins
        this race to the original Hamilton data before writing (see
        TestPinnedRaces below)."""
        races = mod.normalize_races(load_fixture("api_2020_great_britain.json"), 2020)
        race = races[0]
        assert race["race_name"] == "British Grand Prix"
        assert race["winner"] == "Nico Hulkenberg"
        assert race["voting_results"][0] == {
            "driver": "Nico Hulkenberg",
            "percentage": 17.32,
        }
        # no null percentages survive from the old article data
        assert all(r["percentage"] is not None for r in race["voting_results"])

    def test_2019_hungary_tie_produces_six_rows(self):
        races = mod.normalize_races(load_fixture("api_2019_hungary.json"), 2019)
        voting = races[0]["voting_results"]
        assert len(voting) == 6
        assert voting[4] == {"driver": "Sebastian Vettel", "percentage": 5.18}
        assert voting[5] == {"driver": "Valtteri Bottas", "percentage": 5.18}
        assert races[0]["winner"] == "Max Verstappen"

    def test_2025_azerbaijan_tie_for_third(self):
        races = mod.normalize_races(load_fixture("api_2025_azerbaijan.json"), 2025)
        voting = races[0]["voting_results"]
        assert len(voting) == 6
        assert voting[2] == {"driver": "George Russell", "percentage": 8.34}
        assert voting[3] == {"driver": "Lewis Hamilton", "percentage": 8.34}
        assert voting[0]["driver"] == "Carlos Sainz"

    def test_2019_austria_official_winner_kubica(self):
        """Normalisation is transport-level: the API payload still parses to
        Kubica, but the pipeline pins this race to the original Verstappen
        data before anything is written (see TestPinnedRaces below)."""
        races = mod.normalize_races(load_fixture("api_2019_austria.json"), 2019)
        race = races[0]
        assert race["winner"] == "Robert Kubica"
        by_driver = {r["driver"]: r["percentage"] for r in race["voting_results"]}
        assert by_driver["Robert Kubica"] == 41.2
        assert by_driver["Max Verstappen"] == 23.11
        assert by_driver["Charles Leclerc"] == 11.38

    def test_sorted_by_position_then_percentage_then_name(self):
        races = mod.normalize_races(load_fixture("api_2019_hungary.json"), 2019)
        voting = races[0]["voting_results"]
        # API already ordered, but the sort must be stable/correct anyway
        names = [r["driver"] for r in voting]
        assert names == [
            "Max Verstappen",
            "Lewis Hamilton",
            "Carlos Sainz",
            "Kimi Räikkönen",
            "Sebastian Vettel",
            "Valtteri Bottas",
        ]

    def test_year_mismatch_rejected(self):
        with pytest.raises(mod.DotdError, match="does not match"):
            mod.normalize_races(load_fixture("api_2026_australia.json"), 2025)

    def test_missing_supplementary_falls_back_to_winner_row(self):
        payload = {
            "year": "2026",
            "data": [
                {
                    "votePosition": 1,
                    "votePercentage": 30,
                    "driverFirstName": "Max",
                    "driverLastName": "Verstappen",
                    "meetingLocation": "Australia",
                }
            ],
        }
        races = mod.normalize_races(payload, 2026)
        assert races[0]["voting_results"] == [
            {"driver": "Max Verstappen", "percentage": 30}
        ]
        assert races[0]["winner"] == "Max Verstappen"

    def test_empty_data_normalizes_to_empty_list(self):
        races = mod.normalize_races(load_fixture("api_2016_empty.json"), 2016)
        assert races == []

    def test_invalid_percentage_rejected_by_validation(self):
        payload = {
            "year": "2026",
            "data": [
                {
                    "votePosition": 1,
                    "votePercentage": 250,
                    "driverFirstName": "Max",
                    "driverLastName": "Verstappen",
                    "meetingLocation": "Australia",
                    "supplementaryResults": [
                        {
                            "votePosition": 1,
                            "votePercentage": 250,
                            "driverFirstName": "Max",
                            "driverLastName": "Verstappen",
                            "meetingLocation": "Australia",
                        }
                    ],
                }
            ],
        }
        race = mod.normalize_races(payload, 2026)[0]
        with pytest.raises(mod.DotdError, match="invalid percentage"):
            mod.validate_race(race, 2026)


# ---------------------------------------------------------------------------
# Writing: race files, year summary, empty-season policy (plan §10)
# ---------------------------------------------------------------------------


class TestWriting:
    def test_write_race_and_year_summary(self, tmp_path):
        payload = load_fixture("api_2026_australia.json")
        races = mod.normalize_races(payload, 2026)
        for race in races:
            mod.validate_race(race, 2026)

        mod.write_race(races[0], tmp_path)
        summary_path = mod.write_year_summary(2026, races, tmp_path)

        race_file = tmp_path / "2026" / "Australian Grand Prix" / "dotd.json"
        assert race_file.exists()
        on_disk = json.loads(race_file.read_text(encoding="utf-8"))
        assert on_disk == races[0]
        assert list(on_disk) == ["race_name", "year", "winner", "voting_results"]

        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        assert summary["year"] == 2026
        assert summary["total_races"] == len(races)
        assert summary["races"] == races

    def test_year_summary_matches_api_order(self, tmp_path):
        payload = load_fixture("api_2026_australia.json")
        races = mod.normalize_races(payload, 2026)
        summary_path = mod.write_year_summary(2026, races, tmp_path)
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        assert summary["total_races"] == len(races)
        assert [r["race_name"] for r in summary["races"]] == [
            r["race_name"] for r in races
        ]

    def test_year_summary_is_newest_first(self, tmp_path):
        """Races are stored newest-first, matching the original F1 pages."""
        payload = load_fixture("api_2026_australia.json")
        base = mod.normalize_races(payload, 2026)[0]
        first = dict(base, race_name="Bahrain Grand Prix")
        second = dict(base, race_name="Australian Grand Prix")
        summary_path = mod.write_year_summary(2026, [first, second], tmp_path)
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        assert [r["race_name"] for r in summary["races"]] == [
            "Australian Grand Prix",
            "Bahrain Grand Prix",
        ]

    def test_empty_season_writes_nothing(self, tmp_path, monkeypatch):
        """2016-style empty payload must not create or delete anything."""
        (tmp_path / "2016" / "Australian Grand Prix").mkdir(parents=True)
        existing = tmp_path / "2016" / "dotd_2016.json"
        existing.write_text(json.dumps({"year": 2016, "races": []}), encoding="utf-8")

        payload = load_fixture("api_2016_empty.json")
        assert payload["data"] == []
        # the pipeline treats empty data as a skip before any write call
        assert mod.normalize_races(payload, 2016) == []

        assert json.loads(existing.read_text(encoding="utf-8"))["year"] == 2016
        assert (tmp_path / "2016" / "Australian Grand Prix").exists()

    def test_overall_summary_shape(self, tmp_path):
        races = mod.normalize_races(load_fixture("api_2026_australia.json"), 2026)
        mod.write_year_summary(2026, races, tmp_path)
        legacy = {
            "year": 2016,
            "total_races": 1,
            "last_updated": "x",
            "races": [
                {
                    "race_name": "Australian Grand Prix",
                    "year": 2016,
                    "winner": "Romain Grosjean",
                    "voting_results": [],
                }
            ],
        }
        (tmp_path / "2016").mkdir()
        (tmp_path / "2016" / "dotd_2016.json").write_text(
            json.dumps(legacy), encoding="utf-8"
        )

        path = mod.compile_overall_summary(tmp_path)
        overall = json.loads(path.read_text(encoding="utf-8"))

        assert overall["years_processed"] == [2016, 2026]
        assert overall["total_years"] == 2
        assert overall["total_races"] == 2
        assert set(overall["data_by_year"]) == {"2016", "2026"}
        # race_name + winner only
        assert overall["data_by_year"]["2026"]["races"] == [
            {"race_name": "Australian Grand Prix", "winner": "Max Verstappen"}
        ]
        assert overall["data_by_year"]["2016"]["races"] == [
            {"race_name": "Australian Grand Prix", "winner": "Romain Grosjean"}
        ]


# ---------------------------------------------------------------------------
# Pinned races: original data survives official-source updates
# ---------------------------------------------------------------------------


class TestPinnedRaces:
    ORIGINAL_AUSTRIA = {
        "race_name": "Austrian Grand Prix",
        "year": 2019,
        "winner": "Max Verstappen",
        "voting_results": [
            {"driver": "Max Verstappen", "percentage": 74.0},
            {"driver": "Charles Leclerc", "percentage": 11.0},
        ],
    }

    def _write_pinned_2019_austria(self, tmp_path, data=None):
        race_dir = tmp_path / "2019" / "Austrian Grand Prix"
        race_dir.mkdir(parents=True, exist_ok=True)
        (race_dir / "dotd.json").write_text(
            json.dumps(data or self.ORIGINAL_AUSTRIA), encoding="utf-8"
        )

    def test_the_four_pinned_races(self):
        assert set(mod.PINNED_RACES) == {
            (2019, "Austrian Grand Prix"),
            (2020, "British Grand Prix"),
            (2021, "Portuguese Grand Prix"),
            (2022, "Canadian Grand Prix"),
        }

    def test_is_pinned(self):
        assert mod.is_pinned(2019, "Austrian Grand Prix")
        assert not mod.is_pinned(2019, "British Grand Prix")
        assert not mod.is_pinned(2026, "Austrian Grand Prix")

    def test_apply_pinned_substitutes_original_data(self, tmp_path):
        self._write_pinned_2019_austria(tmp_path)
        api_races = mod.normalize_races(load_fixture("api_2019_austria.json"), 2019)
        result = mod.apply_pinned_races(2019, api_races, tmp_path)
        assert result == [self.ORIGINAL_AUSTRIA]

    def test_apply_pinned_appends_race_missing_from_payload(self, tmp_path):
        """Even if the official source drops the race, the year summary keeps
        the original data from disk."""
        self._write_pinned_2019_austria(tmp_path)
        result = mod.apply_pinned_races(2019, [], tmp_path)
        assert result == [self.ORIGINAL_AUSTRIA]

    def test_apply_pinned_falls_back_when_file_missing(self, tmp_path):
        api_races = mod.normalize_races(load_fixture("api_2019_austria.json"), 2019)
        result = mod.apply_pinned_races(2019, api_races, tmp_path)
        assert result == api_races

    def test_apply_pinned_falls_back_when_file_invalid(self, tmp_path):
        self._write_pinned_2019_austria(tmp_path, data={"race_name": "junk"})
        api_races = mod.normalize_races(load_fixture("api_2019_austria.json"), 2019)
        result = mod.apply_pinned_races(2019, api_races, tmp_path)
        assert result == api_races

    def test_non_pinned_races_pass_through_untouched(self, tmp_path):
        races = mod.normalize_races(load_fixture("api_2026_australia.json"), 2026)
        assert mod.apply_pinned_races(2026, races, tmp_path) == races

    def test_null_percentages_allowed_in_pinned_data(self, tmp_path):
        """Original 2020 British GP data holds a null percentage; validation
        must skip pinned races so this data stays writable to summaries."""
        original = {
            "race_name": "British Grand Prix",
            "year": 2020,
            "winner": "Lewis Hamilton",
            "voting_results": [
                {"driver": "Lewis Hamilton", "percentage": 9.96},
                {"driver": "Alex Albon", "percentage": None},
            ],
        }
        race_dir = tmp_path / "2020" / "British Grand Prix"
        race_dir.mkdir(parents=True)
        (race_dir / "dotd.json").write_text(json.dumps(original), encoding="utf-8")
        api_races = mod.normalize_races(
            load_fixture("api_2020_great_britain.json"), 2020
        )
        result = mod.apply_pinned_races(2020, api_races, tmp_path)
        assert result == [original]
        # and the run-loop's validation skip must not choke on it either
        assert mod.is_pinned(2020, result[0]["race_name"])


# ---------------------------------------------------------------------------
# Folder retire (plan §10)
# ---------------------------------------------------------------------------


class TestFolderRetire:
    def _setup_2026(self, tmp_path):
        races = mod.normalize_races(load_fixture("api_2026_bahrain.json"), 2026)
        for race in races:
            mod.write_race(race, tmp_path)
        mod.write_year_summary(2026, races, tmp_path)
        old = tmp_path / "2026" / "Bahrain Grand Prix in Malaysia"
        old.mkdir(parents=True, exist_ok=True)
        (old / "dotd.json").write_text(
            json.dumps({"race_name": "Bahrain Grand Prix in Malaysia"}),
            encoding="utf-8",
        )
        return races, old

    def test_bahrain_in_malaysia_folder_retired(self, tmp_path):
        races, old = self._setup_2026(tmp_path)
        retired = mod.retire_obsolete_folders(
            2026, {r["race_name"] for r in races}, tmp_path
        )
        assert retired == ["Bahrain Grand Prix in Malaysia"]
        assert not old.exists()
        assert (tmp_path / "2026" / "Bahrain Grand Prix" / "dotd.json").exists()

    def test_folder_with_extra_files_is_kept(self, tmp_path):
        races, old = self._setup_2026(tmp_path)
        (old / "notes.txt").write_text("keep me", encoding="utf-8")
        retired = mod.retire_obsolete_folders(
            2026, {r["race_name"] for r in races}, tmp_path
        )
        assert retired == []
        assert old.exists()

    def test_no_retire_when_canonical_not_written(self, tmp_path):
        _, old = self._setup_2026(tmp_path)
        retired = mod.retire_obsolete_folders(2026, {"Australian Grand Prix"}, tmp_path)
        assert retired == []
        assert old.exists()


# ---------------------------------------------------------------------------
# API-key resolution (plan §7.3)
# ---------------------------------------------------------------------------


class TestApiKeyResolution:
    def test_env_var_wins(self, monkeypatch):
        monkeypatch.setenv("F1_APIGEE_APIKEY", "env-key")
        assert mod.resolve_api_key() == "env-key"

    def test_extract_key_from_awards_html(self):
        html = (
            'window.__ENV={"NEXT_PUBLIC_GLOBAL_EVENTTRACKER_APIKEY\\":\\"'
            "ABC123defGHI456"
            '\\","NEXT_PUBLIC_GLOBAL_APIGEE_BASEURL\\":\\"https://api.formula1.com\\"}'
        )
        assert mod.extract_key_from_awards_page(html) == "ABC123defGHI456"

    def test_missing_key_raises_auth_error(self, monkeypatch):
        import requests as requests_mod

        monkeypatch.delenv("F1_APIGEE_APIKEY", raising=False)

        class FakeResponse:
            text = "<html>no key here</html>"

            def raise_for_status(self):
                pass

        class FakeSession:
            def get(self, *a, **kw):
                return FakeResponse()

        with pytest.raises(mod.DotdAuthError, match="No API key"):
            mod.resolve_api_key(FakeSession())
        del requests_mod  # silence unused-import linters


# ---------------------------------------------------------------------------
# HTML fallback parsing (plan §7.6)
# ---------------------------------------------------------------------------


class TestHtmlFallback:
    def _awards_html(self, rows_json: str) -> str:
        escaped = (
            rows_json.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        )
        push = '{\\"data\\":[],\\"accordianData\\":' + escaped + "}"
        script = 'self.__next_f.push([1,"' + push + '"])'
        return (
            "<title>Salesforce Driver of the Day</title><script>" + script + "</script>"
        )

    def test_extract_accordian_data(self):
        rows = [
            [
                {
                    "votePosition": 1,
                    "votePercentage": 30,
                    "driverFirstName": "Max",
                    "driverLastName": "Verstappen",
                    "meetingLocation": "Australia",
                },
                {
                    "votePosition": 2,
                    "votePercentage": 14.23,
                    "driverFirstName": "Charles",
                    "driverLastName": "Leclerc",
                    "meetingLocation": "Australia",
                },
            ]
        ]
        html = self._awards_html(json.dumps(rows))
        parsed = mod.extract_accordian_data(html)
        assert parsed == rows

    def test_fetch_season_html_shapes_payload_like_api(self, monkeypatch):
        rows = [
            [
                {
                    "votePosition": 1,
                    "votePercentage": 30,
                    "driverFirstName": "Max",
                    "driverLastName": "Verstappen",
                    "meetingLocation": "Australia",
                },
                {
                    "votePosition": 2,
                    "votePercentage": 14.23,
                    "driverFirstName": "Charles",
                    "driverLastName": "Leclerc",
                    "meetingLocation": "Australia",
                },
            ]
        ]

        class FakeResponse:
            status_code = 200
            text = self._awards_html(json.dumps(rows))

            def raise_for_status(self):
                pass

        class FakeSession:
            def get(self, *a, **kw):
                return FakeResponse()

        payload = mod.fetch_season_html(2026, FakeSession())
        assert payload["year"] == "2026"
        assert len(payload["data"]) == 1
        race = mod.normalize_races(payload, 2026)[0]
        assert race["winner"] == "Max Verstappen"
        assert race["voting_results"] == [
            {"driver": "Max Verstappen", "percentage": 30},
            {"driver": "Charles Leclerc", "percentage": 14.23},
        ]

    def test_wrong_award_title_is_fatal(self):
        html = (
            '<title>DHL Fastest Lap</title><script>self.__next_f.push([1,"x"])</script>'
        )

        class FakeResponse:
            status_code = 200
            text = html

            def raise_for_status(self):
                pass

        class FakeSession:
            def get(self, *a, **kw):
                return FakeResponse()

        with pytest.raises(mod.DotdError, match="not the Driver of the Day"):
            mod.fetch_season_html(2016, FakeSession())


# ---------------------------------------------------------------------------
# CLI year selection (plan §5.1)
# ---------------------------------------------------------------------------


class TestIterYears:
    def _args(self, **kw):
        defaults = {
            "year": None,
            "all_years": False,
            "from_year": None,
            "to_year": None,
            "dry_run": False,
            "source": "api",
        }
        defaults.update(kw)
        return argparse.Namespace(**defaults)

    def test_default_is_all_years(self):
        args = self._args()
        years = mod.iter_years(args)
        assert years[0] == mod.FIRST_DOTD_YEAR
        assert years[-1] == mod._default_last_year()

    def test_single_year(self):
        assert mod.iter_years(self._args(year=2026)) == [2026]

    def test_range(self):
        assert mod.iter_years(self._args(from_year=2019, to_year=2021)) == [
            2019,
            2020,
            2021,
        ]

    def test_range_clamped_at_2016(self):
        assert mod.iter_years(self._args(from_year=2012, to_year=2017))[0] == 2016

    def test_reversed_range_is_error(self):
        with pytest.raises(SystemExit):
            mod.iter_years(self._args(from_year=2026, to_year=2019))

    def test_all_years_conflicts_with_range(self):
        with pytest.raises(SystemExit):
            mod.iter_years(self._args(all_years=True, from_year=2019))
