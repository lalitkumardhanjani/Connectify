import warnings
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL.*')
import signal
import sys
from pipelines.email_outreach.pipeline import run_pipeline

def handle_sigterm(signum, frame):
    print(f"\n[SYSTEM] Received termination signal {signum}. Closing Chrome and exiting...")
    sys.exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigterm)

    success = run_pipeline(phase="phase1")
    if not success:
        sys.exit(1)
