from . import globals
from playwright.sync_api import Page
import os
import shutil
from pathlib import Path

OUTPUT_FOLDER_PATH = f"{globals.base_dir}/output"
def log(message, reset=False):
    print(message)

    if not os.path.exists(OUTPUT_FOLDER_PATH):
        os.makedirs(OUTPUT_FOLDER_PATH,exist_ok=True)

    mode = "w" if reset else "a"

    with open(f"{OUTPUT_FOLDER_PATH}/job_bot.log", mode, encoding="UTF-8") as f:
        f.write(message + "\n")

def clean_output_folder():
    if not os.path.exists(OUTPUT_FOLDER_PATH):
        os.makedirs(OUTPUT_FOLDER_PATH,exist_ok=True)

    folder = Path(OUTPUT_FOLDER_PATH)
    for item in folder.iterdir():
        if item.is_file() or item.is_symlink():
            item.unlink()  # Deletes the file or symbolic link
        elif item.is_dir():
            shutil.rmtree(item)  # Deletes the subfolder and its contents

    os.makedirs(OUTPUT_FOLDER_PATH,exist_ok=True)

def write_debug_file(file_name,content, debug=False):
    if not os.path.exists(OUTPUT_FOLDER_PATH):
        os.makedirs(OUTPUT_FOLDER_PATH,exist_ok=True)
    
    try:
        cleaned_file_name = clean_file_name(file_name)
        with open(f"{OUTPUT_FOLDER_PATH}/{cleaned_file_name}","w",encoding="UTF-8") as w:
            w.write(content)
        if debug:
            print(f" -> Successfully wrote '{cleaned_file_name}'")
    except Exception as e:
        print(f"[WARN] Could not write debug text files: {e}")

async def take_playwright_screenshot(page:Page, screenshot_file_name:str, image_extension:str =".jpg"):
    if not os.path.exists(OUTPUT_FOLDER_PATH):
        os.makedirs(OUTPUT_FOLDER_PATH,exist_ok=True)
        
    file_name = clean_file_name(f"{screenshot_file_name}{image_extension}")
    screenshot_path = f"{OUTPUT_FOLDER_PATH}/{file_name}"
    await page.screenshot(path=screenshot_path)

def clean_file_name(file_name):
    cleaned_file_name = file_name.replace("/","_")
    cleaned_file_name = cleaned_file_name.replace(":","_")
    cleaned_file_name = cleaned_file_name.replace("/","_")
    cleaned_file_name = cleaned_file_name.replace("\n","_")
    cleaned_file_name = cleaned_file_name.replace("\t","_")
    cleaned_file_name = cleaned_file_name.replace("\\","_")
    cleaned_file_name = cleaned_file_name.replace("(","_")
    cleaned_file_name = cleaned_file_name.replace(")","_")
    cleaned_file_name = cleaned_file_name.replace("|","_")
    cleaned_file_name = cleaned_file_name.replace("*","_")
    cleaned_file_name = cleaned_file_name.replace(" ","_")
    return cleaned_file_name