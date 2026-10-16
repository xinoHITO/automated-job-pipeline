import os
import json
import time
import dateparser
from urllib.parse import urlparse
from colorama import Fore, Back, Style
from notion_client import Client
from notion_client.errors import APIResponseError
from dotenv import load_dotenv

from . import globals
from .debug import log

load_dotenv()

# 1. Initialize credentials
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
DATABASE_ID = os.environ.get("DATABASE_ID")
DATA_SOURCE_ID = os.environ.get("DATA_SOURCE_ID")

_client:Client = None

def get_client() -> Client:
    """Lazy singleton: validates config only when Notion is actually needed."""
    global _client
    if _client is None:
        missing = [
            name for name, value in
            [("NOTION_TOKEN", NOTION_TOKEN),
             ("DATABASE_ID", DATABASE_ID),
             ("DATA_SOURCE_ID", DATA_SOURCE_ID)]
            if not value
        ]
        if missing:
            raise RuntimeError(
                f"Missing required environment variables: {', '.join(missing)}. "
                "Copy .env.example to .env and fill them in."
            )
        _client = Client(auth=NOTION_TOKEN)
    return _client

def job_exists_in_notion(job_title:str, company:str, date_posted:str):
    """Queries Notion to check if an entry with matching title, company, and posted date exists."""
    if not job_title or not company or not date_posted:
        return False

    # Format date string into ISO format matching Notion's stored date
    try:
        settings = {"DATE_ORDER": "MDY"}
        date_object = dateparser.parse(date_posted, settings=settings)
        if not date_object:
            return False
        # Extract YYYY-MM-DD or full ISO string depending on how dateparser produces it
        iso_date = date_object.date().isoformat()
    except Exception as e:
        log(f"⚠️ Error parsing date for duplicate check: {e}")
        return False

    try:
        response = get_client().data_sources.query(
            data_source_id=DATA_SOURCE_ID,
            filter={
                "and": [
                    {
                        "property": "Job Title",
                        "title": {
                            "equals": job_title
                        }
                    },
                    {
                        "property": "Company",
                        "rich_text": {
                            "equals": company
                        }
                    },
                    {
                        "property": "Date Posted",
                        "date": {"equals": iso_date}
                    }
                ]
            }
        )
        duplicates = response.get("results", [])
        for page in duplicates:
            properties = page.get("properties", {})
            date_prop = properties.get("Date Posted", {}).get("date")
            posted_date = date_prop.get("start") if date_prop else None
            print(posted_date)
        return len(duplicates) > 0
    except APIResponseError as e:
        log(f"⚠️ Error checking job duplication (Title/Company/Date): {e}")
        return False

def url_exists_in_notion(url):
    """Queries Notion to check if a page with the given URL already exists."""
    if not url:
        return False
    try:
        response = get_client().data_sources.query(
            data_source_id=DATA_SOURCE_ID,
            filter={
                "property": "URL",
                "url": {
                    "equals": url
                }
            }
        )
        # If the results list is not empty, the URL already exists
        return len(response.get("results", [])) > 0
    except APIResponseError as e:
        log(f"⚠️ Error checking URL duplication: {e}")
        return False

def is_valid_url(url: str) -> bool:
    try:
        result = urlparse(url)
        # A valid URL must have a protocol (scheme) and a domain (netloc)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

def update_notion_database_with_file(json_file):
    # Load your local JSON file
    try:
        with open(json_file, "r", encoding="utf-8") as file:            
            update_notion_database(file.read())
    except FileNotFoundError:
        log(f"Error: Could not find file {json_file}. Please check the file path.")
        exit()    

def update_notion_database(json_text:str):
    log(f"\n ---NOTION UPLOAD START--- ")

    entries = json.loads(json_text)

    if entries is not None and len(entries) > 0:
        log(f"Found {len(entries)} entries to upload. Starting process...")
    else:
        log(f"Found 0 entries to upload. Ending process")

    # 3. Iterate and upload each entry
    for index, item in enumerate(entries, start=1):
        
        try:
            job_title = item.get("job_title", "Untitled job")
            if not job_title:
                job_title = "Untitled job"
            company =  item.get("company", "")
            if not company:
                company = "Untitled company"
            match_reason = item.get("match_reason", "")
                    
            job_location = item.get("location", "Anywhere")

            is_repeated = url_exists_in_notion(item.get("link",""))
            if is_repeated:
                log(f"[{index}/{len(entries)}] Already in database. Skipping: {Fore.RED} {job_title}{Style.RESET_ALL}")
                continue

            # Dynamically build the Notion database schema properties mapping
            # Ensure properties match the Column Names and Types in your Notion DB exactly
            notion_properties = {
                "Job Title": { 
                    "title": [{"text": {"content": job_title}}]
                },
                "Company": { 
                    "rich_text": [{"text": {"content": company}}]
                },
                "Match Reason": { 
                    "rich_text": [{"text": {"content": match_reason}}]
                },
                "Location": { 
                    "rich_text": [{"text": {"content": job_location}}]
                }
            }

            # Conditional formatting to avoid API validation errors for empty fields
            if item.get("date_posted"):
                try:
                    settings = {"DATE_ORDER":"MDY"}
                    date_posted = item["date_posted"]
                    date_object = dateparser.parse(date_posted,settings=settings)
                    iso_string = date_object.isoformat()
                    notion_properties["Date Posted"] = {"date": {"start": iso_string}}

                    is_duplicated = job_exists_in_notion(job_title,company,date_posted)
                    if is_duplicated:
                        log(f"[{index}/{len(entries)}] Already in database. Skipping: {Fore.RED} {job_title}{Style.RESET_ALL}")
                        continue
                except:
                    log(f"[{index}/{len(entries)}] Invalid date_posted... leaving field empty")

            if item.get("link"):
                if is_valid_url(item["link"]):                
                    notion_properties["URL"] = {"url": item["link"]}
                else:
                    log(f"[{index}/{len(entries)}] Invalid URL {Fore.MAGENTA}{item["link"]}{Style.RESET_ALL} - Skipping: {Fore.RED} {job_title}{Style.RESET_ALL}")
                    continue
            else:
                log(f"[{index}/{len(entries)}] No URL found - Skipping: {Fore.RED} {job_title}{Style.RESET_ALL}")
                continue
                
            if item.get("total_score") is not None:
                try:
                    notion_properties["Score"] = {"number": int(item["total_score"])}
                except ValueError:
                    notion_properties["Score"] = {"number": 0}
                    log(f"[{index}/{len(entries)}] Couldn't parse score for {Fore.YELLOW}{job_title}{Style.RESET_ALL} - {Fore.CYAN}{company}{Style.RESET_ALL} setting to zero")

            # 4. Build the Page Body Content (Blocks)
            page_content = []
            cover_letter_text = item.get("generated_cover_letter", "").strip()

            if cover_letter_text:
                # Add a heading for styling inside the page
                page_content.append({
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"text": {"content": "Generated Cover Letter"}}]
                    }
                })
                
                # Split cover letter by newlines so it displays naturally as individual paragraphs
                paragraphs = cover_letter_text.split('\n')
                for para in paragraphs:
                    # Skip empty lines to prevent excessive spacing blocks
                    if para.strip():
                        page_content.append({
                            "object": "block",
                            "type": "paragraph",
                            "paragraph": {
                                "rich_text": [{"text": {"content": para.strip()}}]
                            }
                        })
        except Exception as e:
            log(f"Unexpected error when parsing new entry {Fore.GREEN}{index}{Style.RESET_ALL} - {Fore.RED}{e}{Style.RESET_ALL}")

            continue
        try:
            # Create the page in Notion
            get_client().pages.create(
                parent={"database_id": DATABASE_ID},
                properties=notion_properties,
                children=page_content if page_content else None # Injects content into the page body
            )
            log(f"[{index}/{len(entries)}] Successfully added: {Fore.GREEN}{job_title}{Style.RESET_ALL}")
                
            # Rate limit safety buffer (Notion limits requests to roughly 3 per second)
            time.sleep(0.35)

        except APIResponseError as e:
            log(f"APIResponseError on entry {Fore.GREEN}{index} {Fore.CYAN}({job_title}){Style.RESET_ALL}: {Fore.RED}{e}{Style.RESET_ALL}")
        except Exception as e:
            log(f"Unexpected error when uploading new row to Notion databse: {Fore.RED}{e}{Style.RESET_ALL}")
        

    log(f" ---NOTION UPLOAD FINISHED--- ")

if __name__ =="__main__":
    update_notion_database(f"{globals.base_dir}/temp/entries.json")