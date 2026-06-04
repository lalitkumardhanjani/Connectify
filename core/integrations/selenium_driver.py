import os
import sys
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from config.settings import get_chrome_profile_dir, MAC_CHROME_BINARY, CHROMEDRIVER_PATH
from core.logging.config import logger

def get_driver():
    """Initializes and returns a Selenium webdriver.Chrome instance with the configured profile and options."""
    options = Options()
    options.add_argument("--remote-debugging-port=9222")
    chrome_profile_dir = get_chrome_profile_dir()
    options.add_argument(f"--user-data-dir={chrome_profile_dir}")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-popup-blocking")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    
    prefs = {
        "profile.default_content_setting_values.popups": 1,
    }
    options.add_experimental_option("prefs", prefs)

    # MacOS Chrome Binary check
    if sys.platform == 'darwin' and os.path.exists(MAC_CHROME_BINARY):
        options.binary_location = MAC_CHROME_BINARY
        logger.info(f"Using custom Chrome binary location: {MAC_CHROME_BINARY}")

    # Chromedriver setup
    if os.path.exists(CHROMEDRIVER_PATH):
        logger.info(f"Using local chromedriver binary: {CHROMEDRIVER_PATH}")
        service = Service(CHROMEDRIVER_PATH)
    else:
        logger.info("Local chromedriver not found, installing via webdriver_manager...")
        from webdriver_manager.chrome import ChromeDriverManager
        service = Service(ChromeDriverManager(driver_version="148.0.7778.216").install())

    driver = webdriver.Chrome(service=service, options=options)
    driver.maximize_window()
    return driver

def wait_for_page(seconds=5):
    """Simple wrapper to sleep execution for page loads or actions."""
    time.sleep(seconds)

def inject_runtime_overlay(driver):
    """Injects a visually distinct timer overlay onto the web page."""
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
    """Removes the timer overlay from the web page."""
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
