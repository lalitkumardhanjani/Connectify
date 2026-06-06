import subprocess
import sys

def main():
    print("=== Connectify: Updating project from GitHub ===")
    
    # 1. Abort any active merge conflict to clean up the state
    try:
        subprocess.run(
            ["git", "merge", "--abort"],
            capture_output=True,
            text=True,
            check=False
        )
    except Exception:
        pass

    try:
        # 2. Fetch the latest changes from origin
        print("Fetching latest changes from GitHub...")
        subprocess.run(
            ["git", "fetch", "origin"],
            capture_output=True,
            text=True,
            check=True
        )

        # 3. Force-reset the branch to match origin/main exactly
        print("Resetting local branch to match origin/main...")
        result = subprocess.run(
            ["git", "reset", "--hard", "origin/main"],
            capture_output=True,
            text=True,
            check=True
        )

        print("\n[SUCCESS] Project successfully updated to latest version:")
        if result.stdout.strip():
            print(result.stdout)
            
    except FileNotFoundError:
        print("\n[ERROR] Git command not found. Please ensure Git is installed on your system.")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"\n[ERROR] Git update failed with code {e.returncode}:")
        if e.stdout:
            print(f"Stdout:\n{e.stdout}")
        if e.stderr:
            print(f"Stderr:\n{e.stderr}")
        sys.exit(e.returncode)
    except Exception as e:
        print(f"\n[ERROR] Unexpected error during update: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
