import os
import sys
import time
import random
from datetime import datetime

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.keys import Keys

from config.settings import LINKEDIN_CONNECT_LOG_FILE
from config.user_profiles import get_selected_user_config, get_global_settings, substitute_template_variables, get_resume_file_path
from core.integrations.selenium_driver import get_driver
from core.storage.database import (
    load_jobs_for_referral,
    add_or_update_referral,
    is_profile_already_contacted,
    load_all_referrals,
    get_company_sent_count,
    update_status_by_id,
    get_employee_outreach_progress,
    clean_company_url
)
from core.logging.config import setup_logger

# Reuse helpers from the main connector module
from pipelines.linkedin_outreach.services.connector import (
    login_to_linkedin,
    review_and_confirm_message
)

logger = setup_logger(LINKEDIN_CONNECT_LOG_FILE)

def get_referral_message(company=None, target_role=None, person_name=None, employee_designation=None, job_url=None):
    try:
        user_conf = get_selected_user_config()
    except Exception:
        user_conf = {}

    profile = user_conf.get("profile", {})
    connect_conf = user_conf.get("linkedin_connect", {})
    referral_conf = user_conf.get("referral_outreach", {})
    
    template = referral_conf.get("message_template")
    if not template:
        template = connect_conf.get("message_template")
    if not template:
        template = "Hi {RECEIVER_NAME},\n\nI hope you're doing well. My sister, {FIRST_NAME}, is interested in a DBA position at {COMPANY}. She has {EXPERIENCE} years of experience.\n\nWould you be willing to refer her?\n\nJob: {JOB_URL}\nResume: {RESUME}\n\nThank you!"

    resume_link = profile.get("resume_url", "")
    
    resolved_person_name = "there"
    if person_name:
        resolved_person_name = person_name.split()[0] if person_name.strip() else "there"

    extra_vars = {
        # uppercase canonical tokens
        "{RECEIVER_NAME}": resolved_person_name,
        "{COMPANY}": company or "the company",
        "{JOB_URL}": job_url or "",
        "{RESUME}": resume_link or "",
        # legacy lowercase aliases for backward compat with existing saved templates
        "{company}": company or "the company",
        "{job_url}": job_url or "",
        "{resume}": resume_link or "",
        "{first_name}": resolved_person_name,
        "{PERSON_NAME}": resolved_person_name,
    }
    
    msg = substitute_template_variables(template, profile, extra_vars)
    return msg.strip()


def find_company_employees_search_url(driver, company_name):
    """Navigates to company page and finds the search URL for its employees."""
    slug = company_name.lower().replace(" ", "-").replace(".", "").replace(",", "")
    url = f"https://www.linkedin.com/company/{slug}/"
    logger.info(f"Navigating directly to company: {url}")
    try:
        driver.get(url)
        time.sleep(4)
    except Exception as e:
        logger.warning(f"Direct navigation failed: {e}")

    # Fallback search if page not found
    if "Page not found" in driver.title or "404" in driver.title or len(driver.find_elements(By.CSS_SELECTOR, ".error-container")) > 0:
        logger.warning(f"Company page for '{slug}' not found. Searching on LinkedIn...")
        search_url = f"https://www.linkedin.com/search/results/companies/?keywords={company_name.replace(' ', '%20')}"
        try:
            driver.get(search_url)
            time.sleep(4)
            first_result = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".entity-result__title-text a"))
            )
            company_url = first_result.get_attribute("href")
            logger.info(f"Found company page via search: {company_url}")
            driver.get(company_url)
            time.sleep(4)
        except Exception as e:
            logger.error(f"Failed to find company page: {e}")
            return None, clean_company_url(driver.current_url)

    # 1. Extract company ID using extremely robust JS
    company_ids_str = None
    try:
        company_ids_str = driver.execute_script(r"""
            const getCompanyIds = () => {
                const extractIds = (href) => {
                    if (!href) return [];
                    try {
                        const url = new URL(href, window.location.origin);
                        
                        // Try currentCompany query parameter
                        const cc = url.searchParams.get('currentCompany');
                        if (cc) {
                            const matches = decodeURIComponent(cc).match(/\d+/g);
                            if (matches) return matches;
                        }
                        
                        // Try f_C query parameter
                        const fc = url.searchParams.get('f_C');
                        if (fc) {
                            const matches = decodeURIComponent(fc).match(/\d+/g);
                            if (matches) return matches;
                        }
                    } catch (e) {}
                    return [];
                };

                // A. Try URL if it already contains a numeric company ID
                const urlMatch = window.location.href.match(/\/company\/(\d+)/);
                if (urlMatch) return [urlMatch[1]];

                // B. Try meta tags (highly reliable, specific to the current page head)
                const metaSelectors = [
                    'meta[property="al:android:url"]',
                    'meta[name="twitter:app:url:iphone"]',
                    'meta[name="twitter:app:url:ipad"]',
                    'meta[name="twitter:app:url:googleplay"]'
                ];
                for (const sel of metaSelectors) {
                    const el = document.querySelector(sel);
                    if (el) {
                        const content = el.getAttribute('content') || '';
                        const match = content.match(/company\/(\d+)/) || content.match(/urn:li:company:(\d+)/);
                        if (match) return [match[1]];
                    }
                }
                
                // C. Try to find the primary "See all employees" / "View all employees" link
                // excluding sidebars/recommendations, and specifically looking for employee/people/connection keywords in the link text
                const links = Array.from(document.querySelectorAll('a[href*="/search/results/people/"]'));
                for (const link of links) {
                    if (link.closest('aside') || link.closest('.org-similar-pages') || link.closest('.org-people-also-viewed') || link.closest('.org-people-also-viewed-module')) {
                        continue;
                    }
                    const text = (link.innerText || link.textContent || '').toLowerCase();
                    if (text.includes('employee') || text.includes('people') || text.includes('connection')) {
                        const ids = extractIds(link.getAttribute('href'));
                        if (ids.length > 0) return ids;
                    }
                }

                // D. Try jobs link with company ID parameter (f_C)
                const jobLinks = Array.from(document.querySelectorAll('a[href*="f_C="]'));
                for (const link of jobLinks) {
                    if (link.closest('aside') || link.closest('.org-similar-pages') || link.closest('.org-people-also-viewed') || link.closest('.org-people-also-viewed-module')) {
                        continue;
                    }
                    const ids = extractIds(link.getAttribute('href'));
                    if (ids.length > 0) return ids;
                }

                // E. Try any link with currentCompany (excluding sidebars)
                for (const link of links) {
                    if (link.closest('aside') || link.closest('.org-similar-pages') || link.closest('.org-people-also-viewed') || link.closest('.org-people-also-viewed-module')) {
                        continue;
                    }
                    const ids = extractIds(link.getAttribute('href'));
                    if (ids.length > 0) return ids;
                }

                // F. Try parsing script tags, looking for companyUniversalId or objectUrn
                const scripts = document.querySelectorAll('script');
                for (const script of scripts) {
                    const text = script.textContent || '';
                    let match = text.match(/"companyUniversalId"\s*:\s*(\d+)/) || text.match(/companyUniversalId\s*:\s*(\d+)/);
                    if (match) return [match[1]];

                    match = text.match(/"objectUrn"\s*:\s*"urn:li:company:(\d+)"/) || text.match(/"urn:li:company:(\d+)"/);
                    if (match) return [match[1]];
                }
                
                return [];
            };
            return getCompanyIds().join(',');
        """)
    except Exception as e:
        logger.warning(f"Error resolving company ID via JS: {e}")

    # Parse company IDs returned from JS
    company_ids = []
    if company_ids_str:
        company_ids = [i.strip() for i in company_ids_str.split(",") if i.strip()]

    # 2. Python-based regex fallback over page source if JS extraction returned nothing
    if not company_ids:
        logger.info("JS company ID extraction returned nothing. Trying Python page source regex fallback...")
        import re
        page_source = driver.page_source or ""
        current_url = driver.current_url or ""
        
        # A. URL numeric check
        url_match = re.search(r'/company/(\d+)', current_url)
        if url_match:
            company_ids = [url_match.group(1)]
            
        # B. companyUniversalId check (high confidence)
        if not company_ids:
            matches = re.findall(r'"companyUniversalId"\s*:\s*(\d+)', page_source) or re.findall(r'companyUniversalId\s*:\s*(\d+)', page_source)
            if matches:
                company_ids = list(set(matches))
                
        # C. f_C (job filter) check (high confidence)
        if not company_ids:
            # Check for direct f_C numbers or encoded ones
            matches = re.findall(r'f_C=(\d+)', page_source) or re.findall(r'f_C=%5B%22(\d+)%22%5D', page_source)
            if matches:
                company_ids = list(set(matches))

        # NOTE: Generic urn:li:company: matches over the whole source are intentionally avoided,
        # as they capture competitor IDs from recommendations / "people also viewed" scripts.

    if company_ids:
        import json
        import urllib.parse
        # Format as encoded JSON array e.g. %5B%228019%22%2C%2276157629%22%5D
        company_ids_param = urllib.parse.quote(json.dumps(company_ids, separators=(',', ':')))
        constructed_url = f"https://www.linkedin.com/search/results/people/?currentCompany={company_ids_param}&network=%5B%22F%22%5D"
        logger.info(f"Successfully resolved company IDs {company_ids} and constructed search URL: {constructed_url}")
        return constructed_url, clean_company_url(driver.current_url)

    # Step 2: Fallback search link parsing (excluding sidebars)
    logger.info("Company ID could not be determined. Searching page links for fallback...")
    search_url = None
    links = driver.find_elements(By.TAG_NAME, "a")
    for link in links:
        try:
            is_sidebar = driver.execute_script("""
                const el = arguments[0];
                return !!(el.closest('aside') || el.closest('.org-similar-pages') || el.closest('.org-people-also-viewed') || el.closest('.org-people-also-viewed-module'));
            """, link)
            if is_sidebar:
                continue
            href = link.get_attribute("href") or ""
            if "/search/results/people/" in href:
                search_url = href
                if "network" in href or "Network" in href:
                    break
        except Exception:
            continue

    if search_url:
        logger.info(f"Discovered employees search URL via page links: {search_url}")
        if "network" not in search_url.lower() and "facetnetwork" not in search_url.lower():
            if "?" in search_url:
                search_url += "&network=%5B%22F%22%5D"
            else:
                search_url += "?network=%5B%22F%22%5D"
        return search_url, clean_company_url(driver.current_url)

    # Step 3: Second fallback: navigate to people tab directly
    people_url = driver.current_url.rstrip("/") + "/people/"
    logger.info(f"Navigating directly to people tab: {people_url}")
    try:
        driver.get(people_url)
        time.sleep(4)
        links = driver.find_elements(By.TAG_NAME, "a")
        for link in links:
            try:
                is_sidebar = driver.execute_script("""
                    const el = arguments[0];
                    return !!(el.closest('aside') || el.closest('.org-similar-pages') || el.closest('.org-people-also-viewed') || el.closest('.org-people-also-viewed-module'));
                """, link)
                if is_sidebar:
                    continue
                href = link.get_attribute("href") or ""
                if "/search/results/people/" in href:
                    search_url = href
                    if "network" in href or "Network" in href:
                        break
            except Exception:
                continue
    except Exception:
        pass

    company_url = clean_company_url(driver.current_url)

    if search_url:
        if "network" not in search_url.lower() and "facetnetwork" not in search_url.lower():
            search_url += "&network=%5B%22F%22%5D"
        return search_url, company_url

    return None, company_url


def scrape_connections_from_search(driver, max_people=5):
    """Scrapes connection details from the search results page."""
    people_connected = []
    try:
        for _ in range(2):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)

        people_cards = driver.find_elements(By.XPATH, "//div[@role='listitem']")
        for card in people_cards:
            if len(people_connected) >= max_people:
                break
            try:
                profile_url = ""
                try:
                    profile_link = card.find_element(By.CSS_SELECTOR, "a[href*='/in/']")
                    profile_url = profile_link.get_attribute("href")
                    if "?" in profile_url:
                        profile_url = profile_url.split("?")[0]
                except Exception:
                    continue

                if not profile_url:
                    continue

                name = ""
                name_selectors = [
                    ".entity-result__title-text span[aria-hidden='true']",
                    ".entity-result__title-text a",
                    ".entity-result__title-text",
                    "span.entity-result__title-line",
                    "a[href*='/in/']"
                ]
                for sel in name_selectors:
                    try:
                        el = card.find_element(By.CSS_SELECTOR, sel)
                        val = el.text.strip()
                        if val:
                            if "•" in val:
                                val = val.split("•")[0].strip()
                            if "\n" in val:
                                val = val.split("\n")[0].strip()
                            name = val
                            break
                    except Exception:
                        continue

                # Fallback 1: Use the profile link's own text
                if not name:
                    try:
                        val = profile_link.text.strip()
                        if val:
                            if "\n" in val:
                                val = val.split("\n")[0].strip()
                            if "•" in val:
                                val = val.split("•")[0].strip()
                            name = val
                    except Exception:
                        pass

                # Fallback 2: Parse from profile URL slug
                if not name:
                    try:
                        slug = profile_url.rstrip("/").split("/in/")[-1].split("?")[0]
                        parts = slug.split("-")
                        if parts and parts[-1].isdigit() and len(parts[-1]) >= 4:
                            parts = parts[:-1]
                        name = " ".join(parts).title()
                    except Exception:
                        name = "LinkedIn Member"

                role = ""
                role_selectors = [
                    ".entity-result__primary-subtitle",
                    ".entity-result__badge-container + div",
                    "div[class*='subtitle']",
                    ".entity-result__summary"
                ]
                for sel in role_selectors:
                    try:
                        el = card.find_element(By.CSS_SELECTOR, sel)
                        val = el.text.strip()
                        if val:
                            role = val
                            break
                    except Exception:
                        continue

                if not role:
                    role = "Employee"

                people_connected.append({
                    'name': name,
                    'designation': role,
                    'profile_url': profile_url
                })
            except Exception as e:
                logger.warning(f"Error parsing connection card: {e}")
        return people_connected
    except Exception as e:
        logger.error(f"Error during card scraping: {e}")
        return []


def open_messaging_from_profile(driver, name=None):
    """Finds and clicks the Message button on the connection's profile page, or focuses if already open."""
    if name:
        logger.info(f"Checking if chat window for '{name}' is already open...")
        try:
            status = driver.execute_script("""
                const nameToFind = arguments[0].toLowerCase();
                const nameParts = nameToFind.split(/\\s+/).filter(Boolean);
                
                const findAndExpand = (root) => {
                    if (!root) return null;
                    const headers = root.querySelectorAll('.msg-overlay-bubble-header, [class*="bubble-header"]');
                    for (const header of headers) {
                        const text = (header.innerText || '').toLowerCase();
                        const matches = nameParts.every(part => text.includes(part)) || text.includes(nameToFind);
                        if (matches) {
                            const bubble = header.closest('.msg-overlay-conversation-bubble, [class*="conversation-bubble"]');
                            if (bubble) {
                                const isMinimized = bubble.classList.contains('msg-overlay-board--minimized') || 
                                                   bubble.getAttribute('aria-expanded') === 'false' ||
                                                   bubble.clientHeight < 100;
                                if (isMinimized) {
                                    header.click();
                                    header.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
                                    return "expanded_now";
                                } else {
                                    return "already_expanded";
                                }
                            } else {
                                if (header.clientHeight > 0) {
                                    return "already_expanded";
                                }
                            }
                        }
                    }
                    return null;
                };
                
                let res = findAndExpand(document);
                if (res) return res;
                
                const host = document.querySelector('#interop-outlet');
                if (host && host.shadowRoot) {
                    res = findAndExpand(host.shadowRoot);
                    if (res) return res;
                }
                return "not_found";
            """, name)
            
            if status == "already_expanded":
                logger.info(f"Chat window for {name} is already open and expanded. Skipping click.")
                return True
            elif status == "expanded_now":
                logger.info(f"Found minimized chat window for {name} and expanded it.")
                time.sleep(2)
                return True
            else:
                logger.info(f"No active chat window found for {name}. Will search for Message button.")
        except Exception as e:
            logger.warning(f"Error checking if chat window was already open: {e}")
            
    logger.info("Searching for Message button on profile page...")
    
    # Wait for the main content block to be present
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//main"))
        )
    except Exception:
        logger.warning("Timed out waiting for main content tag")
        time.sleep(3)
    
    message_selectors = [
        # Scoped to the top-card section inside main content
        "//main//section[contains(@class, 'top-card') or contains(@class, 'profile-card')]//button[contains(., 'Message') or contains(@aria-label, 'Message')]",
        "//main//section[contains(@class, 'top-card') or contains(@class, 'profile-card')]//a[contains(., 'Message') or contains(@aria-label, 'Message') or contains(@href, 'messaging/thread')]",
        
        # Scoped to the first section of main (which is always the top card)
        "//main//section[1]//button[contains(., 'Message') or contains(@aria-label, 'Message')]",
        "//main//section[1]//a[contains(., 'Message') or contains(@aria-label, 'Message') or contains(@href, 'messaging/thread')]",
        
        # Scoped generally to main tag (excludes sidebars/messaging drawers)
        "//main//button[contains(@aria-label, 'Message') or contains(@aria-label, 'message')]",
        "//main//button[contains(., 'Message') or contains(., 'message')]",
        "//main//a[contains(@href, '/messaging/thread/') or contains(@href, 'messaging/thread')]",
        "//main//a[contains(@aria-label, 'Message') or contains(@aria-label, 'message')]",
        "//main//a[contains(., 'Message') or contains(., 'message')]",
        
        # Original general fallbacks
        "button.pvs-profile-actions__action[aria-label*='Message']",
        "//button[contains(@class, 'pvs-profile-actions__action')][span[text()='Message']]",
        "//button[contains(., 'Message') and not(contains(@aria-label, 'Premium'))]"
    ]
    
    # Try finding and clicking
    for sel in message_selectors:
        try:
            if sel.startswith("//"):
                btn = driver.find_element(By.XPATH, sel)
            else:
                btn = driver.find_element(By.CSS_SELECTOR, sel)
                
            if btn:
                logger.info(f"Found Message button candidate with selector: {sel}")
                
                # Scroll into view
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
                time.sleep(1)
                
                # Try standard click
                try:
                    btn.click()
                    logger.info("Clicked Message button successfully via standard click.")
                    time.sleep(3)
                    return True
                except Exception as click_err:
                    logger.info(f"Standard click failed: {click_err}. Trying JS click...")
                    driver.execute_script("arguments[0].click();", btn)
                    logger.info("Clicked Message button successfully via JS click.")
                    time.sleep(3)
                    return True
        except Exception:
            continue
            
    # If we get here, no selectors worked. Log details to debug
    logger.warning("Message button not found. Dumping button and link elements to help debug...")
    try:
        all_buttons = driver.find_elements(By.TAG_NAME, "button")
        logger.info(f"Total buttons found on page: {len(all_buttons)}")
        for b in all_buttons:
            try:
                text = (b.text or "").strip()
                aria = (b.get_attribute("aria-label") or "").strip()
                classes = (b.get_attribute("class") or "").strip()
                if text or aria:
                    logger.info(f"  [BUTTON] Text: '{text}' | Aria-label: '{aria}' | Class: '{classes}'")
            except Exception:
                pass
                
        all_links = driver.find_elements(By.TAG_NAME, "a")
        logger.info(f"Total links found on page: {len(all_links)}")
        for l in all_links:
            try:
                text = (l.text or "").strip()
                aria = (l.get_attribute("aria-label") or "").strip()
                href = (l.get_attribute("href") or "").strip()
                classes = (l.get_attribute("class") or "").strip()
                if "message" in text.lower() or "message" in aria.lower() or "messaging" in href.lower() or "thread" in href.lower():
                    logger.info(f"  [LINK] Text: '{text}' | Aria-label: '{aria}' | Href: '{href}' | Class: '{classes}'")
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"Failed to dump debug elements: {e}")
        
    return False


def insert_message_draft(driver, message):
    """Inserts the message into the overlay chat box and simulates space/backspace to validate draft."""
    try:
        editor = driver.execute_script("""
            const host = document.querySelector('#interop-outlet');
            if (host && host.shadowRoot) {
                const ed = host.shadowRoot.querySelector('.msg-form__contenteditable');
                if (ed) return ed;
            }
            return document.querySelector('.msg-form__contenteditable');
        """)
        
        if not editor:
            logger.error("Message editor contenteditable not found")
            return False
            
        # Focus and click the editor to prepare it
        driver.execute_script("""
            const editor = arguments[0];
            editor.focus();
            editor.click();
        """, editor)
        time.sleep(0.5)
        
        # Clear existing text and paste the new message using execCommand
        driver.execute_script("""
            const editor = arguments[0];
            const text = arguments[1];
            
            // Clear existing text by selecting all (prevents breaking Draft.js DOM nodes)
            document.execCommand('selectAll', false, null);
            document.execCommand('insertText', false, text);
            
            // Dispatch standard input change events
            ['input', 'change', 'keydown', 'keyup', 'keypress'].forEach(eventType => {
                const event = new Event(eventType, { bubbles: true, cancelable: true });
                editor.dispatchEvent(event);
            });
            
            // Dispatch explicit InputEvent
            const inputEvent = new InputEvent('input', {
                bubbles: true,
                cancelable: true,
                inputType: 'insertText',
                data: text
            });
            editor.dispatchEvent(inputEvent);
        """, editor, message)
        time.sleep(1)
        
        # Simulating space and backspace natively via Selenium keys to update Draft.js state
        try:
            editor.send_keys(" ")
            time.sleep(0.5)
            editor.send_keys(Keys.BACKSPACE)
            time.sleep(0.5)
        except Exception as e:
            logger.warning(f"Failed to send native space/backspace: {e}")
            
        editor_text = driver.execute_script("return arguments[0].innerText || arguments[0].textContent;", editor)
        logger.info(f"Draft text in editor is now: '{editor_text[:60].strip()}...'")
        return True
    except Exception as e:
        logger.error(f"Failed to insert message draft: {e}")
        return False


def click_send_message(driver):
    """Finds, enables, and clicks the send button."""
    try:
        editor = driver.execute_script("""
            const host = document.querySelector('#interop-outlet');
            if (host && host.shadowRoot) {
                const ed = host.shadowRoot.querySelector('.msg-form__contenteditable');
                if (ed) return ed;
            }
            return document.querySelector('.msg-form__contenteditable');
        """)
        
        send_button = driver.execute_script("""
            const editor = arguments[0];
            let btn = null;
            if (editor) {
                const form = editor.closest('form') || editor.closest('.msg-convo-wrapper') || editor.closest('.msg-form__container');
                if (form) {
                    btn = form.querySelector('.msg-form__send-button');
                }
            }
            if (!btn) {
                const host = document.querySelector('#interop-outlet');
                if (host && host.shadowRoot) {
                    btn = host.shadowRoot.querySelector('.msg-form__send-button');
                }
            }
            if (!btn) {
                btn = document.querySelector('.msg-form__send-button');
            }
            if (btn) {
                btn.removeAttribute('disabled');
                btn.disabled = false;
            }
            return btn;
        """, editor)
        
        if not send_button:
            logger.error("Send button not found")
            return False
            
        logger.info("Clicking the Send button...")
        try:
            if send_button.is_displayed() and send_button.is_enabled():
                send_button.click()
                logger.info("Clicked Send button via native Selenium click.")
                time.sleep(3)
                return True
        except Exception as sel_err:
            logger.debug(f"Native Selenium click failed: {sel_err}. Trying JavaScript click...")
            
        driver.execute_script("arguments[0].click();", send_button)
        logger.info("Clicked Send button via JavaScript click.")
        time.sleep(3)
        return True
    except Exception as e:
        logger.error(f"Failed to click send button: {e}")
        return False


def upload_resume_attachment(driver, profile):
    """Locates the file input element in the chat overlay and uploads the local resume PDF."""
    try:
        resume_path = get_resume_file_path(profile)
        if not resume_path or not os.path.exists(resume_path):
            logger.warning(f"Local resume file not found at path: {resume_path}. Skipping file upload.")
            return False
            
        logger.info(f"Attempting to upload local resume: {resume_path}")
        
        # Locate the file input element inside the active chat form
        file_input = driver.execute_script("""
            const host = document.querySelector('#interop-outlet');
            let form = null;
            if (host && host.shadowRoot) {
                const ed = host.shadowRoot.querySelector('.msg-form__contenteditable');
                if (ed) form = ed.closest('form');
            }
            if (!form) {
                const ed = document.querySelector('.msg-form__contenteditable');
                if (ed) form = ed.closest('form') || ed.closest('.msg-convo-wrapper') || ed.closest('.msg-form__container');
            }
            if (form) {
                return form.querySelector('input[type="file"]');
            }
            return document.querySelector('.msg-form__footer input[type="file"]') || document.querySelector('input[type="file"].msg-form__attachment-input') || document.querySelector('input[type="file"]');
        """)
        
        if not file_input:
            logger.warning("LinkedIn chat file input element not found.")
            return False
            
        # Send the absolute path of the resume file to the file input
        file_input.send_keys(resume_path)
        logger.info("Resume file path sent to LinkedIn chat file input.")
        time.sleep(3) # Wait for upload to complete
        return True
    except Exception as e:
        logger.warning(f"Error uploading resume attachment: {e}")
        return False


def verify_delivery(driver, sent_text):
    """Verifies that the message appears in the chat thread history."""
    try:
        bubbles = driver.execute_script("""
            const host = document.querySelector('#interop-outlet');
            if (host && host.shadowRoot) {
                return Array.from(host.shadowRoot.querySelectorAll('.msg-s-event-listitem__body, .msg-thread__message-text')).map(el => el.innerText);
            }
            return Array.from(document.querySelectorAll('.msg-s-event-listitem__body, .msg-thread__message-text')).map(el => el.innerText);
        """)
        if not bubbles:
            logger.warning("No message bubbles found to verify.")
            return False
            
        last_messages = bubbles[-3:]
        short_sent = sent_text[:50].strip().lower()
        for msg in last_messages:
            if msg and short_sent in msg.lower():
                logger.info("Delivery verified! Sent message matches chat history.")
                return True
        logger.warning(f"No message matching draft found. Scraped bubbles: {bubbles}")
        return False
    except Exception as e:
        logger.warning(f"Error verifying delivery: {e}")
        return False


def close_chat_window(driver):
    """Closes the overlay chat window."""
    try:
        # Find and click all possible close buttons for chat overlay windows using robust recursive logic and MouseEvent dispatching
        clicked = driver.execute_script("""
            let count = 0;
            const clickElement = (btn) => {
                if (!btn) return;
                try {
                    btn.click();
                } catch(e) {}
                try {
                    btn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
                } catch(e) {}
                count++;
            };
            
            const closeAllInRoot = (root) => {
                if (!root) return;
                const headers = root.querySelectorAll('.msg-overlay-bubble-header, header, [class*="bubble-header"]');
                headers.forEach(header => {
                    const buttons = header.querySelectorAll('button');
                    buttons.forEach(btn => {
                        const ariaLabel = (btn.getAttribute('aria-label') || '').toLowerCase();
                        const btnClass = (btn.className || '').toLowerCase();
                        const innerText = (btn.innerText || '').toLowerCase();
                        const id = (btn.id || '').toLowerCase();
                        
                        let shouldClick = ariaLabel.includes('close') || ariaLabel.includes('dismiss') || ariaLabel.includes('cancel') ||
                                          btnClass.includes('close') || btnClass.includes('dismiss') || btnClass.includes('cancel') ||
                                          id.includes('close') || id.includes('dismiss') || id.includes('cancel') ||
                                          innerText.includes('close') || ariaLabel.includes('conversation');
                                          
                        if (!shouldClick) {
                            const svg = btn.querySelector('svg');
                            if (svg) {
                                const svgClass = (svg.getAttribute('class') || '').toLowerCase();
                                const svgType = (svg.getAttribute('type') || '').toLowerCase();
                                const svgData = (svg.getAttribute('data-type') || '').toLowerCase();
                                const svgTestIcon = (svg.getAttribute('data-test-icon') || '').toLowerCase();
                                
                                let useClose = false;
                                const useEl = svg.querySelector('use');
                                if (useEl) {
                                    const useHref = (useEl.getAttribute('href') || useEl.getAttribute('xlink:href') || '').toLowerCase();
                                    if (useHref.includes('close') || useHref.includes('cancel') || useHref.includes('dismiss')) {
                                        useClose = true;
                                    }
                                }
                                
                                if (svgClass.includes('close') || svgType.includes('close') || svgData.includes('close') || svgTestIcon.includes('close') || useClose ||
                                    svgClass.includes('cancel') || svgType.includes('cancel') || svgTestIcon.includes('cancel') ||
                                    svgClass.includes('x') || svgType.includes('x') || svgTestIcon.includes('x') ||
                                    svgClass.includes('dismiss') || svgType.includes('dismiss') || svgTestIcon.includes('dismiss')) {
                                    shouldClick = true;
                                }
                            }
                        }
                        
                        if (shouldClick) {
                            clickElement(btn);
                        }
                    });
                });
            };
            
            // 1. Close in main document
            closeAllInRoot(document);
            
            // 2. Close in shadow DOM
            const host = document.querySelector('#interop-outlet');
            if (host && host.shadowRoot) {
                closeAllInRoot(host.shadowRoot);
            }
            return count;
        """)
        time.sleep(1)
        if clicked and clicked > 0:
            logger.info(f"Closed {clicked} chat window overlay(s).")
            return True
        else:
            # Fallback: click direct close elements
            clicked_fallback = driver.execute_script("""
                const els = document.querySelectorAll('.msg-overlay-bubble-header__control--close, button[aria-label*="Close conversation"], [data-control-name="close_comparison"]');
                els.forEach(el => {
                    try { el.click(); } catch(e) {}
                    try { el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window })); } catch(e) {}
                });
                return els.length;
            """)
            if clicked_fallback > 0:
                logger.info(f"Closed {clicked_fallback} chat window overlays using fallback.")
                return True
    except Exception as e:
        logger.warning(f"Could not close chat window: {e}")
    return False


# ─────────────────────────────────────────────────────────────
# Step Validation Helpers
# ─────────────────────────────────────────────────────────────

def verify_correct_profile_loaded(driver, expected_url, timeout=12):
    """Polls until the browser URL matches the expected profile URL.
    Returns True when confirmed, False on timeout."""
    clean_expected = expected_url.split("?")[0].rstrip("/")
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            current = driver.current_url.split("?")[0].rstrip("/")
            if clean_expected in current or current in clean_expected:
                logger.info(f"Profile URL verified: {current}")
                return True
        except Exception:
            pass
        time.sleep(0.5)
    logger.warning(f"Profile URL mismatch after {timeout}s. Expected '{clean_expected}', got '{driver.current_url}'.")
    return False


def wait_for_message_dialog(driver, timeout=15):
    """Waits until the LinkedIn message editor (contenteditable) is present
    and visible in the DOM. Returns True when ready, False on timeout."""
    logger.info("Waiting for message dialog/editor to become ready...")
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            editor = driver.execute_script("""
                const host = document.querySelector('#interop-outlet');
                if (host && host.shadowRoot) {
                    const ed = host.shadowRoot.querySelector('.msg-form__contenteditable');
                    if (ed && ed.offsetParent !== null) return ed;
                }
                const ed = document.querySelector('.msg-form__contenteditable');
                if (ed && ed.offsetParent !== null) return ed;
                return null;
            """)
            if editor:
                logger.info("Message dialog is open and editor is ready.")
                return True
        except Exception:
            pass
        time.sleep(0.8)
    logger.warning(f"Message editor did not appear within {timeout}s.")
    return False


def verify_editor_has_text(driver, expected_text, timeout=8):
    """Verifies that the active message editor contains meaningful text from
    expected_text. Guards against the 'pasted into wrong window' bug.
    Returns True if the text is present, False otherwise."""
    # Normalize whitespace in the expected snippet so newline differences
    # between the Python string and the LinkedIn DOM's innerText don't cause false failures.
    import re
    words = re.findall(r'\w+', expected_text)
    # Use first 3 significant words (skip very short words like "Hi") as the check snippet
    sig_words = [w for w in words if len(w) > 2][:3]
    if not sig_words:
        sig_words = words[:5]
    snippet = ' '.join(sig_words).lower()
    
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            editor_text = driver.execute_script("""
                const host = document.querySelector('#interop-outlet');
                if (host && host.shadowRoot) {
                    const ed = host.shadowRoot.querySelector('.msg-form__contenteditable');
                    if (ed) return ed.innerText || ed.textContent || '';
                }
                const ed = document.querySelector('.msg-form__contenteditable');
                return ed ? (ed.innerText || ed.textContent || '') : '';
            """)
            if editor_text:
                # Normalize whitespace in what the DOM gives us too
                normalized_editor = ' '.join(editor_text.lower().split())
                # Check each significant word is present
                if all(w.lower() in normalized_editor for w in sig_words):
                    logger.info("Editor content verified — message is in the correct chat window.")
                    return True
        except Exception:
            pass
        time.sleep(0.5)
    logger.warning(f"Editor does not contain expected words after {timeout}s. Checked words: {sig_words}")
    return False



def wait_for_chat_closed(driver, timeout=6):
    """Waits until no msg-form__contenteditable is visible, confirming the
    chat overlay has fully closed before navigating away."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            visible = driver.execute_script("""
                const host = document.querySelector('#interop-outlet');
                if (host && host.shadowRoot) {
                    const ed = host.shadowRoot.querySelector('.msg-form__contenteditable');
                    if (ed && ed.offsetParent !== null) return true;
                }
                const ed = document.querySelector('.msg-form__contenteditable');
                return !!(ed && ed.offsetParent !== null);
            """)
            if not visible:
                logger.info("Chat overlay confirmed closed.")
                return True
        except Exception:
            pass
        time.sleep(0.5)
    logger.warning("Chat overlay did not close within timeout — continuing anyway.")
    return False
def clean_company_name(name):
    if not name:
        return ""
    import re
    # Lowercase
    name = name.lower()
    # Remove punctuation
    name = re.sub(r'[^\w\s]', ' ', name)
    # Tokenize
    words = name.split()
    # Remove common corporate suffixes
    suffixes = {'inc', 'llc', 'ltd', 'corp', 'corporation', 'gmbh', 'co', 'pvt', 'limited', 'private', 'incorporated'}
    filtered = [w for w in words if w not in suffixes]
    return " ".join(filtered)


# Markers that indicate a person is no longer at the company
_NEGATIVE_COMPANY_MARKERS = [
    'former', 'ex-', ' ex ', 'past ', 'previous', 'retired', 'ex employee',
    'used to work', 'worked at', 'alumnus', 'alumni', 'open to', 'immediate joiner',
    'looking for', 'seeking', 'job search', 'available'
]

# Terms that indicate someone is a job seeker, not a current employee
_JOB_SEEKER_NAME_MARKERS = [
    'immediate joiner', 'open to work', 'open to opportunities', 'looking for',
    'available for', 'actively looking', 'job seeker', 'fresher'
]

def company_names_match(target, extracted):
    """Returns True only when 'extracted' confidently names the same company as 'target'.
    
    Stricter than before:
    - Rejects strings containing ex-employee language (e.g. 'Ex-IBM', 'Former Infosys')
    - Requires significant word overlap with a minimum match score
    - Extracted text must be short enough to be an actual company name (< 80 chars)
    """
    if not target or not extracted:
        return False

    extracted_lower = extracted.lower()

    # Reject immediately if the extracted string contains negative markers
    for marker in _NEGATIVE_COMPANY_MARKERS:
        if marker in extracted_lower:
            return False

    # Extracted text that is too long is not a company name — it's a sentence (headline, bio, etc.)
    if len(extracted.strip()) > 80:
        return False

    target_clean = clean_company_name(target)
    extracted_clean = clean_company_name(extracted)

    if not target_clean or not extracted_clean:
        return False

    # Exact match of cleaned strings
    if target_clean == extracted_clean:
        return True

    # Word token matching — requires ALL target words (>2 chars) to appear in extracted
    target_words = [w for w in target_clean.split() if len(w) > 2]
    extracted_words = set(extracted_clean.split())

    if not target_words or not extracted_words:
        return False

    # All significant target words must be present in the extracted company name
    matched = [w for w in target_words if w in extracted_words]
    if len(matched) == len(target_words) and len(matched) > 0:
        return True

    return False


def is_job_seeker_name(name: str) -> bool:
    """Returns True if the person's display name contains job-seeker language."""
    if not name:
        return False
    name_lower = name.lower()
    return any(marker in name_lower for marker in _JOB_SEEKER_NAME_MARKERS)


def scroll_to_experience_section(driver):
    logger.info("Scrolling page incrementally to trigger lazy loading of experience section...")
    try:
        has_workspace = driver.execute_script("return !!document.getElementById('workspace');")
        if has_workspace:
            for offset in range(400, 3200, 400):
                driver.execute_script(f"const w = document.getElementById('workspace'); if (w) w.scrollTop = {offset};")
                time.sleep(0.5)
        else:
            for offset in range(400, 2600, 400):
                driver.execute_script(f"window.scrollTo(0, {offset});")
                time.sleep(0.5)
    except Exception as se:
        logger.warning(f"Error scrolling workspace/window: {se}")

    try:
        # Also attempt to scroll experience element into view directly if it exists
        driver.execute_script("""
            let exp = document.getElementById('experience');
            if (!exp) {
                const headings = document.querySelectorAll('h2, h3, h4');
                for (const h of headings) {
                    if (h.textContent.trim().toLowerCase() === 'experience') {
                        exp = h;
                        break;
                    }
                }
            }
            if (exp) {
                exp.scrollIntoView({block: 'center'});
            }
        """)
        time.sleep(1)
    except Exception as ee:
        logger.warning(f"Error scrolling experience section element: {ee}")


def extract_active_roles(driver):
    logger.info("Running DOM extraction script on profile...")
    try:
        active_roles = driver.execute_script("""
            const getActiveRoles = () => {
                const activeRoles = [];
                const normalize = (t) => t ? t.trim().replace(/\\s+/g, ' ') : '';
                
                const isDateRange = (line) => {
                    if (!line) return false;
                    const l = line.toLowerCase();
                    return l.includes('present') || 
                           l.match(/^[a-z]{3}\\s\\d{4}/i) || 
                           l.match(/^\\d{4}/) ||
                           l.includes(' - ') ||
                           l.includes(' – ');
                };

                // Find Experience Section
                let expAnchor = document.getElementById('experience');
                if (!expAnchor) {
                    const headings = document.querySelectorAll('h2, h3, h4');
                    for (const h of headings) {
                        if (h.textContent.trim().toLowerCase() === 'experience') {
                            expAnchor = h.closest('section');
                            break;
                        }
                    }
                } else {
                    expAnchor = expAnchor.closest('section');
                }

                if (expAnchor) {
                    // Find all company-related links
                    const links = Array.from(expAnchor.querySelectorAll('a')).filter(a => {
                        return a.href && a.href.includes('/company/') && a.innerText && a.innerText.trim();
                    });

                    const empTypes = ['full-time', 'part-time', 'contract', 'freelance', 'internship', 'apprenticeship', 'self-employed', 'seasonal'];
                    let currentCompany = '';
                    links.forEach(a => {
                        const text = a.innerText.trim();
                        const lines = text.split('\\n').map(l => l.trim()).filter(l => l.length > 0);
                        if (lines.length === 0) return;

                        // Check if it is a company header (e.g. Infosys, Full-time · 3 yrs 2 mos)
                        // It is a company header if NO line matches isDateRange
                        let hasDateRange = false;
                        for (let i = 0; i < lines.length; i++) {
                            if (isDateRange(lines[i])) {
                                hasDateRange = true;
                                break;
                            }
                        }

                        if (!hasDateRange) {
                            currentCompany = lines[0];
                            return;
                        }

                        let title = '';
                        let company = '';
                        let dateRange = '';

                        // Grouped role: Line 0 is title, Line 1 is date range
                        if (isDateRange(lines[1])) {
                            title = lines[0];
                            company = currentCompany;
                            dateRange = lines[1];
                        } 
                        // Grouped role with employment type: Line 0 is title, Line 1 is empType (e.g. Full-time), Line 2 is date range
                        else if (lines.length >= 3 && empTypes.includes(lines[1].toLowerCase().trim())) {
                            title = lines[0];
                            company = currentCompany;
                            dateRange = lines[2];
                        }
                        // Flat role: Line 0 is title, Line 1 is company, Line 2 is date range
                        else if (isDateRange(lines[2])) {
                            title = lines[0];
                            company = lines[1].split(' · ')[0];
                            dateRange = lines[2];
                        }
                        // Fallback: search lines for date range
                        else {
                            title = lines[0];
                            for (let i = 1; i < lines.length; i++) {
                                if (isDateRange(lines[i])) {
                                    dateRange = lines[i];
                                    if (i === 1) {
                                        company = currentCompany;
                                    } else {
                                        company = lines[1].split(' · ')[0];
                                    }
                                    break;
                                }
                            }
                        }

                        if (title && company) {
                            // Only include active roles
                            if (dateRange.toLowerCase().includes('present')) {
                                activeRoles.push({
                                    company: normalize(company),
                                    title: normalize(title),
                                    date_range: normalize(dateRange),
                                    source: 'experience_link_parsed'
                                });
                            }
                        }
                    });
                }
                
                // Fallbacks (top card, etc.)
                // Only use fallback header/panel sources when experience section
                // returned zero results — avoids false positives from bio/headline text
                if (activeRoles.length === 0) {
                    const rightPanelItems = document.querySelectorAll('.pv-text-details__right-panel-item, li.pv-text-details__right-panel-item');
                    rightPanelItems.forEach(el => {
                        const text = normalize(el.innerText || el.textContent);
                        // Only use if reasonably short (actual company name, not a sentence)
                        if (text && text.length > 2 && text.length < 60) {
                            activeRoles.push({
                                company: text,
                                title: '',
                                date_range: 'Present',
                                source: 'header_panel_fallback'
                            });
                        }
                    });

                    const currentCompanyBtn = document.querySelector('button[aria-label*="Current company"]') || 
                                             document.querySelector('[data-field="experience_company_logo"]') ||
                                             document.querySelector('a[data-field="company_link"]');
                    if (currentCompanyBtn) {
                        const text = normalize(currentCompanyBtn.innerText || currentCompanyBtn.textContent);
                        if (text && text.length > 2 && text.length < 60) {
                            activeRoles.push({
                                company: text,
                                title: '',
                                date_range: 'Present',
                                source: 'header_company_button_fallback'
                            });
                        }
                    }
                }

                // NOTE: The top-card blanket text scrape has been intentionally removed.
                // It caused false positives by matching bio/headline text (e.g. "Ex-IBM",
                // "500+ connections") as current company names.

                return activeRoles;
            };
            return getActiveRoles();
        """)
        return active_roles or []
    except Exception as e:
        logger.warning(f"Error executing active roles extractor JS: {e}")
        return []


def go_to_next_page(driver):
    try:
        next_button = driver.execute_script("""
            const btn = document.querySelector('button.artdeco-pagination__button--next') ||
                        document.querySelector('button[aria-label="Next"]') ||
                        document.querySelector('button[data-testid="pagination-controls-next-button"]');
            if (btn) return btn;
            const buttons = Array.from(document.querySelectorAll('button'));
            for (const b of buttons) {
                if (b.innerText && b.innerText.trim().toLowerCase() === 'next') {
                    return b;
                }
            }
            return null;
        """)
        if not next_button:
            return False

        is_disabled = driver.execute_script("return arguments[0].disabled;", next_button)
        if is_disabled:
            return False

        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_button)
        time.sleep(1)
        driver.execute_script("arguments[0].click();", next_button)
        time.sleep(5)
        return True
    except Exception:
        return False


def run_phase_one_discovery():
    """Phase 1: Discover connected 1st-degree employees at target companies."""
    logger.info("=" * 60)
    logger.info("Phase 1: Discovering Connected Employees...")
    logger.info("=" * 60)
    
    user_conf = get_selected_user_config()
    global_conf = get_global_settings()
    connect_conf = user_conf.get("linkedin_connect", {})
    max_referrals = int(connect_conf.get("max_connections_per_company") or connect_conf.get("max_connections_per_run") or 5)
    
    email = global_conf.get("linkedin_email")
    password = global_conf.get("linkedin_password")
    
    job_data = load_jobs_for_referral(status_filter='Interested')
    if not job_data:
        logger.info("No jobs with status 'Interested' found. Nothing to discover.")
        return

    try:
        driver = get_driver()
    except Exception as e:
        logger.error(f"Error starting Chrome: {e}")
        sys.exit(1)

    try:
        driver.get("https://www.linkedin.com/feed/")
        if not login_to_linkedin(driver, email, password):
            logger.error("Failed to login to LinkedIn. Exiting...")
            sys.exit(1)

        for job in job_data:
            company = job.get('CompanyName') or ''
            job_id = job.get('JobID') or ''
            job_url = job.get('ShortenURL') or job.get('CompanyURL') or ''
            
            # Update current Job Lead status to In Progress
            try:
                update_status_by_id(job_id, 'In Progress')
            except Exception as e:
                logger.warning(f"Failed to update status to In Progress: {e}")

            # Check company target connections progress (active connection outreach/discovery count)
            from core.storage.database import get_completed_referral_count, load_all_referrals
            referrals = load_all_referrals()
            completed_progress = get_completed_referral_count(company, job_url, job_id=job_id)
            
            # Count existing pending employee connections in database
            pending_count = sum(
                1 for r_item in referrals
                if str(r_item.get("CompanyName") or "").strip().lower() == company.strip().lower()
                and str(r_item.get("JobID") or "").strip() == str(job_id).strip()
                and str(r_item.get("Referral_Source") or "").strip().lower() in ("existing employee", "sent employee connection")
                and str(r_item.get("Referral_Status") or "").strip().lower() == "pending"
            )
            
            total_exist = completed_progress + pending_count
            
            if completed_progress >= max_referrals:
                logger.info(f"Target connection count of {max_referrals} already reached/completed for {company} (completed progress: {completed_progress}). Skipping discovery.")
                try:
                    update_status_by_id(job_id, 'Referral Outreach Completed')
                except Exception as e:
                    logger.warning(f"Failed to update status to Referral Outreach Completed: {e}")
                continue
                
            if total_exist >= max_referrals:
                logger.info(f"Total existing (completed: {completed_progress} + pending: {pending_count}) already meets target limit of {max_referrals} for {company}. Skipping discovery.")
                continue
                
            remaining_cap = max_referrals - total_exist
            logger.info(f"\nProcessing company: {company} (JobID {job_id}). Remaining discovery capacity: {remaining_cap}")
            
            search_url, actual_company_url = find_company_employees_search_url(driver, company)
            if not search_url:
                logger.warning(f"Could not find employees search link for: {company}. Reverting status to 'Interested' so LinkedIn connector can process it.")
                try:
                    update_status_by_id(job_id, 'Interested')
                except Exception as e:
                    logger.warning(f"Failed to revert status to Interested: {e}")
                continue
                
            if actual_company_url:
                company_url = actual_company_url
                
            driver.get(search_url)
            time.sleep(4)
            
            # Verify if the current company filter is active in the UI
            is_active = driver.execute_script("""
                const el = document.querySelector('[componentkey="SearchResults_filter_pill_currentCompany"]') ||
                           document.querySelector('[aria-label*="Current companies"]');
                if (el) {
                    const txt = (el.innerText || el.textContent || '').trim().toLowerCase();
                    return !txt.includes('current companies') && !txt.includes('current company');
                }
                return false;
            """)
            if not is_active:
                logger.warning("Current Company filter is not active after direct URL navigation. Applying via UI...")
                from pipelines.linkedin_outreach.services.connector import apply_current_company_filter_via_ui
                apply_current_company_filter_via_ui(driver, company)
            
            verified_connections = []
            page_num = 1
            
            while len(verified_connections) < remaining_cap:
                # Scrape candidates on current search page (up to 15 to grab all 10 on page)
                candidates = scrape_connections_from_search(driver, max_people=15)
                if not candidates:
                    logger.info(f"No connections found on page {page_num} for {company}.")
                    break
                    
                logger.info(f"Found {len(candidates)} candidates on page {page_num} for {company}. Starting verification...")
                
                # Check eligibility and verify each candidate one by one
                for conn in candidates:
                    if len(verified_connections) >= remaining_cap:
                        break
                        
                    profile_url = conn['profile_url']
                    
                    if is_profile_already_contacted(profile_url, job_url=job_url):
                        logger.info(f"Connection {conn['name']} already messaged or skipped for job {job_url}. Skipping.")
                        continue
                        
                    # Reject job seekers by name before even visiting profile
                    if is_job_seeker_name(conn['name']):
                        logger.warning(f"⛔ SKIPPED (job seeker name): {conn['name']} — name contains job-seeking language.")
                        continue

                    logger.info(f"Navigating to {conn['name']}'s profile: {profile_url}")
                    try:
                        driver.get(profile_url)
                        time.sleep(3)

                        # Scroll to trigger lazy loading of experience section
                        scroll_to_experience_section(driver)
                        
                        # Extract experience active roles
                        active_roles = extract_active_roles(driver)
                        
                        is_verified = False
                        verified_company = ""
                        verified_designation = conn['designation']
                        
                        for role in active_roles:
                            extracted_comp = role.get('company') or ''
                            if company_names_match(company, extracted_comp):
                                comp_lower = extracted_comp.lower()
                                if any(k in comp_lower for k in ['former', 'ex-', 'ex ', 'past', 'previous', 'retired']):
                                    continue
                                is_verified = True
                                verified_company = extracted_comp
                                if role.get('title'):
                                    verified_designation = role.get('title')
                                break
                                
                        if is_verified:
                            logger.info(f"✅ VERIFIED: {conn['name']} currently works at {verified_company} as {verified_designation}")
                            verified_connections.append({
                                'name': conn['name'],
                                'profile_url': profile_url,
                                'designation': verified_designation,
                                'actual_company': verified_company
                            })
                        else:
                            logger.warning(f"❌ REJECTED: {conn['name']} does NOT currently work at target company {company}. Active roles: {active_roles}")
                    except Exception as pe:
                        logger.error(f"Error checking candidate {conn['name']}'s profile: {pe}")
                        
                # Go back to search and move to next page if capacity not met
                if len(verified_connections) < remaining_cap:
                    logger.info(f"Capacity of {remaining_cap} not met (currently verified: {len(verified_connections)}). Trying next search results page...")
                    driver.get(search_url)
                    time.sleep(4)
                    
                    # Navigate page_num times next
                    current_p = 1
                    navigated_ok = True
                    while current_p <= page_num:
                        if go_to_next_page(driver):
                            current_p += 1
                        else:
                            logger.info("No more search pages available.")
                            navigated_ok = False
                            break
                    if navigated_ok:
                        page_num += 1
                    else:
                        break # exit while loop
            
            # Store all verified connections to database
            discovered_count = 0
            for conn in verified_connections:
                referral_data = {
                    'JobID': job_id,
                    'CompanyName': conn['actual_company'], # actual verified company name
                    'Job_URL': job_url,
                    'Referral_Person_Name': conn['name'],
                    'Referral_Person_Email': '',
                    'Referral_Person_Profile_URL': conn['profile_url'],
                    'Referral_Source': 'Existing Employee',
                    'Referral_Status': 'Pending',
                    'Employment_Verification_Status': 'Verified'
                }
                add_or_update_referral(referral_data)
                discovered_count += 1
                logger.info(f"Discovered and Saved: {conn['name']} - Pending outreach")

            logger.info(f"Found and stored {discovered_count} verified 1st-degree connection contacts for {company}.")

            if discovered_count == 0:
                # No 1st-degree employees found — revert status to 'Interested' so the
                # LinkedIn connector pipeline (run_linkedin_connect.py) can still run
                # and send connection requests to 2nd/3rd-degree people at this company.
                logger.info(
                    f"No verified 1st-degree employees found for {company}. "
                    f"Reverting job status from 'In Progress' → 'Interested' so "
                    f"LinkedIn connector can still process connection requests."
                )
                try:
                    update_status_by_id(job_id, 'Interested')
                except Exception as e:
                    logger.warning(f"Failed to revert status to Interested: {e}")
            time.sleep(2)
            
    except Exception as e:
        logger.error(f"Fatal error in connection discovery: {e}")
        sys.exit(1)
    finally:
        logger.info("Closing browser...")
        driver.quit()


def prompt_referral_action(recipient_name, review_mode=True):
    if not review_mode:
        return "send"

    sys.stdout.write("\n" + "="*50 + "\n")
    sys.stdout.write("INVITE QUALITY GATE - REFERRAL MESSAGE REVIEW\n")
    sys.stdout.write("="*50 + "\n")
    sys.stdout.write(f"Recipient: {recipient_name}\n")
    sys.stdout.write("-" * 50 + "\n")
    sys.stdout.write("Please review the message draft in the LinkedIn chat window.\n")
    sys.stdout.write("="*50 + "\n")
    # This exact string is detected by SubprocessRunner to show the UI quality gate overlay
    sys.stdout.write("Send [S] / Skip [K] / Quit [Q]\n")
    sys.stdout.flush()  # CRITICAL: flush before blocking on input()
    
    choice = sys.stdin.readline().strip().lower()
    while choice not in ('s', 'k', 'q'):
        sys.stdout.write("Invalid option. Please enter Send [S], Skip [K], or Quit [Q]:\n")
        sys.stdout.flush()
        choice = sys.stdin.readline().strip().lower()
        
    if choice == 'k':
        return "skip"
    elif choice == 'q':
        return "quit"
    else:
        return "send"


def run_phase_two_messaging():
    """Phase 2-5: Message pending connections and verify delivery.
    
    Exit codes:
      0 — normal completion
      1 — fatal error
      2 — user requested Quit (stops all remaining pipeline steps)
    """
    logger.info("=" * 60)
    logger.info("Phase 2-5: Sending Referral Messages...")
    logger.info("=" * 60)
    
    user_conf = get_selected_user_config()
    profile = user_conf.get("profile", {})
    global_conf = get_global_settings()
    referral_conf = user_conf.get("referral_outreach", {})
    connect_conf = user_conf.get("linkedin_connect", {})
    # Quality Gate: prefer referral_outreach.review_mode, fall back to linkedin_connect.review_mode
    review_mode = referral_conf.get("review_mode")
    if review_mode is None:
        review_mode = connect_conf.get("review_mode", True)
    review_mode = bool(review_mode)
    interval = int(referral_conf.get("interval") or connect_conf.get("interval") or 5)
    max_referrals = int(connect_conf.get("max_connections_per_company") or connect_conf.get("max_connections_per_run") or 5)
    
    email = global_conf.get("linkedin_email")
    password = global_conf.get("linkedin_password")
    
    logger.info(f"REVIEW_MODE (Quality Gate) : {review_mode}")
    
    all_referrals = load_all_referrals()
    pending = [
        r for r in all_referrals
        if str(r.get('Referral_Status')).strip().lower() == 'pending'
        and not str(r.get('Referral_Source') or '').strip().startswith('Recruiter')
    ]
    
    if not pending:
        logger.info("No pending connections found for outreach.")
        return
        
    logger.info(f"Found {len(pending)} pending connection messages to process.")
    
    try:
        driver = get_driver()
    except Exception as e:
        logger.error(f"Error starting Chrome: {e}")
        sys.exit(1)

    sent_count = 0
    user_quit = False
    try:
        driver.get("https://www.linkedin.com/feed/")
        if not login_to_linkedin(driver, email, password):
            logger.error("Failed to login to LinkedIn. Exiting...")
            sys.exit(1)

        # ── Step 0: Clean up any chat overlays restored by LinkedIn on login ──
        logger.info("Performing initial post-login chat window cleanup...")
        close_chat_window(driver)
        wait_for_chat_closed(driver, timeout=4)
        time.sleep(1)

        # Load ALL job metadata (no status filter) so we resolve job URLs regardless
        # of what status the job was transitioned to during the discovery phase
        job_data = load_jobs_for_referral(status_filter=None)
        job_titles = {str(j.get('JobID')): (j.get('JobTitle') or j.get('SearchKeyword')) for j in job_data}
        job_urls = {str(j.get('JobID')): (j.get('ShortenURL') or j.get('CompanyURL') or '') for j in job_data}

        for idx, ref in enumerate(pending):
            if sent_count >= max_referrals:
                logger.info(f"Max referrals limit of {max_referrals} reached. Stopping.")
                break
                
            ref_id = ref.get('ReferralID')
            job_id = str(ref.get('JobID'))
            company = ref.get('CompanyName')
            
            from core.storage.database import get_completed_referral_count
            job_url = ref.get("Job_URL") or job_urls.get(job_id) or ""
            completed_progress = get_completed_referral_count(company, job_url, job_id=job_id)
            if completed_progress >= max_referrals:
                logger.info(f"Target connection count of {max_referrals} already reached/completed for "
                            f"{company} (completed progress: {completed_progress}). "
                            f"Skipping message to {ref.get('Referral_Person_Name')}.")
                try:
                    update_status_by_id(job_id, 'Referral Outreach Completed')
                except Exception as e:
                    logger.warning(f"Failed to update status: {e}")
                continue
                
            name = ref.get('Referral_Person_Name')
            profile_url = ref.get('Referral_Person_Profile_URL')
            target_role = job_titles.get(job_id) or "DBA"
            
            logger.info("\n" + "=" * 60)
            logger.info(f"[Contact {idx+1}/{len(pending)}] Processing referral message to {name} ({company})")
            logger.info("=" * 60)
            
            # ── Final eligibility check ──────────────────────────────────────
            if is_profile_already_contacted(profile_url, job_url=job_url):
                logger.info(f"Eligibility check: profile already messaged for job {job_url}. Skipping.")
                ref['Referral_Status'] = 'Skipped'
                add_or_update_referral(ref)
                continue

            # ── Step 1: Close ALL open chat overlays for a clean slate ────────
            logger.info("[Step 1] Closing any open chat overlays...")
            close_chat_window(driver)
            wait_for_chat_closed(driver, timeout=5)
            time.sleep(1)

            # ── Step 2: Navigate to profile and verify correct page loaded ────
            logger.info(f"[Step 2] Navigating to profile: {profile_url}")
            driver.get(profile_url)
            time.sleep(3)  # base wait for initial render
            
            if not verify_correct_profile_loaded(driver, profile_url, timeout=12):
                logger.warning(f"[Step 2] Profile URL verification failed for {name}. Skipping.")
                ref['Referral_Status'] = 'Failed'
                ref['Error_Reason'] = 'Profile URL did not load correctly'
                add_or_update_referral(ref)
                close_chat_window(driver)
                continue
            time.sleep(1)  # let the page settle after URL confirmed

            # ── Step 3: Click Message button and wait for dialog to open ─────
            logger.info(f"[Step 3] Opening Message dialog for {name}...")
            if not open_messaging_from_profile(driver, name=name):
                logger.warning(f"[Step 3] Message button not found for {name}.")
                ref['Referral_Status'] = 'Failed'
                ref['Error_Reason'] = 'Message button not found on profile'
                add_or_update_referral(ref)
                close_chat_window(driver)
                continue

            # ── Step 4: Wait for message editor to be ready ──────────────────
            logger.info("[Step 4] Waiting for message editor to be ready...")
            if not wait_for_message_dialog(driver, timeout=15):
                logger.warning(f"[Step 4] Message editor did not appear for {name}.")
                ref['Referral_Status'] = 'Failed'
                ref['Error_Reason'] = 'Message editor did not become available'
                add_or_update_referral(ref)
                close_chat_window(driver)
                wait_for_chat_closed(driver, timeout=4)
                continue
            time.sleep(0.5)  # small buffer before inserting text

            # ── Step 5: Build and insert message draft ───────────────────────
            logger.info("[Step 5] Building and inserting message draft...")
            message_text = get_referral_message(
                company=company,
                target_role=target_role,
                person_name=name,
                job_url=job_url
            )
            if len(message_text) > 2000:
                logger.warning("Message exceeds 2000 characters. Truncating.")
                message_text = message_text[:1997] + "..."
                
            logger.info(f"[OUTREACH] Drafting message to connection {name} (Profile URL: {profile_url})\nMessage:\n{message_text}")
            inserted = insert_message_draft(driver, message_text)
            if not inserted:
                logger.warning(f"[Step 5] Failed to insert message draft for {name}.")
                ref['Referral_Status'] = 'Failed'
                ref['Error_Reason'] = 'Failed to insert text into chat box'
                add_or_update_referral(ref)
                close_chat_window(driver)
                wait_for_chat_closed(driver, timeout=4)
                continue

            # ── Step 6: Verify text is in the CORRECT chat window (non-blocking) ──
            logger.info("[Step 6] Verifying message content in correct chat window...")
            if not verify_editor_has_text(driver, message_text, timeout=8):
                logger.warning(
                    f"[Step 6] Editor text verification could not confirm content for {name}. "
                    "Proceeding to quality gate so you can verify manually."
                )
                # NOTE: non-blocking — we proceed to the quality gate rather than aborting,
                # so the user can visually confirm and choose Send/Skip/Quit.

            # ── Step 7: Upload resume attachment (optional) ──────────────────
            logger.info("[Step 7] Attempting resume attachment upload...")
            attachment_ok = upload_resume_attachment(driver, profile)
            if attachment_ok:
                logger.info("[Step 7] Resume attached successfully. Waiting for upload to settle...")
                time.sleep(2)
            else:
                logger.info("[Step 7] No resume attachment (file not configured or not found).")

            # ── Step 8: Verify all fields populated (log only, non-blocking) ─
            logger.info("[Step 8] Final pre-send verification...")
            final_editor_ok = verify_editor_has_text(driver, message_text, timeout=5)
            if not final_editor_ok:
                logger.warning("[Step 8] Pre-send editor check failed. Proceeding with caution.")

            # ── Step 9: Quality Gate ─────────────────────────────────────────
            action = prompt_referral_action(name, review_mode=review_mode)
            
            if action == "skip":
                logger.info(f"[Quality Gate] Skipped referral to {name}.")
                ref['Referral_Status'] = 'Skipped'
                add_or_update_referral(ref)
                close_chat_window(driver)
                wait_for_chat_closed(driver, timeout=5)
                logger.info("Chat closed. Moving to next contact.")
                continue

            elif action == "quit":
                logger.info("[Quality Gate] User selected Quit. Stopping pipeline.")
                try:
                    update_status_by_id(job_id, 'Cancelled')
                except Exception as e:
                    logger.warning(f"Failed to update Job status to Cancelled: {e}")
                close_chat_window(driver)
                user_quit = True
                break

            # ── Step 10: Send message ────────────────────────────────────────
            logger.info("[Step 10] Sending message...")
            sent = click_send_message(driver)
            if sent:
                time.sleep(2)  # let LinkedIn process the send
                # ── Step 11: Verify delivery ─────────────────────────────────
                logger.info("[Step 11] Verifying message delivery...")
                verified = verify_delivery(driver, message_text)
                if verified:
                    logger.info(f"[Step 11] Message to {name} (Profile URL: {profile_url}) confirmed in chat history and successfully sent!")
                    ref['Referral_Status'] = 'Sent'
                    ref['Sent_Time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    ref['Error_Reason'] = ''
                    sent_count += 1
                else:
                    logger.warning(f"[Step 11] Delivery not confirmed in chat history for {name}.")
                    ref['Referral_Status'] = 'Failed'
                    ref['Error_Reason'] = 'Message clicked but did not appear in chat history'
            else:
                logger.warning(f"[Step 10] Send button click failed for {name}.")
                ref['Referral_Status'] = 'Failed'
                ref['Error_Reason'] = 'Failed to click send button'
                
            add_or_update_referral(ref)

            # ── Step 12: Close chat and wait for stable state ─────────────────
            logger.info("[Step 12] Closing chat window and returning to stable state...")
            close_chat_window(driver)
            wait_for_chat_closed(driver, timeout=6)
            
            logger.info(f"Referrals sent this run: {sent_count}/{max_referrals}")
            if idx < len(pending) - 1 and sent_count < max_referrals and not user_quit:
                logger.info(f"Waiting {interval}s before next contact...")
                time.sleep(interval)

    except SystemExit:
        # Re-raise SystemExit so exit codes propagate correctly through the runner
        raise
    except Exception as e:
        logger.error(f"Fatal error in connection outreach: {e}")
        sys.exit(1)
    finally:
        logger.info("Closing browser...")
        try:
            driver.quit()
        except Exception:
            pass

    # ── Post-run job status updates ─────────────────────────────────────────
    # For each distinct job that had messages sent this run, advance its status
    # from 'In Progress' → 'Asked for Referral' so no job stays stuck.
    try:
        sent_job_ids = set(
            str(r.get('JobID')) for r in pending
            if str(r.get('Referral_Status', '')).strip().lower() == 'sent'
        )
        for jid in sent_job_ids:
            try:
                update_status_by_id(jid, 'Asked for Referral')
                logger.info(f"Job {jid}: status updated to 'Asked for Referral' after referral messages sent.")
            except Exception as e:
                logger.warning(f"Failed to update status for job {jid}: {e}")
    except Exception as e:
        logger.warning(f"Post-run job status update failed: {e}")

    # ── Propagate Quit as exit code 2 ─────────────────────────────────────────
    # Exit code 2 is the contract with SubprocessRunner: non-zero stops the
    # pipeline step chain immediately, preventing any further pipeline scripts
    # from launching (whether this is an individual run or Run Complete Pipeline).
    if user_quit:
        logger.info("Exiting with code 2 — pipeline stopped by user Quit action.")
        sys.exit(2)
