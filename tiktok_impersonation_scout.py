# -*- coding: utf-8 -*-
"""
Created on 2024.9.4

@author: PikasZhuang
"""
################ variables setting
FILENAME_SPLITER = "@" # shuold be banned in TikTok's user ID but allowed in file naming
CONFIG_FILEPATH = "configs/main_config.json"


################ import
import json
from pprint import pprint
import pandas as pd
import time
import numpy as np
import re
from typing import Optional
import os
import base64
from datetime import datetime
from tqdm import tqdm
from glob import glob
import shutil
import argparse
from selenium.webdriver.common.by import By
from http.client import RemoteDisconnected
import requests

import sys
sys.stdout.reconfigure(encoding='utf-8')

from tiktok_scraper import TikTokScraper

################ settings
parser = argparse.ArgumentParser(description='TikTok Impersonation Scout')

parser.add_argument('--test', default="N", help="test mode (Y/N)", choices=['Y', 'N'])
parser.add_argument('--target', required=True, help="Specify which target to scan")
parser.add_argument('--skip-scraper', action='store_true', help="Skip the scraping process")
parser.add_argument('--iteration', type=int, help='Iteration number')
parser.add_argument('--snapshot-dir', type=str, help='Snapshot output directory')
parser.add_argument('--report-path', type=str, help='Direct path to save the Excel report')

args = parser.parse_args()

TEST_MODE = args.test == 'Y'
SKIP_SCRAPER = args.skip_scraper
target = args.target

with open(CONFIG_FILEPATH, "r", encoding="utf-8") as f:
    CONFIG = json.load(f)
    assert CONFIG, "No config is loaded."
    pprint(CONFIG)

print("="*100)
COOKIES_FILEPATH = CONFIG["cookies_filepath"]
with open(COOKIES_FILEPATH, "r") as f:
    cookies = json.load(f)["cookies"]
    
TARGET_INFO_FILEPATH = CONFIG["target_info_filepath"]
with open(TARGET_INFO_FILEPATH, "r", encoding="utf-8") as f:
    TARGET_INFO = json.load(f)
    assert TARGET_INFO, "No target info is loaded."
    import json
    print(json.dumps(TARGET_INFO, indent=2, ensure_ascii=False))

DOWNLOAD_VIDEOS = False
DOWNLOADED_VIDEOS_DIR = CONFIG["downloaded_videos_dir"]
os.makedirs(DOWNLOADED_VIDEOS_DIR, exist_ok=True)

DOWNLOAD_ICONS = False
DOWNLOADED_ICONS_DIR = CONFIG["downloaded_icons_dir"]
os.makedirs(DOWNLOADED_ICONS_DIR, exist_ok=True)

REPORTS_DIR = CONFIG["reports_dir"]
os.makedirs(REPORTS_DIR, exist_ok=True)

MAINTAINER_EMPLOYEEID = CONFIG["MAINTAINER_EMPLOYEEID"]
LOGO_CLASSIFICATION_API_URL = CONFIG["LOGO_CLASSIFICATION_API_URL"]
        
def load_history(history_path: str) -> dict:
    try:
        with open(history_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_history(history_path: str, history: dict):
    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

def contains_language(text: str, language: str) -> bool:
    patterns = {
        "英文": r"[A-Za-z]",
        "中文": r"[\u4e00-\u9fff]",
        "藏文": r"[\u0F00-\u0FFF]",
        "泰文": r"[\u0E00-\u0E7F]",
        "天城文": r"[\u0900-\u097F]",
        "緬甸文": r"[\u1000-\u109F]",
        "希臘文": r"[\u0370-\u03FF]",
        "西里爾文": r"[\u0400-\u04FF]",
        "希伯來文": r"[\u0590-\u05FF]",
        "泰米爾文": r"[\u0B80-\u0BFF]",
        "衣索比亞文": r"[\u1200-\u137F]",
        "韓文": r"[\uAC00-\uD7AF\u1100-\u11FF]",
        "日文": r"[\u3040-\u30FF\u31F0-\u31FF\uFF66-\uFF9D]",
        "阿拉伯文": r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]",
        "越南文": r"[ăâêôơưđĂÂÊÔƠƯĐáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ₫]",
    }

    pattern = patterns.get(language)
    if not pattern:
        print(f"[contains_language] Unsupported Language: {language}")
        return False
    else:
        return bool(re.search(pattern, text))
    
def get_new_rows_from_hashtag_search_results(hashtag_search_results: list, download_videos=False, download_icon=False) -> pd.DataFrame:
    global DOWNLOADED_VIDEOS_DIR, DOWNLOADED_ICONS_DIR, FILENAME_SPLITER, video_url_history, scraper
    global keywords4risk_estimation, general_keywords2ignore, language2ignore, target, ocr_history, asr_history
    new_rows = []
    for hashtag_result in tqdm(hashtag_search_results, desc="Processing search results"):
        try:
            video_url = hashtag_result["video"]["share_link"]
            if video_url in video_url_history or video_url == "":
                continue
            video_url_history.add(video_url)
            
            video_desc = hashtag_result["video"]["desc"]
            if not any(all(kw.lower() in video_desc.lower() for kw in kws) for kws in keywords4risk_estimation):
                continue
            elif any(all(kw.lower() in video_desc.lower() for kw in kws) for kws in general_keywords2ignore):
                continue
            elif any(contains_language(video_desc, language) for language in language2ignore):
                continue

            user_id = hashtag_result["author"]["id"]
            video_id = hashtag_result["video"]["id"]
            new_rows.append({
                            "target": target, 
                            # "matched_keywords": {kw for kw in keywords if kw in video_desc}, 
                            "user_id": user_id, 
                            "user_nickname": hashtag_result["author"]["nickname"],
                            "user_signature": hashtag_result["author"]["signature"],
                            "video_id": video_id,
                            "video_created_time": hashtag_result["video"]["create_time"],
                            "video_url": video_url, 
                            "video_desc": video_desc
                            })

            video_filename = f"{user_id}{FILENAME_SPLITER}{video_id}"
            if download_videos and (video_filename not in ocr_history or video_filename not in asr_history):
                headers = {'cookie': scraper.get_tiktok_cookies_formatted()}
                if not TikTokScraper.save_media(hashtag_result["video"]["download_url"],
                                                os.path.join(DOWNLOADED_VIDEOS_DIR, video_filename + ".mp4"),
                                                headers=headers):
                    print(f"Failed to download video: {video_url = }")
                # else:
                    # print(f"Downloaded video: {video_url}")
            
            downloaded_icon_path = os.path.join(DOWNLOADED_ICONS_DIR, f"{user_id}.png")
            if download_icon and not os.path.exists(downloaded_icon_path):
                headers = {'cookie': scraper.get_tiktok_cookies_formatted()}
                icon_img_url = hashtag_result["author"]["icon_img_url_L"] or hashtag_result["author"]["icon_img_url_M"] or hashtag_result["author"]["icon_img_url_S"]
                if icon_img_url and not TikTokScraper.save_media(icon_img_url, downloaded_icon_path, headers=headers):
                    print(f"Failed to download icon: {icon_img_url = }")
                    
        except KeyError as ke:
            print(f"KeyError: {ke}\n{hashtag_result}\n---------")
            continue

        except Exception as e:
            print(f"Exception: {e}")
            continue

    return pd.DataFrame(new_rows)

def get_new_rows_from_video_search_results(video_search_results: list, download_videos=False, download_icon=False) -> pd.DataFrame:
    return get_new_rows_from_hashtag_search_results(video_search_results, download_videos=download_videos, download_icon=download_icon)

def logo_classify(image_path: str):
    global LOGO_CLASSIFICATION_API_URL
    try:
        files = {"file": open(image_path, "rb")}
        response = requests.post(LOGO_CLASSIFICATION_API_URL, files=files)
        response.raise_for_status()
        result = response.json()["recognition_result"]
        return result["pred_class_name"].split('#')[0] if result["class_prob"] > 0.999999 else ''
        
    except requests.exceptions.HTTPError as e:
        print(f"[logo_classify] {e.response.status_code = }")
        return
        
    except Exception as e:
        print(f"[logo_classify] {e}")
        return
        
def get_new_rows_from_profile_info(profile_info: dict, download_videos=False, download_icon=False) -> pd.DataFrame:
    global DOWNLOADED_VIDEOS_DIR, DOWNLOADED_ICONS_DIR, FILENAME_SPLITER, video_url_history, scraper
    global keywords4risk_estimation, general_keywords2ignore, language2ignore, target, ocr_history, asr_history
    
    user_id = profile_info["unique_id"]
    if download_icon:
        if not TikTokScraper.save_media(profile_info["icon_img_url"], os.path.join(DOWNLOADED_ICONS_DIR, f"{user_id}.png")):
            print(f"Failed to download icon: {profile_info['icon_img_url']}")

    new_rows = []
    for video in tqdm(profile_info["videos"], desc=f"Scraping {user_id}'s videos"):
        try:
            video_url = video["share_link"]
            if video_url in video_url_history:
                continue
            video_url_history.add(video_url)

            video_id = video["id"]
            video_desc = video["desc"]

            if not any(all(kw.lower() in video_desc.lower() for kw in kws) for kws in keywords4risk_estimation):
                continue
            elif any(all(kw.lower() in video_desc.lower() for kw in kws) for kws in general_keywords2ignore):
                continue
            elif any(contains_language(video_desc, language) for language in language2ignore):
                continue
                
            new_rows.append({
                                "target": target, 
                                # "matched_keywords": {kw for kw in keywords if kw in video_desc}, 
                                "user_id": user_id, 
                                "user_nickname": profile_info["nickname"],
                                "user_signature": profile_info["signature"],
                                "video_id": video_id, 
                                "video_created_time": video["create_time"],
                                "video_url": video_url, 
                                "video_desc": video_desc
                                })
            
            filename = f"{user_id}{FILENAME_SPLITER}{video_id}"
            if download_videos and (filename not in ocr_history or filename not in asr_history):
                headers = {'cookie': scraper.get_tiktok_cookies_formatted()}
                if not TikTokScraper.save_media(video["download_url"],
                                                os.path.join(DOWNLOADED_VIDEOS_DIR, filename + ".mp4"),
                                                headers=headers):
                    print(f"Failed to download video: {video_url}")
                    print(f"{video = }")
                # else:
                    # print(f"Downloaded video: {video_url}")

        except KeyError as ke:
            print(f"KeyError: {ke}\n{video}\n---------")
            continue

        except Exception as e:
            print(f"Exception: {e}")
            break
    return pd.DataFrame(new_rows)

def time_convertion_string(s: int) -> str:
    if s < 0:
        return '0 sec'

    units = {'yr': 31536000, 'd': 86400, 'hr': 3600, 'min': 60, 'sec': 1}

    result = list()
    for unit, value in units.items():
        if s >= value:
            result.append(f'{s // value:3.0f} {unit}')
            s %= value

    return ' '.join(result)

if not SKIP_SCRAPER:
    if __name__ == "__main__":
    ###initializes
        start_time = time.time()
        today = datetime.today().strftime("%Y%m%d")
        
        snapshot_dir = args.snapshot_dir

        report_filename = f"report{args.iteration}.xlsx"
        report_filepath = os.path.join(args.snapshot_dir, "reports", report_filename)
        
        scraper = TikTokScraper()
        ocr_history = {}
        asr_history = {}

        max_report_len = 0
        for retry_iter in range(2):
            try:
                scraper.activate_webdriver(vm_mode=True, user_agent=CONFIG["user_agent"])
                report = pd.DataFrame(columns=["target", "matched_keywords", 
                                                "user_id", "user_nickname", "user_signature", 
                                                "video_id", "video_created_time", "video_url", "video_desc",
                                                "video_OCR", "video_ASR", "detected_logo_in_profile_icon", "risk_level"])
                
                ### load cookies
                scraper.navigate_to("https://www.tiktok.com/")
                for cookie in cookies:
                    scraper.driver.add_cookie({
                                                'name': cookie['name'],
                                                'value': cookie['value'],
                                                'domain': cookie['domain'],
                                                'path': cookie['path'],
                                                'secure': cookie.get('secure', False),
                                                'httpOnly': cookie.get('httpOnly', False)
                                                })
                scraper.driver.refresh()
                time.sleep(3)
                print("start.png saved.")
                
                ### scraping tiktok
                if target not in TARGET_INFO:
                    raise ValueError(f"Target '{target}' not found in target_info config.")

                keywords4risk_estimation = TARGET_INFO[target]["keywords4risk_estimation"]
                general_keywords2ignore = TARGET_INFO[target]["general_keywords2ignore"]
                language2ignore = TARGET_INFO[target].get("language2ignore") or TARGET_INFO[target].get("languages2ignore", [])
                keywords2search = set(' '.join(kw_lst) for kw_lst in TARGET_INFO[target]["keywords2search"])
                print(f"{keywords2search = }")
                video_url_history = set()
                for keyword in keywords2search:

                    ### hashatg search result
                    print(f"Searching for hashtag by \"{keyword.replace(' ','')}\" in TikTok...")
                    hashtag_search_results = scraper.get_hashtag_search_results(keyword.replace(' ',''))
                    if not hashtag_search_results:
                        print("No hashtag results. retrying...")
                        hashtag_search_results = scraper.get_hashtag_search_results(keyword)
                    new_rows_h = get_new_rows_from_hashtag_search_results(hashtag_search_results, download_videos=DOWNLOAD_VIDEOS, download_icon=DOWNLOAD_ICONS)

                    ### video search result
                    print(f"Searching for video by \"{keyword}\" in TikTok...")
                    video_search_results = scraper.get_video_search_results(keyword)
                    if not video_search_results:
                        print("No video results. retrying...")
                        video_search_results = scraper.get_video_search_results(keyword)
                    new_rows_v = get_new_rows_from_video_search_results(video_search_results, download_videos=DOWNLOAD_VIDEOS, download_icon=DOWNLOAD_ICONS)

                    report = pd.concat([report, new_rows_h, new_rows_v], ignore_index=True)
                    
                    if TEST_MODE: break
                    
                    ### user search result
                    print(f"Searching for user by \"{keyword}\" in TikTok...")
                    user_search_results = scraper.get_user_search_results(keyword)
                    for user_info in user_search_results:
                        user_desc = user_info["nickname"]+':'+user_info["signature"]
                        if not any(all(kw.lower() in user_desc.lower() for kw in kws) for kws in keywords4risk_estimation):
                            continue
                        user_id = user_info["unique_id"]
                        profile_url = "https://www.tiktok.com/@"+user_id
                        try:
                            profile_info = scraper.get_profile_info(profile_url)
                        except (ConnectionResetError, ConnectionError, RemoteDisconnected) as cre:
                            print(f"Failed to get profile info due to {cre} ({profile_url = })\nretry after 10 seconds...")
                            time.sleep(10)
                            profile_info = scraper.get_profile_info(profile_url)
                        if not profile_info.get("videos"):
                            print(f"{user_id} has no video.")
                            #print(f"{profile_info = }")
                            continue
                        new_rows_p = get_new_rows_from_profile_info(profile_info, download_videos=DOWNLOAD_VIDEOS, download_icon=DOWNLOAD_ICONS)
                        report = pd.concat([report, new_rows_p], ignore_index=True)
                if TEST_MODE:
                    break
                break
                
            except Exception as e:
                print(type(e).__name__, ':', str(e))
                with open("err_html.html", 'w', encoding="utf-8") as f:
                    f.write(scraper.driver.page_source)
                    
            finally:
                if 'report' not in locals():
                    report = pd.DataFrame(columns=["target", "matched_keywords", 
                                                "user_id", "user_nickname", "user_signature", 
                                                "video_id", "video_created_time", "video_url", "video_desc",
                                                "video_OCR", "video_ASR", "detected_logo_in_profile_icon", "risk_level"])
                
                report["video_id"] = report["video_id"].astype(str)
                report["user_id"] = report["user_id"].astype(str)
                report["video_created_time"] = pd.to_datetime(report["video_created_time"], unit='s', errors='coerce')
                report["video_created_time"] = report["video_created_time"].dt.strftime("%Y%m%d %H:%M")

                os.makedirs(os.path.dirname(report_filepath), exist_ok=True)
                print(f"📁 Saving report to: {report_filepath}")
                report.to_excel(report_filepath, index=False)
                scraper.close_webdriver()
                print(f"⏱️ Total time: {time.time() - start_time:.2f} sec")

  
    

else:
    print("⚠️ Scraper skipped by --skip-scraper flag.")

    report = None

    # Ensure report is defined
    if 'report' in locals() and isinstance(report, pd.DataFrame) and not report.empty:
        try:
            report['risk_level'] = 0
            report['matched_keywords'] = [set() for _ in range(len(report))]
            for idx, row in report.iterrows():
                keywords4risk_estimation = TARGET_INFO[row["target"]]["keywords4risk_estimation"]
                col2search = [row.get('video_desc'), row.get('user_nickname'), row.get('user_signature')]
                for col_val in col2search:
                    if pd.isna(col_val):
                        continue
                    find_matched_keywords = False
                    for kws in keywords4risk_estimation:
                        if all(kw.lower() in col_val.lower() for kw in kws):
                            find_matched_keywords = True
                            report.at[idx, 'matched_keywords'].add(" + ".join(kws))
                    report.at[idx, 'risk_level'] += int(find_matched_keywords)
                report.at[idx, 'risk_level'] += int(pd.notna(row.get('detected_logo_in_profile_icon')))
            
            print(f"📁 Saving report to: {report_filepath}")
            report.to_excel(report_filepath, index=False)

            notify_text = f"target2detect postprocess completed in {time_convertion_string(time.time() - start_time)}."
            print(notify_text)
        except Exception as e:
            print("⚠️ Error during report post-processing:", type(e).__name__, str(e))
    else:
        print("⚠️ No valid report to post-process.")