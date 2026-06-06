import subprocess
import sys

def main():
    print("=== Connectify: Checking for updates from GitHub ===")
    try:
        # Run git pull command
        result = subprocess.run(
            ["git", "pull"],
            capture_output=True,
            text=True,
            check=True
        )
        print("\n[SUCCESS] Git Pull complete:")
        if result.stdout.strip():
            print(result.stdout)
        else:
            print("Already up to date.")
    except FileNotFoundError:
        print("\n[ERROR] Git command not found. Please ensure Git is installed on your system.")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"\n[ERROR] Git pull failed with code {e.returncode}:")
        if e.stdout:
            print(f"Stdout:\n{e.stdout}")
        if e.stderr:
            print(f"Stderr:\n{e.stderr}")
        sys.exit(e.returncode)
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
