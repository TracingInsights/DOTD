# Plan: Official awards page as Driver of the Day source of truth

**Status:** implemented — `fetch_official_dotd.py`, tests in `tests/`, and `.github/workflows/fetch_official_dotd.yml`; 2019–2026 data rewritten from the official source, 2016–2018 left untouched  
**Official page (2026 example):** [https://www.formula1.com/en/results/2026/awards/driver-of-the-day](https://www.formula1.com/en/results/2026/awards/driver-of-the-day)  
**Season URL pattern:** `https://www.formula1.com/en/results/{year}/awards/driver-of-the-day`

This document is the implementation plan for a **new script** and **GitHub Action** that treat Formula 1’s results-site awards pages (and the JSON API those pages call) as the source of truth. Percentages on that source are stored to **two decimal places**. Existing repo data mostly comes from yearly “Driver of the Day {year}” editorial articles and is rounded to **one decimal**.

---

## 1. Goal

Replace article scraping as the primary ingest path with the official awards results dataset for **every season that source actually publishes**.

The new pipeline must:

1. Fetch Driver of the Day (DOTD) voting results from the official awards system, not from `formula1.com/en/latest/article/driver-of-the-day-{year}`.
2. Persist **exact official percentages** (max two decimal places). Do not re-round to one decimal.
3. Run for **all years**, not only 2026: try `2016…current year` on a schedule, write files when the source has races, and **leave existing files alone** when the source returns an empty season.
4. Keep the current on-disk layout and JSON shape so yearly summaries and `dotd_overall_summary.json` stay compatible.
5. Ship a GitHub Action (scheduled + manual) that commits updates when data changes.

Out of scope for this plan’s first implementation: rewriting `latest_dotd.py` / `fetch_single_dotd.py`, Tabstack, or Jina article parsing. Those stay as fallbacks until the official pipeline is proven.

---

## 2. What exists in this repo today

### 2.1 Layout

| Path | Role |
| --- | --- |
| `{year}/{Race Name}/dotd.json` | One race, full top-N voting list |
| `{year}/dotd_{year}.json` | Year summary: `year`, `total_races`, `last_updated`, `races[]` |
| `dotd_overall_summary.json` | Cross-year index of race names + winners only |
| `mapping.py` | Editorial article URLs + `FORMULA 1 … GRAND PRIX {year}` → folder name |
| `latest_dotd.py` | Weekly job: Jina markdown of the **year article**, regex parse, write 2026 |
| `dotd.py` | Older multi-year article extractor (local `.md` for 2019–2021) |
| `fetch_single_dotd.py` | Manual Action: Tabstack extract from a **single news article URL** |
| `.github/workflows/fetch.yml` | Cron Monday 12:00 UTC → `python latest_dotd.py` |
| `.github/workflows/fetch_single_dotd.yml` | `workflow_dispatch` with article URL; commit + GitHub Release |

Race JSON shape (target to keep):

```json
{
  "race_name": "Australian Grand Prix",
  "year": 2026,
  "winner": "Max Verstappen",
  "voting_results": [
    { "driver": "Max Verstappen", "percentage": 30.0 }
  ]
}
```

Year summary embeds the same race objects. Overall summary stores `{ "race_name", "winner" }` only.

### 2.2 How data is produced today

`latest_dotd.py` loads `urls[year]` from `mapping.py` (editorial recap pages), fetches markdown via `https://r.jina.ai/{url}`, and regex-parses lines like `Driver Name - 14.2%`. That article copy is **one-decimal fan-vote recap**, not the awards archive.

`fetch_single_dotd.py` is even more article-shaped: it only accepts `/en/latest/article/…` URLs and uses Tabstack (`TABSTACK_API_KEY`).

`mapping.py` has no official awards URLs. Commented entries for 2016–2018 point at Wayback copies of the **old** HTML awards pages, which this repo never wired up.

### 2.3 Coverage on disk

| Year | Per-race `dotd.json` folders | Year summary | Voting quality in repo |
| --- | ---: | --- | --- |
| 2016 | 21 | yes | Winner only; no `percentage` |
| 2017 | 20 | yes | Winner only; no `percentage` |
| 2018 | **0 folders** | yes (21 races) | Top 3, whole percents; typos (`Braziian`, `Hunarian`); Australia `percentage: null` |
| 2019 | 21 | yes | Top 5, mostly 1 decimal |
| 2020 | 17 | yes | Top 5, mostly 1 decimal; British GP is wrong (see §5) |
| 2021 | 21 | yes | Top 5, 1 decimal |
| 2022 | 22 | yes | Top 5, 1 decimal |
| 2023 | 22 | yes | Top 5, 1 decimal |
| 2024 | 24 | yes | Top 5, 1 decimal |
| 2025 | 24 | yes | Top 5, 1 decimal |
| 2026 | 16 | yes | Mix of 1 dp (articles) and 2 dp (Japan already matches official) |

`dotd_overall_summary.json` currently: **11 years, 229 races**, last updated 2026-10-04.

---

## 3. Official source analysis

### 3.1 The page the user pointed at

[The 2026 awards page](https://www.formula1.com/en/results/2026/awards/driver-of-the-day) is a Next.js results app (`assets/result/_next/…`), route:

`app/(pages)/[locale]/results/[season]/awards/[awardType]`

with `awardType = driver-of-the-day`.

Visible UI:

- Season dropdown (1950–current). DOTD only exists from **2016**.
- Award dropdown: DHL Fastest Lap, DHL Fastest Pit Stop, Salesforce Driver of the Day, Pirelli Pole Position.
- Results table: Grand Prix (flag + **meeting location**), winner headshot + name + TLA, chevron accordion.
- Accordion (collapsed in static HTML; data is already in the SSR payload): top vote-getters with **two-decimal** percentages.

Meeting labels on the 2026 page (not “Australian Grand Prix”):

`Australia, China, Japan, Miami, Canada, Monaco, Barcelona-Catalunya, Austria, Great Britain, Belgium, Hungary, Netherlands, Italy, Spain, Azerbaijan, Bahrain`

Note **two Spanish races** in 2026: `Barcelona-Catalunya` vs `Spain`. Folder names must not collapse both to “Spanish Grand Prix”.

Bahrain 2026 was held in Malaysia. The official location is still **`Bahrain`**. The repo folder is currently `Bahrain Grand Prix in Malaysia`.

### 3.2 Same data, two equivalent transports

The page ENV exposes:

- `NEXT_PUBLIC_GLOBAL_APIGEE_BASEURL` = `https://api.formula1.com`
- `NEXT_PUBLIC_GLOBAL_ENDPOINT_RESULTS_EXTENSION_DOTD` = `v1/fom-results-extension/driver-of-the-day`

The HTML SSR payload also embeds `accordianData` (F1’s spelling) as an array of per-race arrays of voter rows. That payload is the same numbers as the API.

**Primary ingest (recommended):** JSON API

```http
GET https://api.formula1.com/v1/fom-results-extension/driver-of-the-day?season={year}
Accept: application/json
apikey: <public Apigee key used by the results frontend>
```

Without `apikey`, Apigee returns 401 (`Failed to resolve API Key variable request.header.apikey`). Other frontend keys are rejected for this resource.

**Fallback ingest:** GET the awards HTML URL for that year and parse the SSR `accordianData` / `votePercentage` blob. Use this only if the API is down or the key rotates. Do **not** use Jina markdown of this page: collapsed accordions omit percentages.

Do not scrape the editorial article URLs in `mapping.py` for this pipeline.

### 3.3 API payload shape (verified 2026)

Top-level keys: `text`, `cta`, `articleTag`, `articles`, `data`, `isSponsored`, `year`.

`data` is **one object per race** (winner row). The full ranking is `supplementaryResults` (typically 5 drivers, winner repeated as position 1).

Useful fields per driver row:

| Field | Example | Use |
| --- | --- | --- |
| `votePosition` | `1` | Sort; ties allowed (duplicate positions) |
| `votePercentage` | `14.23`, `30`, `11.4` | Persist as-is |
| `driverFirstName` + `driverLastName` | `Max` + `Verstappen` | `winner` / `voting_results[].driver` |
| `driverTLA` | `VER` | Optional extra field; not in current schema |
| `meetingLocation` | `Australia` | Map to repo `race_name` / folder |
| `meetingKey` | `1279` | Stable race id; optional extra field |
| `meetingEndDate` | `2026-03-08` | Sort order, changelog |
| `meetingIsoCountryName` / `meetingCountryCode` | `Australia` / `AUS` | Disambiguation only |
| `teamName` | `Red Bull Racing` | Optional; not in current schema |

`articles` is related news (not required to write JSON).

Percentages are JSON numbers, not strings. Trailing zeros are not present (`30` not `30.00`). Precision is **at most two decimals**. Implementation should **not** round; it should dump the API number. Optional pretty-print: custom JSON encoder that always writes two fraction digits. That is cosmetic; Python `json.dump(30.00)` still emits `30.0` / `30` unless a custom encoder or string is used. **Recommendation:** keep JSON numbers (current schema) and stop rounding. Do not switch percentages to strings unless we explicitly want `"30.00"` on disk.

### 3.4 Year coverage on the official source (verified)

| Year | Awards HTML title | API `data` length | Notes |
| --- | --- | ---: | --- |
| 2015 | n/a | 0 | DOTD did not exist |
| 2016 | **DHL Fastest Lap** (wrong award) | **0** | URL 200s but site falls through; API `{data:[], year:"2016"}` |
| 2017 | DHL Fastest Lap | **0** | Same |
| 2018 | DHL Fastest Lap | **0** | Same |
| 2019 | Salesforce Driver of the Day | 21 | 20×5 voters, Hungary **6** (tie for 5th) |
| 2020 | Salesforce Driver of the Day | 17 | All 5; includes 70th Anniversary, Styria, Tuscany, Eifel, Sakhir |
| 2021 | Salesforce Driver of the Day | 21 | All 5 |
| 2022 | Salesforce Driver of the Day | 22 | All 5 |
| 2023 | Salesforce Driver of the Day | 22 | All 5 |
| 2024 | Salesforce Driver of the Day | 24 | All 5 |
| 2025 | Salesforce Driver of the Day | 24 | 23×5, Azerbaijan **6** (tie for 3rd) |
| 2026 | Salesforce Driver of the Day | 16 | Season in progress (through Bahrain) |

**Hard constraint:** the official awards source **cannot backfill 2016–2018 percentages**. The script must iterate those years, detect empty `data`, log a skip, and **not delete** current 2016–2018 files.

Older Wayback URLs in `mapping.py` / README are a separate, optional later project. They are not this source of truth.

---

## 4. Existing vs official: what will change

Compared 2019–2026 API races to on-disk `dotd.json` files. Almost every percentage that “looks close” is **one-decimal rounding of a two-decimal official value**.

### 4.1 Rounding (expected, apply everywhere)

Example — 2026 Australia:

| Driver | Official | Repo now |
| --- | ---: | ---: |
| Max Verstappen | `30` | `30.0` |
| Charles Leclerc | `14.23` | `14.2` |
| Arvid Lindblad | `10.54` | `10.5` |
| George Russell | `10.24` | `10.2` |
| Lewis Hamilton | `9.62` | `9.6` |

Banker’s vs half-up rounding already causes small mismatches (`5.25` → repo `5.3`; `8.25` → `8.3`; `6.07` → `6.0`; `16.08` → `16.0`). After the switch, official values win.

2026 Japan is already exact (`27.36`, `18.94`, …) — likely copied from the awards page rather than the article.

### 4.2 Real content errors (official overwrites)

These are not rounding; the article/manual data is wrong or incomplete:

| Race | Repo today | Official |
| --- | --- | --- |
| 2019 Austrian GP | Winner Verstappen 74.0 / Leclerc 11.0 / … | **Robert Kubica 41.2** / Verstappen 23.11 / Leclerc 11.38 / … |
| 2020 British GP | Winner Hamilton; Albon `percentage: null`; Hulk missing | **Nico Hulkenberg 17.32** / Hamilton 9.96 / Verstappen 9.69 / Norris 8.53 / Sainz 8.33 |
| 2026 Italian GP | Antonelli **39.9** | Antonelli **38.87** |
| 2019 Hungarian GP | Top 5 only (Vettel 5.2, Bottas omitted) | Tie for 5th: Vettel **5.18** and Bottas **5.18** (6 rows) |
| 2025 Azerbaijan GP | Top 5, Lawson 5th | Tie for 3rd: Russell **8.34** and Hamilton **8.34**, then Lawson 7.42, Antonelli 7.27 (**6 rows**) |

README already notes the 2020 British GP Hulkenberg DNS case. The awards API **does** publish his percentage.

### 4.3 Driver-name normalisation (official overwrites)

API names vs repo names (same person):

| Official API | Common repo form |
| --- | --- |
| `Sergio Perez` | `Sergio Pérez` |
| `Nico Hulkenberg` | `Nico Hülkenberg` |
| `Alexander Albon` | `Alex Albon` |
| `Guanyu Zhou` | `Zhou Guanyu` |
| `Kimi Räikkönen` | `Kimi Räikkönen` (already matches when accented) |

**Decision for v1:** write `"{driverFirstName} {driverLastName}"` exactly as the API returns it. `winner` must equal `voting_results[0].driver` after sorting by `votePosition` (see ties).

If we later want accented display names, add an optional alias map — do not mix sources in v1.

### 4.4 Folder / `race_name` mismatches to fix or preserve

| Official `meetingLocation` | Current folder | Plan |
| --- | --- | --- |
| `Bahrain` (2026) | `Bahrain Grand Prix in Malaysia` | Prefer **`Bahrain Grand Prix`** (official location). On first write, migrate: write new folder, delete old folder if the only file is `dotd.json`. |
| `Barcelona-Catalunya` | `Barcelona-Catalunya Grand Prix` | Keep. `mapping.py` still says `Barcelona Grand Prix` — ignore article mapping. |
| `Mexico` | `Mexico City Grand Prix` (2021+) vs `Mexican Grand Prix` (2016–2019) | Year-specific alias (table in §6). |
| `Brazil` | `São Paulo Grand Prix` (2021+) vs `Brazilian Grand Prix` (2016–2019); 2018 summary typo `Braziian` | Year-specific alias. |
| `Emilia-Romagna` | `Emilia Romagna Grand Prix` | Keep hyphenless existing folder. |
| `Great Britain` | `British Grand Prix` | Keep. |
| `Netherlands` | `Dutch Grand Prix` | Keep. |
| `70th Anniversary` | `70th Anniversary Grand Prix` | Keep. |
| `Styria` / `Tuscany` | `Styrian` / `Tuscan Grand Prix` | Keep adjectival forms. |

---

## 5. Target behaviour

### 5.1 Years the job always requests

```
FIRST_DOTD_YEAR = 2016
last_year = max(datetime.utcnow().year, 2026)  # or date.today().year
years = range(FIRST_DOTD_YEAR, last_year + 1)
```

Default scheduled run: **all years** (cheap: ~11 GETs). Empty 2016–2018 responses are a few dozen bytes.

Optional CLI / Action inputs:

- `--year 2026` — one season (faster during a race weekend)
- `--from 2019 --to 2026`
- `--all-years` — default for cron

### 5.2 Empty-season policy

If `data` is missing or `[]`:

- Log: `skip {year}: official source has 0 races`
- Do not remove `{year}/` or `dotd_{year}.json`
- Do not rewrite 2016–2018 winners-only / integer data

### 5.3 Write policy

For each official race:

1. Map `meetingLocation` → canonical `race_name` / folder (§6).
2. Build `voting_results` from `supplementaryResults` (fallback: winner-only row if supplementary missing).
3. Sort by `votePosition` ascending, then by percentage descending, then by driver name. **Keep tied rows** (same `votePosition`).
4. `winner` = first row’s driver (position 1). If two position-1 rows ever appear, keep both in `voting_results` and set `winner` to the first after the sort (log a warning).
5. Write `{year}/{race_name}/dotd.json`.
6. After all races in that year, rewrite `{year}/dotd_{year}.json` from the official race list (order = API order, which follows calendar / `meetingEndDate`).
7. After all years, rebuild `dotd_overall_summary.json` from year summaries (same as `compile_overall_summary()` in `latest_dotd.py`).

Do not merge with old voting_results. Official list **replaces** the race file.

Folder rename: if mapping says the canonical name differs from an existing folder for the same `meetingKey`/`location`, write canonical and delete the obsolete folder only when it contains solely `dotd.json`.

### 5.4 Fields we will not add in v1

Keep schema stable. Do not add `meetingKey`, TLA, team, or `votePosition` to JSON until a later revision. Ties are represented by two entries with the same rounded-or-exact percentage; we can add `position` later if needed.

Optional follow-up schema (not v1):

```json
{ "driver": "Sebastian Vettel", "percentage": 5.18, "position": 5 }
```

---

## 6. `meetingLocation` → repo `race_name`

Use a dedicated map in the new script (do **not** reuse `F1_RACES` keys, which are editorial title strings).

### 6.1 Default rule

If `meetingLocation` is already a full event name (`70th Anniversary`), append ` Grand Prix` when the existing folder uses that suffix.

Adjective / conventional names:

| `meetingLocation` | Canonical `race_name` |
| --- | --- |
| Australia | Australian Grand Prix |
| China | Chinese Grand Prix |
| Japan | Japanese Grand Prix |
| Bahrain | Bahrain Grand Prix |
| Saudi Arabia | Saudi Arabian Grand Prix |
| Miami | Miami Grand Prix |
| Emilia-Romagna | Emilia Romagna Grand Prix |
| Monaco | Monaco Grand Prix |
| Spain | Spanish Grand Prix |
| Barcelona-Catalunya | Barcelona-Catalunya Grand Prix |
| Canada | Canadian Grand Prix |
| Austria | Austrian Grand Prix |
| Great Britain | British Grand Prix |
| Hungary | Hungarian Grand Prix |
| Belgium | Belgian Grand Prix |
| Netherlands | Dutch Grand Prix |
| Italy | Italian Grand Prix |
| Azerbaijan | Azerbaijan Grand Prix |
| Singapore | Singapore Grand Prix |
| Russia | Russian Grand Prix |
| United States | United States Grand Prix |
| Mexico | Mexico City Grand Prix |
| Brazil | São Paulo Grand Prix |
| Las Vegas | Las Vegas Grand Prix |
| Qatar | Qatar Grand Prix |
| Abu Dhabi | Abu Dhabi Grand Prix |
| France | French Grand Prix |
| Germany | German Grand Prix |
| Styria | Styrian Grand Prix |
| 70th Anniversary | 70th Anniversary Grand Prix |
| Tuscany | Tuscan Grand Prix |
| Eifel | Eifel Grand Prix |
| Portugal | Portuguese Grand Prix |
| Turkey | Turkish Grand Prix |
| Sakhir | Sakhir Grand Prix |

### 6.2 Year-specific overrides

| Years | Location | Canonical name (match existing folders) |
| --- | --- | --- |
| 2016–2019 | Mexico | Mexican Grand Prix |
| 2016–2019 | Brazil | Brazilian Grand Prix |
| 2021+ | Mexico | Mexico City Grand Prix |
| 2021+ | Brazil | São Paulo Grand Prix |

Unknown `meetingLocation`: derive `{location} Grand Prix`, log a warning, still write. Do not fail the whole year.

---

## 7. New script design

### 7.1 Suggested path

`fetch_official_dotd.py`

Keep it independent of `mapping.py` article URLs. Shared write/summary helpers may be extracted later; for v1, duplicating the small `json.dump` / year-summary / overall-summary logic from `latest_dotd.py` is acceptable to avoid changing the article scraper mid-migration.

### 7.2 CLI

```text
python fetch_official_dotd.py
python fetch_official_dotd.py --year 2026
python fetch_official_dotd.py --all-years
python fetch_official_dotd.py --from-year 2019 --to-year 2026
python fetch_official_dotd.py --dry-run
```

Exit codes:

- `0` success (including “no file changes”)
- `1` fatal: network/auth/parse failure after retries
- `0` with skip logs if some years empty

`--dry-run`: print planned race list + percentages, write nothing.

### 7.3 Config / secrets

| Name | Where | Purpose |
| --- | --- | --- |
| `F1_APIGEE_APIKEY` | GitHub Actions secret + local env | `apikey` header for `api.formula1.com` |

The results site ships a public Apigee key in `window.__ENV`. **Do not commit that value.** Store it as a repository secret so it can be rotated. Document how to copy it from the awards page ENV if it changes (`NEXT_PUBLIC_GLOBAL_EVENTTRACKER_APIKEY` is the key that currently authorises this resource).

Optional robustness: if `F1_APIGEE_APIKEY` is unset, parse the key from the awards HTML ENV and then call the API. That avoids a required secret for local runs, at the cost of an extra HTML GET. Fine as a fallback, not as the only path in CI (HTML/CMP can break).

User-Agent: a normal desktop browser UA. Timeout ~30s. Retry 2–3 times on 5xx/timeout. Treat 401 as fatal with a clear “check F1_APIGEE_APIKEY” message.

### 7.4 Core functions (logical)

1. `iter_years(args) -> list[int]`
2. `fetch_season(year) -> dict` — HTTP GET API
3. `normalize_races(payload, year) -> list[race_dict]` — map names, build voting_results
4. `canonical_race_name(location, year) -> str`
5. `write_race(race_dict)` — mkdir + `dotd.json`
6. `write_year_summary(year, races)`
7. `compile_overall_summary()` — scan year dirs, same structure as today
8. `retire_obsolete_folder(old, new)` — 2026 Bahrain rename

Validation before write:

- `year` matches request
- at least one race when we intend to rewrite the year file
- each race has non-empty winner
- each `percentage` is `int` or `float` in `[0, 100]` (allow official values like `30`)
- `votePosition` ≥ 1
- do not require percentages to sum to 100 (top N only)

Logging: one line per race (`year location -> race_name winner pct`) and a year total.

### 7.5 Dependencies

`requests` is enough (already in `pyproject.toml` / `requirements.txt`). **No Tabstack, no Jina.**

Use **uv** in the new workflow (consistent with `fetch_single_dotd.yml`). `fetch.yml` still uses pip + `requirements.txt`; the new workflow should not depend on Tabstack being installed.

### 7.6 HTML fallback (phase 2 if needed)

If implemented:

1. GET `https://www.formula1.com/en/results/{year}/awards/driver-of-the-day`
2. Confirm `<title>` contains `Driver of the Day`, not `DHL Fastest Lap`
3. Extract `accordianData` from the RSC/HTML payload (escaped JSON)
4. Same normalize/write path

Parsing Next.js flight data is brittle; keep this behind `--source html` and default to API.

---

## 8. GitHub Action

### 8.1 New workflow file

`.github/workflows/fetch_official_dotd.yml`

Do **not** overload `fetch.yml` until this job is trusted. Run them in parallel for a short period, then switch the Monday cron to the official script and retire `latest_dotd.py` from CI.

### 8.2 Triggers

```yaml
on:
  schedule:
    - cron: '0 12 * * 1'   # keep Monday 12:00 UTC (after typical Sunday races)
  workflow_dispatch:
    inputs:
      year:
        description: 'Season year (empty = all years from 2016 through current)'
        required: false
        type: string
```

Optional later: a second cron on Sunday 22:00 UTC for same-day race weekends. Not required for v1. README currently claims “within 1hr 10 minutes of race end”; the official awards page is updated after F1 publishes DOTD, which is later than that. The Action can only be as fresh as the API.

### 8.3 Job sketch

1. `actions/checkout@v7`
2. `astral-sh/setup-uv@v7` + `uv python install` + `uv sync`
3. `uv run python fetch_official_dotd.py` with `F1_APIGEE_APIKEY`
   - if `inputs.year` set → `--year ${{ inputs.year }}`
   - else → `--all-years`
4. `git status --porcelain` → `has_changes`
5. If changes: configure `github-actions[bot]`, `git add` the year trees + `dotd_overall_summary.json` (avoid `git add .` so markdown/plans are not committed accidentally), commit, push
6. If no changes: echo up to date

Permissions:

```yaml
permissions:
  contents: write
```

(`fetch.yml` currently omits this; the new file should include it explicitly.)

Concurrency:

```yaml
concurrency:
  group: fetch-official-dotd
  cancel-in-progress: false
```

Do **not** create GitHub Releases on the bulk/all-years job. Releases stay a `fetch_single_dotd.yml` behaviour.

Commit message:

```text
Update official Driver of the Day data [automated]
```

Manual single-year: `Update official Driver of the Day data for 2026 [automated]`

### 8.4 Secrets to add

| Secret | Required |
| --- | --- |
| `F1_APIGEE_APIKEY` | Yes for the new workflow |

`TABSTACK_API_KEY` remains only for the article workflow.

### 8.5 What happens to existing workflows

| Workflow | v1 | After official job is stable |
| --- | --- | --- |
| `fetch.yml` (`latest_dotd.py`) | Keep; may overwrite 2026 with 1-dp article data if it still runs | **Disable cron** or point it at `fetch_official_dotd.py` |
| `fetch_single_dotd.yml` | Keep for one-off article backfills (2016–2018 / missing races) | Keep as manual fallback; extend URL regex later if we want to pass awards URLs in |

**Important sequencing:** until `fetch.yml` is stopped, a Monday run of `latest_dotd.py` could **re-round 2026 back to one decimal** after the official job writes two decimals. Either (a) ship the official Action **and** remove/stop `fetch.yml` in the same change, or (b) change `fetch.yml` to call the new script. **Do (a) or (b) in the implementation PR; do not leave both writers active.**

---

## 9. Implementation sequence (when coding starts)

Ordered so the first PR can be reviewed as “new writer + Action”, with a deliberate overwrite of 2019–2026 JSON.

1. Add `fetch_official_dotd.py` with `--dry-run`, location map, API client, validators.
2. Local dry-run for 2016, 2019, 2025, 2026: confirm empty skip vs race counts 0 / 21 / 24 / 16.
3. Add unit tests **without** hitting the network: fixture JSON captured from the API (small, redacted images) for 2026 Australia + 2019 Hungary (tie) + 2025 Azerbaijan (tie) + empty 2016.
4. Local real run for 2026 only; inspect diffs (rounding + Italy 38.87 + Bahrain folder rename).
5. Add workflow + secret documentation in README.
6. Remove or retarget `fetch.yml` so article scraping cannot clobber official files.
7. Run `--all-years` once (local or manual Action) to rewrite 2019–2026 and refresh summaries. Leave 2016–2018 untouched.
8. Follow-up (optional): 2018 per-race folders + typo fixes from existing summary; 2016–2017 still winners-only unless a different archive source is approved.

No code in this planning step.

---

## 10. Tests to write with the script

| Test | Assert |
| --- | --- |
| Location map | `Great Britain` → `British Grand Prix`; 2019 `Mexico` → `Mexican Grand Prix`; 2024 `Mexico` → `Mexico City Grand Prix`; `Barcelona-Catalunya` stays distinct from `Spain` |
| Ties | 2019 Hungary produces 6 `voting_results` rows; two with `5.18` |
| Empty season | 2016 fixture writes nothing |
| Percentage fidelity | `14.23` stays `14.23`, not `14.2` |
| Winner | Equals first sorted voting row; 2020 Great Britain winner is Hulkenberg in the fixture |
| Year summary | `total_races == len(races)`; order matches API |
| Folder retire | `Bahrain Grand Prix in Malaysia` → `Bahrain Grand Prix` |

Do not call Formula 1 from CI on every push unless we add a weekly integration job; fixtures are enough for PRs.

---

## 11. README updates (implementation PR)

- State that **2019–present** voting percentages come from the [official awards results pages](https://www.formula1.com/en/results/2026/awards/driver-of-the-day) / `fom-results-extension/driver-of-the-day`.
- State that values are **two-decimal official figures**, not article one-decimal recaps.
- Document `F1_APIGEE_APIKEY` and the new Action (`year` input).
- Document 2016–2018 limitation (empty official dataset).
- Keep the single-article Action as an optional manual path.
- Drop or qualify “data updated within 1hr 10 minutes of race end” unless we add a tighter cron; the awards API is the gate.

---

## 12. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Apigee key rotation | Secret + clear 401 error; HTML ENV fallback; HTML `accordianData` fallback |
| CMP / bot blocking of HTML | Prefer API in CI |
| 2016–2018 URLs render Fastest Lap | Detect empty `data` **and** wrong title; never parse Fastest Lap tables as DOTD |
| Two Spain 2026 races | Map on `meetingLocation`, never on country code `ESP` |
| Ties (two 5ths / two 3rds) | Allow `voting_results` length ≠ 5; do not `minItems: 5` |
| `fetch.yml` overwrites 2-dp files | Retarget or disable in the same PR |
| Driver name churn vs historical JSON | Accept API spelling as canonical from this change forward |
| `json.dump` drops trailing zeros | Accept `30` vs `30.00`; precision of `14.23` is what matters |
| Rate limits | 11 season requests per run is fine; backoff on 429 |
| Legal / ToS | Same class of public results the site already shows; use a polite UA; no scraping of authenticated/live-timing APIs |

---

## 13. Decisions locked in by this plan

1. **Source:** official awards API that backs `/en/results/{year}/awards/driver-of-the-day`, for every year 2016–current.
2. **Precision:** store API percentages unchanged (two-decimal source). Stop 1-dp rounding.
3. **Empty years:** skip write; keep 2016–2018 data.
4. **Schema:** keep `race_name` / `year` / `winner` / `voting_results[{driver, percentage}]`.
5. **Names:** API `FirstName LastName`; mapped Grand Prix folder names as in §6.
6. **CI:** new Action; do not leave `latest_dotd.py` on the same Monday cron once the official writer is enabled.
7. **No implementation in this document’s delivery** — script and workflow come in a later change.

---

## 14. Open items (resolve during implementation PR if needed)

1. Cosmetic JSON: custom two-decimal encoder vs native numbers (`30` vs `30.00`).
2. Whether to add `position` on tied rows in v1 (lean **no**).
3. Whether 2026 Bahrain folder should stay `… in Malaysia` for human context (lean **no**, follow official `Bahrain`).
4. Whether a later archive pass should target 2016–2018 from Wayback / fandom (explicitly **not** this source).
5. Sunday-evening extra cron vs Monday-only.

---

## 15. Appendix: 2026 official winners (for later verification)

| Meeting | Winner | Winner % (official) |
| --- | --- | ---: |
| Australia | Max Verstappen | 30 |
| China | Kimi Antonelli | 23.43 |
| Japan | Oscar Piastri | 27.36 |
| Miami | Max Verstappen | 26.32 |
| Canada | Lewis Hamilton | 27.73 |
| Monaco | Kimi Antonelli | 22.37 |
| Barcelona-Catalunya | Lewis Hamilton | 51.86 |
| Austria | Max Verstappen | 39.61 |
| Great Britain | Charles Leclerc | 26.82 |
| Belgium | Charles Leclerc | 17.7 |
| Hungary | Max Verstappen | 18.85 |
| Netherlands | Lando Norris | 18.52 |
| Italy | Kimi Antonelli | 38.87 |
| Spain | Max Verstappen | 23.48 |
| Azerbaijan | Max Verstappen | 26.6 |
| Bahrain | Max Verstappen | 25.93 |
