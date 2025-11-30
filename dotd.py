import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import requests

from mapping import F1_RACES, urls


def fetch_markdown_from_url(url):
    """Fetch markdown content from Jina AI URL"""
    jina_url = f"https://r.jina.ai/{url}"

    try:
        headers = {
                        "X-No-Cache": "true"
        }

        print(f"Fetching data from: {jina_url}")
        response = requests.get(jina_url, timeout=30, headers=headers)
        response.raise_for_status()

        print(f"Successfully fetched {len(response.text)} characters")
        return response.text

    except requests.exceptions.RequestException as e:
        print(f"Error fetching data from URL: {e}")
        return None


def read_local_markdown_file(year):
    """Read markdown content from local file"""
    filename = f"dotd_{year}.md"

    try:
        print(f"Reading local file: {filename}")
        with open(filename, "r", encoding="utf-8") as f:
            content = f.read()

        print(f"Successfully read {len(content)} characters from {filename}")
        return content

    except FileNotFoundError:
        print(f"Local file {filename} not found")
        return None
    except Exception as e:
        print(f"Error reading local file {filename}: {e}")
        return None


def extract_dotd_data_from_local(content, year):
    """Extract Driver of the Day data from local markdown content (different format)"""

    # Get race mappings for the year
    race_mappings = F1_RACES.get(year, {})

    all_races_data = []

    if year == 2019:
        # 2019 format: ### Nico Hulkenberg, Renault - Formula 1 Etihad Airways Abu Dhabi Grand Prix 2019
        race_sections = re.findall(
            r"### (.+?) - (Formula 1 .+? \d{4})\n\n.*?\n\n.*?\n\n\*\*(.*?)\*\*",
            content,
            re.DOTALL,
        )

        for winner_info, race_title, voting_data in race_sections:
            print(f"Processing race: {race_title}")

            # Get clean race name from mapping
            clean_race_name = race_mappings.get(
                race_title,
                race_title.replace("Formula 1 ", "").replace(f" {year}", "").strip(),
            )

            # Extract voting percentages
            vote_lines = voting_data.strip().split("\n")
            drivers_votes = []

            for line in vote_lines:
                line = line.strip()
                if not line:
                    continue

                # Handle em dash (–) for 2019
                if " – " in line and "%" in line:
                    parts = line.split(" – ")
                    if len(parts) >= 2:
                        driver_name = parts[0].strip()
                        percentage_str = parts[1].strip().replace("%", "")

                        try:
                            percentage_float = float(percentage_str)
                            drivers_votes.append(
                                {"driver": driver_name, "percentage": percentage_float}
                            )
                        except ValueError:
                            print(f"Could not parse percentage: {percentage_str}")
                            continue

            if not drivers_votes:
                print(f"No valid voting data found for {race_title}")
                continue

            # Create race data structure
            race_data = {
                "race_name": clean_race_name,
                "year": int(year),
                "winner": drivers_votes[0]["driver"] if drivers_votes else None,
                "voting_results": drivers_votes,
            }

            all_races_data.append(race_data)
            save_race_data(race_data, year, clean_race_name)

    elif year in [2020, 2021]:
        # 2020/2021 format: ### Formula 1 Etihad Airways Abu Dhabi Grand Prix 2020/2021
        race_sections = re.findall(
            r"### (Formula 1 .+? \d{4})\n\n.*?\n\n.*?\n\n\*\*(.*?)\*\*",
            content,
            re.DOTALL,
        )

        for race_title, voting_data in race_sections:
            print(f"Processing race: {race_title}")

            # Get clean race name from mapping
            clean_race_name = race_mappings.get(
                race_title,
                race_title.replace("Formula 1 ", "").replace(f" {year}", "").strip(),
            )

            # Extract voting percentages
            vote_lines = voting_data.strip().split("\n")
            drivers_votes = []

            for line in vote_lines:
                line = line.strip()
                if not line:
                    continue

                # Handle regular dash (-) for 2020/2021
                if " - " in line and "%" in line:
                    parts = line.split(" - ")
                    if len(parts) >= 2:
                        driver_name = parts[0].strip()
                        percentage_str = parts[1].strip().replace("%", "")

                        try:
                            percentage_float = float(percentage_str)
                            drivers_votes.append(
                                {"driver": driver_name, "percentage": percentage_float}
                            )
                        except ValueError:
                            print(f"Could not parse percentage: {percentage_str}")
                            continue

            if not drivers_votes:
                print(f"No valid voting data found for {race_title}")
                continue

            # Create race data structure
            race_data = {
                "race_name": clean_race_name,
                "year": int(year),
                "winner": drivers_votes[0]["driver"] if drivers_votes else None,
                "voting_results": drivers_votes,
            }

            all_races_data.append(race_data)
            save_race_data(race_data, year, clean_race_name)

    return all_races_data


def extract_dotd_data(content, year):
    """Extract Driver of the Day data from markdown content (URL format)"""

    # Get race mappings for the year
    race_mappings = F1_RACES.get(year, {})

    # Find all race sections
    race_sections = re.findall(
        r"### (FORMULA 1 .+? \d{4})\n\n.*?\n\n(.*?)\n\n\*\*(.*?)\*\*",
        content,
        re.DOTALL,
    )

    all_races_data = []

    for race_title, description, voting_data in race_sections:
        # Get clean race name from mapping
        clean_race_name = race_mappings.get(
            race_title,
            race_title.replace("FORMULA 1 ", "").replace(f" {year}", "").strip(),
        )

        # Extract voting percentages
        vote_lines = voting_data.strip().split("\n")
        drivers_votes = []

        for line in vote_lines:
            line = line.strip()
            if " - " in line and "%" in line:
                # Split driver name and percentage
                parts = line.split(" - ")
                if len(parts) == 2:
                    driver_name = parts[0].strip()
                    percentage = parts[1].strip().replace("%", "")

                    try:
                        percentage_float = float(percentage)
                        drivers_votes.append(
                            {"driver": driver_name, "percentage": percentage_float}
                        )
                    except ValueError:
                        continue

        # Create race data structure
        race_data = {
            "race_name": clean_race_name,
            "year": int(year),
            "winner": drivers_votes[0]["driver"] if drivers_votes else None,
            "voting_results": drivers_votes,
        }

        all_races_data.append(race_data)

        # Create folder structure and save individual race file
        save_race_data(race_data, year, clean_race_name)

    return all_races_data


def save_race_data(race_data, year, clean_race_name):
    """Save individual race data to JSON file in organized folder structure"""

    # Create year folder
    year_folder = Path(str(year))
    year_folder.mkdir(exist_ok=True)

    # Create race folder using clean race name as is
    race_folder = year_folder / clean_race_name
    race_folder.mkdir(exist_ok=True)

    # Save race data as JSON
    json_file = race_folder / "dotd.json"

    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(race_data, f, indent=2, ensure_ascii=False)

    print(f"Saved: {json_file}")


def process_year(year, url):
    """Process DOTD data for a specific year"""

    print(f"\n{'=' * 50}")
    print(f"Processing {year} Driver of the Day data...")
    print(f"{'=' * 50}")

    # Check if we should use local file for years 2019-2021
    if year in [2019, 2020, 2021]:
        content = read_local_markdown_file(year)
        use_local_format = True
    else:
        # Fetch markdown content from URL
        content = fetch_markdown_from_url(url)
        use_local_format = False

    if not content:
        print(f"Failed to get data for {year}!")
        return []

    try:
        print("Extracting race data...")

        if use_local_format:
            all_races = extract_dotd_data_from_local(content, year)
        else:
            all_races = extract_dotd_data(content, year)

        if not all_races:
            print(f"No race data found for {year}!")
            return []

        # Get current UTC time for last_updated
        current_utc_time = datetime.now(timezone.utc).isoformat()

        # Save summary file with all races for the year
        summary_file = Path(str(year)) / f"dotd_{year}.json"

        summary_data = {
            "year": year,
            "total_races": len(all_races),
            "last_updated": current_utc_time,
            "races": all_races,
        }

        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(summary_data, f, indent=2, ensure_ascii=False)

        print(f"\n✅ Extraction complete for {year}!")
        print(f"📊 Total races processed: {len(all_races)}")
        print(f"📁 Summary saved: {summary_file}")

        # Print race list
        print(f"\n🏁 Races processed for {year}:")
        for i, race in enumerate(all_races, 1):
            print(f"{i:2d}. {race['race_name']} - Winner: {race['winner']}")

        return all_races

    except Exception as e:
        print(f"❌ Error processing data for {year}: {e}")
        import traceback

        traceback.print_exc()
        return []


def main():
    """Main function to process all years of DOTD data"""

    print("🏎️  Formula 1 Driver of the Day Data Extractor")
    print("=" * 60)

    all_years_data = {}

    for year, url in urls.items():
        races_data = process_year(year, url)
        if races_data:
            all_years_data[year] = races_data

    # Create overall summary
    if all_years_data:
        # Get current UTC time for last_updated
        current_utc_time = datetime.now(timezone.utc).isoformat()

        overall_summary = {
            "years_processed": list(all_years_data.keys()),
            "total_years": len(all_years_data),
            "total_races": sum(len(races) for races in all_years_data.values()),
            "last_updated": current_utc_time,
            "data_by_year": {
                year: {
                    "total_races": len(races),
                    "races": [
                        {"race_name": race["race_name"], "winner": race["winner"]}
                        for race in races
                    ],
                }
                for year, races in all_years_data.items()
            },
        }

        with open("dotd_overall_summary.json", "w", encoding="utf-8") as f:
            json.dump(overall_summary, f, indent=2, ensure_ascii=False)

        print(f"\n🎯 Overall Summary:")
        print(f"📅 Years processed: {len(all_years_data)}")
        print(f"🏁 Total races: {sum(len(races) for races in all_years_data.values())}")
        print(f"📁 Overall summary saved: dotd_overall_summary.json")


if __name__ == "__main__":
    main()
