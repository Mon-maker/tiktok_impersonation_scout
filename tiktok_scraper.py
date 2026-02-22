# -*- coding: utf-8 -*-
"""
Created on Fri Jan  3 14:25:52 2025

@author: PikasZhuang
"""

import os
import re
import time
import json
import base64
import requests
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from web_scraper import WebScraper
from urllib.parse import quote
import cv2
import numpy as np
from functools import wraps

class TikTokScraper(WebScraper):

    def __init__(self, wait_time=3):
        super().__init__()
        self.BASE_URL = "https://www.tiktok.com/"
        self.WAIT_TIME = wait_time
    
    def get_tiktok_cookies_formatted(self) -> str:
        """
        Get TikTok cookies formatted as a single string.
        
        Returns:
            Formatted cookie string in the format:
            'msToken=value; ttwid=value; ...'
        """
        if not self.driver.current_url.startswith(self.BASE_URL):
            self.navigate_to(self.BASE_URL)
            time.sleep(self.WAIT_TIME)
        
        cookies = self.driver.get_cookies()
        return "; ".join(f"{cookie['name']}={cookie['value']}" for cookie in cookies)
    
    @staticmethod
    def save_media(url: str, file_path: str, headers=None) -> bool:
        """
        Download and save media from a URL.
        
        Args:
            url: URL of the media to download
            file_path: Path where to save the media
            headers: Optional request headers
            
        Returns:
            bool: True if successful, False otherwise
        """
        headers = headers or {}
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "wb") as file:
                file.write(response.content)
            return True
        except Exception as e:
            print(f"Failed to save media: {e}")
            return False
    
    @staticmethod
    def save_json(to_save, file_path: str):
        """
        Save data as JSON file.
        
        Args:
            to_save: Data to save
            file_path: Path where to save the JSON file
        """
        assert file_path.endswith(".json")
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(to_save, f, ensure_ascii=False, indent=4)
    
    def _find_api_urls_and_headers_from_log(self, url_pattern='.*'):
        """
        Helper function to extract API URLs and headers from the browser log.
        
        Args:
            url_pattern: Regex pattern to match URLs. Defaults to '.*' to match any URL.
            
        Returns:
            tuple: (list of matching URLs, dict of headers from the last matching request)
        """
        logs = self.driver.get_log('performance')
        api_urls = []
        headers = {}
        
        for entry in logs:
            try:
                log = json.loads(entry['message'])
                message = log['message']['params']
                if 'request' in message:
                    request = message['request']
                    url = request.get('url', '')
                    if re.match(url_pattern, url):
                        headers = request.get('headers', {})
                        api_urls.append(url)
            except:
                continue
        
        return api_urls, headers
    
    @staticmethod
    def _pad_with_transparent_bg(inner_circle, outer_circle_shape):
        """Make inner_circle's shape as same as outer_circle by filling transparent pixels"""
        padded = np.zeros(outer_circle_shape, dtype=np.uint8)
        center = (outer_circle_shape[1] // 2, outer_circle_shape[0] // 2)
        h, w = inner_circle.shape[:2]
        x, y = center[0] - w // 2, center[1] - h // 2
        padded[y:y+h, x:x+w] = inner_circle
        return padded
    
    @staticmethod
    def _compute_boundary_similarity(inner_circle, outer_circle):
        inner_circle_height, inner_circle_width = inner_circle.shape[:2]
        radius = min(inner_circle_height, inner_circle_width) // 2 + 1

        ### enlarge the inner_circle to 102%
        inner_circle = cv2.resize(inner_circle, 
                                  (int(inner_circle_width * 1.02), int(inner_circle_height * 1.02)), #new size
                                  interpolation=cv2.INTER_LINEAR)

        inner_circle = TikTokScraper._pad_with_transparent_bg(inner_circle, outer_circle.shape)
        boundary_mask = np.zeros(outer_circle.shape, dtype=np.uint8) 
        center = (outer_circle.shape[1] // 2, outer_circle.shape[0] // 2)
        cv2.circle(boundary_mask, center, radius, 255, 1)

        inner_circle_boundary = cv2.bitwise_and(inner_circle, inner_circle, mask=boundary_mask)
        outer_circle_boundary = cv2.bitwise_and(outer_circle, outer_circle, mask=boundary_mask)
        diff = np.abs(inner_circle_boundary.astype(np.float32) - outer_circle_boundary.astype(np.float32))
        return np.mean(diff)
    
    @staticmethod
    def rotation_match(inner_circle_img_path: str, outer_circle_img_path: str, angle_step=1):
        ### change input imgs to gray scale
        inner_circle = cv2.imread(inner_circle_img_path, cv2.IMREAD_UNCHANGED)
        outer_circle = cv2.imread(outer_circle_img_path, cv2.IMREAD_UNCHANGED) 
        inner_circle = cv2.cvtColor(inner_circle, cv2.COLOR_BGR2GRAY) if len(inner_circle.shape) == 3 else inner_circle
        outer_circle = cv2.cvtColor(outer_circle, cv2.COLOR_BGR2GRAY) if len(outer_circle.shape) == 3 else outer_circle
        
        best_angle = 0
        min_diff = 1
        inner_circle_height, inner_circle_width = inner_circle.shape[:2]
        inner_circle_center = (inner_circle_width // 2, inner_circle_height // 2)
        for angle in range(0, 361, angle_step):
            M = cv2.getRotationMatrix2D(inner_circle_center, angle, 1.0)
            rotated_inner_circle = cv2.warpAffine(inner_circle, M, (inner_circle_width, inner_circle_height))
            diff = TikTokScraper._compute_boundary_similarity(rotated_inner_circle, outer_circle)
            if diff < min_diff:
                min_diff = diff
                best_angle = angle
        
        return best_angle
        
    def _remove_blockers(self) -> int:
        """
        Helper function to remove overlays that block interaction.
        
        Returns:
            int: Number of blocker elements that were removed
        """
        closes_xpaths = [
            '//span[@data-e2e="launch-popup-close"]',
            '//button[@class="tux-base-dialog__close-button"]',
            '//div[@role="button"][@aria-label="關閉"]',
            '//div[contains(@class, "DivGuestModeContainer")]',
            "//div[text()='以訪客身分繼續']",
        ]
        
        removed_count = 0
        for xpath in closes_xpaths:
            for close in self.find_elements(By.XPATH, xpath):
                try:
                    close.click()
                    removed_count += 1
                except Exception as e:
                    try:
                        self.driver.execute_script("arguments[0].click();", close)
                        removed_count += 1
                    except Exception as e:
                        print(f"Failed to remove blocker: {xpath = }")
        
        captcha_imgs = self.find_elements(By.XPATH, "//img[@alt='Captcha']")
        js_script2download_blob_img = """
                                        let img = arguments[0];
                                        let canvas = document.createElement('canvas');
                                        let ctx = canvas.getContext('2d');
                                        canvas.width = img.naturalWidth;
                                        canvas.height = img.naturalHeight;
                                        ctx.drawImage(img, 0, 0);
                                        return canvas.toDataURL('image/png').split(',')[1];  // 取得 base64 資料
                                    """
        if len(captcha_imgs) == 2:
            ### download the outer captcha img
            base64_data = self.driver.execute_script(js_script2download_blob_img, captcha_imgs[0])
            image_data = base64.b64decode(base64_data)
            outer_circle_img_path = "temp_validation_pic_out.png"
            with open(outer_circle_img_path, "wb") as f:
                f.write(image_data)
            assert os.path.exists(outer_circle_img_path)

            ### download the inner captcha img
            base64_data = self.driver.execute_script(js_script2download_blob_img, captcha_imgs[1])
            image_data = base64.b64decode(base64_data)
            inner_circle_img_path = "temp_validation_pic_in.png"
            with open(inner_circle_img_path, "wb") as f:
                f.write(image_data)
            assert os.path.exists(inner_circle_img_path)

            ###calculate the validation angle
            validation_angle = TikTokScraper.rotation_match(inner_circle_img_path, outer_circle_img_path)
            print(f"{validation_angle = }")

            # Clean up temp CAPTCHA images
            try:
                os.remove(outer_circle_img_path)
                os.remove(inner_circle_img_path)
            except Exception as e:
                print(f"Failed to delete temp CAPTCHA images: {e}")

            sliders = self.find_elements(By.XPATH, "//*[@draggable='true']")
            slider_tracks = self.find_elements(By.XPATH, "//*[@draggable='true']/parent::div")
            
            if sliders and slider_tracks:
                slider = sliders[0]
                slider_track = slider_tracks[0]
                slider_width = slider.size['width']
                track_width = slider_track.size['width']
                max_offset_px = track_width - slider_width  # the maximum distance the slider can move
                # print(f"最大滑動距離: {max_offset_px} 像素")

                action = ActionChains(self.driver)
                action.click_and_hold(slider)

                ### simulate human-like movement
                current_pos = 0
                move_distance = int((360-validation_angle) / 360 * max_offset_px)
                while current_pos < move_distance:
                    step = min(10, move_distance - current_pos)  # move at most 10px at a time
                    action.move_by_offset(step, 0)
                    current_pos += step
                    time.sleep(0.05) 
                action.release().perform()
                time.sleep(1) # wait for validation
                sliders = self.find_elements(By.XPATH, "//*[@draggable='true']")
                slider_tracks = self.find_elements(By.XPATH, "//*[@draggable='true']/parent::div")
                assert len(sliders) == 0 and len(slider_tracks) == 0, "Either slider_tracks nor slider is still displayed!"
                removed_count += 1
            else:
                raise Exception(f"Couldn't find slider or slider! ({len(sliders) = }, {len(slider_tracks) = })")
                      
        elif captcha_imgs:
            for i, captcha_img in enumerate(captcha_imgs):
                base64_data = self.driver.execute_script(js_script2download_blob_img, captcha_img)
                image_data = base64.b64decode(base64_data)
                with open(f"Captcha404_{i}.png", "wb") as f:
                    f.write(image_data)
                    
            sliders = self.find_elements(By.XPATH, "//*[@draggable='true']")
            slider_tracks = self.find_elements(By.XPATH, "//*[@draggable='true']/parent::div")
            if sliders and slider_tracks:
                slider = sliders[0]
                slider_track = slider_tracks[0]
                slider_width = slider.size['width']
                track_width = slider_track.size['width']
                max_offset_px = track_width - slider_width  # the maximum distance the slider can move
                print(f"最大滑動距離: {max_offset_px} 像素")
            else:
                print(f"Couldn't find slider or slider! ({len(sliders) = }, {len(slider_tracks) = })")
                
            raise Exception(f"{len(captcha_imgs) = } but not 2")
        
        if removed_count:
            print(f"{removed_count} blockers were removed.")
        # else:
        #     print("No blockers detected")

        return removed_count

    @staticmethod
    def remove_blockers_before_and_after(func): #decorator
        @wraps(func)
        def wrapper(*args, **kwargs):
            self = args[0]
            self._remove_blockers()
            result = func(*args, **kwargs)
            self._remove_blockers()
            return result
        return wrapper

    @remove_blockers_before_and_after    
    def get_profile_info(self, profile_url: str) -> dict:
        """
        Get TikTok user's profile information and video list.
        
        Args:
            profile_url: URL of the TikTok profile to scrape
            
        Returns:
            dict: Profile information including user details and videos
        """
        self.navigate_to(profile_url)
        self.wait_by_xpath('//div[@id="app"]')
        self.scroll_down(10)
        
        urls, headers = self._find_api_urls_and_headers_from_log(url_pattern="^https://www.tiktok.com/api/post/item_list/")
        headers["cookie"] = self.get_tiktok_cookies_formatted()
        
        profile = {
            "id": "", "nickname": "", "signature": "", "unique_id": "",
            "icon_img_url": "", "author_stats": {}, "videos": []
        }
        
        for i, url in enumerate(urls):
            response = requests.get(url=url, headers=headers)
            if not hasattr(response, "text") or not response.text:
                continue
                
            response_json = json.loads(response.text)
            item_list = response_json.get("itemList", [])
            if not item_list:
                continue
            
            # Get author info from first item only
            if i == 0:
                author = item_list[0]["author"]
                profile.update({
                                "id": author["id"],
                                "nickname": author["nickname"],
                                "signature": author["signature"],
                                "unique_id": author["uniqueId"],
                                "icon_img_url": author.get("avatarLarger", ""),
                                "author_stats": item_list[0]["authorStats"]
                                })
            
            # Add videos from all items
            profile["videos"] += [{
                                    "id": item["id"],
                                    "desc": item["desc"],
                                    "create_time": item["createTime"],
                                    "share_link": f"{self.BASE_URL}@{profile['unique_id']}/video/{item['id']}",
                                    "cover_img_url": item["video"].get("cover", ""),
                                    "download_url": item["video"].get("downloadAddr") or item["video"].get("playAddr", "")
                                    } for item in item_list] 
        return profile

    @remove_blockers_before_and_after
    def get_post_info(self, post_url: str) -> dict:
        """
        Get TikTok post information.
        
        Args:
            post_url: URL of the TikTok post
            
        Returns:
            dict: Post information including author details and video data
        """
        self.navigate_to(post_url)
        self.wait_by_xpath('//span[@data-e2e="share-icon"]')
        
        post = {"author": {}}
        
        try:
            # Author information
            author_ids = self.find_elements(By.XPATH, '//span[@data-e2e="browse-username"]')
            if author_ids:
                post["author"]["unique_id"] = author_ids[0].text
            else:
                print("Warning: Could not find author username")
            
            author_infos = self.find_elements(By.XPATH, '//span[@data-e2e="browser-nickname"]')
            if author_infos:
                author_info = author_infos[0].text
                post["author"]["nickname"], post["post_date"] = author_info.split("\n·\n", 1)
            else:
                print("Warning: Could not find author nickname")
            
            # Video description
            video_descs = self.find_elements(By.XPATH, '//*[@data-e2e="browse-video-desc"]')
            if video_descs:
                post["description"] = video_descs[0].text
            else:
                print("Warning: Could not find video description")
            
            # Share link and video ID
            share_icons = self.find_elements(By.XPATH, '//span[@data-e2e="share-icon"]')
            if share_icons:
                self.driver.execute_script("arguments[0].click();", share_icons[0])
                share_links = self.find_elements(By.XPATH, '//input[@class="TUXTextInputCore-input"]')
                if share_links:
                    post["share_link"] = share_links[0].get_attribute("value")
                    if match := re.search(r"@([^/]+)/", post["share_link"]):
                        post["author"]["unique_id"] = match.group(1)
            else:
                print("Warning: Could not find share button")
            
            post["share_link"] = post.get("share_link") or self.driver.current_url
            
            # Video sources
            video_srcs = self.find_elements(By.XPATH, '//video/source')
            if video_srcs:
                post["video_srcs"] = [video_src.get_attribute("src") for video_src in video_srcs]
            else:
                print("Warning: Could not find video sources")
            
        except Exception as e:
            print(f"Error in get_post_info: {str(e)}")
            print(f"Current URL: {self.driver.current_url}")
        return post

    @remove_blockers_before_and_after
    def get_user_search_results(self, keyword: str) -> list:
        """
        Search for TikTok users by keyword.
        
        Args:
            keyword: Search term
            
        Returns:
            list: List of user information dictionaries
        """
        self.navigate_to(f"{self.BASE_URL}search/user?q={quote(keyword)}")
        self.wait_by_xpath('//div[@id="app"]')
        self.scroll_down(3)
        
        urls, headers = self._find_api_urls_and_headers_from_log(url_pattern="^https://www.tiktok.com/api/search/user/full")
        headers["cookie"] = self.get_tiktok_cookies_formatted()
        
        users = []
        for url in urls:
            response = requests.get(url=url, headers=headers)
            if not hasattr(response, "text") or not response.text:
                continue
                
            response_json = json.loads(response.text)
            try:
                users += [{
                            "uid": info["user_info"]["uid"],
                            "nickname": info["user_info"]["nickname"],
                            "signature": info["user_info"]["signature"],
                            "unique_id": info["user_info"]["unique_id"],
                            "follower_count": info["user_info"]["follower_count"],
                            "icon_img_url": info["user_info"]["avatar_thumb"]["url_list"][0]
                            } for info in response_json.get("user_list", [])]
            except KeyError as e:
                print(f"\n\n\nKeyError: {e}")
                break    
        return users

    @remove_blockers_before_and_after
    def get_post_comments(self, post_url: str) -> list:
        """
        Get all comments from a TikTok post.
        
        Args:
            post_url: URL of the TikTok post
            
        Returns:
            list: List of comment dictionaries containing nickname and text
        """
        self.navigate_to(post_url)
        self.wait_by_xpath('//div[@id="app"]')
        self.scroll_down(3)
        
        urls, headers = self._find_api_urls_and_headers_from_log(url_pattern="^https://www.tiktok.com/api/comment/list/")
        headers["cookie"] = self.get_tiktok_cookies_formatted()
        
        comments = []
        for url in urls:
            try:
                response = requests.get(url=url, headers=headers)
                if not hasattr(response, "text") or not response.text:
                    continue
                    
                response_json = json.loads(response.text)
                for comment_info in response_json.get("comments", []):
                    text = comment_info.get("text")
                    if text:
                        comments.append({
                                        "nickname": comment_info["user"].get("nickname", "unknown"),
                                        "text": text
                                        })
            except KeyError as e:
                print(f"\nError processing comment: {e}")
                print(f"Comment info: {comment_info}")
            except Exception as e:
                print(f"\nUnexpected error in comment processing: {e}")   
        return comments

    @remove_blockers_before_and_after
    def get_video_search_results(self, keyword: str) -> list:
        """
        Search for videos by keyword.
        
        Args:
            keyword: Search term
            
        Returns:
            list: List of video information dictionaries
        """
        self.navigate_to(f"{self.BASE_URL}search/video?q={quote(keyword)}")
        self.wait_by_xpath('//div[@id="app"]')
        self.scroll_down(3)
        
        urls, headers = self._find_api_urls_and_headers_from_log(url_pattern="^https://www.tiktok.com/api/search/item/full")
        headers["cookie"] = self.get_tiktok_cookies_formatted()
        
        videos = []
        for url in urls:
            response = requests.get(url=url, headers=headers)
            if not hasattr(response, "text") or not response.text:
                continue
                
            response_json = json.loads(response.text)
            for item in response_json.get("item_list", []):
                try:
                    video_id = item["id"]
                    author_id = item["author"]["uniqueId"]
                    videos.append({
                        "video": {
                            "id": video_id,
                            "desc": item["desc"],
                            "create_time": item["createTime"],
                            "share_link": f"{self.BASE_URL}@{author_id}/video/{video_id}",
                            "cover_img_url": item["video"].get("cover", ""),
                            "download_url": item["video"].get("downloadAddr") or item["video"].get("playAddr", "")
                        },
                        "author": {
                            "id": author_id,
                            "nickname": item["author"]["nickname"],
                            "signature": item["author"]["signature"],
                            "icon_img_url_L": item["author"].get("avatarLarger", ""),
                            "icon_img_url_M": item["author"].get("avatarMedium", ""),
                            "icon_img_url_S": item["author"].get("avatarThumb", "")
                        }
                    })
                except KeyError as e:
                    print(f"\nKeyError in video search: {e}")
                    break        
        return videos

    @remove_blockers_before_and_after
    def get_hashtag_search_results(self, keyword: str) -> list:
        """
        Search for videos by hashtag.
        
        Args:
            keyword: Hashtag to search for (without #)
            
        Returns:
            list: List of video information dictionaries
        """
        self.navigate_to(f"{self.BASE_URL}tag/{quote(keyword)}")
        self.wait_by_xpath('//div[@id="app"]')
        self.scroll_down(3)
        
        urls, headers = self._find_api_urls_and_headers_from_log(url_pattern="^https://www.tiktok.com/api/challenge/item_list")
        headers["cookie"] = self.get_tiktok_cookies_formatted()
        
        videos = []
        for url in urls:
            response = requests.get(url=url, headers=headers)
            if not hasattr(response, "text") or not response.text:
                continue
                
            response_json = json.loads(response.text)
            for item in response_json.get("itemList", []):
                try:
                    video_id = item["id"]
                    author_id = item["author"]["uniqueId"]
                    videos.append({
                                    "video": {
                                                "id": video_id,
                                                "desc": item["desc"],
                                                "create_time": item["createTime"],
                                                "share_link": f"{self.BASE_URL}@{author_id}/video/{video_id}",
                                                "cover_img_url": item["video"].get("cover", ""),
                                                "download_url": item["video"].get("downloadAddr") or item["video"].get("playAddr", "")
                                            },
                                    "author": {
                                                "id": author_id,
                                                "nickname": item["author"]["nickname"],
                                                "signature": item["author"]["signature"],
                                                "icon_img_url_L": item["author"].get("avatarLarger", ""),
                                                "icon_img_url_M": item["author"].get("avatarMedium", ""),
                                                "icon_img_url_S": item["author"].get("avatarThumb", "")
                                            }
                                })
                except KeyError as e:
                    print(f"\nKeyError in hashtag search: {e}\nItem: {item}")
                    break          
        return videos

    @remove_blockers_before_and_after
    def get_homepage_video_info(self) -> list:
        """
        Search for videos by hashtag.
        
        Args:
            keyword: Hashtag to search for (without #)
            
        Returns:
            list: List of video information dictionaries
        """
        if self.driver.current_url != "https://www.tiktok.com/foryou":
            self.navigate_to("https://www.tiktok.com/foryou")
            time.sleep(self.WAIT_TIME)
        urls, headers = self._find_api_urls_and_headers_from_log(url_pattern="^https://www.tiktok.com/api/recommend/item_list")
        headers["cookie"] = self.get_tiktok_cookies_formatted()
        
        videos = []
        for url in urls:
            response = requests.get(url=url, headers=headers)
            if not hasattr(response, "text") or not response.text:
                continue
                
            response_json = json.loads(response.text)
            for item in response_json.get("itemList", []):
                if "liveRoomInfo" in item:
                    continue # Skip cuz live room videos has no author info
                try:
                    video_id = item["id"]
                    author_id = item["author"]["uniqueId"]
                    videos.append({
                                    "video": {
                                                "id": video_id,
                                                "desc": item["desc"],
                                                "create_time": item["createTime"],
                                                "share_link": f"{self.BASE_URL}@{author_id}/video/{video_id}",
                                                "cover_img_url": item["video"].get("cover", ""),
                                                "download_url": item["video"].get("downloadAddr") or item["video"].get("playAddr", "")
                                            },
                                    "author": {
                                                "id": author_id,
                                                "nickname": item["author"]["nickname"],
                                                "signature": item["author"]["signature"],
                                                "icon_img_url_L": item["author"].get("avatarLarger", ""),
                                                "icon_img_url_M": item["author"].get("avatarMedium", ""),
                                                "icon_img_url_S": item["author"].get("avatarThumb", "")
                                            }
                                })
                except KeyError as e:
                    print(f"\nKeyError in hashtag search: {e}\nItem: {item}")
                    break        
        return videos
    
if __name__ == "__main__":
    tts = None
    try:
        tts = TikTokScraper()
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
        tts.activate_webdriver(vm_mode=False, user_agent=user_agent)
        
        result = tts.get_profile_info("https://www.tiktok.com/@hankuoyu")
        TikTokScraper.save_json(result, 'result.json')
        print("Successfully scraped profile and saved results")
    except Exception as e:
        print(f"Error during scraping: {str(e)}")
    finally:
        if tts and tts.driver:
            tts.close_webdriver()
