from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import time
import json
import os
from datetime import datetime
from dotenv import load_dotenv

# ============== CONFIG ==============

load_dotenv()

LINKEDIN_EMAIL = os.getenv("LINKEDIN_EMAIL")
LINKEDIN_PASSWORD = os.getenv("LINKEDIN_PASSWORD")

SEARCH_URL = "https://www.linkedin.com/jobs/search-results/?keywords=Software%20engineer&origin=JOB_SEARCH_PAGE_JOB_FILTER&referralSearchId=sqKqYrh1BjUqO3zSCaTNnw%3D%3D&f_TPR=r86400&f_SAL=f_SA_id_230001%3A289003%24f_SA_id_227001%3A276001%24f_SA_id_226001%3A272015"
# SEARCH_URL = "https://www.linkedin.com/jobs/search-results/?keywords=Software%20engineer&origin=JOB_SEARCH_PAGE_JOB_FILTER&referralSearchId=DRhB8s0S%2BwF%2Bt1cpjk%2Fi%2BA%3D%3D&f_TPR=r604800&f_SAL=f_SA_id_230001%3A289003%24f_SA_id_227001%3A276001%24f_SA_id_226001%3A272015"
# SEARCH_URL = "https://www.linkedin.com/jobs/search/?currentJobId=4423202659&f_E=2&f_F=it%2Ceng&f_I=6%2C96%2C4&f_JT=F&f_T=9%2C25201%2C30128%2C340%2C2732&f_TPR=r86400&origin=JOB_SEARCH_PAGE_JOB_FILTER&sortBy=DD"

OUTPUT_FILE = "linkedin_jobs.json"

# ============== DRIVER SETUP ==============

options = Options()

options.add_argument("--remote-debugging-port=9222")
options.add_argument(r"--user-data-dir=C:\selenium-chrome-profile")

driver = webdriver.Chrome(options=options)

driver.maximize_window()

# ============== HELPERS ==============

import re

NEGATIVE_PATTERNS = [
    # seniority
    r"\bstaff\b",
    r"\bprincipal\b",
    r"\blead\b",
    r"\barchitect\b",
    r"\biii\b",
    r"\biv\b",
    r"\bsoftware engineer iii\b",
    r"\bprincipal\b"

    # infra / devops / platform / intern / QA
    r"\bdevops\b",
    r"\bqa\b",
    r"\bcloud platform\b",
    r"\binfrastructure\b",
    r"\bautomation\b",
    r"\btool chain\b",
    r"\beai\b",
    r"\bapim\b",
    r"\binternship\b",
    r"\bintern\b",
    r"\binterns\b",
    r"\bpresident\b",
    r"\bdirector\b",
    r"\btest\b"
]

POSITIVE_PATTERNS = [
    r"\bbackend\b",
    r"\bfull stack\b",
    r"\bsoftware engineer i\b",
    r"\bsde i\b",
    r"\bassociate engineer\b",
    r"\bjava\b",
    r"\bnodejs\b",
    r"\bnode\b",
    r"\bspring\b",
]

def normalize_text(*parts):
    return " ".join(
        p.strip() for p in parts if isinstance(p, str) and p.strip()
    ).lower()

def matches_any(text, patterns):
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)

def should_mark_not_applicable(company, position):
    text = normalize_text(company, position)

    if not text:
        return False, "empty title/company"

    negative_hit = matches_any(text, NEGATIVE_PATTERNS)
    positive_hit = matches_any(text, POSITIVE_PATTERNS)

    if negative_hit and not positive_hit:
        return True, "matched negative pattern"

    return False, ""

def check_validation_errors(driver):

    import threading

    error_count = driver.execute_script("""
        const host = document.querySelector('#interop-outlet');

        if (!host || !host.shadowRoot) {
            return 0;
        }

        const root = host.shadowRoot;

        return root.querySelectorAll(
            "li-icon[type='error-pebble-icon']"
        ).length;
    """)

    print(f"Validation error count: {error_count}")

    if error_count > 0:

        print("\nValidation errors detected.")
        print("Complete the required fields manually.")
        print("Press ENTER within 3 minutes to continue automation.")
        print("If no input is received, the job will automatically be saved.\n")

        user_responded = False

        def wait_for_input():

            nonlocal user_responded

            input(
                "Press ENTER after completing the review step... "
            )

            user_responded = True

        input_thread = threading.Thread(
            target=wait_for_input
        )

        input_thread.daemon = True
        input_thread.start()

        input_thread.join(timeout=3*60)

        if user_responded:

            print(
                "User completed review step. Continuing automation..."
            )

            return False

        else:

            print(
                "No input received within 2 minutes."
            )

            print(
                "Saving job automatically..."
            )

            return True

    return False


def handle_easy_apply(
    driver,
    company,
    position,
    current_page_url
):

    position = position.replace("(Verified job)", "").strip()

    should_save = False

    for _ in range(10):

        time.sleep(2)

        # =========================================================
        # NEXT BUTTON
        # =========================================================

        try:

            next_button = driver.execute_script("""
                const host = document.querySelector('#interop-outlet');

                if (!host) {
                    return document.querySelector(
                        'button[aria-label*="Continue to next step"]'
                    );
                }

                const root = host.shadowRoot;

                if (!root) {
                    return document.querySelector(
                        'button[aria-label*="Continue to next step"]'
                    );
                }

                return root.querySelector(
                    'button[aria-label*="Continue to next step"]'
                );
            """)

            if next_button:

                print("Next button found")

                driver.execute_script("""
                    arguments[0].click();
                """, next_button)

                time.sleep(3)

                should_save = check_validation_errors(driver)

                if should_save:
                    break

                continue

        except Exception as e:

            print(f"Next button error: {str(e)}")

        # =========================================================
        # REVIEW BUTTON
        # =========================================================

        try:

            review_button = driver.execute_script("""
                const host = document.querySelector('#interop-outlet');

                if (!host) {
                    return document.querySelector(
                        'button[aria-label*="Review your application"]'
                    );
                }

                const root = host.shadowRoot;

                if (!root) {
                    return document.querySelector(
                        'button[aria-label*="Review your application"]'
                    );
                }

                return root.querySelector(
                    'button[aria-label*="Review your application"]'
                );
            """)

            if review_button:

                print("Review button found")

                driver.execute_script("""
                    arguments[0].click();
                """, review_button)

                time.sleep(3)

                should_save = check_validation_errors(driver)

                if should_save:
                    break

                continue

        except Exception as e:

            print(f"Review button error: {str(e)}")

        # =========================================================
        # SUBMIT BUTTON
        # =========================================================

        try:

            submit_button = driver.execute_script("""
                const host = document.querySelector('#interop-outlet');

                if (!host) {
                    return document.querySelector(
                        'button[aria-label*="Submit application"]'
                    );
                }

                const root = host.shadowRoot;

                if (!root) {
                    return document.querySelector(
                        'button[aria-label*="Submit application"]'
                    );
                }

                return root.querySelector(
                    'button[aria-label*="Submit application"]'
                );
            """)

            if submit_button:

                print("Submit application button found")

                driver.execute_script("""
                    arguments[0].click();
                """, submit_button)

                time.sleep(3)

                should_save = check_validation_errors(driver)

                if should_save:
                    break

                should_save = False

                print("Application submitted successfully")

                break

        except Exception as e:

            print(f"Submit button error: {str(e)}")

        print("No Next / Review / Submit button found")

        break

    # =========================================================
    # SAVE JOB
    # =========================================================

    if should_save:

        save_job({
            "type": "easy_apply",
            "url": current_page_url,
            "company": company,
            "position": position,
            "saved_at": datetime.now().isoformat(),
            "status": "Pending"
        })

        print("Saved Easy Apply job")

    # =========================================================
    # CLOSE MODAL
    # =========================================================

    try:

        dismiss_button = driver.execute_script("""
            const host = document.querySelector('#interop-outlet');

            if (!host) {
                return document.querySelector(
                    'button[aria-label*="Dismiss"]'
                );
            }

            const root = host.shadowRoot;

            if (!root) {
                return document.querySelector(
                    'button[aria-label*="Dismiss"]'
                );
            }

            return root.querySelector(
                'button[aria-label*="Dismiss"]'
            );
        """)

        if dismiss_button:

            driver.execute_script("""
                arguments[0].click();
            """, dismiss_button)

            time.sleep(1)

    except Exception as e:

        print(f"Dismiss modal error: {str(e)}")

    return True

def wait_for_page(seconds=5):
    time.sleep(seconds)

def save_job(data):

    jobs = []

    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                jobs = json.load(f)
        except:
            jobs = []

    existing_urls = []
    for job in jobs:

        url = job.get("url")

        if url:
            existing_urls.append(url)

    if data["url"] not in existing_urls:

        jobs.append(data)

        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(jobs, f, indent=4)

        print(f"Saved job: {data['url']}")

    else:
        print("Job already exists. Skipping.")

def get_job_cards(driver):

    print("Loading job cards...")

    all_cards = []

    previous_count = 0

    for _ in range(15):

        driver.execute_script("""
            const jobsPane = document.querySelector('.jobs-search-results-list');

            if (jobsPane) {
                jobsPane.scrollTop = jobsPane.scrollHeight;
            } else {
                window.scrollBy(0, 1200);
            }
        """)

        time.sleep(2)

        cards = driver.find_elements(
            By.CSS_SELECTOR,
            'div[role="button"][componentkey*="job-card-component-ref"]'
        )

        print(f"Currently visible cards: {len(cards)}")

        if len(cards) == previous_count:
            break

        previous_count = len(cards)

        all_cards = cards

    print(f"Final cards found: {len(all_cards)}")

    return all_cards


def is_job_already_processed(company, position):
    """Check if job already exists in JSON file"""
    try:
        if not os.path.exists(OUTPUT_FILE):
            return False
        
        with open(OUTPUT_FILE, 'r') as f:
            existing_jobs = json.load(f)
        
        # Create unique identifier
        job_signature = f"{company.lower().strip()}|{position.lower().strip()}"
        
        for job in existing_jobs:
            existing_signature = f"{job['company'].lower().strip()}|{job['position'].lower().strip()}"
            if existing_signature == job_signature:
                return True
        
        return False
        
    except Exception as e:
        print(f"Error checking duplicates: {str(e)}")
        return False

def go_to_next_jobs_page(driver):

    try:

        print("Trying to move to next jobs page...")

        next_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((
                By.CSS_SELECTOR,
                'button[data-testid="pagination-controls-next-button-visible"], button[data-testid="pagination-controls-next-button"]'
            ))
        )

        disabled = driver.execute_script("""
            return arguments[0].disabled ||
                   arguments[0].getAttribute('disabled') !== null;
        """, next_button)

        if disabled:
            print("Next page button disabled")
            return False

        driver.execute_script("""
            arguments[0].scrollIntoView({
                block: 'center'
            });
        """, next_button)

        time.sleep(1)

        driver.execute_script("""
            arguments[0].click();
        """, next_button)

        print("Moved to next jobs page")

        time.sleep(6)

        return True

    except Exception as e:

        print(f"Could not move to next page: {str(e)}")

        return False

def process_current_job(
    driver,
    company,
    position
):
    current_page_url = driver.current_url

    # cleanup title
    position = position.replace("(Verified job)", "").strip()

    apply_selectors = [
        "a[aria-label*='Apply on company website']",
        "a[href*='linkedin.com/safety/go']",
    ]

    easy_apply_selectors = [
        "a[aria-label*='Easy Apply']",
        "button[aria-label*='Easy Apply']",
    ]

    # ========== EXTERNAL APPLY ==========

    for selector in apply_selectors:

        try:

            apply_button = driver.find_element(
                By.CSS_SELECTOR,
                selector
            )

            apply_url = apply_button.get_attribute("href")

            print(f"Opening external apply link: {apply_url}")

            original_tab = driver.current_window_handle

            driver.execute_script("""
                window.open(arguments[0], '_blank');
            """, apply_url)

            time.sleep(3)

            driver.switch_to.window(driver.window_handles[-1])

            time.sleep(5)

            external_url = driver.current_url

            save_job({
                "type": "external_apply",
                "url": external_url,
                "company": company,
                "position": position,
                "saved_at": datetime.now().isoformat(),
                "status": "Pending"
            })

            driver.close()

            driver.switch_to.window(original_tab)

            print("Closed external tab and switched back")

            return True

        except NoSuchElementException:
            continue

        except Exception as e:

            print(f"External apply failed: {str(e)}")

            continue

    # ========== EASY APPLY ==========

    for selector in easy_apply_selectors:

        try:

            easy_apply_button = driver.find_element(
                By.CSS_SELECTOR,
                selector
            )

            print("Found Easy Apply")

            driver.execute_script("""
                arguments[0].click();
            """, easy_apply_button)

            time.sleep(3)

            handle_easy_apply(
                driver,
                company,
                position,
                current_page_url
            )

            return True

        except NoSuchElementException:
            continue

    print("No apply button found")

    return False
# ============== MAIN ==============

driver.get(SEARCH_URL)

print("Waiting for LinkedIn jobs page to load...")

wait_for_page(8)

# ===== CLICK DURATION FILTER =====
selectors = [
    'div[aria-label="Filter by Past 24 hours"]',
    'div[aria-label="Filter by Past week"]',
    'div[aria-label="Filter by Past month"]'
]

filter_clicked = False

for selector in selectors:

    try:

        print(f"Checking selector: {selector}")

        duration = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((
                By.CSS_SELECTOR,
                selector
            ))
        )

        driver.execute_script("""
            arguments[0].scrollIntoView({
                block: 'center'
            });
        """, duration)

        time.sleep(1)

        driver.execute_script("""
            arguments[0].click();
        """, duration)

        print(f"Clicked filter using selector: {selector}")

        filter_clicked = True

        break

    except NoSuchElementException:

        print(f"Selector not found: {selector}")

    except Exception as e:

        print(f"Failed with selector {selector}: {str(e)}")

if not filter_clicked:

    print("Could not click any duration filter")

wait_for_page(4)

# ===== CLICK SHOW RESULTS =====

try:

    show_results = WebDriverWait(driver, 15).until(
        EC.element_to_be_clickable((
            By.XPATH,
            "//a[.//span[contains(text(),'Show results')]]"
        ))
    )

    driver.execute_script("""
        arguments[0].scrollIntoView({
            block: 'center'
        });
    """, show_results)

    time.sleep(1)

    driver.execute_script("""
        arguments[0].click();
    """, show_results)

    print("Clicked Show Results")

except Exception as e:

    print(f"Could not click Show Results: {str(e)}")

wait_for_page(2)

page_no = 1

while True:

    print("=" * 60)
    print(f"Processing jobs page {page_no}")
    print("=" * 60)

    job_cards = get_job_cards(driver)

    if not job_cards:

        print("No jobs found on current page")

        break

    print(f"Found {len(job_cards)} jobs on page {page_no}")

    for index in range(len(job_cards)):

        try:

            # refresh elements every loop
            job_cards = driver.find_elements(
                By.CSS_SELECTOR,
                'div[role="button"][componentkey*="job-card-component-ref"]'
            )

            if index >= len(job_cards):
                break

            card = job_cards[index]

            driver.execute_script("""
                arguments[0].scrollIntoView({
                    block: 'center'
                });
            """, card)

            time.sleep(2)

            company = ""
            position = ""

            # ===== JOB URL =====

            try:

                job_link = card.find_element(
                    By.CSS_SELECTOR,
                    "a[href*='/jobs/view/']"
                )

            except Exception as e:

                print("Could not get URL:", e)

            # ===== POSITION =====

            position = ""

            try:
                # first meaningful title span inside card
                title_el = card.find_element(
                    By.CSS_SELECTOR,
                    'p span[aria-hidden="true"]'
                )

                position = title_el.text.strip()

                # remove verified badge text if present
                position = position.replace("(Verified job)", "").strip()

            except Exception as e:
                print("Could not get position:", e)

            # ===== COMPANY =====

            company = ""

            try:
                company_el = card.find_element(
                    By.XPATH,
                    './/div[@data-display-contents="true"]/following-sibling::div[1]//p'
                )

                company = company_el.text.strip()

            except Exception as e:
                print("Could not get company:", e)

            print("Position:", position)
            print("Company:", company)
            
            skip, reason = should_mark_not_applicable(company, position)
            if skip:
                print(f"Skipping early as Not Applicable: {reason}")
                continue

            if is_job_already_processed(company, position):
                print("Job already processed. Skipping.")
                continue
            
            driver.execute_script("""
                arguments[0].click();
            """, card)

            print(f"Opened job {index + 1} on page {page_no}")

            # give LinkedIn time to render right panel
            time.sleep(3)

            # wait until Apply / Easy Apply button appears
            try:

                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((
                        By.CSS_SELECTOR,
                        """
                        a[aria-label*='Easy Apply'],
                        button[aria-label*='Easy Apply'],
                        a[aria-label*='Apply on company website'],
                        a[href*='linkedin.com/safety/go']
                        """
                    ))
                )

                print("Apply section loaded")

            except Exception:

                print("Apply buttons not loaded yet")

            # additional stability delay
            time.sleep(2)

            process_current_job(
                driver,
                company,
                position
            )

            time.sleep(2)

        except Exception as e:

            print(f"Error processing job {index + 1}: {str(e)}")

            continue

    moved = go_to_next_jobs_page(driver)

    if not moved:

        print("No more pages left")

        break

    page_no += 1

print("Done processing jobs")

input("\nPress ENTER to close browser...")