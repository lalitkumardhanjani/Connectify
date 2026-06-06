# Connectify – Automated LinkedIn Job Application & Outreach Hub

Connectify is a clean, modular Python and Selenium-based automation framework that automates the process of finding job postings, scraping recruiter/contact emails, sending referral request messages, and logging all applications in structured Excel sheets. It includes a user-friendly Flask-based web dashboard.

---

## 📁 Project Directory Layout

```
Connectify/
├── app.py                         # Web dashboard server (Flask)
│
├── config/                        # Dynamic profile & settings configuration
│   ├── settings.py                # Runtime dynamic user path resolution
│   ├── constants.py               # Central schema definitions and default keywords
│   ├── user_profiles.py           # Sandboxed profile management & upgrade scripts
│   └── email_templates.py         # Static fallback outreach templates
│
├── core/                          # Shared library & support package
│   ├── analytics/
│   │   └── metrics.py             # Sandboxed stats calculator
│   ├── storage/
│   │   └── database.py            # Unified openpyxl Excel read/write CRUD database
│   ├── integrations/
│   │   ├── selenium_driver.py     # Centralized Chrome WebDriver configurations
│   │   └── url_shortener.py       # TinyURL shortening service
│   ├── logging/
│   │   └── config.py              # DynamicUserFileHandler (sandboxed logger)
│   └── utils/
│       ├── string_utils.py        # Email address extraction regex
│       └── url_utils.py           # URL normalization, decoding, and parsing
│
├── pipelines/                     # Pipeline execution modules
│   ├── email_outreach/            # Pipeline 1: Email Scraper & Sender
│   │   ├── services/
│   │   │   ├── scraper.py         # Selenium post content email scraper
│   │   │   └── sender.py          # SMTP & Gmail Web automation senders
│   │   └── pipeline.py            # Phase 1 & 2 coordinator
│   │
│   └── linkedin_outreach/         # Pipeline 2: LinkedIn Job Search & Connect
│   │   ├── services/
│   │   │   ├── job_finder.py      # Scrapes external job postings (location-aware)
│   │   │   ├── reviewer.py        # Terminal CLI reviewer for new jobs
│   │   │   └── connector.py       # Connects and messages referral targets
│   │   └── pipeline.py            # Outreach step coordinator
│   │
│   └── [GIT IGNORED] users/       # Local sandboxed profile data (NEVER committed)
│       ├── active_user.json       # Tracks active user profile key
│       └── <username>/            # Dedicated sandbox directory per user
│           ├── config.json        # Profile credentials, keywords, preferred locations
│           ├── data/              # job_tracker.xlsx, LinkedIn_Job_Tracker.xlsx
│           ├── logs/              # private automation.log, linkedin_connect.log
│           ├── resumes/           # private uploaded applicant resumes
│           └── chrome-profile/    # private isolated Chrome Selenium profiles
│
├── static/                        # CSS/JS dashboard assets
├── templates/                     # Flask dashboard view templates
│
├── run_email_outreach.py          # Pipeline 1 runner (graceful SIGTERM handling)
├── run_job_search.py              # Pipeline 2 runner: Find job opportunities (graceful SIGTERM handling)
├── run_referral_review.py         # Pipeline 2 runner: CLI job evaluator (graceful SIGTERM handling)
├── run_linkedin_connect.py        # Pipeline 2 runner: Outreach & messaging (graceful SIGTERM handling)
└── run_url_shortener.py           # Utility runner to shorten job URLs (graceful SIGTERM handling)
```

---

## 🚀 Onboarding & Cloning Guide (MacOS & Windows)

If your friend or colleague wants to clone and run this project, they can follow these steps.

### Step 1: Install System Dependencies
- **All OS**: Make sure you have the standard [Google Chrome](https://www.google.com/chrome/) browser installed.
- **Windows**: 
  1. Download and install [Git for Windows](https://gitforwindows.org/).
  2. Download and install [Python 3.9+](https://www.python.org/). Make sure to check the box **"Add Python to PATH"** during installation.

### Step 2: Clone the Project
Open your terminal (Terminal on Mac, or Command Prompt/PowerShell on Windows) and run:
```bash
git clone https://github.com/lalitkumardhanjani/Connectify.git
cd Connectify
```

### Step 3: Set Up Virtual Environment & Packages
- **On macOS / Linux**:
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
  ```
- **On Windows (Command Prompt / PowerShell)**:
  ```cmd
  python -m venv .venv
  .venv\Scripts\activate
  pip install -r requirements.txt
  ```
*Note: Pip will install Selenium, Flask, openpyxl, pandas, requests, python-dotenv, and webdriver-manager.*

> [!TIP]
> **VS Code Extension Setup**: If you run the project in VS Code and receive `ModuleNotFoundError: No module named 'flask'`, it means VS Code is trying to run python using your global system interpreter rather than the virtual environment `.venv`.
> To resolve this:
> 1. Open the Command Palette (`Cmd + Shift + P` on Mac, `Ctrl + Shift + P` on Windows).
> 2. Search for and select **`Python: Select Interpreter`**.
> 3. Select the option pointing to the local directory's **`.venv`** interpreter (e.g. `./.venv/bin/python`).

### Step 4: Configure Settings & Onboarding
1. Copy the example configuration file:
   - **On macOS / Linux**:
     ```bash
     cp .env.example .env
     ```
   - **On Windows (Command Prompt or PowerShell)**:
     ```cmd
     copy .env.example .env
     ```
2. Update the `.env` file with default environment fallbacks if needed (e.g. `SMTP_SERVER`). Note: LinkedIn credentials and user settings are now handled dynamically on a per-profile basis in the dashboard!
3. **LinkedIn Credentials & Manual Login**:
   - You do **not** need to pre-configure your LinkedIn email and password in settings.
   - If credentials are left blank, or if auto-login triggers security verification / Two-Factor Authentication (2FA), the automation pipeline will output a warning in the console log and pause for up to **5 minutes (300 seconds)**.
   - Simply log in manually in the opened Chrome browser window, and the pipeline will automatically resume running once it detects you have successfully signed in.
4. **Launch Onboarding**:
   - There is no need to copy `users_config.json` manually! On your first launch, the web dashboard will guide you through profile creation.
   - **Legacy Upgrades**: If you have a legacy `users_config.json` from a previous version, placing it at the project root before launching will trigger a one-time automated migration, sandboxing your old profiles, databases, and Chrome profiles under `users/` automatically.

---

## 🛠️ Running the Application

### Option A: Running the Web Dashboard (Recommended)
Launch the web interface locally:
```bash
python app.py
```
Open your browser and navigate to **`http://127.0.0.1:5001`**. From here, you can:
- Swap profile contexts (e.g. Yuvashree, Lalit) using the avatar switcher in the top-right corner.
- Upload resumes and manage your candidate profile.
- Edit configurations dynamically under the **Settings** tab — keyword changes apply immediately to the JSON config.
- Browse and search the **Outreach Leads** (email scraper) database with full pagination.
- Browse and manage the **Referral Opportunities** (LinkedIn jobs) database with full pagination.
- Monitor real-time execution logs and launch or stop pipeline steps from the **Pipelines** tab.

### Option B: Running Pipelines Individually via Terminal
You can run any pipeline or utility directly from the command line using the root wrapper scripts:

- **On macOS / Linux**:
  ```bash
  source .venv/bin/activate
  python run_email_outreach.py --phase full
  ```
- **On Windows**:
  ```cmd
  .venv\Scripts\activate
  python run_email_outreach.py --phase full
  ```

Other runner scripts:
```bash
# 1. Run Job Search Automation
python run_job_search.py

# 2. Launch Terminal Reviewer (Flags new jobs as Interested/Skip)
python run_referral_review.py

# 3. Run TinyURL url shortener on gathered URLs
python run_url_shortener.py

# 4. Execute LinkedIn Connections & Referrals messaging outreach
python run_linkedin_connect.py
```

> **Note:** All pipeline runners support graceful termination — pressing `Ctrl+C` or clicking Stop in the dashboard will cleanly shut down the Chrome browser and save all in-progress data before exiting.

---

## 🖥️ Dashboard Overview

### Settings Tab
The Settings panel is split into two sub-sections:

- **Outreach Engine**: Configure the email scraper pipeline — set the search execution frequency, enable/disable the Outreach Quality Gate (review mode), manage target post keywords (changes save instantly to your profile config), and compose your outreach email template with a real-time preview inside a mock email window.
- **LinkedIn Automator**: Configure the LinkedIn connection pipeline — set the action timing delay, enable/disable the Invite Quality Gate (review mode), manage target network keywords (changes save instantly to your profile config), and compose your 300-character LinkedIn invite note with a live preview rendered in a mock LinkedIn invitation bubble.

### Preferred Location Support
Each user profile supports a **Preferred Location** field in the User Profile section. When set:
- The **Email Scraper** automatically appends each location to your search keywords (e.g. `"SQL DBA Bangalore"`), expanding reach across all configured locations.
- The **LinkedIn Job Finder** filters job postings by each preferred location automatically.
- **Multiple locations** (comma-separated) are fully supported — the pipeline repeats the search for each location independently.

### Database Tabs
- **Outreach Leads**: Displays emails scraped from LinkedIn posts. Records are sorted by ID (ascending). Supports per-column filtering, status-based filtering, keyword dropdown, and paginated browsing (10 records per page).
- **Referral Opportunities**: Displays job opportunities tracked for LinkedIn referral outreach. Records are sorted by ID (ascending). Supports full-text search, status and date filters, and paginated browsing (10 records per page).

### Pipelines Tab
- Start or stop any of the 6 individual pipeline steps directly from the UI.
- **Real-time log streaming**: The console panel streams live output from the running process until the pipeline completes or is manually stopped.
- **Graceful stop**: Clicking Stop sends a termination signal to the pipeline subprocess, which cleanly quits the Chrome driver before exiting. The status correctly reflects `stopped` — it will never incorrectly show `failed` after a manual stop.
- **Smart scroll detection**: The email scraper automatically moves to the next keyword as soon as it reaches the end of available posts, without waiting for the full timeout window.

### Company Analytics Dashboard
The **Company Analytics** panel in the Dashboard tab shows status breakdowns for your tracked companies:
- 🔵 **New** — Blue badge: Companies newly added, not yet actioned.
- 🟢 **Done** — Teal/green badge: Companies where outreach has been completed.
- 🔴 **Not Interested** — Red badge: Companies marked as not relevant.

Status colors are consistent across KPI cards, the status pie chart, the keyword-vs-status table, and the column header pills.

---

## ⚠️ Troubleshooting & Browser Tips

- **Windows Chrome & Chromedriver**: On Windows, the system automatically detects the OS, bypasses the Mac local binary check, and relies on `webdriver_manager` to download the matching Windows `chromedriver.exe` binary. No manual setup is needed.
- **Unrecognized Chrome Version / Microsoft Edge Launching**: If you experience browser version errors (e.g., `SessionNotCreatedException: unrecognized Chrome version: Edg/...`), Microsoft Edge may have hijacked the default `chrome` app execution alias on Windows. To fix this, add the absolute path of your actual Google Chrome installation to your `.env` file using the `CHROME_BINARY_PATH` environment variable:
  ```env
  CHROME_BINARY_PATH=C:\Program Files\Google\Chrome\Application\chrome.exe
  ```
- **Mac Chrome Execution**: The driver is configured to automatically search for Google Chrome in the standard `/System/Volumes/Data/Volumes/Google Chrome/Google Chrome.app` path or default location.
- **Mac Excel Sheet Reloads**: The system uses AppleScript to reload active Excel/Numbers sheets automatically if they are open while data is writing. If prompted, grant terminal permission to script applications.
- **Google Sign-In**: Avoid choosing "Continue with Google" during automated sessions as Google security blocks automated login pages. Sign in directly using email and password.
- **Empty Data for a New Profile**: Each user profile starts with an empty `data/` directory. Data files (`job_tracker.xlsx`, `LinkedIn_Job_Tracker.xlsx`) are automatically created the first time a pipeline is run under that profile.
- **urllib3 SSL Warning**: If you see a `NotOpenSSLWarning` from urllib3, this is a known macOS LibreSSL compatibility notice and is automatically suppressed in all pipeline runners — it has no effect on functionality.