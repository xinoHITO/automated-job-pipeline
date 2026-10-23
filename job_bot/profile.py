import os
from pathlib import Path
from pydantic import BaseModel
from typing import List

from . import globals
from .hiring_rules import HiringRulesModel
from .debug import log

class HiringProfileModel(BaseModel):
    name:str
    hiring_rules: HiringRulesModel
    cover_letter_template: str
    data_files: List[str]

    def get_profile_folder_path(self):
        return f"{PROFILES_PATH}/{self.name}"

PROFILES_PATH = f"{globals.base_dir}/profiles"

def load_profile(profile_name:str):
    if not os.path.exists(PROFILES_PATH):
        os.makedirs(PROFILES_PATH,exist_ok=True)

    if not os.path.exists(PROFILES_PATH):
        return None

    hiring_rules_path = f"{PROFILES_PATH}/{profile_name}/hiring_rules.json"
    hiring_rules_model: HiringRulesModel = None
    files_array = []
    try:
        with open(hiring_rules_path, "r") as r:
            hiring_rules_model = HiringRulesModel.model_validate_json(r.read())
    except Exception as e:
        log(f"[ERROR] Could read hiring rules JSON file: {e}")
        return None   

    data_files_path = Path(f"{PROFILES_PATH}/{profile_name}/data")
    try:
        files_array = [str(file) for file in data_files_path.iterdir() if file.is_file()]
        if files_array is None or len(files_array) == 0:
            raise Exception
    except Exception as e:
        log(f"[ERROR] No files in data folder: {e}")
        return None

    cover_leter_template_path = f"{PROFILES_PATH}/{profile_name}/coverLetterTemplate.txt"
    cover_letter_template = None
    try:
        with open(cover_leter_template_path,"r",encoding="UTF-8") as r:
            cover_letter_template = r.read()
        if cover_letter_template is None:
            raise Exception
    except Exception as e:
        log(f"[ERROR] Could read cover letter template: {e}")
        return None
    
    my_profile = HiringProfileModel(name=profile_name,hiring_rules=hiring_rules_model,cover_letter_template=cover_letter_template,data_files=files_array)
    return my_profile
