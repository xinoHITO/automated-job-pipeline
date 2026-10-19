import os
from pathlib import Path
from pydantic import BaseModel
from typing import List

from . import globals
from .hiring_rules import HiringRulesModel
from .debug import log

class ProfileModel(BaseModel):
    name:str
    hiring_rules: HiringRulesModel
    cover_letter_template: str
    data_files: List[str]

def load_profile(profile_name:str):
    profiles_path = f"{globals.base_dir}/profiles"
    if not os.path.exists(profiles_path):
        os.makedirs(profiles_path,exist_ok=True)

    if not os.path.exists(profiles_path):
        return None

    hiring_rules_path = f"{profiles_path}/{profile_name}/hiring_rules.json"
    hiring_rules_model: HiringRulesModel = None
    files_array = []
    try:
        with open(hiring_rules_path, "r") as r:
            hiring_rules_model = HiringRulesModel.model_validate_json(r.read())
    except Exception as e:
        log(f"[ERROR] Could read hiring rules JSON file: {e}")
        return None   

    data_files_path = Path(f"{profiles_path}/{profile_name}/data")
    try:
        files_array = [str(file) for file in data_files_path.iterdir() if file.is_file()]
        if files_array is None or len(files_array) == 0:
            raise Exception
    except Exception as e:
        log(f"[ERROR] No files in data folder: {e}")
        return None

    cover_leter_template_path = f"{profiles_path}/{profile_name}/coverLetterTemplate.txt"
    cover_letter_template = None
    try:
        with open(cover_leter_template_path, "r") as r:
            cover_letter_template = r.read()
        if cover_letter_template is None:
            raise Exception
    except Exception as e:
        log(f"[ERROR] Could read cover letter template: {e}")
        return None
    
    my_profile = ProfileModel(name=profile_name,hiring_rules=hiring_rules_model,cover_letter_template=cover_letter_template,data_files=files_array)
    print (files_array)
    return my_profile

if __name__ == "__main__":
    load_profile("test")