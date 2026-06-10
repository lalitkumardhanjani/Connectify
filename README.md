# Connectify – Automated LinkedIn Job Application & Outreach Hub

Connectify is a clean, modular Python and Selenium-based automation framework that automates the process of finding job postings, scraping recruiter/contact emails, sending referral request messages, connecting with recruiters, and logging all activity in structured Excel sheets. It includes a user-friendly Flask-based web dashboard with real-time log streaming and full pipeline control.

---

## 📁 Project Directory Layout

```
Connectify/
├── app.py                             # Web dashboard server (Flask)
│
├── config/                            # Dynamic profile & settings configuration
│   ├── settings.py                    # Runtime dynamic user path resolution
│   ├── constants.py                   # Central schema definitions and default keywords
│   ├── user_profiles.py               # Sandboxed profile management & upgrade scripts
│   └── email_templates.py             # Static fallback outreach templates
│
├── core/                              # Shared library & support package
│   ├── analytics/
│   │   └── metrics.py                 # Sandboxed stats calculator
│   ├── storage/
│   │   └── database.py                # Unified openpyxl Excel read/write CRUD database
│   ├── integrations/
│   │   ├── selenium_driver.py         # Centralized Chrome WebDriver configurations
│   │   └── url_shortener.py           # TinyURL shortening service
│   ├── logging/
│   │   └── config.py                  # DynamicUserFileHandler (sandboxed logger)
│   └── utils/
│       ├── string_utils.py            # Email address extraction regex
│       └── url_utils.py               # URL normalization, decoding, and parsing
│
├── pipelines/                         # Pipeline execution modules
│   ├── email_outreach/                # Pipeline 1: Email Scraper & Sender
│   │   ├── services/
│   │   │   ├── scraper.py             # Selenium post content email scraper
│   │   │   └── sender.py              # SMTP & Gmail Web automation senders
│   │   └── pipeline.py                # Phase 1 & 2 coordinator
│   │
│   └── linkedin_outreach/             # Pipeline 2–6: LinkedIn Job Search, Referral & Recruiter Outreach
│       ├── services/
│       │   ├── job_finder.py          # Scrapes external job postings (location-aware, sequential)
│       │   ├── reviewer.py            # Terminal CLI reviewer for new jobs
│       │   ├── connector.py           # LinkedIn Connect & referral message sender
│       │   ├── referral_outreach.py   # Discover connected employees & send referral messages
│       │   ├── recruiter_connector.py # Discover & message recruiters at target companies
│       │   └── shortener.py          # TinyURL shortener service for job links
│       └── pipeline.py                # Step coordinator interface
│
├── [GIT IGNORED] users/               # Local sandboxed profile data (NEVER committed)
│   ├── active_user.json               # Tracks active user profile key
│   └── <username>/                    # Dedicated sandbox directory per user
│       ├── config.json                # Profile credentials, keywords, preferred locations
│       ├── data/                      # job_tracker.xlsx, LinkedIn_Job_Tracker.xlsx
│       ├── logs/                      # private automation.log, linkedin_connect.log
│       ├── resumes/                   # private uploaded applicant resumes
│       └── chrome-profile/            # private isolated Chrome Selenium profiles
│
├── static/                            # CSS/JS dashboard assets
├── templates/                         # Flask dashboard view templates
├── docs/
│   └── architecture_docs.md           # Detailed technical architecture reference
│
├── run_email_outreach.py              # Pipeline 1 runner (full: scrape + send, graceful SIGTERM handling)
├── run_email_scraper.py               # Pipeline 1a runner: Scrape emails from LinkedIn posts only
├── run_email_sender.py                # Pipeline 1b runner: Send outreach emails to scraped contacts only
├── run_job_search.py                  # Pipeline 2 runner: Find job opportunities
├── run_referral_review.py             # Pipeline 3 runner: CLI job evaluator
├── run_linkedin_connect.py            # Pipeline 4 runner: Outreach & messaging
├── run_referral_outreach_discover.py  # Pipeline 5a runner: Discover connected employees
├── run_referral_outreach_send.py      # Pipeline 5b runner: Send referral messages
├── run_recruiter_outreach_discover.py # Pipeline 6a runner: Discover recruiters
├── run_recruiter_outreach_send.py     # Pipeline 6b runner: Message recruiters
├── run_recruiter_outreach.py          # Pipeline 6 runner: Complete recruiter pipeline
├── run_url_shortener.py               # Utility runner to shorten job URLs
└── update_project.py                  # One-command project updater (git fetch + reset)
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

## 🔄 Updating the Project

To pull the latest code changes from GitHub without losing any local user data:
```bash
python update_project.py
```

This script performs a safe `git fetch` + `git reset --hard origin/main`, which:
- Updates all source code files to the latest version.
- **Never touches** your `users/` directory (which is git-ignored), so all profiles, data, and logs remain intact.

After updating, re-run `pip install -r requirements.txt` if dependencies have changed.

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
- Edit configurations dynamically under the **Settings** tab — keyword changes apply immediately to your JSON config.
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

All available runner scripts:
```bash
# Pipeline 1 – Full Email Scraper & Outreach (scrape + send in one run)
python run_email_outreach.py

# Pipeline 1a – Scrape emails from LinkedIn posts only
python run_email_scraper.py

# Pipeline 1b – Send outreach emails to already-scraped contacts only
python run_email_sender.py

# Pipeline 2 – Find Job Opportunities (LinkedIn Job Search)
python run_job_search.py

# Pipeline 3 – CLI Job Reviewer (mark jobs as Interested / Skip)
python run_referral_review.py

# Pipeline 4 – LinkedIn Connect & Referral Messaging
python run_linkedin_connect.py

# Pipeline 5a – Discover Connected Employees (for referral outreach)
python run_referral_outreach_discover.py

# Pipeline 5b – Send Referral Messages to discovered employees
python run_referral_outreach_send.py

# Pipeline 6a – Discover Recruiters at target companies
python run_recruiter_outreach_discover.py

# Pipeline 6b – Send messages to discovered recruiters
python run_recruiter_outreach_send.py

# Pipeline 6 (Complete) – Run full Recruiter Outreach pipeline end-to-end
python run_recruiter_outreach.py

# Utility – Shorten job URLs with TinyURL
python run_url_shortener.py
```

> **Note:** All pipeline runners support graceful termination — pressing `Ctrl+C` or clicking Stop in the dashboard will cleanly shut down the Chrome browser and save all in-progress data before exiting.

---

## 🖥️ Dashboard Overview

### Pipelines Tab
All 6 pipeline stages (plus their sub-steps) are available directly from the **Pipelines** tab. Each pipeline card provides:
- A **Start** / **Stop** button to launch or kill the automation process.
- A **real-time console** that streams live log output until the pipeline completes or is stopped.
- **Graceful stop**: Clicking Stop sends a termination signal to the subprocess, which cleanly quits the Chrome driver. The status correctly reflects `stopped` — it will never incorrectly show `failed` after a manual stop.

Available pipeline steps in the UI:
| Step | Name | Description |
|------|------|-------------|
| 1 | Email Scraper & Outreach | Scrapes LinkedIn posts for emails and sends outreach |
| 2 | Find Job Opportunities | Searches LinkedIn Jobs for postings matching your keywords |
| 3 | Review Job Applications | Terminal CLI to flag jobs as Interested or Skip |
| 4 | LinkedIn Connect & Referral | Sends connection requests with personalized notes |
| 5a | Discover Connected Employees | Finds employees at target companies via LinkedIn |
| 5b | Send Referral Messages | Sends templated referral request messages to found contacts |
| 6 | Run Complete Recruiter Pipeline | Discovers recruiters and messages them in one run |
| 6a | Discover Recruiters | Finds recruiters at target companies |
| 6b | Message Recruiters | Sends personalized messages to discovered recruiters |

### Settings Tab
The Settings panel uses a **horizontal tab layout** and is split into two sub-sections:

#### Outreach Engine (Email Scraper Settings)
- **Search Execution Frequency**: Controls how frequently the scraper paginates LinkedIn feeds between post reads.
- **Outreach Quality Gate**: When enabled, emails are held in the database for manual review before sending. When disabled, outreach is sent automatically after scraping.
- **Target Post Keywords**: Tag-based keyword manager. Add or remove terms searched on LinkedIn content boards. **Changes are persisted immediately** to the user's `config.json` on every add/remove action — no save button required.
- **Outreach Email Template Studio**: Rich text editor with clickable variable tokens and a **Real-time Preview** mode that renders your template inside a mock email window.

  **Available Tokens for Email Templates:**
  | Token | Description |
  |-------|-------------|
  | `{FIRST_NAME}` | Recipient's first name |
  | `{LAST_NAME}` | Recipient's last name |
  | `{COMPANY}` | Company name |
  | `{POSITION}` | Job position |
  | `{MY_NAME}` | Your name |
  | `{MY_EXPERIENCE}` | Your experience summary |

#### LinkedIn Automator (LinkedIn Connect Settings)
- **Action Timing Delay**: Controls wait time between LinkedIn browser automation steps.
- **Invite Quality Gate**: When enabled, connection requests are staged for review before being sent. When disabled, requests are sent automatically.
- **Target Connections Per Run**: Sets the maximum number of new LinkedIn connections to send per pipeline run.
- **Target Network Keywords**: Tag-based keyword manager. Add or remove terms used for LinkedIn people search during connection routines. **Changes are persisted immediately** to the user's `config.json`.
- **Available Invite Note Tokens** *(displayed above the editor)*: All tokens available for your LinkedIn invite notes, identical to the message template tokens. Click any token to insert it at the cursor.
- **LinkedIn Invite Note Studio**: Rich text editor with a character counter (300-char LinkedIn limit enforced). **Real-time Preview** renders your note inside a mock LinkedIn invitation modal.

  **Available Tokens for LinkedIn Invite Notes & All Message Templates:**
  | Token | Description |
  |-------|-------------|
  | `{FIRST_NAME}` | Recipient's first name |
  | `{LAST_NAME}` | Recipient's last name |
  | `{COMPANY}` | Company name |
  | `{POSITION}` | Job position |
  | `{MY_NAME}` | Your name |
  | `{MY_EXPERIENCE}` | Your experience summary |
  | `{JOB_TITLE}` | Job title from the opportunity |
  | `{JOB_URL}` | Direct URL to the job posting |
  | `{SHORT_URL}` | TinyURL-shortened job URL |
  | `{REFERRAL_INTRO}` | Introductory referral phrase |

- **Referral Message Template Studio**: Compose referral request messages with the full token set. Tokens insert at cursor position.

### Preferred Location Support
Each user profile supports a **Preferred Location** field in the User Profile section. When set:
- The **Email Scraper** automatically appends each location to your search keywords (e.g. `"SQL DBA Bangalore"`), expanding reach across all configured locations.
- Posts are then **strictly filtered** by location: if a location is successfully parsed from the post (e.g. `"Work From Office — Bangalore"`), it is matched only against that extracted field. Posts from non-matching cities are rejected even if the word "Bangalore" appears elsewhere in the post body.
- The **LinkedIn Job Finder** filters job postings by each preferred location automatically.
- **Multiple locations** (comma-separated) are fully supported — the pipeline repeats the search for each location independently.
- **City synonyms** are automatically expanded: `Bangalore` also matches `Bengaluru` / `BLR`; `Delhi` also matches `NCR`, `Gurgaon`, `Noida`, `Gurugram`; `Mumbai` matches `Bombay`; `Hyderabad` matches `Secunderabad`.

### Database Tabs
- **Outreach Leads**: Displays emails scraped from LinkedIn posts. Records are sorted by ID (ascending). Supports per-column filtering, status-based filtering, keyword dropdown, and paginated browsing (10 records per page).
- **Referral Opportunities**: Displays job opportunities tracked for LinkedIn referral outreach. Records are sorted by ID (ascending). Supports full-text search, status and date filters, and paginated browsing (10 records per page).

### Company Analytics Dashboard
The **Company Analytics** panel in the Dashboard tab shows status breakdowns for your tracked companies:
- 🔵 **New** — Blue badge: Companies newly added, not yet actioned.
- 🟢 **Done** — Teal/green badge: Companies where outreach has been completed.
- 🔴 **Not Interested** — Red badge: Companies marked as not relevant.

Status colors are consistent across KPI cards, the status pie chart, the keyword-vs-status table, and the column header pills.

---

## 🔁 Referral Outreach Workflow

The Referral Outreach system is a two-stage pipeline for finding contacts at target companies and sending them personalized referral request messages.

### Stage 1 – Discover Connected Employees (Pipeline 5a)
- Reads target companies from your **Referral Opportunities** database with status `Interested`.
- Searches LinkedIn for people working at each company.
- Prioritizes **1st-degree connections** (people you already know) and **2nd-degree connections**.
- Saves discovered contacts into the database and marks the company as `Discovered`.
- Respects the **Target Connections Per Run** limit from Settings.

### Stage 2 – Send Referral Messages (Pipeline 5b)
- Reads discovered contacts with status `Pending Message`.
- Opens each contact's LinkedIn profile and sends your configured **Referral Message Template**.
- Marks each contact as `Message Sent` after successful delivery.
- Marks the parent company as `Done` once all contacts have been messaged.

---

## 📨 Recruiter Outreach Workflow

The Recruiter Outreach system finds recruiters at target companies and messages them directly.

### Recruiter Discovery (Pipeline 6a)
- Searches LinkedIn for people with recruiter titles (e.g., "Talent Acquisition", "HR Manager") at each target company.
- Saves discovered recruiters into the outreach database.

### Recruiter Messaging (Pipeline 6b)
- Sends personalized messages to each discovered recruiter using your message template.
- Updates status to `Sent` after each successful message.

### Complete Pipeline (Pipeline 6)
- Runs both discovery and messaging sequentially in one go.

---

## 📊 Spreadsheet Databases & Status Workflow

Connectify records and manages its automation state across three user-specific Excel spreadsheets located in `users/<username>/data/`.

### 1. Email Scraper Tracker (`job_tracker.xlsx`)
Tracks contact email leads scraped from LinkedIn posts and the status of cold email outreach campaigns.
* **Columns**: `ID`, `Email`, `Status`, `Timestamp`, `Keyword`, `PostURL`, `CompanyName`, `Experience`, `Location`
* **Workflow & Pipeline Transitions**:
  * **Email Scraper** (`run_email_scraper.py`): Appends scraped emails with status **`New`**. Also stores the LinkedIn post URL (`PostURL`), parsed company name (`CompanyName`), years of experience (`Experience`), and job location (`Location`) extracted from each post.
  * **Email Sender** (`run_email_sender.py` / `run_email_outreach.py`): Reads emails with status `New`. If the email is successfully sent, updates to **`sent`**. If skipped by the user or pre-checks, updates to **`skipped`**.
* **Location Filtering**: The scraper strictly filters posts based on the **Preferred Locations** field in the user profile (comma-separated). When a location is cleanly extracted from the post body (e.g. `"Work From Office — Bangalore"`), it is matched **only** against the extracted location field — not the full post text — to avoid false positives (e.g. a Chennai post that mentions "Bangalore" in passing). If no location can be extracted, the full post body is searched as a fallback.
* **Status Definitions**:
  * **`New`**: Newly scraped contact email address, queued for email sending.
  * **`sent`**: Cold email outreach was successfully sent to this address.
  * **`skipped`**: Cold email outreach was manually skipped by user choice or skipped during validation.

---

### 2. Job Search Leads Tracker (`LinkedIn_Job_Tracker.xlsx`)
Tracks job postings discovered during searches and their progression through the referral and recruiter outreach pipeline.
* **Columns**: `JobID`, `JobTitle`, `CompanyName`, `CompanyURL`, `ShortenURL`, `SearchKeyword`, `Status`, `ShortUrlCreated`, `CreatedDateTime`
* **Workflow & Pipeline Transitions**:
  * **Find Relevant Jobs** (`run_job_search.py`): Automatically appends newly scraped job postings with status **`NEW`**.
  * **Review Job Applications** (`run_referral_review.py`): Evaluates jobs with status **`NEW`**. The user selects either **`Interested`** or **`Not Interested`**.
  * **Discover Connected Employees** (`run_referral_outreach_discover.py`): Processes jobs with status **`Interested`**. Sets job status to **`In Progress`** during execution. If company target outreach capacity is already met, sets status directly to **`Asked for Referral`**.
  * **LinkedIn Connect & Referral** (`run_linkedin_connect.py`): Processes jobs with status **`Interested`**. If target connections are achieved, sets job status to **`Asked for Referral`**. If connection limit is reached but company capacity is not met, sets status to **`Completed – Target Not Met`**. If pipeline is stopped mid-way, sets status to **`Cancelled`**.
  * **Discover Recruiters** (`run_recruiter_outreach_discover.py`): Processes jobs with status **`Asked for Referral`**. Sets job status to **`In Progress`** during discovery. If company recruiter capacity is already met, sets status directly to **`Done`**.
  * **Recruiter Connector/Messaging** (`run_recruiter_outreach.py` / `run_recruiter_outreach_send.py`): Processes jobs with status **`Asked for Referral`**. If recruiter outreach target is successfully achieved, sets job status to **`Done`**. If recruiter limit is reached but target not met, sets status to **`Completed – Target Not Met`**. If stopped mid-way, sets status to **`Cancelled`**.
* **Status Definitions**:
  * **`NEW`**: Scraped job posting waiting for review.
  * **`Interested`**: Approved by user, ready for employee discovery and referral outreach.
  * **`Not Interested`**: Disapproved by user, excluded from further automation steps.
  * **`In Progress`**: Discovery phase (employee or recruiter search) is actively running for the target company.
  * **`Asked for Referral`**: Connection request notes or referral messages have been initiated towards target company employees, or target capacity is met.
  * **`Cancelled`**: Runner pipeline was interrupted or stopped by the user.
  * **`Completed – Target Not Met`**: Pipeline completed its search and outreach runs but could not meet the target capacity due to candidate/recruiter pool exhaustion.
  * **`Done`**: Recruiter outreach is completed successfully for the target company.

---

### 3. Referral Outreach Contacts (`referrals.xlsx`)
Logs individual employee and recruiter contacts discovered at target companies, their source type, and outreach outcomes.
* **Columns**: `ReferralID`, `JobID`, `CompanyName`, `Referral_Person_Name`, `Referral_Person_Email`, `Referral_Person_Profile_URL`, `Referral_Person_Designation`, `Referral_Source`, `Referral_Status`, `Employment_Verification_Status`, `Sent_Time`, `Error_Reason`
* **Workflow & Pipeline Transitions**:
  * **Discover Connected Employees** (`run_referral_outreach_discover.py`): Discovers and verifies 1st/2nd degree connections working at target companies. Saves profile with `Referral_Source='Existing Employee'`, `Employment_Verification_Status='Verified'`, and status **`Pending`**.
  * **Send Referral Messages** (`run_referral_outreach_send.py`): Processes contacts with status **`Pending`** and source `Existing Employee`. If the template message is successfully sent and verified in chat history, updates to **`Sent`**. If skipped by user or pre-checks, updates to **`Skipped`**. If delivery verification fails, updates to **`Failed`**.
  * **LinkedIn Connect & Referral** (`run_linkedin_connect.py`): Connects with 2nd/3rd degree connections, sending invitation notes. Appends contact details with `Referral_Source='Sent Employee Connection'` and status **`Sent`**, **`Skipped`**, or **`Failed`** depending on the connection prompt outcome.
  * **Discover Recruiters** (`run_recruiter_outreach_discover.py`): Discovers recruiters. Saves profile with `Referral_Source='Existing Recruiter'` and status **`Pending`**.
  * **Message Recruiters** (`run_recruiter_outreach_send.py`): Processes recruiter contacts with status **`Pending`**. If direct message is sent and verified, updates to **`Sent`**, otherwise **`Failed`** or **`Skipped`**.
  * **Recruiter Connector** (`run_recruiter_outreach.py`): Connects with recruiters, sending invitation notes. Appends contact details with `Referral_Source='Sent Recruiter Connection'` and status **`Sent`**, **`Skipped`**, or **`Failed`**.
  * **Manual Dashboard Updates**: Users can manually modify any contact row status to **`Replied`** or **`Referral Received`** inside the dashboard.
* **Status Definitions**:
  * **`Pending`**: Discovered and verified contact, queued for outreach message.
  * **`Sent`**: Connection invitation note or direct message has been successfully sent.
  * **`Skipped`**: Contact skipped manually by user, or because the profile was already messaged.
  * **`Failed`**: Direct message input failed or delivery verification check failed.
  * **`Replied`**: (Manual update) Contact has replied to our connection or message.
  * **`Referral Received`**: (Manual update) Contact has successfully referred the applicant.

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
- **LinkedIn Rate Limiting**: If LinkedIn temporarily restricts your account activity, increase the **Action Timing Delay** in the LinkedIn Automator settings to add more wait time between automation steps.

---

## 📖 Additional Documentation

- **Technical Architecture**: See [`docs/architecture_docs.md`](docs/architecture_docs.md) for an in-depth breakdown of the system architecture, data flow diagrams, module responsibilities, and extension guidelines.
- **Example Config**: See [`users_config.json.example`](users_config.json.example) for a reference user profile structure.
- **Environment Variables**: See [`.env.example`](.env.example) for all supported environment variable overrides.

