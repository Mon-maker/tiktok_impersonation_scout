# -*- coding: utf-8 -*-
"""
Created on 2024.9.4

@author: PikasXYZ
"""
################ variables setting
PAGE_LOAD_TIMEOUT = 30

################ import
from selenium import webdriver
from fake_useragent import UserAgent
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
import time
import cloudscraper
import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from urllib.parse import urlparse
from PIL import Image
from io import BytesIO
import warnings

################ settings
warnings.simplefilter('ignore', InsecureRequestWarning)

ocr_history = {}
asr_history = {}


################ class
class WebScraper:
    def __init__(self):
        self.driver = None

    def activate_webdriver(self, vm_mode=True, user_agent=''):
        options = webdriver.ChromeOptions()
        options.add_argument('log-level=1')
        user_agent = user_agent or UserAgent().random
        print(f"{user_agent = }")
        options.add_argument(f'user-agent={user_agent}')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument("--window-size=1920,1080") # necessary on VM
        options.add_argument('--ignore-certificate-errors')
        options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
        if vm_mode:
            options.add_argument("--headless")
            options.add_argument("--lang=zh-TW")
            options.add_argument("--disable-gpu")  # disable the GPU while running on Windows
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")  # resolve resource constraints
            
        driver = webdriver.Chrome(options=options)
        driver.maximize_window()
        self.driver = driver
        self.driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
        
    def navigate_to(self, url:str):
        if self.driver: 
            self.driver.get(url)
        else:
            print("webdriver not found! Please activate_webdriver before.")
    
    def save_screenshot(self, filename: str):
        if self.driver: 
            self.driver.save_screenshot(filename)
        else:
            print("webdriver not found! Please activate_webdriver before.")
            
    def close_webdriver(self):
        if self.driver: 
            self.driver.quit()
            self.driver = None
            print("webdriver has been closed.")
        else:
            print("webdriver not found! Please activate_webdriver before.")
    
    def wait_by_xpath(self, xpath: str, wait_sec=5):
        if self.driver: 
            try:
                return WebDriverWait(self.driver, wait_sec).until(EC.presence_of_element_located((By.XPATH, xpath)))
            except TimeoutException:
                return None
        else:
            print("webdriver not found! Please activate_webdriver before.")       
            return None            
    
    def scroll_down(self, max_scroll: int ,sleep_time=2):
        if self.driver: 
            last_height = 0
            for _ in range(max_scroll):
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(sleep_time)
                new_height = self.driver.execute_script("return document.body.scrollHeight")
                if last_height == new_height:
                    break
                last_height = new_height
        else:
            print("webdriver not found! Please activate_webdriver before.")            
    
    def find_elements(self, by_what: By, selector: str) -> list:
        if self.driver: 
            return self.driver.find_elements(by_what, selector)
        else:
            print("webdriver not found! Please activate_webdriver before.")
            return []            
    
    def get_base_url(self, url: str) -> str:
        parsed_url = urlparse(url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        return base_url
        
    def get_html(self, url: str, retries=3, tool="cloudscraper") -> str:
        global PAGE_LOAD_TIMEOUT
        for _ in range(retries):
            if tool == "cloudscraper":
                user_agent = UserAgent().random
                cldscraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False, 'custom': user_agent})
                try:
                    response = cldscraper.get(url, timeout=PAGE_LOAD_TIMEOUT)
                    return response.text
                except Exception as e:
                    print(f"@@@get_html(cloudscraper)@@@\n", str(e))
                        
            elif tool == "requests":
                try:
                    response = requests.get(url, timeout=PAGE_LOAD_TIMEOUT, verify=False)
                    response.raise_for_status()  # Raise an HTTPError for bad responses
                    return response.text
                except Exception as e:
                    print("@@@get_html(requests)@@@\n", str(e))
                    
            elif tool == "selenium":
                if self.driver is None:
                    self.activate_webdriver()
                self.driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT*2)
                try:
                    self.navigate_to(url)
                    time.sleep(3) #for page loading
                    return self.driver.page_source
                except Exception as e:
                    if "timeout" in str(e):
                        print("@@@get_html(selenium)@@@ timeout!")
                    elif "ERR_NAME_NOT_RESOLVED" in str(e):
                        print(f"@@@get_html(selenium)@@@ unknown domain name! ({url = })")
                    else:
                        print("@@@get_html(selenium)@@@\n", str(e))
                finally:
                    self.driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
                    
            else:
                print(f"Unknown tool! ({tool})")
                break
        return ''
    
    def download_and_convert_to_png(self, image_url: str, output_path: str) -> bool:
        try:
            response = requests.get(image_url, verify=False)
            response.raise_for_status()  
            img = Image.open(BytesIO(response.content))

            if img.format != 'PNG':
                img = img.convert('RGBA')
            img.save(output_path, 'PNG')
            return True
            
        except Exception as e:
            print(f"download_and_convert_to_png ({image_url = }):\n {e}")
            return False
            
    def save_html(self, file_path: str, html_content: str) -> None:
        try:
            with open(file_path, 'w', encoding='utf-8') as file:
                file.write(html_content)
            print(f"{file_path} saved.")
        except Exception as e:
            print(f"@@@save_html@@@\n{e}")
            
    def screenshot_web(self, url: str, screenshot_filename: str) -> bool:
        user_agent = UserAgent().random
        cldscraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False, 'custom': user_agent})

        try:
            status = cldscraper.get(url, timeout=10).status_code
            if status == 200:
                if self.driver is None:
                    self.activate_webdriver()
                self.driver.get(url)
                time.sleep(10)
                self.driver.save_screenshot(screenshot_filename)
                return True
            else:
                print(f'{status = } ({url = })\ntry selenium instead...')
                if self.driver is None:
                    self.activate_webdriver()
                self.driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT*2)
                try:
                    self.navigate_to(url)
                    time.sleep(3) #for page loading
                    self.driver.save_screenshot(screenshot_filename)
                    return True
                except Exception as e:
                    if "timeout" in str(e):
                        print("@@@screenshot_web(selenium)@@@ timeout!")
                    else:
                        print(f"@@@screenshot_web(selenium)@@@\n", str(e))
                finally:
                    self.driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
                return False
                
        except Exception as e:
            print(str(e))
            return False
            
################ main            
if __name__=="__main__":
    ws = WebScraper()
    
    if False: # test webdriver
        URL = "https://cn.aptoide.com/search?query=富邦&type=apps"
        XPATH2WAIT = '//a[contains(@class, "search-result-card__ResultSearchContainer-sc-")]'
        XPATH2FIND = '//a[contains(@class, "search-result-card__ResultSearchContainer-sc-")]'
        
        ws.get(URL)
        print(f"found {XPATH2WAIT}!" if ws.wait_by_xpath(XPATH2WAIT) else f"didn't found {XPATH2WAIT}!")
        ws.scroll_down(2)
        elems = ws.find_elements(By.XPATH, XPATH2FIND)
        print(len(elems))
        print(f"driver is closing...")
        ws.close_webdriver()
    
    if False: # test download_and_convert_to_png
        img_urls = [
                    "https://www.nwf.org/-/media/NEW-WEBSITE/Shared-Folder/Wildlife/Mammals/mammal_american-pika_600x300.jpg",
                    "https://cdn6.aptoide.com/imgs/b/f/4/bf4e03e717a95131088d5a2341fb42fb_icon.png?w=128",
                    "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSCISd0xNaEOAXbWwNxM9-0gt9eGpY0dsepzOz6FTbFHy7k5vMrkSst&usqp=CAE&s",
                    "https://upload.wikimedia.org/wikipedia/commons/thumb/5/5e/Ochotona_princeps_rockies.JPG/220px-Ochotona_princeps_rockies.JPG",
                    "https://www.ndow.org/wp-content/uploads/2024/02/NDOW_Logo_2023-1400x2048.webp"
                    ]
        for i, img_url in enumerate(img_urls):
            ws.download_and_convert_to_png(img_url, f"test/WS_download_and_convert_to_png{i}.png")
            
    if True:
        
        url = "https://tai-qi-yin-xing-dong-yin-xing.softonic.cn/android"
        user_agent = UserAgent().random
        cldscraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False, 'custom': user_agent})

        for url in [
                    "https://tai-qi-yin-xing-dong-yin-xing.softonic.cn/android", #dead
                    "https://line.softonic.cn/android", #alive
                    "https://procreate.softonic.cn/android" #alive
                    ]:
            #response = requests.get(url, timeout=30, verify=False)
            #status = cldscraper.get(url, timeout=10).status_code
            for _ in range(3):
                if ws.driver is None:
                    ws.activate_webdriver()
                try:
                    ws.navigate_to(url)
                    time.sleep(1) #for page loading
                    new_url = ws.driver.current_url 
                    print(f"{url = }\n{new_url = }\n=======")
                    break
                except Exception as e:
                    if "timeout" in str(e):
                        print("@@@get_html(selenium)@@@ timeout!")
                    elif "ERR_NAME_NOT_RESOLVED" in str(e):
                        print(f"@@@get_html(selenium)@@@ unknown domain name! ({url = })")
                    else:
                        print("@@@get_html(selenium)@@@\n", str(e))
            