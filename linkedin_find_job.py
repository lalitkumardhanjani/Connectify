"""
LinkedIn Find Job Runner
Launches the job search automation.
"""

import argparse
from linkedin_job_main import run_automation

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target_url", help="Specific LinkedIn job URL to process", default=None)
    args = parser.parse_args()
    run_automation(target_url=args.target_url)
