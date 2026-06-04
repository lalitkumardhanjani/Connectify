# Connectify LinkedIn Outreach Pipeline

from pipelines.linkedin_outreach.services.job_finder import run_job_finder
from pipelines.linkedin_outreach.services.reviewer import run_reviewer
from pipelines.linkedin_outreach.services.connector import run_connector

def run_step(step_name):
    """Executes a specific step in the LinkedIn Outreach pipeline."""
    if step_name == "job_search":
        run_job_finder()
    elif step_name == "review":
        run_reviewer()
    elif step_name == "connect":
        run_connector()
    else:
        raise ValueError(f"Unknown step: {step_name}")
