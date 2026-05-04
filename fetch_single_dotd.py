#!/usr/bin/env python3
"""
Fetch Driver of the Day results for a single race using Tabstack API.
This script is designed to be triggered via GitHub Actions with a URL input.
"""

import os
import sys
import json
import re
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from urllib.parse import urlparse

try:
    from tabstack import Tabstack
except ImportError as e:
    logging.error(f"Failed to import tabstack: {e}")
    logging.error("Please install tabstack: pip install tabstack")
    sys.exit(1)


# Configuration constants
MAX_RETRIES = 2
F1_URL_PATTERN = re.compile(
    r'https?://(?:www\.)?formula1\.com/en/latest/article/.*',
    re.IGNORECASE
)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)


# JSON Schema for extraction
DOTD_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "F1 Race Driver of the Day",
    "type": "object",
    "required": ["race_name", "year", "winner", "voting_results"],
    "properties": {
        "race_name": {
            "type": "string",
            "description": "Full name of the Grand Prix",
            "example": "Chinese Grand Prix"
        },
        "year": {
            "type": "integer",
            "minimum": 1950,
            "description": "Season year"
        },
        "winner": {
            "type": "string",
            "description": "Driver of the Day winner — must match a driver name in voting_results"
        },
        "voting_results": {
            "type": "array",
            "description": "Top vote-getters, ordered by percentage descending",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["driver", "percentage"],
                "properties": {
                    "driver": {
                        "type": "string",
                        "description": "Driver's full name"
                    },
                    "percentage": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 100,
                        "description": "Share of votes received"
                    }
                },
                "additionalProperties": False
            }
        }
    },
    "additionalProperties": False
}


def validate_f1_url(url: str) -> bool:
    """
    Validate that the URL is a valid F1 article URL.
    
    Args:
        url: URL to validate
        
    Returns:
        True if valid F1 article URL, False otherwise
    """
    if not url or not isinstance(url, str):
        return False
    
    # Parse URL to ensure it's valid
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return False
    except Exception:
        return False
    
    # Check if it matches F1 article pattern
    return bool(F1_URL_PATTERN.match(url))


def extract_dotd_data(url: str, api_key: str, retry_count: int = 0) -> Optional[Dict[str, Any]]:
    """
    Extract DOTD data from the given URL using Tabstack API.
    
    Args:
        url: F1 article URL
        api_key: Tabstack API key
        retry_count: Current retry attempt (0-based)
        
    Returns:
        Extracted data as dict, or None on failure
    """
    try:
        client = Tabstack(api_key=api_key)
        response = client.extract.json(
            url=url,
            json_schema=DOTD_SCHEMA,
            geo_target={"country": "US"},
            nocache=True
        )
        
        # Validate response
        if not response or not isinstance(response, dict):
            raise ValueError("Invalid response from Tabstack API")
        
        # Ensure required fields are present
        required_fields = ["race_name", "year", "winner", "voting_results"]
        for field in required_fields:
            if field not in response:
                raise ValueError(f"Missing required field: {field}")
        
        return response
        
    except (ConnectionError, TimeoutError) as e:
        logging.error(f"Network error extracting data: {e}")
        
        if retry_count < MAX_RETRIES:
            logging.info(f"Retrying... (attempt {retry_count + 1}/{MAX_RETRIES})")
            return extract_dotd_data(url, api_key, retry_count + 1)
        
        logging.error("Max retries exceeded for network errors")
        return None
        
    except ValueError as e:
        logging.error(f"Data validation error: {e}")
        return None
        
    except Exception as e:
        logging.error(f"Unexpected error extracting data: {e}")
        
        if retry_count < MAX_RETRIES:
            logging.info(f"Retrying... (attempt {retry_count + 1}/{MAX_RETRIES})")
            return extract_dotd_data(url, api_key, retry_count + 1)
        
        logging.error("Max retries exceeded")
        return None


def save_race_data(data: Dict[str, Any]) -> Path:
    """
    Save race data to the appropriate folder structure.
    
    Args:
        data: Extracted race data
        
    Returns:
        Path to the saved file
    """
    year = data["year"]
    race_name = data["race_name"]
    
    # Create directory structure: YEAR/RACE_NAME/dotd.json
    race_dir = Path(str(year)) / race_name
    race_dir.mkdir(parents=True, exist_ok=True)
    
    # Save individual race file
    race_file = race_dir / "dotd.json"
    with open(race_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    logging.info(f"Saved race data to {race_file}")
    return race_file


def update_yearly_summary(data: Dict[str, Any]) -> Path:
    """
    Update the yearly summary file with the new race data.
    
    Args:
        data: Extracted race data
        
    Returns:
        Path to the updated yearly summary file
    """
    year = data["year"]
    summary_file = Path(str(year)) / f"dotd_{year}.json"
    
    # Load existing summary or create new one
    if summary_file.exists():
        with open(summary_file, 'r', encoding='utf-8') as f:
            summary = json.load(f)
    else:
        summary = {
            "year": year,
            "total_races": 0,
            "last_updated": None,
            "races": []
        }
    
    # Create race entry for summary
    race_entry = {
        "race_name": data["race_name"],
        "year": data["year"],
        "winner": data["winner"],
        "voting_results": data["voting_results"]
    }
    
    # Update or append race data
    race_index = None
    for i, race in enumerate(summary["races"]):
        if race["race_name"] == data["race_name"]:
            race_index = i
            break
    
    if race_index is not None:
        # Update existing race
        summary["races"][race_index] = race_entry
        logging.info(f"Updated existing race in yearly summary: {data['race_name']}")
    else:
        # Add new race
        summary["races"].append(race_entry)
        logging.info(f"Added new race to yearly summary: {data['race_name']}")
    
    # Update metadata
    summary["total_races"] = len(summary["races"])
    summary["last_updated"] = datetime.now(timezone.utc).isoformat()
    
    # Save updated summary
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    
    logging.info(f"Updated yearly summary: {summary_file}")
    return summary_file


def update_overall_summary(data: Dict[str, Any]) -> Path:
    """
    Update the overall summary file with the new race data.
    
    Args:
        data: Extracted race data
        
    Returns:
        Path to the updated overall summary file
    """
    summary_file = Path("dotd_overall_summary.json")
    
    # Load existing summary
    if summary_file.exists():
        with open(summary_file, 'r', encoding='utf-8') as f:
            summary = json.load(f)
    else:
        summary = {
            "years_processed": [],
            "total_years": 0,
            "total_races": 0,
            "last_updated": None,
            "data_by_year": {}
        }
    
    year_str = str(data["year"])
    
    # Initialize year data if not exists
    if year_str not in summary["data_by_year"]:
        summary["data_by_year"][year_str] = {
            "total_races": 0,
            "races": []
        }
    
    # Create race entry for overall summary
    race_entry = {
        "race_name": data["race_name"],
        "winner": data["winner"]
    }
    
    # Update or append race data
    year_data = summary["data_by_year"][year_str]
    race_index = None
    for i, race in enumerate(year_data["races"]):
        if race["race_name"] == data["race_name"]:
            race_index = i
            break
    
    if race_index is not None:
        year_data["races"][race_index] = race_entry
    else:
        year_data["races"].append(race_entry)
    
    # Update year metadata
    year_data["total_races"] = len(year_data["races"])
    
    # Update overall metadata
    summary["years_processed"] = sorted(set(summary.get("years_processed", []) + [data["year"]]))
    summary["total_years"] = len(summary["years_processed"])
    summary["total_races"] = sum(
        year_data["total_races"] 
        for year_data in summary["data_by_year"].values()
    )
    summary["last_updated"] = datetime.now(timezone.utc).isoformat()
    
    # Save updated summary
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    
    logging.info(f"Updated overall summary: {summary_file}")
    return summary_file


def main():
    """Main execution function."""
    # Get URL from command line argument
    if len(sys.argv) < 2:
        logging.error("URL argument required")
        logging.error("Usage: python fetch_single_dotd.py <F1_ARTICLE_URL>")
        sys.exit(1)
    
    url = sys.argv[1]
    
    # Validate URL format
    if not validate_f1_url(url):
        logging.error(f"Invalid F1 article URL: {url}")
        logging.error("URL must be a Formula 1 article from formula1.com")
        sys.exit(1)
    
    # Get API key from environment variable
    api_key = os.environ.get("TABSTACK_API_KEY")
    if not api_key:
        logging.error("TABSTACK_API_KEY environment variable not set")
        sys.exit(1)
    
    logging.info(f"Fetching DOTD data from: {url}")
    
    # Extract data
    data = extract_dotd_data(url, api_key)
    if not data:
        logging.error("Failed to extract data after retries")
        sys.exit(1)
    
    logging.info(f"Successfully extracted data for {data['race_name']} {data['year']}")
    logging.info(f"Winner: {data['winner']}")
    logging.info(f"Voting results: {len(data['voting_results'])} drivers")
    
    # Save data
    try:
        save_race_data(data)
        update_yearly_summary(data)
        update_overall_summary(data)
        
        logging.info("All data saved successfully!")
        
    except (IOError, OSError) as e:
        logging.error(f"File I/O error saving data: {e}")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Unexpected error saving data: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()