import os
import sys
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from config.settings import get_chrome_profile_dir, MAC_CHROME_BINARY, CHROMEDRIVER_PATH
from core.logging.config import logger

def _cleanup_chrome_locks(profile_dir):
    """Removes stale Chrome singleton lock files that can prevent a new Chrome session from starting."""
    lock_files = ["SingletonLock", "SingletonCookie", "SingletonSocket"]
    for lock in lock_files:
        lock_path = os.path.join(profile_dir, lock)
        if os.path.exists(lock_path):
            try:
                os.remove(lock_path)
                logger.info(f"Removed stale Chrome lock file: {lock_path}")
            except Exception as e:
                logger.warning(f"Could not remove Chrome lock file {lock_path}: {e}")


def _kill_stale_chrome_processes():
    """On Windows, kills any lingering chrome.exe or chromedriver.exe processes before launching a new session."""
    if sys.platform == 'win32':
        for proc in ["chrome.exe", "chromedriver.exe"]:
            result = os.system(f"taskkill /F /IM {proc} /T >nul 2>&1")
            if result == 0:
                logger.info(f"Killed stale process: {proc}")


def get_driver():
    """Initializes and returns a Selenium webdriver.Chrome instance with the configured profile and options."""
    # Kill any lingering Chrome/ChromeDriver processes (Windows only)
    _kill_stale_chrome_processes()

    options = Options()

    # --- Core stability flags (important on Windows to prevent renderer crashes) ---
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-features=RendererCodeIntegrity,VizDisplayCompositor")
    options.add_argument("--start-maximized")

    # --- Anti-detection & behaviour flags ---
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-popup-blocking")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    prefs = {
        "profile.default_content_setting_values.popups": 1,
    }
    options.add_experimental_option("prefs", prefs)

    # --- Chrome profile setup (clean stale locks first) ---
    chrome_profile_dir = get_chrome_profile_dir()
    _cleanup_chrome_locks(chrome_profile_dir)
    options.add_argument(f"--user-data-dir={chrome_profile_dir}")

    # --- Chrome binary resolution ---
    # Check if custom Chrome binary path is provided via env (highest priority)
    env_chrome_path = os.getenv("CHROME_BINARY_PATH")
    if env_chrome_path:
        if os.path.exists(env_chrome_path):
            options.binary_location = env_chrome_path
            logger.info(f"Using custom Chrome binary from CHROME_BINARY_PATH: {env_chrome_path}")
        else:
            logger.error(f"CHROME_BINARY_PATH specified in env does not exist: {env_chrome_path}")
    else:
        # MacOS Chrome Binary check
        if sys.platform == 'darwin' and os.path.exists(MAC_CHROME_BINARY):
            options.binary_location = MAC_CHROME_BINARY
            logger.info(f"Using custom Chrome binary location: {MAC_CHROME_BINARY}")

        # Windows Chrome Binary check
        elif sys.platform == 'win32':
            chrome_path = None
            try:
                import winreg
                reg_paths = [
                    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"),
                    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"),
                    (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe")
                ]
                for hkey, subkey in reg_paths:
                    try:
                        with winreg.OpenKey(hkey, subkey) as key:
                            val, _ = winreg.QueryValueEx(key, "")
                            if val and os.path.exists(val):
                                # Skip if Edge has hijacked the Chrome registry key
                                if "edge" in val.lower() or "msedge" in val.lower():
                                    continue
                                chrome_path = val
                                break
                    except OSError:
                        continue
            except ImportError:
                pass

            # Fallback to multi-drive search
            if not chrome_path:
                win_paths = []
                for drive in ["C", "D", "E", "F", "G", "H"]:
                    win_paths.extend([
                        f"{drive}:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
                        f"{drive}:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe"
                    ])
                win_paths.append(os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"))
                
                for path in win_paths:
                    if os.path.exists(path):
                        if "edge" in path.lower() or "msedge" in path.lower():
                            continue
                        chrome_path = path
                        break

            if chrome_path:
                options.binary_location = chrome_path
                logger.info(f"Using custom Chrome binary location: {chrome_path}")
            else:
                logger.warning(
                    "Google Chrome binary not found in standard registry or program paths! "
                    "Selenium will rely on default system path resolution. If you get browser version errors "
                    "(e.g., unrecognized Chrome version/Edge launching), please set CHROME_BINARY_PATH "
                    "in your .env file to the absolute path of your actual Google Chrome installation (e.g., "
                    "CHROME_BINARY_PATH=C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe)."
                )

    # --- Chromedriver setup ---
    if os.path.exists(CHROMEDRIVER_PATH):
        logger.info(f"Using local chromedriver binary: {CHROMEDRIVER_PATH}")
        service = Service(CHROMEDRIVER_PATH)
    else:
        logger.info("Local chromedriver not found, installing via webdriver_manager...")
        from webdriver_manager.chrome import ChromeDriverManager
        chromedriver_path = ChromeDriverManager().install()
        logger.info(f"webdriver_manager installed chromedriver at: {chromedriver_path}")
        service = Service(chromedriver_path)

    driver = webdriver.Chrome(service=service, options=options)
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
