import asyncio
import requests
import json
from colorama import Fore, Back, Style
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from playwright.async_api import TimeoutError
from playwright.sync_api import Page,Locator,BrowserContext
import dateparser
from datetime import datetime
import time
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from .job_model import JobModel

from . import notion as notion
from . import globals
from . import debug
from .webscraping_rules import WebScrapingRules
from .webscraping_rules import WebsiteConfig
from .webscraping_rules import Click

from .debug import write_debug_file
from .debug import log

from .import db


def load_scraping_rules():
    try:
        webscraping_config_path = f"{globals.base_dir}/{globals.DEFAULT_WEB_SCRAPING_CONFIG_PATH}"
        with open(webscraping_config_path, "r", encoding="utf-8") as f:
            json_text = f.read()
            return WebScrapingRules.model_validate_json(json_text)                                      
    except json.JSONDecodeError as decode_err:
        log(f"[CRITICAL] '{webscraping_config_path}' contains invalid JSON syntax or typos! Check for missing commas or brackets. Error: {decode_err}")
        raise decode_err

async def scrape_all_job_sites(scraping_rules_model:WebScrapingRules, max_days_since_job_posted):
    found_jobs = {}
    try:
        for config in scraping_rules_model.root:
            new_jobs: list
            new_jobs = await scrape_job_site(config, max_days_since_job_posted)
            for new_job in new_jobs:
                add_new_job(found_jobs, new_job)
    except Exception as e:
        log(f"Error when scraping job sites. Error: {e}")
        raise e

    log(f"\n[INFO] Aggregated {len(found_jobs)} deep job profiles.")
    return found_jobs

async def scrape_job_site(config, max_days_since_job_posted, check_duplicates:bool = True):
    if config.use_playwright:
        new_jobs = await __scrape_playwright(config,max_days_since_job_posted,check_duplicates)                    
    else:
        new_jobs = __scrape_static_site(config,max_days_since_job_posted,check_duplicates)
    return new_jobs

def add_new_job(jobs_dict:dict,the_new_job:JobModel):
        title = the_new_job.title.lower().strip()
        company = the_new_job.company.lower().strip()
        posted_date = the_new_job.date_posted.lower().strip()
        job_post_date = clean_date_string(posted_date)
        date_object = dateparser.parse(job_post_date)

        job_key = (title,company,date_object)
        if job_key in jobs_dict:
            job:JobModel = jobs_dict.get(job_key)
            if (
                (job.description is None or len(job.description.strip()) == 0) and
                (the_new_job.description is not None and len(the_new_job.description.strip()) == 0)
                ):
                jobs_dict[job_key] = the_new_job
        else:
            jobs_dict[job_key] = the_new_job        

def log_retry(retry_state):
    error = retry_state.outcome.exception()
    log(f'Attempt #{retry_state.attempt_number} failed: {Fore.RED}{error}{Style.RESET_ALL}')
    log(f'Retrying in {retry_state.next_action.sleep:.1f}s...')

def should_retry_playwright_webscraping(exception):
    if isinstance(exception, TimeoutError):
        return True
            
    return False

@retry(
    retry=retry_if_exception_type((requests.exceptions.Timeout, requests.exceptions.ConnectionError)),
    wait=wait_exponential(multiplier=30, min=30, max=300),
    stop=stop_after_attempt(3),
    before_sleep=log_retry,
    reraise=True
)
def go_to_static_website(prepared_url:str,headers:dict[str,str]):
    response = requests.get(prepared_url, headers=headers, timeout=30)
    return response

def __scrape_static_site(  config_model:WebsiteConfig,
                        max_days_since_job_posted:int,
                        check_duplicates:bool = True
                        ):
    """Scrapes main page via your discovered job-card class and crawls into each link for full details."""
    log(f"[SCRAPE] Accessing {config_model.site_name} index...")
    jobs = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    page_index = 1
    condition = True
    if config_model.max_page != -1:
        condition = page_index <= config_model.max_page
    while condition:
        try:
            pagination_url = ""
            if config_model.pagination != None:
                if "?" not in config_model.starting_url:
                    pagination_url = f"?{config_model.pagination}={page_index}"
                else:
                    pagination_url = f"&{config_model.pagination}={page_index}"
            prepared_url = f"{config_model.starting_url}{pagination_url}"
            response = go_to_static_website(prepared_url,headers)
            soup = BeautifulSoup(response.text, 'html.parser')
            write_debug_file("response.txt",response.text)

            # OUTER LAYER
            cards = soup.select(config_model.job_item)
            if(config_model.jobs_cap == -1):
                log(f"[INFO] Discovered {Fore.GREEN}{len(cards)}{Style.RESET_ALL} matching job cards on {Fore.MAGENTA}{prepared_url}{Fore.GREEN} Page {page_index}{Style.RESET_ALL}")
            else:
                log(f"[INFO] Discovered {Fore.GREEN}{len(cards)}{Style.RESET_ALL} (CAPPED AT {config_model.jobs_cap}) matching job cards on {Fore.MAGENTA}{prepared_url}{Fore.GREEN} Page {page_index}{Style.RESET_ALL}")

            cards_length = len(cards)
            if(config_model.jobs_cap > -1):
                enumeration = enumerate(cards[:config_model.jobs_cap])
                cards_length = config_model.jobs_cap 
            else:
                enumeration = enumerate(cards)

            # Limit to the top N recent jobs per execution run
            for index, card in enumeration:
                # Extract basic title text from card elements
                job_title_item = card.select_one(config_model.job_title)
                job_title    = next(job_title_item.stripped_strings)
                job_title = job_title.replace('\n',"")
                job_title = job_title.strip()
                job_company_item = card.select_one(config_model.job_company)
                job_location = "Unknown location"
                if not config_model.is_location_in_detail:
                    job_location = card.select_one(config_model.job_location).get_text(strip=True) if card.select_one(config_model.job_location) else ""
                job_company = job_company_item.get_text()
                job_post_date = ""       
                dmy_formatted_date = ""     
                if not config_model.is_date_in_detail and config_model.job_post_date != "":
                    date_selector = card.select_one(config_model.job_post_date)
                    if date_selector:
                        date_text:str = date_selector.get_text().strip()
                        job_post_date = clean_date_string(date_text,config_model.job_post_date_prefix,config_model.job_post_date_suffix)
                        date_obj = dateparser.parse(job_post_date)
                        dmy_formatted_date = None
                        if date_obj:
                            dmy_formatted_date = date_obj.strftime("%d-%m-%Y")
                        if is_job_too_old(job_post_date,max_days_since_job_posted):
                            log(f"{Fore.GREEN}[Page {page_index}]{Style.RESET_ALL} [{index+1}/{cards_length}]  └─> Job posted over {max_days_since_job_posted} days ago... {Fore.RED}skipping:{Style.RESET_ALL} {Fore.LIGHTCYAN_EX}{job_company}{Style.RESET_ALL} is hiring a {Fore.YELLOW}{job_title}{Style.RESET_ALL} | {dmy_formatted_date} | {job_location}")
                            condition = False
                            config_model.max_page = -2
                            break

                write_debug_file(f"card{job_title}_{job_company}.html",card.prettify())                                    

                if(config_model.job_url != ''):
                    card_url = card.select_one(config_model.job_url)
                else:
                    card_url = card            

                if card_url is not None:
                    link = card_url.get('href',"")
                    if link.startswith('/'):
                        link = config_model.site_name + link
                else:
                    log(f"{Fore.GREEN}[Page {page_index}]{Style.RESET_ALL} [{index+1}/{cards_length}]  └─> {Fore.RED} [ERROR] Couldn't get link to job item... skipping:{Style.RESET_ALL} {Fore.LIGHTCYAN_EX}{job_company}{Style.RESET_ALL} is hiring a {Fore.YELLOW}{job_title}{Style.RESET_ALL} | {dmy_formatted_date} | {job_location}")
                    continue

                exists_in_db = db.job_url_exists_in_db(link) if check_duplicates else False 
                if exists_in_db:
                    log(f"{Fore.GREEN}[Page {page_index}]{Style.RESET_ALL} [{index+1}/{cards_length}]   └─> Already exists in database with duplicated URL... {Fore.RED}skipping job:{Style.RESET_ALL} {Fore.LIGHTCYAN_EX}{job_company}{Style.RESET_ALL} is hiring a {Fore.YELLOW}{job_title}{Style.RESET_ALL} | {dmy_formatted_date} | {job_location}")
                    continue

                # --- DEEP SCRAPING STEP ---
                full_description = "No extended details parsed."
                try:
                    detail_resp = go_to_static_website(link,headers)
                    #detail_resp = requests.get(link, headers=headers, timeout=30)
                    detail_soup = BeautifulSoup(detail_resp.text, 'html.parser')
                    write_debug_file(f"detail{job_title}_{job_company}.html",detail_soup.prettify())
                    
                    if config_model.is_location_in_detail:
                        job_location = detail_soup.select_one(config_model.job_location).get_text(strip=True) if detail_soup.select_one(config_model.job_location) else ""

                    if config_model.is_date_in_detail and config_model.job_post_date != "":
                        date_selector = detail_soup.select_one(config_model.job_post_date)
                        if date_selector:
                            date_text:str = date_selector.get_text().strip()
                            job_post_date = clean_date_string(date_text,config_model.job_post_date_prefix,config_model.job_post_date_suffix)
                            date_obj = dateparser.parse(job_post_date)
                            dmy_formatted_date = None
                            if date_obj:
                                dmy_formatted_date = date_obj.strftime("%d-%m-%Y")
                            if is_job_too_old(job_post_date,max_days_since_job_posted):
                                log(f"{Fore.GREEN}[Page {page_index}]{Style.RESET_ALL} [{index+1}/{cards_length}]  └─> Job posted over {max_days_since_job_posted} days ago... {Fore.RED}skipping:{Style.RESET_ALL} {Fore.LIGHTCYAN_EX}{job_company}{Style.RESET_ALL} is hiring a {Fore.YELLOW}{job_title}{Style.RESET_ALL} | {dmy_formatted_date} | {job_location}")
                                condition = False
                                config_model.max_page = -2
                                break
                    full_description = ""
                    job_description = detail_soup.select_one(config_model.job_description)
                    if job_description:                    
                        full_description = job_description.get_text()
                except Exception as inner_err:
                    log(f"                  └─> [WARN] Could not dive into details for {link} - {inner_err}")
                write_debug_file(f"description{job_title}_{job_company}.txt",full_description)

                is_duplicated = db.job_exists_in_db(job_title,job_company,job_post_date,max_days_since_job_posted)
                if is_duplicated:
                    log(f"{Fore.GREEN}[Page {page_index}]{Style.RESET_ALL} [{index+1}/{cards_length}]  └─> Already exists in database with same title,studio and posted_date... {Fore.RED}skipping job:{Style.RESET_ALL} {Fore.LIGHTCYAN_EX}{job_company}{Style.RESET_ALL} is hiring a {Fore.YELLOW}{job_title}{Style.RESET_ALL} | {dmy_formatted_date} | {job_location}")
                    continue

                new_job = JobModel(url=link,source_site=config_model.site_name,title=job_title,company=job_company,location=job_location,date_posted=job_post_date,description=full_description)
                jobs.append(new_job)
                log(f"{Fore.GREEN}[Page {page_index}]{Style.RESET_ALL} [{index+1}/{cards_length}]  └─> Deep Crawling Position Detail:{Fore.LIGHTCYAN_EX}{job_company}{Style.RESET_ALL} is hiring a {Fore.YELLOW}{job_title}{Style.RESET_ALL} | {dmy_formatted_date} | {job_location} | description:{full_description[:100]}")
                write_debug_file(f"jobOutput_{job_title}_{job_company}.txt",str(jobs[len(jobs)-1]))
            
            if len(cards) == 0 or config_model.pagination == None:
                break

            page_index+=1
            if config_model.max_page != -1:
                condition = page_index <= config_model.max_page
            else:
                condition = True
        except Exception as e:
            log(f"[WARN] Failed parsing {prepared_url}: {Fore.RED}{e}{Style.RESET_ALL}")
            break
        
    log(f"[FOUND] {config_model.site_name} completed deep-scan for {len(jobs)} positions.")
    return jobs

def is_job_too_old(job_post_date,max_time_period_in_days):
    settings = {"DATE_ORDER":"MDY"}
    date_object = dateparser.parse(job_post_date, settings=settings)
    if date_object:
        date_delta = abs((datetime.now() - date_object))
        if(date_delta.days > max_time_period_in_days):
            return True            
        else:
            return False
    return False

def clean_date_string(post_date_text:str, prefix:str = None, suffix:str = None):
    if post_date_text is None:
        return None
    
    result = post_date_text
    if prefix is not None and suffix is not None:
        start_index = result.find(prefix)
        if start_index != -1:
            start_index = result.find(prefix) + len(prefix)
        else:
            start_index = 0
        end_index = result.rfind(suffix)
        if end_index == -1:
            end_index = len(result)
            
        if start_index <= end_index:
            result = result[start_index:end_index]
        else:
            log(f"Error when parsing date string \"{result}\" - prefix:\"{prefix}\" - suffix:\"{suffix}\" | Prefix and suffix overlap or are out of order")

    result = result.replace("\n","")
    result = result.lower()
    parts = result.split("posted", 1)
    if len(parts) > 1:
        result = parts[1]

    if result:
        date_object = dateparser.parse(result)
        if date_object:
            unified_str = date_object.strftime("%m-%d-%Y")
            return unified_str
    return result


@retry(
    retry=retry_if_exception_type((TimeoutError)),
    wait=wait_exponential(multiplier=30, min=30, max=300),
    stop=stop_after_attempt(3),
    before_sleep=log_retry,
    reraise=True
)
async def go_to_website(page:Page,url:str,wait_until_state:str=None):
    await page.goto(url, wait_until=wait_until_state)

async def block_unnecessary_resources(route):
    url = route.request.url.lower()
    resource_type = route.request.resource_type

    # 1. Block heavy binary assets (Images, Fonts, Audio/Video)
    if resource_type in ["image", "font", "media"]:
        await route.abort()
    # 2. Block telemetry, metric collection scripts, and advertising tags
    elif any(tracker in url for tracker in ["google-analytics", "gtm.js", "sentry", "mixpanel", "datadog"]):
        await route.abort()
    else:
        await route.continue_()

async def __scrape_playwright(  config_model:WebsiteConfig,                                
                                max_days_since_job_posted:int,
                                check_duplicates:bool
                                ):
    log("🚀 Launching headless browser...")
    result = []
    async with async_playwright() as p:
        try:
            # Launch browser with a typical User-Agent to match standard web behavior
            browser = await p.chromium.launch(headless=True,
                                              args=[
                                                "--disable-gpu",  # Server instances don't have a GPU anyway
                                                "--no-sandbox",  # Required for many Linux/Docker containers
                                                "--disable-setuid-sandbox",
                                                "--disable-dev-shm-usage",  # Prevents crashing in small containers
                                                "--js-flags=--max-old-space-size=96",  # CRITICAL: Forces Chromium's JavaScript V8 engine to cap its RAM usage at 96MB
                                                "--disable-extensions",
                                                "--blink-settings=imagesEnabled=false",  # CRITICAL: Do not download or render images
                                            ],)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                #viewport={"width":800, "height":600},
                device_scale_factor=1
            )
            page = await context.new_page()

            # Safe middle ground: block images and fonts first (huge RAM savings, 0% chance of breaking selectors)
            await page.route("**/*",block_unnecessary_resources)
            
            # Navigate to the target page
            url = config_model.starting_url
            log(f"🌐 Navigating to {Fore.MAGENTA}{url}{Style.RESET_ALL}")

            await go_to_website(page,url,"networkidle")

            loop_count = 0
            while_condition = True
            while while_condition:
                loop_count = loop_count+1
                if loop_count >= 50:
                    log(f"{Fore.RED}Infinite loop detected! Bailing out of website:{Fore.CYAN} {config_model.site_name}{Fore.RED} | {Style.RESET_ALL}{Fore.YELLOW}Check the website's pagination settings.{Style.RESET_ALL}")
                    break

                # Give the JavaScript data-feed extra time to populate the job feed list
                log("⏳ Waiting for job cards to render...")
                try:
                    # Replace '.job-card-selector' with the actual container class 
                    # after inspecting the site container (e.g., 'div.job-item', 'article')
                    await page.wait_for_selector(config_model.layer_to_wait_for, timeout=10000)                
                except Exception:
                    log("⚠️ Timeout waiting for specific elements, passing layout directly to parser.")

                await debug.take_playwright_screenshot(page,f"{config_model.site_name}_1_screenshot")
                html_file_name = debug.clean_file_name(f"{config_model.site_name}_page.html")
                debug.write_debug_file(f"{html_file_name}",await page.content())
                await automate_global_clicks(page,config_model.clicks)

                await debug.take_playwright_screenshot(page,f"{config_model.site_name}_2_after_global_clicks_screenshot")

                job_cards_count : int = await page.locator(config_model.job_item).count()
                scraped_jobs = await playwright_parse_html( context,
                                                            page,
                                                            config_model,
                                                            max_days_since_job_posted, 
                                                            job_cards_count,
                                                            url,
                                                            check_duplicates)
                result.extend(scraped_jobs)
                await debug.take_playwright_screenshot(page,f"{config_model.site_name}_3_after_parsing_jobs_screenshot")

                try:
                    if config_model.pagination is not None and config_model.pagination != "":
                        await context.clear_cookies()
                        await context.clear_permissions()

                        log(f"Clicking on next page:{Fore.CYAN}{config_model.pagination}{Style.RESET_ALL}")
                        await page.click(config_model.pagination, timeout=5000)
                    else:
                        while_condition = False
                except TimeoutError:
                    log(f"Reached last page! Moving on to next website")
                    while_condition = False
                except Exception as e:
                    log(f"⚠️ Unknown error when hitting next page! Moving on to next website - {e}")
                    while_condition = False
        except Exception as e:
            log(f"⚠️ Unknown error when loading page! Moving on to next website - {e}")
            while_condition = False

        await page.close()
        await context.close()
        await browser.close()

    return result

async def playwright_parse_html(    context:BrowserContext,
                                    page:Page,
                                    config_model:WebsiteConfig,
                                    max_days_since_job_posted:int,
                                    job_cards_count:int,
                                    url:str,
                                    check_duplicates:bool
                                    ):

    scraped_jobs = []
    log(f"[INFO] Discovered {Fore.GREEN}{job_cards_count}{Style.RESET_ALL} matching job cards on {Fore.MAGENTA}{url}{Style.RESET_ALL}")
    index = 0
    log(f"Locating all items matching the {Fore.LIGHTYELLOW_EX}{config_model.job_item}{Style.RESET_ALL}: {job_cards_count} found")

    for index in range(job_cards_count):
        if config_model.jobs_cap != -1 and index >= config_model.jobs_cap:
            break
        card = page.locator(config_model.job_item).nth(index)

        if card is None:
            continue

        
        if(config_model.click_each_job):
            # Resolve all matching elements currently on the DOM
            try:
                # Scroll into view and click the specific job item link
                await card.scroll_into_view_if_needed()
                await card.click()
                log(f"[{index+1}/{job_cards_count}]  └─> 🖱️ ✅ Clicked: {Fore.GREEN}Job card{Style.RESET_ALL}")
                time.sleep(3.0) # Wait for job details panel to populate
            except Exception as e:
                log(f"[{index+1}/{job_cards_count}]    [Warning] Error on item index {index}: {e}")

        await automate_per_job_click(page,config_model.clicks_per_job_before_parsing)
        parsed_job = await playwright_parse_job_card(   context,
                                                        page,
                                                        card,
                                                        job_cards_count,
                                                        index,
                                                        config_model,
                                                        max_days_since_job_posted,
                                                        check_duplicates
                                                    )
        if parsed_job is not None:
            job_posted_date = parsed_job.date_posted
            title = parsed_job.title
            studio = parsed_job.company
            location = parsed_job.location
            description = parsed_job.description
            if description is None:
                description = "None"
            if job_posted_date is not None:
                if is_job_too_old(job_posted_date,max_days_since_job_posted):                            
                    log(f"[{index+1}/{job_cards_count}]  └─> Job posted over {max_days_since_job_posted} days ago... {Fore.RED}skipping:{Style.RESET_ALL} {Fore.LIGHTCYAN_EX}{studio}{Style.RESET_ALL} is hiring a {Fore.YELLOW}{title}{Style.RESET_ALL} | {job_posted_date} | {location}")
                    break
            scraped_jobs.append(parsed_job)
            log(f"[{index+1}/{job_cards_count}]  └─> Deep Crawling Position Detail:{Fore.LIGHTCYAN_EX}{studio}{Style.RESET_ALL} is hiring a {Fore.YELLOW}{title}{Style.RESET_ALL} | {job_posted_date} | {location} | description:{description[:100]}")
        
        await automate_per_job_click(page,config_model.clicks_per_job_after_parsing)

        index = index+1


    log(f"[FOUND] {Fore.MAGENTA}{url}{Style.RESET_ALL} completed scan for {Fore.GREEN}{job_cards_count}{Style.RESET_ALL} positions.")
    return scraped_jobs

async def playwright_parse_job_card(    context:BrowserContext,
                                        page: Page,
                                        job_card_selector:Locator,
                                        job_cards_count:int,
                                        index:int,
                                        config_model:WebsiteConfig,
                                        max_days_since_job_posted:int,
                                        check_duplicates:bool = True
                                        ):
    detail_page:Page = None
    try:
        title = await job_card_selector.locator(config_model.job_title).inner_text() if await job_card_selector.locator(config_model.job_title).is_visible(timeout=2000) else "Unknown Title"
        studio = await job_card_selector.locator(config_model.job_company).inner_text() if await job_card_selector.locator(config_model.job_company).is_visible(timeout=2000) else "Unknown Studio"        
        location = await job_card_selector.locator(config_model.job_location).inner_text() if await job_card_selector.locator(config_model.job_location).is_visible(timeout=2000) else "Unknown Location"

        job_url = "No Link"
        try:
            # Extract link if available
            link_element = job_card_selector.locator(config_model.job_url)
            job_url = await link_element.evaluate("el => el.href",timeout=3000)
        except TimeoutError:
            link_element = page.locator(config_model.job_url)
            job_url = await link_element.evaluate("el => el.href",timeout=3000)
        except Exception as e:
            job_url = "No Link"
            log(f"[{index+1}/{job_cards_count}] Invalid URL couldn't parse:\"{job_url}\" in {Fore.CYAN}{studio}{Style.RESET_ALL} is hiring a {Fore.YELLOW}{title}{Style.RESET_ALL} | {location} - {e}")

        exists_in_db = db.job_url_exists_in_db(job_url) if check_duplicates else False 
        if exists_in_db:                
            log(f"[{index+1}/{job_cards_count}]  └─> Already exists in database with duplicated URL... {Fore.RED}skipping job:{Style.RESET_ALL} {Fore.LIGHTCYAN_EX}{studio}{Style.RESET_ALL} is hiring a {Fore.YELLOW}{title}{Style.RESET_ALL} | {location}")
            return None

        posted_date = None
        description = None
        if config_model.is_date_in_detail:
            log(f"              -> {Fore.YELLOW}Loading detail page{Style.RESET_ALL}")     
            detail_page = await context.new_page()            
            await go_to_website(detail_page,job_url)
            await debug.take_playwright_screenshot(detail_page,f"{title}_{studio}_detail_screenshot")
            if config_model.job_post_date is not None:                            
                await detail_page.locator(config_model.job_post_date).wait_for(state="visible")
            if config_model.job_description is not None:            
                await detail_page.locator(config_model.job_description).wait_for(state="visible")
            log(f"              -> {Fore.GREEN}Finished loading detail page{Style.RESET_ALL}")
            if config_model.job_post_date is not None:
                posted_date = await detail_page.locator(config_model.job_post_date).inner_text() if await detail_page.locator(config_model.job_post_date).is_visible(timeout=2000) else "Unknown Date"
            if config_model.job_description is not None:
                description = await detail_page.locator(config_model.job_description).inner_text() if await detail_page.locator(config_model.job_description).is_visible(timeout=2000) else None
            await detail_page.close()
        else:
            try:             
                await debug.take_playwright_screenshot(page,f"{title}_{studio}_detail_screenshot")
                post_date_locator = job_card_selector.locator(config_model.job_post_date)
                try:
                    posted_date = await post_date_locator.inner_text(timeout=10000)
                except TimeoutError:
                    post_date_locator = page.locator(config_model.job_post_date)
                    
                try:
                    posted_date = await post_date_locator.inner_text(timeout=10000)
                except TimeoutError:
                    posted_date = "Unknown Date"    
            except Exception as e:
                log(f"Error: couldn't parse a valid date: {e}")

            try:            
                if config_model.job_description is not None:
                    description_locator = job_card_selector.locator(config_model.job_description)
                    try:
                        description = await description_locator.inner_text(timeout=10000)
                    except TimeoutError:
                        description_locator = page.locator(config_model.job_description)

                    try:
                        description = await description_locator.inner_text(timeout=10000)
                    except TimeoutError:
                        description = None

            except Exception as e:
                log(f"Error: couldn't find job description: {e}")

        #Extract posted date if possible
        job_posted_date = ""
        settings = {"DATE_ORDER":"MDY"}
        try:
            posted_date = clean_date_string(posted_date,config_model.job_post_date_prefix,config_model.job_post_date_suffix)
            date_object = dateparser.parse(posted_date,settings=settings)
            job_posted_date = date_object.strftime("%m/%d/%y")
        except Exception as e:
            log(f"[{index+1}/{job_cards_count}] Invalid date couldn't parse:\"{posted_date}\" in {Fore.CYAN}{studio}{Style.RESET_ALL} is hiring a {Fore.YELLOW}{title}{Style.RESET_ALL} | {job_posted_date} | {location} - {e}")
            job_posted_date = ""

        is_duplicated = db.job_exists_in_db(title,studio,job_posted_date,max_days_since_job_posted)
        if is_duplicated:
            log(f"[{index+1}/{job_cards_count}]  └─> Already exists in database... {Fore.RED}skipping job:{Style.RESET_ALL} {Fore.LIGHTCYAN_EX}{studio}{Style.RESET_ALL} is hiring a {Fore.YELLOW}{title}{Style.RESET_ALL} | {location}")
            return None
        parsed_job = JobModel(url=job_url,source_site=config_model.site_name,title=title,company=studio,location=location,date_posted=job_posted_date,description=description)
        """
        parsed_job = {
            "title": title,
            "company": studio,
            "link": job_url,
            "location": location,                
            "date_posted":job_posted_date,                
            "description": description,
        }
        """
        return parsed_job
    except Exception as e:
        log(f"Unknown Error when parsing job card - {e}")        
        if page is not None:
            await debug.take_playwright_screenshot(page,f"{title}_{studio}_error_screenshot")
            log(f"Saving page error screenshot!")
            file_name = debug.clean_file_name(f"{title}_{studio}_error_page.html")
            debug.write_debug_file(f"{file_name}",await page.content())
            log(f"Saving page error html!")
        if detail_page is not None:
            await debug.take_playwright_screenshot(detail_page,f"{title}_{studio}_error_detail_screenshot")
            log(f"Saving detail_page error screenshot!")
            await detail_page.close()
        
        return None    

async def automate_per_job_click(page, clicks_per_job:list[Click]):
    if not clicks_per_job:
        return
    
    try:
        # Execute sub-actions tied to clicking this specific job card
        for sub_action in clicks_per_job:
            await execute_click(page, sub_action)
    except Exception as e:
        log(f"    [Warning] Error on clicking:{e}")

async def automate_global_clicks(page, button_clicks:list[Click]):
    if not button_clicks:
        return
    
    for click_action in button_clicks:
        try:
            await execute_click(page, click_action)
        except Exception:
            break 
  
async def execute_click(page:Page, action:Click):    
    desc = action.description    
    is_optional = action.optional
    target = action.target
    position = action.position
    go_back = action.go_back
    wait_time = action.wait_time
    
    try:
        if go_back:
            await page.go_back(wait_until="networkidle")
        elif target is not None: #locator type
            
            # If optional, give it a short 2-second timeout so it doesn't hang
            locator = page.locator(target)
            timeout = 2000 if is_optional else 10000
            
            # Wait for element visibility
            await locator.first.wait_for(state="visible", timeout=timeout)
            
            if position:
                await locator.first.click(position=position, timeout=timeout)
            else:
                await locator.first.click(timeout=timeout)
        elif position is not None: #position type
            await page.mouse.click(position.x, position.y)

        log(f"              -> 🖱️ ✅ Clicked: {Fore.GREEN}{desc}{Style.RESET_ALL}")
   
        if wait_time is not None:
            await asyncio.sleep(wait_time)

        await asyncio.sleep(1) # Visual/network breathing room
        return True
        
    except Exception as e:
        if is_optional:
            log(f"              -> 🖱️ ❌ Skipped optional click:{Fore.RED} {desc}{Style.RESET_ALL}")
            return False
        else:
            log(f"              {Fore.RED}[Error] Failed critical action '{desc}': {e}{Style.RESET_ALL}")
            raise e
      