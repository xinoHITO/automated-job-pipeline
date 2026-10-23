import os
import pytest

from job_bot.webscraper import clean_date_string, is_job_too_old, add_new_job, scrape_job_site
from job_bot.notion import job_exists_in_notion
from job_bot.filtering import run_hiring_rules
from job_bot.globals import base_dir
from job_bot.webscraping_rules import WebsiteConfig
from job_bot.coverletterwriter import generate_cover_letter
from job_bot.hiring_profile import load_profile

def test_profile_model():
    result = load_profile("test")
    assert result is not None

def test_webscraper_clean_date_string_strips_prefix_and_suffix():
    raw = "On board since Posted 09/15/2026 Click to apply"
    result = clean_date_string(raw, "On board since ", "Click to apply")
    assert result == "09-15-2026"  

def test_webscraper_is_job_too_old_rejects_ancient_posting():
    assert is_job_too_old("01-01-2020", max_time_period_in_days=30) == True

def test_webscraper_is_job_too_old_accepts_recent_posting():
    assert is_job_too_old("10-01-2026", max_time_period_in_days=30) == False

def test_hiring_rules_1():
    test_profile = load_profile("test")
    filter_check = run_hiring_rules(test_profile.hiring_rules,"Gameplay Programmer","Unity gameplay systems","Remote")
    assert filter_check["match_status"] == "MATCH"

def test_hiring_rules_2():
    job_description = None
    path = f"{base_dir}/test/sampleJob.txt"
    with open(path,"r",encoding="UTF-8") as r:
        job_description= r.read()
    test_profile = load_profile("test")
    filter_check = run_hiring_rules(test_profile.hiring_rules,
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

    test_profile = load_profile("test")
    filter_check = run_hiring_rules(test_profile.hiring_rules,
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


requires_notion = pytest.mark.skipif(
    not os.environ.get("NOTION_TOKEN"),
    reason="requires Notion credentials",
)

@requires_notion
def test_notion_check_for_duplicates():
    assert job_exists_in_notion("Senior Software Engineer II Applied AI","Wrapbook","10/14/2026") == True

@pytest.mark.asyncio
async def test_webscraper_scrape_static_job_site():
    sampleWebsite = """
    {
    "site_name": "https://www.workwithindies.com",
    "starting_url": "https://www.workwithindies.com/categories/programming",
    "job_item": ".job-card",
    "jobs_cap": -1,
    "job_url": "",
    "job_title": ".text-block-14",
    "job_company": ".job-card-text-smol",
    "job_description": ".job-description",
    "is_date_in_detail": true,
    "job_post_date":"div.posted:nth-of-type(3)",
    "job_location":".job-card-text.bold:last-child"
  }
    """
    config_data_model = WebsiteConfig.model_validate_json(sampleWebsite)
    found_jobs = await scrape_job_site(config_data_model,5,False)
    assert len(found_jobs) > 0

@pytest.mark.asyncio
async def test_webscraper_scrape_playwright_job_site():
    sample_website = None
    path = f"{base_dir}/test/sample_playwright_website.json"
    with open(path,"r",encoding="UTF-8") as r:
        sample_website= r.read()
    config_data_model = WebsiteConfig.model_validate_json(sample_website)
    found_jobs = await scrape_job_site(config_data_model,1,False)
    assert len(found_jobs) > 0

@pytest.mark.asyncio
async def test_webscraper_scrape_playwright_with_detail_job_site():
    sample_website = None
    path = f"{base_dir}/test/sample_playwright_website_with_detail.json"
    with open(path,"r",encoding="UTF-8") as r:
        sample_website= r.read()
    config_data_model = WebsiteConfig.model_validate_json(sample_website)
    found_jobs = await scrape_job_site(config_data_model,1,False)
    assert len(found_jobs) > 0


requires_gemini = pytest.mark.skipif(
    not os.environ.get("GEMINI_API_KEY"),
    reason="requires GEMINI_API_KEY credentials",
)

@requires_gemini
def test_generate_cover_letter():

    if not os.environ.get('GEMINI_API_KEY'):
        print('Error: GEMINI_API_KEY not set.')
        assert False 

    sample_job_description = None
    test_profile = load_profile("test")

    try:
        with open(f"{base_dir}/test/sampleJob.txt","r",encoding="UTF-8") as r_job_file:
            sample_job_description = r_job_file.read()
    except Exception as e:
        print(f"Error when reading sample txt files:{e}")        
        exit(1)

    if sample_job_description is not None:        
        cover_letter = generate_cover_letter([f"{base_dir}/data/resume.pdf",f"{base_dir}/data/portfolio.pdf"],
                                             sample_job_description,
                                             test_profile.cover_letter_template,
                                             0)
        print(cover_letter)
        assert cover_letter is not None and len(cover_letter) > 0
    