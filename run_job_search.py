import warnings
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL.*')
import argparse
import signal
import sys
from pipelines.linkedin_outreach.services.job_finder import run_job_finder

def handle_sigterm(signum, frame):
    print(f"\n[SYSTEM] Received termination signal {signum}. Closing Chrome and exiting...")
    sys.exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigterm)
    
    parser = argparse.ArgumentParser(description="Connectify LinkedIn Job Search Runner")
    parser.add_argument(
        "--target_url",
        default=None,
        help="Specific LinkedIn job URL to process directly"
    )
    args = parser.parse_args()
    
    from core.logging.config import logger
    logger.info("============================================================")
    logger.info("LinkedIn Job Search Runner Initiated")
    logger.info(f"Target Job URL: {args.target_url or 'None (All matching keywords)'}")
    logger.info("============================================================")
    
    run_job_finder(target_url=args.target_url)

