import argparse
from pipelines.email_outreach.pipeline import run_pipeline

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Connectify Email Outreach Pipeline Runner")
    parser.add_argument(
        "--phase",
        choices=["full", "phase1", "phase2"],
        default="full",
        help="Pipeline phase to execute (full, phase1, phase2)"
    )
    parser.add_argument(
        "--review",
        action="store_true",
        help="Review emails before sending"
    )
    args = parser.parse_args()
    run_pipeline(phase=args.phase, review_mode=args.review)
