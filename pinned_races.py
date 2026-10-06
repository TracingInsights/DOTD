"""Races whose DOTD data is pinned to the repository's original records.

The official awards source (the JSON API behind
formula1.com/en/results/{year}/awards/driver-of-the-day) now publishes
"updated" results for a handful of races that contradict the results
announced at the time of the race. For those races the repository keeps the
original data — the committed ``{year}/{race}/dotd.json`` files — as the
source of truth:

* 2019 Austrian Grand Prix    — Max Verstappen (74.0%), not Kubica
* 2020 British Grand Prix     — Lewis Hamilton, not Hulkenberg
* 2021 Portuguese Grand Prix  — Sergio Pérez (15.4%), not Mazepin
* 2022 Canadian Grand Prix    — Charles Leclerc (21.6%), not Latifi

Every writer must consult this module before overwriting race files or
summaries, so the original data survives local reruns and GitHub Actions
updates alike:

* ``fetch_official_dotd.py`` substitutes the on-disk originals when building
  per-race files, year summaries and the overall summary;
* ``fetch_single_dotd.py`` refuses to overwrite a pinned race;
* ``latest_dotd.py`` keeps the on-disk original if an article mentions one.
"""

from __future__ import annotations

import json
from pathlib import Path

# (year, race_name) -> why the race is pinned
PINNED_RACES: dict[tuple[int, str], str] = {
    (2019, "Austrian Grand Prix"): (
        "original winner Max Verstappen (74.0%); the official source now "
        "returns Robert Kubica (41.2%)"
    ),
    (2020, "British Grand Prix"): (
        "original winner Lewis Hamilton; the official source now returns "
        "Nico Hulkenberg (17.32%)"
    ),
    (2021, "Portuguese Grand Prix"): (
        "original winner Sergio Pérez (15.4%); the official source now "
        "returns Nikita Mazepin (15.03%)"
    ),
    (2022, "Canadian Grand Prix"): (
        "original winner Charles Leclerc (21.6%); the official source now "
        "returns Nicholas Latifi (22.63%)"
    ),
}


def is_pinned(year: int, race_name: str) -> bool:
    """Return True when ``(year, race_name)`` must keep its original data."""
    return (int(year), race_name) in PINNED_RACES


def load_pinned_race(base_dir: str | Path, year: int, race_name: str) -> dict | None:
    """Load the committed original ``dotd.json`` for a pinned race.

    Returns the race dict, or ``None`` when the file is missing or not a
    usable race record (callers should treat ``None`` as "cannot pin").
    """
    path = Path(base_dir) / str(year) / race_name / "dotd.json"
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if (
        not isinstance(data, dict)
        or not data.get("winner")
        or not data.get("voting_results")
    ):
        return None
    return data