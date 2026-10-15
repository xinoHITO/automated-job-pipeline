import os
import pytest

from job_bot.webscraper import clean_date_string, is_job_too_old, add_new_job, scrape_job_site
from job_bot.notion import job_exists_in_notion
from job_bot.JobBot import run_hiring_rules
from job_bot.globals import DEFAULT_HIRING_RULES_PATH
from job_bot.globals import base_dir
from job_bot.webscraping_rules import WebsiteConfig
from job_bot.coverletterwriter import generate_cover_letter
from job_bot.notification import send_discord_notification

def test_notification_send_discord_webhook():
    send_discord_notification()
    assert True

def test_webscraper_clean_date_string_strips_prefix_and_suffix():
    raw = "On board since Posted 09/15/2026 Click to apply"
    result = clean_date_string(raw, "On board since ", "Click to apply")
    assert result == "09-15-2026"  

def test_webscraper_is_job_too_old_rejects_ancient_posting():
    assert is_job_too_old("01-01-2020", max_time_period_in_days=30) == True

def test_webscraper_is_job_too_old_accepts_recent_posting():
    assert is_job_too_old("10-01-2026", max_time_period_in_days=30) == False

def test_hiring_rules_1():
    filter_check = run_hiring_rules(DEFAULT_HIRING_RULES_PATH,"Gameplay Programmer","Unity gameplay systems","Remote")
    assert filter_check["match_status"] == "MATCH"

def test_hiring_rules_2():
    job_description = None
    path = f"{base_dir}/test/sampleJob.txt"
    with open(path,"r",encoding="UTF-8") as r:
        job_description= r.read()
    filter_check = run_hiring_rules(DEFAULT_HIRING_RULES_PATH,
                                    "Principal Game Programmer (f/m/x)",
                                    job_description,
                                    "Remote-Brazil")
    print(f"\nstatus:{filter_check["match_status"]} | score:{filter_check["total_score"]} | reason:{filter_check["reason"]}")
    assert filter_check["match_status"] == "MATCH"

def test_hiring_rules_3():
    job_description = None
    path = f"{base_dir}/test/sampleJob.txt"
    with open(path,"r",encoding="UTF-8") as r:
        job_description= r.read()
    filter_check = run_hiring_rules(DEFAULT_HIRING_RULES_PATH,
                                    "AI-Native Software Engineer (Games)",
                                    "  ",
                                    "Remote (Anywhere)")
    print(f"\nstatus:{filter_check["match_status"]} | score:{filter_check["total_score"]} | reason:{filter_check["reason"]}")
    assert filter_check["match_status"] == "MATCH"

def test_webscraper_check_for_duplicates():
    test_dict ={}
    job1 = {
        "title": " title",
        "company": "company",
        "link": "",
        "location": "job_location",                
        "date_posted":"10/10",                
        "description": "full_description",                
    }
    job2 = {
        "title": "Title ",
        "company": "company",
        "link": "",
        "location": "job_location",                
        "date_posted":"Oct 10th",                
        "description": "full_description",                
    }
    job3 = {
        "title": "  TitlE",
        "company": "  CompanY",
        "link": "",
        "location": "job_location",                
        "date_posted":" October 10th ",                
        "description": "full_description",                
    }
    add_new_job(test_dict,job1)
    add_new_job(test_dict,job2)
    add_new_job(test_dict,job3)
    assert len(test_dict.items()) == 1


def test_notion_check_for_duplicates():
    assert job_exists_in_notion("AI-Native Software Engineer (Games)","Playrix","10/09/2026   (UTC)") == True

@pytest.mark.asyncio
async def test_webscraper_scrape_static_job_site():
    sampleWebsite = """
    {
    "site_name": "https://www.gamesjobsdirect.com",
    "starting_url": "https://www.gamesjobsdirect.com/results?mt=2&ic=False&rl=remote&age=4&exp=4&sper=4&i=16&sort=date",
    "job_item": ".col-sm-9",
    "pagination":"page",
    "jobs_cap": -1,
    "job_url": "a.job-title",
    "job_title": ".job-title",
    "job_company": ".job-company",
    "job_description": ".post-description",
    "is_date_in_detail": false,
    "job_post_date":".job-posteddate",
    "job_location":".job-location"
  }
    """
    config_data_model = WebsiteConfig.model_validate_json(sampleWebsite)
    found_jobs = await scrape_job_site(config_data_model,5)
    assert len(found_jobs) > 0

@pytest.mark.asyncio
async def test_webscraper_scrape_playwright_job_site():
    sample_website = None
    path = f"{base_dir}/test/sample_playwright_website.json"
    with open(path,"r",encoding="UTF-8") as r:
        sample_website= r.read()
    config_data_model = WebsiteConfig.model_validate_json(sample_website)
    found_jobs = await scrape_job_site(config_data_model,2)
    assert len(found_jobs) > 0

@pytest.mark.asyncio
async def test_webscraper_scrape_playwright_with_detail_job_site():
    sample_website = None
    path = f"{base_dir}/test/sample_playwright_website_with_detail.json"
    with open(path,"r",encoding="UTF-8") as r:
        sample_website= r.read()
    config_data_model = WebsiteConfig.model_validate_json(sample_website)
    found_jobs = await scrape_job_site(config_data_model,2)
    assert len(found_jobs) > 0

def test_generate_cover_letter():

    if not os.environ.get('GEMINI_API_KEY'):
        print('Error: GEMINI_API_KEY not set.')
        assert False 

    sample_job_description = None
    sample_cover_letter = None
    COVER_LETTER_TEMPLATE = os.environ.get("COVER_LETTER_TEMPLATE", "config/coverLetterTemplate.example.txt")

    try:
        with open(f"{base_dir}/test/sampleJob.txt","r",encoding="UTF-8") as r_job_file:
            sample_job_description = r_job_file.read()
        with open(f"{base_dir}/{COVER_LETTER_TEMPLATE}","r",encoding="UTF-8") as r_cover_letter:
            sample_cover_letter = r_cover_letter.read()
    except Exception as e:
        print(f"Error when reading sample txt files:{e}")        
        exit(1)

    if sample_job_description is not None:        
        cover_letter = generate_cover_letter([f"{base_dir}/data/resume.pdf",f"{base_dir}/data/portfolio.pdf"],
                                             sample_job_description,
                                             sample_cover_letter,
                                             0)
        print(cover_letter)
        assert cover_letter is not None and len(cover_letter) > 0
    