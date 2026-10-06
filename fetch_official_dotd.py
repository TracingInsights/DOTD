#!/usr/bin/env python3
"""Fetch official Driver of the Day voting results from formula1.com.

Source of truth is the JSON API that backs the official results-site awards
pages (https://www.formula1.com/en/results/{year}/awards/driver-of-the-day):

    GET https://api.formula1.com/v1/fom-results-extension/driver-of-the-day?season={year}
    apikey: <public Apigee key used by the results frontend>

Percentages published by that source carry up to two decimal places and are
persisted unchanged (no re-rounding to one decimal). Seasons with no official
data (2016-2018) are skipped and existing files are left alone.

Usage:
    python fetch_official_dotd.py                 # all years 2016..current
    python fetch_official_dotd.py --year 2026     # single season
    python fetch_official_dotd.py --all-years     # explicit all years
    python fetch_official_dotd.py --from-year 2019 --to-year 2026
    python fetch_official_dotd.py --dry-run        # print, write nothing

Exit codes:
    0  success (including "no file changes" and skipped empty seasons)
    1  fatal: network/auth/parse failure after retries

The API key is read from the F1_APIGEE_APIKEY environment variable. When
unset, the script falls back to parsing the public key that the results
frontend ships in the awards-page HTML ENV block
(NEXT_PUBLIC_GLOBAL_EVENTTRACKER_APIKEY).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests

from pinned_races import PINNED_RACES, is_pinned, load_pinned_race

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

FIRST_DOTD_YEAR = 2016
"""DOTD fan voting started in 2016; older seasons are never requested."""

API_BASE_URL = "https://api.formula1.com"
DOTD_ENDPOINT = "v1/fom-results-extension/driver-of-the-day"

AWARDS_PAGE_URL = "https://www.formula1.com/en/results/{year}/awards/driver-of-the-day"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 30
MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 5

API_KEY_ENV_VAR = "F1_APIGEE_APIKEY"
_API_KEY_ENV_RE = re.compile(
    r'NEXT_PUBLIC_GLOBAL_EVENTTRACKER_APIKEY\\":\\"([A-Za-z0-9\-_]+)'
)

# ---------------------------------------------------------------------------
# meetingLocation -> canonical race_name / folder name (plan §6)
# ---------------------------------------------------------------------------

LOCATION_TO_RACE_NAME = {
    "Australia": "Australian Grand Prix",
    "China": "Chinese Grand Prix",
    "Japan": "Japanese Grand Prix",
    "Bahrain": "Bahrain Grand Prix",
    "Saudi Arabia": "Saudi Arabian Grand Prix",
    "Miami": "Miami Grand Prix",
    "Emilia-Romagna": "Emilia Romagna Grand Prix",
    "Monaco": "Monaco Grand Prix",
    "Spain": "Spanish Grand Prix",
    "Barcelona-Catalunya": "Barcelona-Catalunya Grand Prix",
    "Canada": "Canadian Grand Prix",
    "Austria": "Austrian Grand Prix",
    "Great Britain": "British Grand Prix",
    "Hungary": "Hungarian Grand Prix",
    "Belgium": "Belgian Grand Prix",
    "Netherlands": "Dutch Grand Prix",
    "Italy": "Italian Grand Prix",
    "Azerbaijan": "Azerbaijan Grand Prix",
    "Singapore": "Singapore Grand Prix",
    "Russia": "Russian Grand Prix",
    "United States": "United States Grand Prix",
    "Mexico": "Mexico City Grand Prix",
    "Brazil": "São Paulo Grand Prix",
    "Las Vegas": "Las Vegas Grand Prix",
    "Qatar": "Qatar Grand Prix",
    "Abu Dhabi": "Abu Dhabi Grand Prix",
    "France": "French Grand Prix",
    "Germany": "German Grand Prix",
    "Styria": "Styrian Grand Prix",
    "70th Anniversary": "70th Anniversary Grand Prix",
    "Tuscany": "Tuscan Grand Prix",
    "Eifel": "Eifel Grand Prix",
    "Portugal": "Portuguese Grand Prix",
    "Turkey": "Turkish Grand Prix",
    "Sakhir": "Sakhir Grand Prix",
}

# Year-specific overrides (plan §6.2): (year_from, year_to), location, name.
YEAR_SPECIFIC_OVERRIDES = [
    ((2016, 2019), "Mexico", "Mexican Grand Prix"),
    ((2016, 2019), "Brazil", "Brazilian Grand Prix"),
    ((2021, None), "Mexico", "Mexico City Grand Prix"),
    ((2021, None), "Brazil", "São Paulo Grand Prix"),
]

# Obsolete folder names that should be retired once the canonical folder has
# been (re)written for the same season. The old folder is only deleted when it
# contains nothing but dotd.json (plan §5.3).
FOLDER_ALIASES = {
    "Bahrain Grand Prix in Malaysia": "Bahrain Grand Prix",
}


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class DotdError(Exception):
    """Fatal fetch/parse failure after retries."""


class DotdAuthError(DotdError):
    """API authentication failure (HTTP 401)."""


# ---------------------------------------------------------------------------
# Race-name mapping
# ---------------------------------------------------------------------------


def canonical_race_name(location: str, year: int) -> str:
    """Map an official ``meetingLocation`` to the repo race_name/folder.

    Year-specific overrides (Mexico/Brazil naming eras) win over the default
    map. Unknown locations derive ``{location} Grand Prix`` and are logged by
    the caller.
    """
    for (year_from, year_to), loc, name in YEAR_SPECIFIC_OVERRIDES:
        if (
            loc == location
            and year >= year_from
            and (year_to is None or year <= year_to)
        ):
            return name
    return LOCATION_TO_RACE_NAME.get(location, f"{location} Grand Prix")


# ---------------------------------------------------------------------------
# API key resolution
# ---------------------------------------------------------------------------


def extract_key_from_awards_page(html: str) -> str | None:
    """Pull the public Apigee key out of the awards-page ENV block."""
    match = _API_KEY_ENV_RE.search(html)
    return match.group(1) if match else None


def resolve_api_key(session: requests.Session | None = None) -> str:
    """Return the Apigee API key.

    1. ``F1_APIGEE_APIKEY`` environment variable (CI secret).
    2. Fallback: parse the public key from the current-year awards page HTML.
    """
    key = os.environ.get(API_KEY_ENV_VAR)
    if key:
        return key

    own_session = session is None
    if own_session:
        session = requests.Session()
    try:
        year = max(datetime.now(timezone.utc).year, FIRST_DOTD_YEAR + 10)
        url = AWARDS_PAGE_URL.format(year=year)
        response = session.get(
            url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        key = extract_key_from_awards_page(response.text)
    finally:
        if own_session:
            session.close()

    if not key:
        raise DotdAuthError(
            f"No API key available. Set the {API_KEY_ENV_VAR} environment "
            "variable (the public key shipped in the awards-page ENV "
            "could not be parsed either)."
        )
    print(f"ℹ️ {API_KEY_ENV_VAR} not set; using key parsed from awards-page HTML.")
    return key


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------


def _get_with_retries(
    session: requests.Session, url: str, headers: dict
) -> requests.Response:
    """GET with retries on 5xx/timeouts; exponential-ish backoff on 429."""
    last_error: str | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = session.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        except requests.exceptions.RequestException as exc:
            last_error = f"network error: {exc}"
        else:
            if response.status_code == 401:
                raise DotdAuthError(
                    "API returned 401 Unauthorized. Check the "
                    f"{API_KEY_ENV_VAR} secret/environment variable "
                    "(the public Apigee key may have rotated)."
                )
            if response.status_code == 429:
                last_error = "HTTP 429 rate limited"
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)
                continue
            if 500 <= response.status_code < 600:
                last_error = f"HTTP {response.status_code} server error"
            else:
                response.raise_for_status()
                return response
        if attempt < MAX_ATTEMPTS:
            time.sleep(RETRY_BACKOFF_SECONDS * attempt)
    raise DotdError(f"Giving up on {url} after {MAX_ATTEMPTS} attempts ({last_error}).")


def fetch_season_api(year: int, api_key: str, session: requests.Session) -> dict:
    """Fetch one season's DOTD payload from the official JSON API."""
    url = f"{API_BASE_URL}/{DOTD_ENDPOINT}?season={quote(str(year))}"
    headers = {
        "Accept": "application/json",
        "apikey": api_key,
        "User-Agent": USER_AGENT,
    }
    response = _get_with_retries(session, url, headers)
    try:
        payload = response.json()
    except ValueError as exc:
        raise DotdError(f"Season {year}: invalid JSON from API ({exc}).") from exc
    if not isinstance(payload, dict) or "data" not in payload:
        raise DotdError(
            f"Season {year}: unexpected API payload "
            f"(top-level keys: {sorted(payload) if isinstance(payload, dict) else type(payload)})."
        )
    return payload


# ---------------------------------------------------------------------------
# HTML fallback (plan §7.6) — used only via --source html or --source auto
# ---------------------------------------------------------------------------

_WRONG_AWARD_MARKERS = (
    "DHL Fastest Lap",
    "DHL Fastest Pit Stop",
    "Pirelli Pole Position",
)


def _extract_escaped_json_array(html: str, start: int) -> str:
    """Bracket-match a JSON array embedded in an escaped Next.js payload.

    Within the flight/RSC payload string, quotes appear escaped as ``\\"``;
    a quote preceded by an odd number of backslashes does not toggle string
    state. Returns the raw (still escaped) slice for the array.
    """
    depth = 0
    in_string = False
    i = start
    n = len(html)
    while i < n:
        ch = html[i]
        if ch == '"':
            # a quote is a delimiter only when preceded by an even number
            # of backslashes; in the flight payload every " is escaped
            backslashes = 0
            j = i - 1
            while j >= 0 and html[j] == "\\":
                backslashes += 1
                j -= 1
            if backslashes % 2 == 0:
                in_string = not in_string
        elif not in_string:
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    return html[start : i + 1]
        i += 1
    raise DotdError("Could not locate the end of the accordianData array.")


def _unescape_flight_string(raw: str) -> str:
    """Unescape a slice of an escaped JS/Next.js flight string."""
    placeholder = "\x00"
    raw = raw.replace("\\\\", placeholder)
    raw = raw.replace('\\"', '"')
    raw = raw.replace("\\n", "\n")
    raw = raw.replace("\\t", "\t")
    raw = raw.replace("\\r", "\r")
    return raw.replace(placeholder, "\\")


def extract_accordian_data(html: str) -> list[list[dict]]:
    """Extract the per-race voter arrays from the awards-page SSR payload."""
    marker = "accordianData"
    idx = html.find(marker)
    if idx == -1:
        return []
    start = html.find("[", idx)
    if start == -1:
        return []
    raw = _extract_escaped_json_array(html, start)
    try:
        data = json.loads(_unescape_flight_string(raw))
    except ValueError as exc:
        raise DotdError(f"Could not parse accordianData payload ({exc}).") from exc
    return data


def fetch_season_html(year: int, session: requests.Session) -> dict:
    """Fetch one season's DOTD data from the awards HTML page.

    Fallback transport for when the JSON API is unavailable. The page title
    is verified to be the Driver of the Day award (older URLs used to fall
    through to DHL Fastest Lap), then the SSR ``accordianData`` blob is
    parsed and reshaped to match the API payload.
    """
    url = AWARDS_PAGE_URL.format(year=year)
    response = _get_with_retries(session, url, {"User-Agent": USER_AGENT})
    html = response.text

    title_match = re.search(r"<title>([^<]*)</title>", html)
    title = title_match.group(1) if title_match else ""
    if "Driver of the Day" not in title:
        raise DotdError(
            f"Season {year}: awards page is not the Driver of the Day award "
            f"(title: {title!r}); refusing to parse another award's table."
        )
    for marker in _WRONG_AWARD_MARKERS:
        # tolerate the title check above, but never treat a wrong-award
        # payload as DOTD data
        if title.startswith(marker):
            raise DotdError(f"Season {year}: awards page rendered {marker!r} instead.")

    per_race_rows = extract_accordian_data(html)
    if not per_race_rows:
        return {"data": [], "year": str(year)}

    data = []
    for rows in per_race_rows:
        if not rows:
            continue
        winner_row = dict(rows[0])
        winner_row["supplementaryResults"] = rows
        data.append(winner_row)
    return {"data": data, "year": str(year)}


def fetch_season(
    year: int,
    session: requests.Session,
    api_key: str | None = None,
    source: str = "api",
) -> dict:
    """Fetch one season payload via the requested source."""
    if source == "html":
        return fetch_season_html(year, session)
    return fetch_season_api(year, api_key or resolve_api_key(session), session)


# ---------------------------------------------------------------------------
# Normalisation / validation
# ---------------------------------------------------------------------------


def _is_valid_percentage(value) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return 0 <= value <= 100


def _driver_name(row: dict) -> str:
    first = (row.get("driverFirstName") or "").strip()
    last = (row.get("driverLastName") or "").strip()
    return f"{first} {last}".strip()


def validate_race(race: dict, year: int) -> None:
    """Validate a normalised race dict before it is written to disk."""
    if race["year"] != year:
        raise DotdError(f"Race year {race['year']} does not match season {year}.")
    if not race["winner"]:
        raise DotdError(f"Season {year} {race['race_name']}: empty winner.")
    if not race["voting_results"]:
        raise DotdError(f"Season {year} {race['race_name']}: empty voting_results.")
    for entry in race["voting_results"]:
        if not entry["driver"]:
            raise DotdError(
                f"Season {year} {race['race_name']}: empty driver name in voting_results."
            )
        if not _is_valid_percentage(entry["percentage"]):
            raise DotdError(
                f"Season {year} {race['race_name']}: invalid percentage "
                f"{entry['percentage']!r} for {entry['driver']}."
            )


def normalize_race(row: dict, year: int) -> dict:
    """Build one repo-format race dict from an official winner row.

    ``supplementaryResults`` carries the full ranking (the winner is repeated
    at position 1); if it is missing the winner-only row is used. Rows are
    sorted by votePosition ascending, then percentage descending, then driver
    name — tied rows are kept.
    """
    location = (row.get("meetingLocation") or "").strip()
    if not location:
        raise DotdError(f"Season {year}: race row without meetingLocation.")
    race_name = canonical_race_name(location, year)
    if location not in LOCATION_TO_RACE_NAME and not _is_override(location, year):
        print(f"⚠️ Unknown meetingLocation {location!r} for {year}; deriving race name.")

    source_rows = row.get("supplementaryResults") or [row]

    enriched = []
    for source in source_rows:
        position = source.get("votePosition")
        if position is not None and (not isinstance(position, int) or position < 1):
            raise DotdError(
                f"Season {year} {race_name}: invalid votePosition {position!r}."
            )
        enriched.append(
            {
                "position": position if isinstance(position, int) else 999,
                "percentage": source.get("votePercentage"),
                "driver": _driver_name(source),
            }
        )
    enriched.sort(key=lambda e: (e["position"], -(e["percentage"] or 0), e["driver"]))

    voting_results = [
        {"driver": e["driver"], "percentage": e["percentage"]} for e in enriched
    ]

    winner = voting_results[0]["driver"]
    if (
        len(enriched) > 1
        and enriched[0]["position"] == 1
        and enriched[1]["position"] == 1
    ):
        print(
            f"⚠️ Season {year} {race_name}: two position-1 rows; "
            f"winner set to {winner!r} after sort."
        )

    return {
        "race_name": race_name,
        "year": int(year),
        "winner": winner,
        "voting_results": voting_results,
    }


def _is_override(location: str, year: int) -> bool:
    return canonical_race_name(location, year) != f"{location} Grand Prix"


def normalize_races(payload: dict, year: int) -> list[dict]:
    """Normalise a whole season payload into repo-format race dicts."""
    if str(payload.get("year")) != str(year):
        raise DotdError(
            f"Payload year {payload.get('year')!r} does not match requested {year}."
        )
    return [normalize_race(row, year) for row in payload.get("data") or []]


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def write_race(race: dict, base_dir: Path) -> Path:
    """Write ``{year}/{race_name}/dotd.json``. Returns the file path."""
    path = base_dir / str(race["year"]) / race["race_name"] / "dotd.json"
    _write_json(path, race)
    return path


def write_year_summary(year: int, races: list[dict], base_dir: Path) -> Path:
    """Rewrite ``{year}/dotd_{year}.json`` from the official race list.

    The official payload lists races oldest-first; the repo stores them
    newest-first to match the original F1 pages order.
    """
    path = base_dir / str(year) / f"dotd_{year}.json"
    summary = {
        "year": int(year),
        "total_races": len(races),
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "races": list(reversed(races)),
    }
    _write_json(path, summary)
    return path


def apply_pinned_races(year: int, races: list[dict], base_dir: Path) -> list[dict]:
    """Substitute the original on-disk data for pinned races.

    A few races are pinned (see ``pinned_races.py``): the official source now
    publishes "updated" results that contradict what was announced at the
    time, so the committed ``dotd.json`` files stay the source of truth.
    Pinned races present on disk but missing from the fetched payload are
    appended so the year summary never loses them.
    """
    final: list[dict] = []
    seen: set[str] = set()
    for race in races:
        race_name = race["race_name"]
        seen.add(race_name)
        if is_pinned(year, race_name):
            pinned = load_pinned_race(base_dir, year, race_name)
            if pinned is not None:
                print(
                    f"📌 Pinned {year} {race_name}: keeping original data "
                    f"(winner {pinned['winner']}); official data ignored."
                )
                final.append(pinned)
                continue
            print(
                f"⚠️ Pinned {year} {race_name} has no usable dotd.json on "
                "disk; falling back to official data."
            )
            validate_race(race, year)
        final.append(race)
    for race_name in sorted(name for (y, name) in PINNED_RACES if y == year):
        if race_name not in seen:
            pinned = load_pinned_race(base_dir, year, race_name)
            if pinned is not None:
                print(
                    f"📌 Pinned {year} {race_name} missing from the official "
                    "payload; restored original data from disk."
                )
                final.append(pinned)
    return final


def retire_obsolete_folders(
    year: int, written_race_names: set[str], base_dir: Path
) -> list[str]:
    """Delete alias folders superseded by a canonical write this run.

    An obsolete folder is only removed when it contains solely ``dotd.json``
    (plan §5.3); anything else is preserved with a warning.
    """
    year_dir = base_dir / str(year)
    retired = []
    for old_name, canonical_name in FOLDER_ALIASES.items():
        old_dir = year_dir / old_name
        if not old_dir.is_dir() or canonical_name not in written_race_names:
            continue
        contents = [p for p in old_dir.iterdir()]
        if all(p.name == "dotd.json" and p.is_file() for p in contents):
            shutil.rmtree(old_dir)
            retired.append(old_name)
            print(f"🗑️ Retired obsolete folder: {old_dir}")
        else:
            print(
                f"⚠️ Keeping obsolete folder {old_dir}: "
                "it contains more than just dotd.json."
            )
    return retired


def compile_overall_summary(base_dir: Path) -> Path | None:
    """Rebuild ``dotd_overall_summary.json`` from all year summary files.

    Same structure as ``latest_dotd.compile_overall_summary()``: scans every
    ``{year}/dotd_{year}.json`` on disk (years the official source skipped
    keep their existing data), storing race_name + winner only.
    """
    all_years_data: dict[int, list] = {}
    for item in sorted(base_dir.iterdir()):
        if not (item.is_dir() and item.name.isdigit()):
            continue
        year = int(item.name)
        summary_file = item / f"dotd_{year}.json"
        if not summary_file.exists():
            continue
        try:
            with open(summary_file, encoding="utf-8") as f:
                year_data = json.load(f)
            all_years_data[year] = year_data["races"]
            print(f"Loaded summary for {year}: {len(year_data['races'])} races")
        except (OSError, ValueError, KeyError) as exc:
            print(f"⚠️ Could not load summary for {year}: {exc}")

    if not all_years_data:
        print("No year data found to compile overall summary.")
        return None

    overall_summary = {
        "years_processed": sorted(all_years_data),
        "total_years": len(all_years_data),
        "total_races": sum(len(races) for races in all_years_data.values()),
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "data_by_year": {
            str(year): {
                "total_races": len(races),
                "races": [
                    {"race_name": race["race_name"], "winner": race["winner"]}
                    for race in races
                ],
            }
            for year, races in sorted(all_years_data.items())
        },
    }

    path = base_dir / "dotd_overall_summary.json"
    _write_json(path, overall_summary)
    print(
        f"🎯 Overall summary: {overall_summary['total_years']} years, "
        f"{overall_summary['total_races']} races -> {path}"
    )
    return path


# ---------------------------------------------------------------------------
# CLI / orchestration
# ---------------------------------------------------------------------------


def _default_last_year() -> int:
    return max(datetime.now(timezone.utc).year, 2026)


def iter_years(args: argparse.Namespace) -> list[int]:
    """Resolve the list of seasons to process from CLI arguments."""
    if args.year is not None:
        return [args.year]
    if args.all_years and (args.from_year is not None or args.to_year is not None):
        raise SystemExit(
            "error: --all-years cannot be combined with --from-year/--to-year."
        )
    first = args.from_year if args.from_year is not None else FIRST_DOTD_YEAR
    last = args.to_year if args.to_year is not None else _default_last_year()
    if last < first:
        raise SystemExit(f"error: --to-year ({last}) is before --from-year ({first}).")
    if first < FIRST_DOTD_YEAR:
        print(
            f"ℹ️ Clamping start year to {FIRST_DOTD_YEAR} "
            "(DOTD did not exist before 2016)."
        )
        first = FIRST_DOTD_YEAR
    return list(range(first, last + 1))


def run(args: argparse.Namespace) -> int:
    years = iter_years(args)
    print(f"🏎️ Official Driver of the Day fetcher — seasons {years[0]}..{years[-1]}")
    if args.dry_run:
        print("🔍 Dry run: no files will be written.")

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    api_key = None
    if args.source == "api":
        try:
            api_key = resolve_api_key(session)
        except DotdAuthError as exc:
            print(f"❌ {exc}")
            return 1

    failures = 0
    written_folders: dict[int, set[str]] = {}

    for year in years:
        try:
            payload = fetch_season(year, session, api_key=api_key, source=args.source)
        except DotdAuthError as exc:
            print(f"❌ {exc}")
            return 1
        except DotdError as exc:
            print(f"❌ Season {year} failed: {exc}")
            failures += 1
            continue

        races = payload.get("data") or []
        if not races:
            print(f"⏭️ Skip {year}: official source has 0 races.")
            continue

        try:
            normalized = normalize_races(payload, year)
        except DotdError as exc:
            print(f"❌ Season {year} normalisation failed: {exc}")
            failures += 1
            continue

        for race in normalized:
            # Pinned races keep their original on-disk data; only the
            # official (non-pinned) payload needs strict validation —
            # original records may legitimately hold null percentages.
            if not is_pinned(year, race["race_name"]):
                validate_race(race, year)

        base_dir = Path.cwd()
        normalized = apply_pinned_races(year, normalized, base_dir)

        print(f"\nSeason {year}: {len(normalized)} races from the official source.")
        for race in normalized:
            top = race["voting_results"][0]
            print(
                f"  {year} {race['race_name']}: winner {race['winner']} "
                f"({top['percentage']}%) — {len(race['voting_results'])} rows"
            )

        if args.dry_run:
            continue

        for race in normalized:
            if is_pinned(year, race["race_name"]):
                print(
                    f"  📌 Kept original data for "
                    f"{base_dir / str(year) / race['race_name']}"
                )
                continue
            path = write_race(race, base_dir)
            print(f"  ✅ Wrote {path}")
        summary_path = write_year_summary(year, normalized, base_dir)
        print(f"  ✅ Wrote {summary_path}")

        names = {race["race_name"] for race in normalized}
        retire_obsolete_folders(year, names, base_dir)
        written_folders[year] = names

    if args.dry_run:
        print("\n🔍 Dry run complete; nothing written.")
        return 1 if failures else 0

    if written_folders:
        compile_overall_summary(Path.cwd())

    session.close()
    if failures:
        print(f"\n❌ {failures} season(s) failed; not exiting cleanly.")
        return 1
    print("\n✅ Done.")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch Driver of the Day voting results from the official "
            "formula1.com awards results source."
        )
    )
    target = parser.add_mutually_exclusive_group()
    target.add_argument(
        "--year",
        type=int,
        help="fetch a single season (e.g. 2026)",
    )
    target.add_argument(
        "--all-years",
        action="store_true",
        help="fetch every season from 2016 through the current year (default)",
    )
    parser.add_argument(
        "--from-year",
        type=int,
        help="first season of a range (default 2016)",
    )
    parser.add_argument(
        "--to-year",
        type=int,
        help=f"last season of a range (default {_default_last_year()})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the planned race list and percentages without writing files",
    )
    parser.add_argument(
        "--source",
        choices=("api", "html"),
        default="api",
        help=(
            "data transport: official JSON API (default) or awards-page HTML "
            "accordianData fallback"
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return run(args)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
