# DOTD

Data updated within 1hr 10 minutes of race end
https://www.formula1.com/en/latest/article/driver-of-the-day-2025.1vNM15UysUT1r3A2OMaFqH

## Fetching Single Race Data

You can manually fetch Driver of the Day results for a specific race using the GitHub Actions workflow:

1. Go to the **Actions** tab in this repository
2. Select **"Fetch Single DOTD Result"** workflow
3. Click **"Run workflow"**
4. Enter the F1 article URL (e.g., `https://www.formula1.com/en/latest/article/driver-of-the-day-verstappens-battling-miami-drive-gets-your-vote.45ksNzyjWSu135WKHMhMfo`)
5. Click **"Run workflow"** button

The workflow will:
- Extract the DOTD data using Tabstack API
- Save the race data to `YEAR/RACE_NAME/dotd.json`
- Update the yearly summary file `YEAR/dotd_YEAR.json`
- Update the overall summary file `dotd_overall_summary.json`
- Commit and push the changes
- Create a GitHub release with the race results

### Requirements

- `TABSTACK_API_KEY` must be set as a repository secret

https://f1.fandom.com/wiki/Driver_of_the_Day#2016

2018: https://www.formula1.com/en/latest/article/driver-of-the-day.6dwMp9DDgssMeaAkgYuusQ

2020 British GP - Hulk was voted even though he DNS so no voting percentage published - https://www.reddit.com/r/formula1/comments/kklo3z/f1_driver_of_the_day_championship/

https://core-ecs-origin-driverteam.staging.watchliveformula1.com/en/latest/article/driver-of-the-day-2024.1I7A0iPl3nMaXyPIeFVFLZ?utm_source=chatgpt.com

2018
Abu Dhabi Grand Prix -

ALO  - 22%
SIR - 17%
VER - 16%

Braziian Grand Prix
VER - 37%
RIC - 17%
HAM - 10%

Mexican Grand Prix
VER - 28%
RIC - 21%
VET - 19%

United States Grand Prix
VER - 34%
RAi - 31%
HAM - 12%

Japanese Grand Prix
RIC - 32%
VER - 18%
VET - 15%

Russian Grand Prix
VER - 45$
LEC - 12%
HAM - 11%

Singapore Grand Prix
VER - 19%
SIR - 16%
ALO - 16%

Italian Grand Prix
RAI - 25%
HAM - 24%
VET - 17%

Belgian Grand Prix
VET - 22%
BOT - 19%
VER - 17%

Hunarian Grand Prix
RIC - 23%
VET - 18%
HAM -13%

German Grand Prix
HAM - 33%
RAI - 14%
VET - 13%

British Grand Prix
HAM - 28%
VET - 23%
RAI - 17%

Austrian Grand Prix
VER - 27%
RAI - 16%
VET - 15%

French Grand Prix
VET - 18%
VER - 17%
RAI - 15%

Canadian Grand Prix
VET - 25%
LEC - 14%
VER - 12%

Monaco Grand Prix
RIC - 29%
VER - 22%
GAS - 9%

Spanish Grand Prix
HAM - 15%
VER - 12%
LEC - 12%

Azerbaijan Grand Prix
LEC - 16%
BOT - 11%
VET - 10%

Chinese Grand Prix
RIC - 86%
VER - 5%
RAI - 3%

Bahrain Grand Prix
GAS - 89%
HAM - 4%
VET - 3%

Australian Grand Prix
ALO
