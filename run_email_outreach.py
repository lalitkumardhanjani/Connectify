import warnings
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL.*')
import argparse
import signal
import sys
from pipelines.email_outreach.pipeline import run_pipeline

def handle_sigterm(signum, frame):
    print(f"\n[SYSTEM] Received termination signal {signum}. Closing Chrome and exiting...")
    sys.exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigterm)
    
    parser = argparse.ArgumentParser(description="Connectify Email Outreach Pipeline Runner")
    parser.add_argument(
        "--phase",
        choices=["full", "phase1", "phase2"],
        default="full",
        help="Pipeline phase to execute (full, phase1, phase2)"
    )
    parser.add_argument(
        "--review",
        dest="review",
        action="store_true",
        help="Review emails before sending (overrides config)"
    )
    parser.add_argument(
        "--no-review",
        dest="review",
        action="store_false",
        help="Do not review emails before sending (overrides config)"
    )
    parser.set_defaults(review=None)
    args = parser.parse_args()
    success = run_pipeline(phase=args.phase, review_mode=args.review)
    if not success:
        sys.exit(1)

