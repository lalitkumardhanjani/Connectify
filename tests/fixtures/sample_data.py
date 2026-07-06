"""
Sample seed data for all three storage tables.
Used by test files to pre-populate databases before running pipeline logic.
"""

# -----------------------------------------------------------------------
# Emails table (email_scraper / job_tracker.xlsx)
# -----------------------------------------------------------------------
SAMPLE_EMAILS = [
    {
        "ID": 1,
        "Email": "hr@companyA.com",
        "Status": "New",
        "Timestamp": "2025-01-01T10:00:00",
        "Keyword": "Data Engineer",
        "PostURL": "https://linkedin.com/posts/postA",
        "CompanyName": "Company A",
        "Experience": "5-8 years",
        "Location": "Bangalore",
    },
    {
        "ID": 2,
        "Email": "recruiter@companyB.com",
        "Status": "sent",
        "Timestamp": "2025-01-02T11:00:00",
        "Keyword": "Senior Data Engineer",
        "PostURL": "https://linkedin.com/posts/postB",
        "CompanyName": "Company B",
        "Experience": "3-5 years",
        "Location": "Remote",
    },
    {
        "ID": 3,
        "Email": "hiring@companyC.com",
        "Status": "skipped",
        "Timestamp": "2025-01-03T12:00:00",
        "Keyword": "Data Engineer",
        "PostURL": "https://linkedin.com/posts/postC",
        "CompanyName": "Company C",
        "Experience": "2-4 years",
        "Location": "Hyderabad",
    },
    {
        "ID": 4,
        "Email": "talent@companyD.com",
        "Status": "New",
        "Timestamp": "2025-01-04T09:00:00",
        "Keyword": "Cloud Data Engineer",
        "PostURL": "https://linkedin.com/posts/postD",
        "CompanyName": "Company D",
        "Experience": "4-7 years",
        "Location": "Mumbai",
    },
]

# -----------------------------------------------------------------------
# Jobs table (linkedin_job_tracker.xlsx)
# -----------------------------------------------------------------------
SAMPLE_JOBS = [
    {
        "JobID": 1,
        "JobTitle": "Senior Data Engineer",
        "CompanyName": "TechCorp",
        "LinkedIn_Company_URL": "https://www.linkedin.com/company/techcorp/",
        "CompanyURL": "https://techcorp.com/careers/de-12345",
        "ShortenURL": "",
        "SearchKeyword": "Data Engineer",
        "Status": "NEW",
        "ShortUrlCreated": "0",
        "CreatedDateTime": "2025-01-01 10:00:00",
    },
    {
        "JobID": 2,
        "JobTitle": "Data Engineer",
        "CompanyName": "DataViz",
        "LinkedIn_Company_URL": "https://www.linkedin.com/company/dataviz/",
        "CompanyURL": "https://dataviz.io/jobs/de-67890",
        "ShortenURL": "https://short.ly/dv1",
        "SearchKeyword": "Analytics Engineer",
        "Status": "Asked for Referral",
        "ShortUrlCreated": "1",
        "CreatedDateTime": "2025-01-02 11:00:00",
    },
    {
        "JobID": 3,
        "JobTitle": "Cloud Data Engineer",
        "CompanyName": "CloudBase",
        "LinkedIn_Company_URL": "https://www.linkedin.com/company/cloudbase/",
        "CompanyURL": "https://cloudbase.dev/jobs/cde-99",
        "ShortenURL": "",
        "SearchKeyword": "Cloud Engineer",
        "Status": "Not Interested",
        "ShortUrlCreated": "0",
        "CreatedDateTime": "2025-01-03 09:00:00",
    },
]

# -----------------------------------------------------------------------
# Referrals table (referrals.xlsx)
# -----------------------------------------------------------------------
SAMPLE_REFERRALS = [
    {
        "ReferralID": 1,
        "JobID": "1",
        "CompanyName": "TechCorp",
        "Company_URL": "https://www.linkedin.com/company/techcorp/",
        "JobTitle": "Senior Data Engineer",
        "Job_URL": "https://techcorp.com/careers/de-12345",
        "Referral_Person_Name": "Alice Smith",
        "Referral_Person_Profile_URL": "https://www.linkedin.com/in/alicesmith/",
        "Referral_Source": "existing employee",
        "Referral_Status": "sent",
        "Outreach_Message": "Hi Alice, ...",
        "Response_Notes": "",
        "DateTime": "2025-01-05 14:00:00",
    },
    {
        "ReferralID": 2,
        "JobID": "1",
        "CompanyName": "TechCorp",
        "Company_URL": "https://www.linkedin.com/company/techcorp/",
        "JobTitle": "Senior Data Engineer",
        "Job_URL": "https://techcorp.com/careers/de-12345",
        "Referral_Person_Name": "Bob Jones",
        "Referral_Person_Profile_URL": "https://www.linkedin.com/in/bobjones/",
        "Referral_Source": "existing recruiter",
        "Referral_Status": "pending",
        "Outreach_Message": "",
        "Response_Notes": "",
        "DateTime": "2025-01-06 09:00:00",
    },
]
