import logging
from data_store import load_jobs_for_referral, append_referral_person

def get_jobs_for_referral():
    """Load jobs from the Excel workbook where Status == 'Asked for referral'."""
    try:
        jobs = load_jobs_for_referral()
        logging.info(f"Loaded {len(jobs)} jobs with status 'Asked for referral'.")
        return jobs
    except Exception as e:
        logging.error(f"Failed to load jobs for referral: {e}")
        return []

def add_referral_person(job_id, person_name):
    """Append a referral person's name to the Referral Person column for the given job ID."""
    try:
        success = append_referral_person(job_id, person_name)
        if success:
            logging.info(f"Appended referral person '{person_name}' to job ID {job_id}.")
        else:
            logging.warning(f"Job ID {job_id} not found, could not append referral person.")
        return success
    except Exception as e:
        logging.error(f"Error appending referral person: {e}")
        return False
