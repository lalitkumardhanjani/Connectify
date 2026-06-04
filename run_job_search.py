import argparse
from pipelines.linkedin_outreach.services.job_finder import run_job_finder

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Connectify LinkedIn Job Search Runner")
    parser.add_argument(
        "--target_url",
        default=None,
        help="Specific LinkedIn job URL to process directly"
    )
    args = parser.parse_args()
    run_job_finder(target_url=args.target_url)
