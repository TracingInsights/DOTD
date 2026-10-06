# DOTD

Formula 1 **Driver of the Day** fan-vote results, season by season.

## Source of truth

**2019–present** voting percentages come from the official awards results
pages — <https://www.formula1.com/en/results/2026/awards/driver-of-the-day>
— via the JSON API that backs them
(`api.formula1.com/v1/fom-results-extension/driver-of-the-day`).

Those values are the **official two-decimal figures** (e.g. `14.23`), not the
one-decimal recaps published in the editorial "Driver of the Day {year}"
articles. `fetch_official_dotd.py` fetches every season from 2016 through the
current year and **skips seasons the source doesn't publish** (2016–2018
return an empty dataset), leaving existing files alone.

**2016–2018** are historical: winners only (2016–2017), top-3 whole
percentages (2018, no per-race folders). The official awards API cannot
backfill these seasons — see the notes at the bottom of this file.

## Pinned races (original data)

For four races the official awards source now serves "updated" results that
contradict what was announced at the time of the race, so the repository
keeps the **original data** as the source of truth (`pinned_races.py`):

| Race | Original data kept | Official source now returns |
| --- | --- | --- |
| 2019 Austrian Grand Prix | Max Verstappen (74.0%) | Robert Kubica (41.2%) |
| 2020 British Grand Prix | Lewis Hamilton | Nico Hulkenberg (17.32%) |
| 2021 Portuguese Grand Prix | Sergio Pérez (15.4%) | Nikita Mazepin (15.03%) |
| 2022 Canadian Grand Prix | Charles Leclerc (21.6%) | Nicholas Latifi (22.63%) |

All writers enforce this automatically, so the original data survives reruns
and GitHub Actions updates:

- `fetch_official_dotd.py` substitutes the committed `dotd.json` data for
  pinned races when writing the year summaries and never overwrites their
  per-race files — even when the API payload disagrees;
- `fetch_single_dotd.py` refuses to overwrite a pinned race;
- `latest_dotd.py` keeps the committed data if an article mentions one.

`dotd_overall_summary.json` is rebuilt from the year summaries, so pinned
races keep their original winners there too. A pinned race is also restored
into the year summary if the official source ever drops it.

## Data layout

| Path | Content |
| --- | --- |
| `{year}/{Race Name}/dotd.json` | One race: `race_name`, `year`, `winner`, `voting_results[{driver, percentage}]` |
| `{year}/dotd_{year}.json` | Year summary: `year`, `total_races`, `last_updated`, `races[]` |
| `dotd_overall_summary.json` | Cross-year index of race names + winners only |

Percentages are stored exactly as the official source publishes them (up to
two decimals; whole numbers stay whole, e.g. `30`).

## GitHub Actions

### Update official Driver of the Day data

Scheduled every **Monday 12:00 UTC** (and manual), the
**"Fetch Official DOTD Data"** workflow runs:

```bash
python fetch_official_dotd.py --all-years        # scheduled / default
python fetch_official_dotd.py --year 2026       # manual single season
python fetch_official_dotd.py --from-year 2019 --to-year 2026
python fetch_official_dotd.py --dry-run
```

and commits any data changes as
`Update official Driver of the Day data [automated]`.

- Manual runs accept an optional `year` input for a single-season refresh.
- Empty seasons are skipped; failed seasons abort the commit (exit code 1).

### Fetching single race data (article fallback)

For one-off article backfills (e.g. 2016–2018 material) you can still use the
manual workflow:

1. Go to the **Actions** tab in this repository
2. Select **"Fetch Single DOTD Result"** workflow
3. Click **"Run workflow"**
4. Enter the F1 article URL (e.g., `https://www.formula1.com/en/latest/article/driver-of-the-day-verstappens-battling-miami-drive-gets-your-vote.45ksNzyjWSu135WKHMhMfo`)
5. Click **"Run workflow"** button

The workflow extracts the DOTD data using the Tabstack API, saves the race
data, updates the yearly and overall summaries, commits/pushes, and creates a
GitHub release with the race results.

## Requirements / secrets

| Secret | Used by | Purpose |
| --- | --- | --- |
| `F1_APIGEE_APIKEY` | Fetch Official DOTD Data | `apikey` header for `api.formula1.com`. The results frontend ships a public Apigee key in the awards-page ENV (`NEXT_PUBLIC_GLOBAL_EVENTTRACKER_APIKEY`); copy that value into the secret — do **not** commit it. If it rotates (the API returns 401), copy the new value from the awards page. |
| `TABSTACK_API_KEY` | Fetch Single DOTD Result | Tabstack article extraction |

For local runs, `F1_APIGEE_APIKEY` is optional: if unset, the script falls
back to parsing the public key from the awards-page HTML.

## Local development

```bash
uv sync
uv run python fetch_official_dotd.py --dry-run
uv run pytest tests/
```

Tests use captured API fixtures only — they never hit formula1.com.

## Notes and limitations

- Data freshness is bounded by the official awards source: it is updated
  after F1 publishes the DOTD result for a race, which is later than the
  editorial article recap.
- 2020 British GP: Nico Hülkenberg won the fan vote despite not starting the
  race (DNS). The official awards API *does* publish his percentage, so the
  official dataset (now on disk) is authoritative for that race.
- The legacy article scrapers (`latest_dotd.py`, `dotd.py`,
  `fetch_single_dotd.py`) are kept as fallbacks; `latest_dotd.py` no longer
  runs on a schedule so it cannot re-round official two-decimal values back
  to one decimal.

https://f1.fandom.com/wiki/Driver_of_the_Day#2016

2018: https://www.formula1.com/en/latest/article/driver-of-the-day.6dwMp9DDgssMeaAkgYuusQ

2018 data recorded from the article recap (whole percentages, top 3):

- Abu Dhabi Grand Prix — ALO 22%, SIR 17%, VER 16%
- Brazilian Grand Prix — VER 37%, RIC 17%, HAM 10%
- Mexican Grand Prix — VER 28%, RIC 21%, VET 19%
- United States Grand Prix — VER 34%, RAI 31%, HAM 12%
- Japanese Grand Prix — RIC 32%, VER 18%, VET 15%
- Russian Grand Prix — VER 45%, LEC 12%, HAM 11%
- Singapore Grand Prix — VER 19%, SIR 16%, ALO 16%
- Italian Grand Prix — RAI 25%, HAM 24%, VET 17%
- Belgian Grand Prix — VET 22%, BOT 19%, VER 17%
- Hungarian Grand Prix — RIC 23%, VET 18%, HAM 13%
- German Grand Prix — HAM 33%, RAI 14%, VET 13%
- British Grand Prix — HAM 28%, VET 23%, RAI 17%
- Austrian Grand Prix — VER 27%, RAI 16%, VET 15%
- French Grand Prix — VET 18%, VER 17%, RAI 15%
- Canadian Grand Prix — VET 25%, LEC 14%, VER 12%
- Monaco Grand Prix — RIC 29%, VER 22%, GAS 9%
- Spanish Grand Prix — HAM 15%, VER 12%, LEC 12%
- Azerbaijan Grand Prix — LEC 16%, BOT 11%, VET 10%
- Chinese Grand Prix — RIC 86%, VER 5%, RAI 3%
- Bahrain Grand Prix — GAS 89%, HAM 4%, VET 3%
- Australian Grand Prix — ALO
