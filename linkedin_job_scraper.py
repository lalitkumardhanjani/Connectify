import time
import re
import threading
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from linkedin_job_driver import wait_for_page

def get_job_cards(driver):
    print("Loading job cards...")
    
    # Use a set to track processed jobs to handle duplicates during scrolling
    processed_job_ids = set()
    
    # Try to locate the scrollable container
    scrollable_container = None
    try:
        scrollable_container = driver.find_element(By.CSS_SELECTOR, '.jobs-search-results-list')
    except:
        pass

    for _ in range(8):
        if scrollable_container:
            driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", scrollable_container)
        else:
            driver.execute_script("window.scrollBy(0, window.innerHeight);")
            
        time.sleep(1.5)

    raw_jobs = driver.execute_script("""
        const nodes = Array.from(document.querySelectorAll(
            'li.jobs-search-results__list-item, div.job-card-container, div.job-card-list__item, div.job-card-square__content, div.result-card, ul.jobs-search__results-list li, div.jobs-search-results__list-item, .base-card'
        ));

        const seen = new Set();
        const jobs = [];

        nodes.forEach(node => {
            const link = node.querySelector('a[href*="/jobs/view/"]');
            if (!link) {
                return;
            }

            const url = link.href.split('?')[0];
            const jobIdMatch = url.match(/\/jobs\/view\/(\d+)/);
            const job_id = jobIdMatch ? jobIdMatch[1] : '';

            if (!job_id || seen.has(job_id)) {
                return;
            }

            seen.add(job_id);

            const title = (link.innerText || link.textContent || '').trim();
            const companyEl = node.querySelector(
                'a[href*="/company/"], a.job-card-container__company-name, a.job-card-list__company-name, span.job-card-container__company-name, span.base-search-card__subtitle, .artdeco-entity-lockup__subtitle'
            );
            const locationEl = node.querySelector(
                'span.job-card-container__metadata-item, span.job-card-list__location, div.job-card-container__company-location, .job-card-container__location, .job-card-list__location, .base-search-card__location, .artdeco-entity-lockup__caption'
            );
            const dateEl = node.querySelector(
                'time, span.job-card-container__listed-time, span.job-card-list__footer-wrapper, .job-card-container__listed-time'
            );

            jobs.push({
                url,
                job_id,
                title,
                company: companyEl ? companyEl.innerText.trim() : '',
                location: locationEl ? locationEl.innerText.trim() : '',
                date_posted: dateEl ? dateEl.innerText.trim() : ''
            });
        });

        return jobs;
    """)

    print(f"Found {len(raw_jobs)} job cards")
    return raw_jobs

def extract_job_info(card):
    if isinstance(card, dict):
        return {
            "url": card.get("url", ""),
            "company": card.get("company", ""),
            "position": card.get("title", "")
        }

    title = ""
    company = ""
    location = ""
    date_posted = ""
    job_url = ""

    try:
        link_el = card.find_element(
            By.CSS_SELECTOR,
            'a[href*="/jobs/view/"], a.job-card-list__title, a.job-card-container__link'
        )
        job_url = link_el.get_attribute("href") or ""
        title = link_el.text.strip() or title
    except Exception:
        pass

    try:
        company_el = card.find_element(
            By.CSS_SELECTOR,
            'a.job-card-container__company-name, a.job-card-list__company-name, span.job-card-container__company-name'
        )
        company = company_el.text.strip()
    except Exception:
        pass

    try:
        location_el = card.find_element(
            By.CSS_SELECTOR,
            'span.job-card-container__metadata-item, span.job-card-list__location, div.job-card-container__metadata-item'
        )
        location = location_el.text.strip()
    except Exception:
        pass

    try:
        date_el = card.find_element(
            By.CSS_SELECTOR,
            'time, span.job-card-container__listed-time, span.job-card-list__footer-wrapper'
        )
        date_posted = date_el.text.strip()
    except Exception:
        pass

    if not title:
        try:
            title = card.text.splitlines()[0].strip()
        except Exception:
            title = title

    return {
        "url": job_url,
        "company": company,
        "position": title
    }

def find_external_apply_url(driver):
    return driver.execute_script("""
        const textMatches = (el) => {
            const text = (el.innerText || el.getAttribute('aria-label') || '').toLowerCase();
            return text.includes('apply') && !text.includes('easy apply');
        };

        const links = Array.from(document.querySelectorAll('a'));
        for (const link of links) {
            const href = link.href || link.getAttribute('href') || '';
            if (!href) {
                continue;
            }
            const text = (link.innerText || link.getAttribute('aria-label') || '').toLowerCase();
            if (!textMatches(link)) {
                continue;
            }
            // prefer non-linkedin external hrefs
            if (href && !href.includes('linkedin.com')) {
                return href;
            }
            if (href.includes('/safety/go') || href.includes('/jobdesc') || href.includes('career.') || href.includes('externalcareers') || href.includes('careers-') || href.includes('apply')) {
                return href;
            }
        }

        const buttons = Array.from(document.querySelectorAll('button'));
        for (const button of buttons) {
            const text = (button.innerText || button.getAttribute('aria-label') || '').toLowerCase();
            if (text.includes('apply') && !text.includes('easy apply')) {
                const onclick = button.getAttribute('onclick') || '';
                const dataHref = button.getAttribute('data-href') || '';
                if (dataHref) {
                    return dataHref;
                }
                if (onclick) {
                    const match = onclick.match(/['\"]([^'\"]*apply[^'\"]+)['\"]/i);
                    if (match) {
                        return match[1];
                    }
                }
            }
        }

        return null;
    """)

def go_to_next_jobs_page(driver):
    try:
        print("Trying to move to next jobs page...")
        try:
            next_button = WebDriverWait(driver, 6).until(
                EC.element_to_be_clickable((
                    By.CSS_SELECTOR,
                    'button.artdeco-pagination__button--next, button[aria-label="Next"], button[data-testid="pagination-controls-next-button-visible"], button[data-testid="pagination-controls-next-button"]'
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
                arguments[0].scrollIntoView({ block: 'center' });
            """, next_button)

            time.sleep(0.8)
            driver.execute_script("arguments[0].click();", next_button)
            print("Moved to next jobs page (primary selector)")
            time.sleep(6)
            return True
        except Exception:
            pass

        try:
            next_candidate = driver.execute_script(r"""
                const els = Array.from(document.querySelectorAll('a, button'));
                for (const el of els) {
                    const txt = (el.innerText || el.getAttribute('aria-label') || '').toLowerCase().trim();
                    if (!txt) continue;
                    if (txt === 'next' || txt.startsWith('next ') || txt.includes('next')) {
                        const disabled = el.disabled || el.getAttribute('aria-disabled') === 'true' || el.className.indexOf('disabled')!==-1;
                        if (disabled) continue;
                        return el;
                    }
                }
                return null;
            """)

            if next_candidate:
                try:
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'})", next_candidate)
                    time.sleep(0.6)
                    driver.execute_script("arguments[0].click();", next_candidate)
                    print("Moved to next jobs page (text-based fallback)")
                    time.sleep(6)
                    return True
                except Exception as e:
                    print(f"Fallback click failed: {str(e)}")
        except Exception:
            pass

        print("No Next button found via selectors or text-based fallback")
        return False

    except Exception as e:
        print(f"Could not move to next page: {str(e)}")
        return False

def check_validation_errors(driver):
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
            input("Press ENTER after completing the review step... ")
            user_responded = True

        input_thread = threading.Thread(target=wait_for_input)
        input_thread.daemon = True
        input_thread.start()
        input_thread.join(timeout=3*60)

        if user_responded:
            print("User completed review step. Continuing automation...")
            return False
        else:
            print("No input received within 2 minutes.")
            print("Saving job automatically...")
            return True

    return False
