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
│   │   │   ├── job_finder.py      # Scrapes external job postings
│   │   │   ├── reviewer.py        # Terminal CLI reviewer for new jobs
│   │   │   └── connector.py       # Connects and messages referral targets
│   │   └── pipeline.py            # Outreach step coordinator
│   │
│   └── [GIT IGNORED] users/       # Local sandboxed profile data (NEVER committed)
│       ├── active_user.json       # Tracks active user profile key
│       └── <username>/            # Dedicated sandbox directory per user
│           ├── config.json        # Profile credentials, keywords, settings
│           ├── data/              # job_tracker.xlsx, LinkedIn_Job_Tracker.xlsx
│           ├── logs/              # private automation.log, linkedin_connect.log
│           ├── resumes/           # private uploaded applicant resumes
│           └── chrome-profile/    # private isolated Chrome Selenium profiles
│
├── static/                        # CSS/JS dashboard assets
├── templates/                     # Flask dashboard view templates
│
├── run_email_outreach.py          # Pipeline 1 runner
├── run_job_search.py              # Pipeline 2 runner: Find job opportunities
├── run_referral_review.py         # Pipeline 2 runner: CLI job evaluator
├── run_linkedin_connect.py        # Pipeline 2 runner: Outreach & messaging
└── run_url_shortener.py           # Utility runner to shorten job URLs
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
3. **Launch Onboarding**:
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
- Swap profile contexts (e.g. Yuvashree, Lalit).
- Upload resumes.
- Edit configurations dynamically.
- Monitor execution logs and launch scraping/outreach jobs in real time.

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

---

## ⚠️ Troubleshooting & Browser Tips

- **Windows Chrome & Chromedriver**: On Windows, the system automatically detects the OS, bypasses the Mac local binary check, and relies on `webdriver_manager` to download the matching Windows `chromedriver.exe` binary. No manual setup is needed.
- **Mac Chrome Execution**: The driver is configured to automatically search for Google Chrome in the standard `/System/Volumes/Data/Volumes/Google Chrome/Google Chrome.app` path or default location.
- **Mac Excel Sheet Reloads**: The system uses AppleScript to reload active Excel/Numbers sheets automatically if they are open while data is writing. If prompted, grant terminal permission to script applications.
- **Google Sign-In**: Avoid choosing "Continue with Google" during automated sessions as Google security blocks automated login pages. Sign in directly using email and password.