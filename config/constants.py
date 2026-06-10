# System-wide static default parameters

DBA_KEYWORDS_DEFAULT = []

LINKEDIN_CONNECT_KEYWORDS_DEFAULT = []

# Table schemas for tracking spreadsheets
SCRAPER_HEADERS = ['ID', 'Email', 'Status', 'Timestamp', 'Keyword', 'PostURL', 'CompanyName', 'Experience', 'Location']

JOB_LEADS_HEADERS = [
    'JobID', 'JobTitle', 'CompanyName', 'LinkedIn_Company_URL', 'CompanyURL', 'ShortenURL', 'SearchKeyword', 'Status', 
    'ShortUrlCreated', 'CreatedDateTime'
]

REFERRAL_HEADERS = [
    'ReferralID', 'JobID', 'CompanyName', 'Job_URL', 'Referral_Person_Name', 'Referral_Person_Email',
    'Referral_Person_Profile_URL', 'Referral_Source',
    'Referral_Status', 'Employment_Verification_Status', 'Sent_Time', 'Error_Reason'
]
