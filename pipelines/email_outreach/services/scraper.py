import time
import random
import re
from urllib.parse import quote
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException

from config.user_profiles import get_selected_user_config, get_global_settings
from config.constants import DBA_KEYWORDS_DEFAULT
from core.utils.string_utils import extract_emails
from core.storage.database import append_email, init_scraper_store
from core.logging.config import logger

class LinkedInScraper:
    def __init__(self, driver):
        self.driver = driver

    def _find_post_containers(self):
        selectors = [
            ("css", ".feed-shared-update-v2"),
            ("xpath", "//div[@role='listitem' and .//button[@data-testid='expandable-text-button'] ]"),
            ("xpath", "//div[@role='listitem']"),
            ("xpath", "//article")
        ]
        for strategy, selector in selectors:
            try:
                if strategy == "css":
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                else:
                    elements = self.driver.find_elements(By.XPATH, selector)
                if elements:
                    logger.info(f"Found {len(elements)} potential posts using selector: {selector}")
                    return elements
            except Exception as e:
                logger.warning(f"Post container selector failed: {selector} -> {e}")
        return []

    def _expand_post(self, post_element):
        expand_selectors = [
            ".//button[@data-testid='expandable-text-button']",
            ".//button[contains(normalize-space(.), 'more')]",
            ".//button[contains(translate(., 'MORE', 'more'), 'more')]"
        ]
        for selector in expand_selectors:
            try:
                button = post_element.find_element(By.XPATH, selector)
                self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", button)
                time.sleep(0.5)
                self.driver.execute_script("arguments[0].click();", button)
                time.sleep(0.7)
                return True
            except (NoSuchElementException, StaleElementReferenceException):
                continue
            except Exception as e:
                logger.warning(f"Unable to expand post content: {e}")
                continue
        return False

    def login(self):
        """Handle LinkedIn login using config profiles."""
        self.driver.get("https://www.linkedin.com/feed/")
        logger.info("Checking if already logged in...")
        try:
            search_bar_selectors = [
                "input[placeholder*='Search']",
                ".search-global-typeahead__input",
                "input[role='combobox']"
            ]
            for selector in search_bar_selectors:
                try:
                    search_bar = WebDriverWait(self.driver, 2).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    if search_bar:
                        logger.info("Already logged in! (Search bar found)")
                        return True
                except TimeoutException:
                    continue
                    
            logger.info("Not logged in. Attempting login...")
            global_conf = get_global_settings()
            email = global_conf.get("linkedin_email")
            password = global_conf.get("linkedin_password")
            
            if not email or not password:
                logger.warning("LinkedIn credentials missing in config. Waiting up to 300 seconds for manual login in the browser window...")
                start_time = time.time()
                while time.time() - start_time < 300:
                    try:
                        for selector in search_bar_selectors:
                            try:
                                search_bar = self.driver.find_element(By.CSS_SELECTOR, selector)
                                if search_bar.is_displayed():
                                    logger.info("Manual login detected!")
                                    return True
                            except NoSuchElementException:
                                continue
                    except Exception:
                        pass
                    time.sleep(2)
                logger.error("Manual login timeout. Exiting.")
                return False
                
            email_selectors = [
                "input[id*='username']",
                "input[name='session_key']",
                "input[type='email']",
                "#username"
            ]
            email_input = None
            for selector in email_selectors:
                try:
                    email_input = WebDriverWait(self.driver, 3).until(
                        EC.visibility_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    break
                except TimeoutException:
                    continue
                    
            if email_input:
                email_input.send_keys(email)
                password_input = self.driver.find_element(By.CSS_SELECTOR, "input[type='password']")
                password_input.send_keys(password)
                
                button_selectors = [
                    "button[type='submit']",
                    "button[data-litms-control-urn*='sign-in']",
                    ".btn__primary--large"
                ]
                for selector in button_selectors:
                    try:
                        self.driver.find_element(By.CSS_SELECTOR, selector).click()
                        break
                    except NoSuchElementException:
                        continue
                time.sleep(5)
                
                # Check if logged in
                logged_in_after_auto = False
                for selector in search_bar_selectors:
                    try:
                        search_bar = self.driver.find_element(By.CSS_SELECTOR, selector)
                        if search_bar.is_displayed():
                            logged_in_after_auto = True
                            break
                    except NoSuchElementException:
                        continue
                        
                if logged_in_after_auto:
                    logger.info("Login successful!")
                    return True
                else:
                    logger.warning("Auto-login failed or security check (2FA) required. Waiting up to 300 seconds for manual login...")
                    start_time = time.time()
                    while time.time() - start_time < 300:
                        try:
                            for selector in search_bar_selectors:
                                try:
                                    search_bar = self.driver.find_element(By.CSS_SELECTOR, selector)
                                    if search_bar.is_displayed():
                                        logger.info("Manual login completed!")
                                        return True
                                except NoSuchElementException:
                                    continue
                        except Exception:
                            pass
                        time.sleep(2)
                    logger.error("Manual login timeout. Exiting.")
                    return False
        except Exception as e:
            logger.error(f"Login error: {str(e)}")
            logger.info("Waiting up to 300 seconds for manual login...")
            start_time = time.time()
            while time.time() - start_time < 300:
                try:
                    for selector in search_bar_selectors:
                        try:
                            search_bar = self.driver.find_element(By.CSS_SELECTOR, selector)
                            if search_bar.is_displayed():
                                logger.info("Manual login completed!")
                                return True
                        except NoSuchElementException:
                            continue
                except Exception:
                    pass
                time.sleep(2)
            return False

    def search_for_keyword(self, keyword):
        """Navigate to the LinkedIn search page for a given keyword and ensure the Posts/LATEST view is active."""
        search_query = quote(keyword)
        url = f"https://www.linkedin.com/search/results/content/?keywords={search_query}&origin=GLOBAL_SEARCH_HEADER&sortBy=%22date_posted%22"
        logger.info(f"Navigating to: {url}")
        self.driver.get(url)
        time.sleep(5)
        if "search/results/content" not in self.driver.current_url:
            logger.warning("Direct navigation failed – falling back to manual UI steps.")
            self.driver.get("https://www.linkedin.com/feed/")
            time.sleep(3)
            try:
                search_input = self.driver.find_element(By.CLASS_NAME, "search-global-typeahead__input")
                search_input.send_keys(keyword)
                search_input.send_keys(u'\ue007')  # Enter
                time.sleep(5)
                posts_btn = self.driver.find_element(By.XPATH, "//button[text()='Posts']")
                posts_btn.click()
                time.sleep(3)
                sort_btn = self.driver.find_element(By.XPATH, "//button[contains(@aria-label, 'Sort by')]")
                sort_btn.click()
                time.sleep(1)
                latest_option = self.driver.find_element(By.XPATH, "//span[text()='Latest']")
                latest_option.click()
                time.sleep(3)
            except Exception as e:
                logger.error(f"Failed to navigate to Posts view: {e}")
                return False
        return True

    def extract_post_data(self, post_element):
        """Extract raw text content from a post element."""
        try:
            self._expand_post(post_element)
            content_selectors = [
                ".//*[contains(@class, 'feed-shared-text')]",
                ".//*[contains(@class, 'update-components-text')]",
                ".//div[contains(@data-display-contents, 'true')]",
                ".//div[contains(@class, 'show-more-less-html')]",
                ".//div[@data-test-id='feed-item-text']",
                ".//p",
                ".//span",
                "."
            ]
            post_content = ""
            for selector in content_selectors:
                try:
                    elements = post_element.find_elements(By.XPATH, selector)
                    if not elements:
                        continue
                    texts = []
                    for el in elements:
                        try:
                            txt = el.text.strip()
                            if txt and len(txt) > 5:
                                texts.append(txt)
                        except Exception:
                            continue
                    post_content = " ".join(texts).strip()
                    if len(post_content) > 50:
                        break
                except Exception:
                    continue
            post_content = re.sub(r"\s+", " ", post_content).replace("… more", "").strip()
            return {"content": post_content}
        except StaleElementReferenceException:
            logger.warning("Post element went stale while processing.")
            return None
        except Exception as e:
            logger.warning(f"Error extracting post data: {e}")
            return None

    def process_keyword(self, keyword, timeout_seconds=60):
        """Scroll and scrape emails for the given keyword.
        
        Runs until timeout_seconds has elapsed. Handles LinkedIn's lazy-loading
        by retrying with scroll-back + extended waits when the page height stops
        growing, rather than exiting early.
        """
        start_time = time.time()
        processed_ids = set()
        no_posts_found_count = 0
        consecutive_no_new_content = 0   # tracks consecutive scroll attempts with no height change
        max_consecutive_no_new = 6       # try up to 6 times with back-scroll + longer wait before giving up
        search_url = self.driver.current_url  # remember the search URL to re-navigate if redirected

        user_conf = get_selected_user_config()
        email_scraper = user_conf.get("email_scraper", {})
        search_keywords = email_scraper.get("keywords", DBA_KEYWORDS_DEFAULT)
        excluded_keywords = [kw.lower().strip() for kw in email_scraper.get("excluded_keywords", []) if kw.strip()]

        logger.info(f"Starting keyword '{keyword}' scrape — timeout: {timeout_seconds}s")

        while True:
            elapsed = time.time() - start_time

            # Primary exit: timeout reached
            if elapsed >= timeout_seconds:
                logger.info(f"Keyword '{keyword}' — timeout reached after {int(elapsed)}s. Moving to next keyword.")
                break

            # Re-navigate if LinkedIn redirected us away from search results
            current_url = self.driver.current_url
            if "search/results/content" not in current_url:
                logger.warning(f"LinkedIn redirected away from search page. Re-navigating to search URL...")
                try:
                    self.driver.get(search_url)
                    time.sleep(4)
                    if "search/results/content" not in self.driver.current_url:
                        logger.warning("Re-navigation failed — LinkedIn rejected the search URL. Stopping keyword.")
                        break
                    consecutive_no_new_content = 0
                except Exception as nav_err:
                    logger.error(f"Re-navigation error: {nav_err}")
                    break

            # Record height BEFORE processing this batch
            pre_scroll_height = self.driver.execute_script("return document.body.scrollHeight")
            new_posts_this_batch = 0

            try:
                posts = self._find_post_containers()
                if not posts:
                    logger.warning("No posts found on the current page.")
                    no_posts_found_count += 1
                    if no_posts_found_count >= 5:
                        logger.info("No posts found for 5 consecutive checks — page may be empty. Stopping keyword.")
                        break
                    time.sleep(3)
                    continue
                else:
                    no_posts_found_count = 0

                for post in posts:
                    # Enforce timeout mid-batch
                    if time.time() - start_time >= timeout_seconds:
                        logger.info(f"Keyword '{keyword}' timeout reached mid-batch. Moving to next keyword.")
                        return
                    post_id = post.get_attribute("data-urn") or str(hash(post.text[:100] if post.text else ""))
                    if post_id in processed_ids:
                        continue
                    new_posts_this_batch += 1
                    data = self.extract_post_data(post)
                    if data and data.get('content'):
                        content = data['content']
                        if any(kw.lower() in content.lower() for kw in search_keywords):
                            excluded_hit = next((kw for kw in excluded_keywords if kw in content.lower()), None)
                            if excluded_hit:
                                logger.debug(f"Post excluded by exclusion keyword '{excluded_hit}' — skipped.")
                            else:
                                emails = extract_emails(content)
                                for email in emails:
                                    appended = append_email(email, keyword)
                                    if appended:
                                        logger.info(f"Collected new email: {email}")
                        else:
                            logger.debug("Post did not contain any target keyword — skipped.")
                    processed_ids.add(post_id)

            except Exception as e:
                logger.error(f"Error during post processing: {e}")

            # Scroll to bottom to trigger LinkedIn lazy-loading
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(random.uniform(2, 3))

            post_scroll_height = self.driver.execute_script("return document.body.scrollHeight")

            if post_scroll_height <= pre_scroll_height and new_posts_this_batch == 0:
                consecutive_no_new_content += 1
                remaining = timeout_seconds - (time.time() - start_time)
                logger.info(
                    f"Scroll height unchanged (attempt {consecutive_no_new_content}/{max_consecutive_no_new}). "
                    f"Elapsed: {int(time.time() - start_time)}s / {timeout_seconds}s — {int(remaining)}s remaining."
                )

                if consecutive_no_new_content >= max_consecutive_no_new:
                    logger.info(
                        f"Keyword '{keyword}' — LinkedIn feed exhausted after {max_consecutive_no_new} extended retries. "
                        f"Stopping early at {int(time.time() - start_time)}s (timeout was {timeout_seconds}s)."
                    )
                    break

                # LinkedIn lazy-loader trick: scroll back up halfway, wait, then scroll to bottom again
                # This often triggers LinkedIn to load the next batch of posts
                scroll_back_wait = min(5 + consecutive_no_new_content * 3, 20)
                logger.info(f"Attempting lazy-load trigger: scrolling back up, waiting {scroll_back_wait}s, then re-scrolling down...")
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 2);")
                time.sleep(scroll_back_wait)
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(random.uniform(2, 3))
            else:
                # New content loaded — reset counter
                consecutive_no_new_content = 0
