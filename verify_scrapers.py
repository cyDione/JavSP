import sys
import os
import yaml
from http.cookies import SimpleCookie

# Add project root to path
sys.path.append(os.getcwd())

from javsp.web.base import Request, is_connectable

JAVDB_URL = "https://javdb.com/search?q=STARS-7787"
JAVLIB_URL = "https://www.y78k.com/vl_searchbyid.php?keyword=STARS-7787" # Using the proxy_free URL from config example or default

CONFIG_PATH = "config.yml"

def load_cookie_from_config(site):
    if not os.path.exists(CONFIG_PATH):
        print(f"Config file not found: {CONFIG_PATH}")
        return None
    
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
        try:
            return config['crawler']['cookies'].get(site)
        except KeyError:
            print(f"Cookie for {site} not found in config.yml")
            return None

def verify_javdb():
    print(f"--- Verifying JavDB: {JAVDB_URL} ---")
    # Test 1: With Cookies (from config)
    print("Test 1: With Config Cookies")
    raw_cookie = load_cookie_from_config('javdb')
    req = Request(use_scraper=True, impersonate="chrome110")
    if raw_cookie:
         cookie = SimpleCookie()
         cookie.load(raw_cookie)
         cookies_dict = {k: v.value for k, v in cookie.items()}
         req.cookies = cookies_dict
    
    try:
        r = req.get(JAVDB_URL)
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            if "Just a moment" in r.text:
                 print("Result: FAILED (Cloudflare Challenge Page)")
            else:
                 print(f"Result: SUCCESS (Found: {'STARS-7787' in r.text})")
        else:
             print(f"Result: FAILED (Status {r.status_code})")
    except Exception as e:
        print(f"Error: {e}")

    # Test 2: Without Cookies
    print("\nTest 2: Without Cookies")
    req_clean = Request(use_scraper=True, impersonate="chrome110")
    try:
        r = req_clean.get(JAVDB_URL)
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            if "Just a moment" in r.text:
                 print("Result: FAILED (Cloudflare Challenge Page)")
            else:
                 print(f"Result: SUCCESS (Found: {'STARS-7787' in r.text})")
        else:
             print(f"Result: FAILED (Status {r.status_code})")
    except Exception as e:
        print(f"Error: {e}")

def verify_javlib():
    print(f"\n--- Verifying JavLib: {JAVLIB_URL} ---")
    
    # Try different impersonations
    browsers = ["chrome110"]
    for browser in browsers:
        print(f"\nTesting with impersonate='{browser}' WITH PROXY (Default)")
        try:
            req = Request(use_scraper=True, impersonate=browser)
            r = req.get(JAVLIB_URL)
            print(f"Status: {r.status_code}")
        except Exception as e:
            print(f"Error: {e}")

        print(f"\nTesting with impersonate='{browser}' WITHOUT PROXY")
        try:
            req_no_proxy = Request(use_scraper=True, impersonate=browser)
            req_no_proxy.proxies = {} # Disable proxy
            r = req_no_proxy.get(JAVLIB_URL)
            print(f"Status: {r.status_code}")
            if r.status_code == 200:
                 if "Just a moment" in r.text or "Checking your browser" in r.text:
                     print("Result: FAILED (Cloudflare Challenge Page)")
                 else:
                     print(f"Result: SUCCESS (Found: {'STARS-7787' in r.text or 'javlibrary' in r.text})")
            else:
                 print(f"Result: FAILED (Status {r.status_code})")
        except Exception as e:
            print(f"Error: {e}")

    print("\nTesting with Cloudscraper (enable_cffi=False)")
    try:
        req = Request(use_scraper=True, enable_cffi=False)
        r = req.get(JAVLIB_URL)
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
                if "Just a moment" in r.text or "Checking your browser" in r.text:
                    print("Result: FAILED (Cloudflare Challenge Page - Cloudscraper failed)")
                else:
                    print(f"Result: SUCCESS (Found: {'STARS-7787' in r.text or 'javlibrary' in r.text})")
        elif r.status_code == 503:
                print("Result: FAILED (503 Service Unavailable - Cloudscraper failed)")
        else:
                print(f"Result: FAILED (Status {r.status_code})")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    verify_javdb()
    verify_javlib()
