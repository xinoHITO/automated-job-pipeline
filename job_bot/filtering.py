
import os
import json
from colorama import Fore, Style
import requests
from bs4 import BeautifulSoup
import time

from . import notion as notion
from . import webscraper as webscraper
from . import coverletterwriter as coverletterwriter
from . import globals

from .hiring_rules import HiringRulesModel

from .debug import write_debug_file
from .debug import log

FAST_FILTER_TIMOUT = 2000

# LOCAL OLLAMA PIPELINE: SPLIT ENGINE LAYER

def load_scoring_rules():
    json_path = f"{globals.base_dir}/config/rules.json"

    """
    Loads and compiles criteria parameters dynamically from a local JSON disk structure.
    Auto-generates a pristine template file if it does not exist.
    """
    # Check if the file actually exists in your project folder
    if not os.path.exists(json_path):
        log(f"[WARN] '{json_path}' missing. Creating pristine point rules schema matrix.")
        
        # Hardcoded fallback structure to prevent app crashes
        default_rules = {
            "score_threshold": 65,
            "scoring_matrix": {
                "title_gate": {
                    "points_allocated": 25,
                    "target_keywords": ["gameplay", "systems", "generalist", "programmer", "engineer", "developer"],
                    "instant_reject_keywords": ["artist", "animator", "ui designer", "ux designer", "producer", "community manager", "marketing"],
                    "prompt_instruction": "TITLE FILTER GATE (Max {points_allocated} pts): Match title against [{target_keywords}]. CRITICAL: If primary title covers [{instant_reject_keywords}], set total score to 0 immediately."
                },
                "engine_depth": {
                    "points_allocated": 35,
                    "core_engines": ["unity", "unreal", "c#", "c++"],
                    "advanced_systems": ["behavior tree", "ai", "serialization", "save engine", "multiplayer", "networking", "mirror"],
                    "prompt_instruction": "ENGINE & SYSTEMS DEPTH (Max {points_allocated} pts): Grant major weights for core requirements: [{core_engines}]. Grant points for specialized subsystems: [{advanced_systems}]."
                },
                "career_level": {
                    "points_allocated": 20,
                    "preferred_tiers": ["junior", "mid", "mid-level", "1-5 years"],
                    "senior_tiers": ["senior", "lead", "principal", "5+ years"],
                    "prompt_instruction": "CAREER BAND LEVEL (Max {points_allocated} pts): Look for mid/junior tiers [{preferred_tiers}]. Grant low priority points for senior constraints [{senior_tiers}]."
                },
                "specialty_bonuses": {
                    "points_allocated": 20,
                    "tools_engineering": ["editor tools", "pipeline", "plugins", "workflow extensions"],
                    "technical_art": ["shader", "hlsl", "cel-shading", "rendering", "optimization", "stencil buffer"],
                    "prompt_instruction": "BONUS SPECIALTIES (Max {points_allocated} pts): Cross-reference tech art variables [{technical_art}] and workflow variables [{tools_engineering}]."
                }
            }
        }
        
        # Write the fallback template back to the hard drive automatically
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(default_rules, f, indent=2, ensure_ascii=False)
            log(f"[SYSTEM] Auto-generated fresh fallback configuration at: '{json_path}'")
        except Exception as write_err:
            log(f"[ERROR] Could not auto-create fallback JSON file: {write_err}")
            return default_rules
            
        return default_rules
        
    # If the file exists, safely read and return it as a Python Dictionary
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as decode_err:
        log(f"[CRITICAL] 'rules.json' contains invalid JSON syntax or typos! Check for missing commas or brackets. Error: {decode_err}")
        raise decode_err

def run_quick_filter(model_name, job_item,rules_cfg):
    """
    Step 1: Uses a lightning-fast model to do a strict binary gate check.
    No prose writing allowed—just a clean, rapid assessment.
    """
    url = "http://localhost:11434/api/chat"
    matrix = rules_cfg.get("scoring_matrix", {})
    compiled_rules = []

    # Loop through each section block dynamically (title_gate, engine_depth, etc.)
    for section_key, section_data in matrix.items():
        # Create a copy of the dictionary so we don't destroy your original raw data
        fmt_ctx = section_data.copy()
        
        # Automatically join list values into neat comma strings for the prompt text
        for key, value in fmt_ctx.items():
            if isinstance(value, list):
                fmt_ctx[key] = ", ".join(value)
        
        # UNPACKING LAYER: **fmt_ctx maps keys directly to identically named string tags
        rule_string = section_data["prompt_instruction"].format(**fmt_ctx)
        compiled_rules.append(rule_string)

    # Reconstruct the system instructions window using the unpacked list parameters
    system_instruction = f"""
    You are a precise technical assessment node calculating an objective Match Score (0 to 100) for a Game Programmer application.
    The candidate is exclusively a Software Engineer. They are NOT an artist, animator, or manager.

    SCORING SYSTEM RULES:
    1. {compiled_rules[0]}
    2. {compiled_rules[1]}
    3. {compiled_rules[2]}
    4. {compiled_rules[3]}

    FINAL THRESHOLD VERDICT RULE:
    If calculated total points score >= {rules_cfg['score_threshold']}, your MATCH_STATUS MUST be MATCH. Otherwise, it is NO_MATCH.

    CRITICAL EXECUTION RULE:
    You MUST output your result using this exact 3-line format. Do not write markdown, do not use bullet points, do not add introductory text.
    TOTAL_SCORE: [Type calculated numeric score out of 100]
    MATCH_STATUS: [MATCH or NO_MATCH]
    REASON: [Brief breakdown summary line detailing point allocations]
    """
    
    user_data = f"""
    TARGET JOB LISTING TO EVALUATE:
    ---
    Title: {job_item['title']}
    Location: {job_item['location']}
    Full Text Specification: {job_item['description']}
    ---
    """    

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_data}
        ],
        "stream": False,
        "keep_alive": -1,
        "options": {
            "num_ctx": 16384,     
            "stop": ["\n\n"]   
        }
    }
    
    try:

        start_time = time.time();
        response = requests.post(url, json=payload, timeout=FAST_FILTER_TIMOUT)
        end_time = time.time();
        elapsed_seconds = round(end_time-start_time,2)
       
        if response.status_code != 200:
            return {"match_status": "NO_MATCH", "reason": "Ollama connection error"}
        
        write_debug_file(f"prompt_{job_item['title']}_response.txt",response.text)

        ai_output = response.json().get("message", {}).get("content", "").strip()
        
        status = "NO_MATCH"
        reason = "Failed to parse filter response."
        total_score = "0"
        for line in ai_output.split('\n'):
            if line.startswith("MATCH_STATUS:"):
                status = line.replace("MATCH_STATUS:", "").strip()
            elif line.startswith("REASON:"):
                reason = line.replace("REASON:", "").strip()
            elif line.startswith("TOTAL_SCORE:"):
                total_score = line.replace("TOTAL_SCORE:", "").strip()

        log(Fore.CYAN+f"Request took {elapsed_seconds} seconds"+Style.RESET_ALL )
           
        return {"match_status": status, "reason": reason, "total_score": total_score}
    except Exception as e:
        log(f"[ERROR] Quick filter fail: {e}")
        return {"match_status": "NO_MATCH", "reason": str(e)}

def run_hiring_rules(hiring_rules_model: HiringRulesModel,job_title:str,job_description:str,job_location:str):
    def is_keyword_in_text(text:str, keyword:str):
        if text is None:
            return False

        if keyword is None or len(keyword) == 0:
            return False

        import re

        if re.search(r'\b' + re.escape(keyword) + r'\b', text):
            return True
            
        return False
    
    title_instant_win_keywords = hiring_rules_model.title_instant_win_keywords
    title_target_keywords = hiring_rules_model.title_target_keywords
    title_exclude_keywords = hiring_rules_model.title_exclude_keywords
    scoring_rules = hiring_rules_model.description_scoring_rules
    required_job_score = hiring_rules_model.required_description_score
    locations = hiring_rules_model.locations    
    require_remote = hiring_rules_model.require_remote
    insta_win_locations = hiring_rules_model.insta_win_locations
    
    #if the title contains the exclude words... bail out
    for exclude_keyword in title_exclude_keywords:
       if exclude_keyword.lower() in job_title.lower():
              return {"match_status": "NO MATCH", "reason": f"Job title contains [{exclude_keyword}] exclude keyword", "total_score":0}            

    #if insta-win location is found then we skip the rest of location check
    if not any(insta_win_location.lower().strip() in job_location.lower().strip() for insta_win_location in insta_win_locations):
        #not a insta-win location so we do a normal location check
        #check if it's remote
        is_work_mode_correct = True
        if require_remote:
            is_work_mode_correct = job_location.lower().strip().find("remote") != -1
        else:
            is_work_mode_correct = job_location.lower().strip().find("remote") == -1

        if is_work_mode_correct:
            #in case the location it's just "remote" then that should pass
            if job_location.lower().strip() == "remote":
                locations.append("remote")
            if not any(location.lower().strip() in job_location.lower().strip() for location in locations):
                return {"match_status": "NO MATCH", "reason": f"Job location [{job_location}] is not appropiate", "total_score":0}
        else:
            if require_remote:
                return {"match_status": "NO MATCH", "reason": f"Job location [{job_location}] is not remote", "total_score":0}
            else:
                return {"match_status": "NO MATCH", "reason": f"Job location [{job_location}] is remote and we're looking for on-site", "total_score":0}
       
    #insta-win in title just find one and go
    for target_keyword in title_instant_win_keywords:
        if target_keyword.lower() in job_title.lower():    
            return {"match_status": "MATCH", "reason": f"Found insta-win keyword [{target_keyword}] in job title", "total_score":100}            

    if job_description is not None and len(job_description.strip()) > 0:
        #title_target_keyword - if insta-win title keywords are not in the title then check for regular target title keywords. If they are then check for description keywords
        for title_target_keyword in title_target_keywords:
            if title_target_keyword.lower() in job_title.lower():
                final_score = 0
                matched_keywords = []
                for scoring_rule in scoring_rules:
                    score_delta = 0
                    for keyword in scoring_rule.target_keywords:
                        was_keyword_found = is_keyword_in_text(job_description.lower().replace(".",""),keyword.lower())
                        if was_keyword_found:
                            score_delta += scoring_rule.score_per_match
                            matched_keywords.append(keyword)
                            if score_delta > scoring_rule.score_cap:
                                score_delta = scoring_rule.score_cap
                                break                
                    final_score += score_delta
                if final_score >= required_job_score:
                    return {"match_status": "MATCH", "reason": f"Found title keyword [{title_target_keyword}] and [{", ".join(matched_keywords)}] keywords in description", "total_score":final_score}
                else:
                    return {"match_status": "NO MATCH", "reason": f"Not enough score. Found title keyword [{title_target_keyword}] and [{", ".join(matched_keywords)}] keywords in description", "total_score":final_score}
    else:
        for title_target_keyword in title_target_keywords:
            if title_target_keyword.lower().strip() in job_title.lower().strip():
                return {"match_status": "MATCH", "reason": f"Found title keyword [{title_target_keyword}]. No description provided", "total_score":required_job_score}
    
    return {"match_status": "NO MATCH", "reason": "Couldn't find any target keywords in title nor description", "total_score":0}
