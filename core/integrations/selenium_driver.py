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
    """On Windows, kills any lingering chromedriver.exe processes before launching a new session.
    Note: We intentionally do NOT kill chrome.exe to avoid closing the user's personal browser.
    Stale Chrome profile locks are handled separately by _cleanup_chrome_locks().
    """
    if os.getenv("CONNECTIFY_PARALLEL") == "true":
        logger.info("Parallel run detected; skipping global chromedriver process termination.")
        return

    if sys.platform == 'win32':
        result = os.system("taskkill /F /IM chromedriver.exe /T >nul 2>&1")
        if result == 0:
            logger.info("Killed stale chromedriver.exe process.")


def _kill_lingering_chrome_instances(profile_dir):
    """On Windows, kills any lingering chrome.exe processes that are using our specific profile directory."""
    if sys.platform != 'win32':
        return
        
    try:
        norm_path = os.path.abspath(profile_dir)
        import subprocess
        # Query and kill chrome processes matching our custom profile directory path
        ps_cmd = f'Get-CimInstance Win32_Process -Filter "name = \'chrome.exe\'" | Where-Object {{ $_.CommandLine -like \'*{norm_path}*\' }} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }}'
        cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        logger.info(f"Cleaned up lingering Chrome processes using profile: {profile_dir}")
    except Exception as e:
        logger.warning(f"Could not check/kill lingering Chrome processes: {e}")


def get_driver(profile_suffix=None, headless=False):
    """Initializes and returns a Selenium webdriver instance (Edge on Windows, Chrome on macOS/Linux).
    On Windows, using Microsoft Edge is required because Google's unsigned chromedriver is blocked by 
    Application Control / AppLocker policies, whereas Microsoft's signed msedgedriver is whitelisted.
    """
    is_win = (sys.platform == 'win32')

    if profile_suffix:
        from config.settings import get_user_dir
        chrome_profile_dir = os.path.join(get_user_dir(), profile_suffix)
        os.makedirs(chrome_profile_dir, exist_ok=True)
    else:
        chrome_profile_dir = get_chrome_profile_dir()

    # Kill any lingering Chrome/Edge / ChromeDriver processes (Windows only)
    if is_win:
        _kill_stale_chrome_processes()
        try:
            os.system("taskkill /F /IM msedgedriver.exe /T >nul 2>&1")
        except Exception:
            pass
        _kill_lingering_chrome_instances(chrome_profile_dir)

    # Initialize Options
    if is_win:
        from selenium.webdriver.edge.options import Options as EdgeOptions
        options = EdgeOptions()
    else:
        from selenium.webdriver.chrome.options import Options as ChromeOptions
        options = ChromeOptions()

    options.page_load_strategy = 'eager'

    # --- Core stability flags ---
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    if is_win:
        options.add_argument("--disable-features=RendererCodeIntegrity")
    else:
        options.add_argument("--disable-features=RendererCodeIntegrity,VizDisplayCompositor")
    options.add_argument("--start-maximized")

    # Headless mode config
    if headless:
        options.add_argument("--headless=new")
        options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    # --- Anti-detection & behaviour flags ---
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-popup-blocking")
    
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    prefs = {
        "profile.default_content_setting_values.popups": 1,
        "profile.default_content_setting_values.clipboard": 1,
    }
    options.add_experimental_option("prefs", prefs)

    # --- Profile setup (clean stale locks first) ---
    _cleanup_chrome_locks(chrome_profile_dir)
    options.add_argument(f"--user-data-dir={chrome_profile_dir}")

    # --- Driver and Binary resolution ---
    if is_win:
        from webdriver_manager.microsoft import EdgeChromiumDriverManager
        edgedriver_path = EdgeChromiumDriverManager().install()
        logger.info(f"webdriver_manager installed msedgedriver at: {edgedriver_path}")
        service = Service(edgedriver_path)
        driver = webdriver.Edge(service=service, options=options)
    else:
        # Check custom Chrome binary path via env
        env_chrome_path = os.getenv("CHROME_BINARY_PATH")
        if env_chrome_path:
            if os.path.exists(env_chrome_path):
                options.binary_location = env_chrome_path
                logger.info(f"Using custom Chrome binary from CHROME_BINARY_PATH: {env_chrome_path}")
            else:
                logger.error(f"CHROME_BINARY_PATH specified in env does not exist: {env_chrome_path}")
        else:
            if sys.platform == 'darwin' and os.path.exists(MAC_CHROME_BINARY):
                options.binary_location = MAC_CHROME_BINARY
                logger.info(f"Using custom Chrome binary location: {MAC_CHROME_BINARY}")

        if os.path.exists(CHROMEDRIVER_PATH):
            logger.info(f"Using local chromedriver binary: {CHROMEDRIVER_PATH}")
            service = Service(CHROMEDRIVER_PATH)
        else:
            logger.info("Local chromedriver not found, installing via webdriver_manager...")
            
            # Cleanup any stale webdriver_manager lock files
            try:
                wdm_dir = os.path.expanduser("~/.wdm")
                if os.path.exists(wdm_dir):
                    for root, dirs, files in os.walk(wdm_dir):
                        for file in files:
                            if "lock" in file.lower() or file.endswith(".lock") or file.startswith(".wdm-lock-"):
                                lock_file_path = os.path.join(root, file)
                                try:
                                    os.remove(lock_file_path)
                                except Exception:
                                    pass
            except Exception:
                pass

            from webdriver_manager.chrome import ChromeDriverManager
            chromedriver_path = ChromeDriverManager().install()
            logger.info(f"webdriver_manager installed chromedriver at: {chromedriver_path}")
            service = Service(chromedriver_path)

        driver = webdriver.Chrome(service=service, options=options)

    try:
        driver.set_page_load_timeout(60)
    except Exception:
        pass
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
