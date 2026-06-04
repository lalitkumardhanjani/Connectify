import json
from selenium.webdriver.chrome.options import Options
from selenium import webdriver

JSON_FILE = "linkedin_jobs.json"


def load_job_data(filename):
    """Load job data from JSON file"""
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"JSON file '{filename}' not found!")
        return []
    except json.JSONDecodeError:
        print(f"Invalid JSON format in '{filename}'!")
        return []


def save_job_data(filename, jobs):
    """Save updated jobs back to JSON"""
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(jobs, f, indent=4, ensure_ascii=False)


def get_status(choice):
    """Return status text based on user input"""
    status_map = {
        "0": "Applied",
        "1": "Will Apply",
        "2": "Not Applicable",
    }
    return status_map.get(choice, "Will Apply")


def should_process_job(job):
    """
    Treat missing status as Pending.
    Process only jobs that are Pending or Will Apply.
    """
    status = job.get("status") or "Pending"
    return status in ["Pending"
                    #   , "Will Apply"
                      ]


def main():
    jobs = load_job_data(JSON_FILE)

    if not jobs:
        print("No jobs found!")
        return

    print(f"Loaded {len(jobs)} total jobs")

    # Only process jobs that still need review
    filtered_jobs = [job for job in jobs if should_process_job(job)]
    total = len(filtered_jobs)

    print(f"Jobs to process: {total}")

    if total == 0:
        print("No Pending / Will Apply jobs left to process.")
        return

    # Chrome setup
    options = Options()
    options.add_argument("--remote-debugging-port=9222")
    options.add_argument(r"--user-data-dir=C:\selenium-chrome-profile")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    driver = webdriver.Chrome(options=options)
    driver.maximize_window()

    try:
        for index, job in enumerate(filtered_jobs, start=1):
            url = job.get("url", "")
            company = job.get("company", "Unknown")
            position = job.get("position", "Unknown")
            job_type = job.get("type", "")
            current_status = job.get("status") or "Pending"

            print("\n" + "=" * 60)
            print("gagangunawat05@gmail.com   ,  kkUI763568784asdasbhj#")
            print(" https://www.linkedin.com/in/gagan-meena-243b65255/ ")
            print(" https://shorturl.at/F5UIk ")
            print(f"Job {index}/{total}")
            print(f"Company : {company}")
            print(f"Position: {position}")
            print(f"Type    : {job_type}")
            print(f"Status  : {current_status}")
            print("=" * 60)

            if not url:
                print("No URL found. Skipping...")
                continue

            driver.get(url)

            print("\nOptions:")
            print("0 -> Applied")
            print("1 -> Will Apply")
            print("2 -> Not Applicable")
            print("q -> Quit")

            choice = input("\nEnter choice: ").strip().lower()

            if choice == "q":
                print("Stopping script...")
                break

            new_status = get_status(choice)
            job["status"] = new_status

            print(f"Updated status -> {new_status}")

            # Save after every update
            save_job_data(JSON_FILE, jobs)

        print("\nUpdated JSON saved")
        print(f"Total jobs in file: {len(jobs)}")

    except Exception as e:
        print(f"\nFatal error: {e}")

    finally:
        print("\nScript finished")
        print("Browser remains open")


if __name__ == "__main__":
    main()