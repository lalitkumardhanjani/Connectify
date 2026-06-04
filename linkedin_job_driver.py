import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from linkedin_job_config import CHROME_PROFILE_DIR

def get_driver():
    options = Options()
    options.add_argument("--remote-debugging-port=9222")
    options.add_argument(f"--user-data-dir={CHROME_PROFILE_DIR}")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-popup-blocking")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    prefs = {
        "profile.default_content_setting_values.popups": 1,
    }
    options.add_experimental_option("prefs", prefs)
    options.binary_location = "/System/Volumes/Data/Volumes/Google Chrome/Google Chrome.app/Contents/MacOS/Google Chrome"

    import os
    from selenium.webdriver.chrome.service import Service
    local_chromedriver = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chromedriver")
    if os.path.exists(local_chromedriver):
        service = Service(local_chromedriver)
    else:
        from webdriver_manager.chrome import ChromeDriverManager
        service = Service(ChromeDriverManager(driver_version="148.0.7778.216").install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.maximize_window()
    return driver

def wait_for_page(seconds=5):
    time.sleep(seconds)

def wait_for_search_results(driver, timeout=30):
    try:
        WebDriverWait(driver, timeout).until(lambda d: d.execute_script(
            "return !!document.querySelector('a[href*=\"/jobs/view/\"]') || "
            "!!document.querySelector('ul.jobs-search__results-list li') || "
            "!!document.querySelector('div.jobs-search-results__list-item') || "
            "!!document.querySelector('div.job-card-container') || "
            "!!document.querySelector('div.job-card-list__item') || "
            "!!document.querySelector('.base-card')"
        ))
        return True
    except Exception:
        return False

def is_logged_in(driver):
    try:
        return driver.execute_script(
            "return !!document.querySelector("
            "  'input[placeholder*=\"Search\"],"
            "   input[role=\"combobox\"],"
            "   .search-global-typeahead__input'"
            ");"
        )
    except Exception:
        return False

def wait_until_logged_in(driver, timeout_seconds=300):
    print("\nLogin required.")
    print("In the opened Chrome window, sign in to LinkedIn using email/password.")
    print("Avoid 'Continue with Google' here; Google often blocks sign-in in automated browsers.")

    start = time.time()
    while time.time() - start < timeout_seconds:
        if is_logged_in(driver):
            print("Login detected.")
            return True
        time.sleep(2)

    return False

def inject_runtime_overlay(driver):
    try:
        driver.execute_script(r"""
            (function(){
                if(window.__copilot_timer_installed) return;
                window.__copilot_timer_installed = true;
                window.__copilot_timer_start = Date.now();
                const el = document.createElement('div');
                el.id = 'copilot-run-timer';
                el.style.position = 'fixed';
                el.style.right = '12px';
                el.style.top = '12px';
                el.style.zIndex = 9999999;
                el.style.background = 'rgba(0,0,0,0.7)';
                el.style.color = '#fff';
                el.style.padding = '6px 10px';
                el.style.borderRadius = '6px';
                el.style.fontFamily = 'Arial, sans-serif';
                el.style.fontSize = '12px';
                el.style.boxShadow = '0 2px 6px rgba(0,0,0,0.4)';
                el.innerText = 'Running: 00:00:00';
                document.body.appendChild(el);
                window.__copilot_timer_interval = setInterval(function(){
                    try{
                        var s = Math.floor((Date.now() - window.__copilot_timer_start)/1000);
                        var hh = Math.floor(s/3600);
                        var mm = Math.floor((s%3600)/60);
                        var ss = s%60;
                        var fmt = (hh?hh+':':'') + String(mm).padStart(2,'0') + ':' + String(ss).padStart(2,'0');
                        var el2 = document.getElementById('copilot-run-timer');
                        if(el2) el2.innerText = 'Running: ' + fmt;
                    }catch(e){}
                }, 1000);
            })();
        """)
    except Exception:
        pass

def remove_runtime_overlay(driver):
    try:
        driver.execute_script(r"""
            (function(){
                try{
                    if(window.__copilot_timer_installed){
                        clearInterval(window.__copilot_timer_interval);
                        var el = document.getElementById('copilot-run-timer');
                        if(el) el.remove();
                        window.__copilot_timer_installed = false;
                    }
                }catch(e){}
            })();
        """)
    except Exception:
        pass
