import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import requests

from mapping import F1_RACES, urls


def fetch_dotd_data(year=2025):
    """
    Fetch Driver of the Day data for a specific year

    Args:
        year (int): The year to fetch data for (default: 2025)

    Returns:
        list: List of race data for the specified year
    """
    print(f"\n{'=' * 50}")
    print(f"Processing {year} Driver of the Day data...")
    print(f"{'=' * 50}")

    # Check if the year is in our URLs mapping
    if year not in urls:
        print(f"Error: No URL available for year {year}")
        return []

    # Fetch markdown content from URL
    url = urls[year]
    jina_url = f"https://r.jina.ai/{url}"
    headers = {        
        "X-No-Cache": "true"
    }

    try:
        print(f"Fetching data from: {jina_url}")
        response = requests.get(jina_url, timeout=30, headers=headers)
        response.raise_for_status()

        content = response.text
        print(f"Successfully fetched {len(content)} characters")

        # Extract race data
        all_races = extract_dotd_data(content, year)

        if not all_races:
            print(f"No race data found for {year}!")
            return []

        # Get current UTC time for last_updated
        current_utc_time = datetime.now(timezone.utc).isoformat()

        # Save summary file with all races for the year
        year_dir = Path(str(year))
        year_dir.mkdir(exist_ok=True)
        summary_file = year_dir / f"dotd_{year}.json"

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

    except requests.exceptions.RequestException as e:
        print(f"Error fetching data from URL: {e}")
        return []
    except Exception as e:
        print(f"❌ Error processing data for {year}: {e}")
        import traceback

        traceback.print_exc()
        return []


def extract_dotd_data(content, year):
    """
    Extract Driver of the Day data from markdown content

    Args:
        content (str): Markdown content
        year (int): The year of the data

    Returns:
        list: List of race data dictionaries
    """
    # Get race mappings for the year
    race_mappings = F1_RACES.get(year, {})

    # Find all race sections
    race_sections = re.findall(
        r"### (FORMULA 1 .+? \d{4})(.*?)[Hh]ere’s how the (?:voting|numbers) broke down…\n\n(.*?)(?=\n### |$)",
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
    """
    Save individual race data to JSON file in organized folder structure

    Args:
        race_data (dict): Race data dictionary
        year (int): Year of the race
        clean_race_name (str): Clean race name for folder
    """
    # Create year folder
    year_folder = Path(str(year))
    year_folder.mkdir(exist_ok=True)

    # Create race folder using clean race name
    race_folder = year_folder / clean_race_name
    race_folder.mkdir(exist_ok=True)

    # Save race data as JSON
    json_file = race_folder / "dotd.json"

    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(race_data, f, indent=2, ensure_ascii=False)

    print(f"Saved: {json_file}")


def compile_overall_summary():
    """
    Compile overall summary using existing year summary JSON files
    """
    all_years_data = {}

    # Find all year directories
    for item in os.listdir():
        if os.path.isdir(item) and item.isdigit():
            year = int(item)
            year_summary_file = Path(item) / f"dotd_{year}.json"

            if year_summary_file.exists():
                try:
                    with open(year_summary_file, "r", encoding="utf-8") as f:
                        year_data = json.load(f)
                        all_years_data[year] = year_data["races"]
                        print(
                            f"Loaded data for year {year}: {len(year_data['races'])} races"
                        )
                except Exception as e:
                    print(f"Error loading data for year {year}: {e}")

    # Create overall summary
    if all_years_data:
        # Get current UTC time for last_updated
        current_utc_time = datetime.now(timezone.utc).isoformat()

        overall_summary = {
            "years_processed": sorted(list(all_years_data.keys())),
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
                for year, races in sorted(all_years_data.items())
            },
        }

        with open("dotd_overall_summary.json", "w", encoding="utf-8") as f:
            json.dump(overall_summary, f, indent=2, ensure_ascii=False)

        print(f"\n🎯 Overall Summary:")
        print(f"📅 Years processed: {len(all_years_data)}")
        print(f"🏁 Total races: {sum(len(races) for races in all_years_data.values())}")
        print(f"📁 Overall summary saved: dotd_overall_summary.json")
    else:
        print("No year data found to compile overall summary")


def main():
    """Main function to process DOTD data and compile overall summary"""
    print("🏎️  Formula 1 Driver of the Day Data Extractor")
    print("=" * 60)

    # Fetch data for 2025 (or change the year as needed)
    fetch_dotd_data(year=2025)

    # Compile overall summary using existing data
    compile_overall_summary()


if __name__ == "__main__":
    main()
