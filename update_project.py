"""
update_project.py — Connectify Project Updater
-----------------------------------------------
Run this script to safely pull the latest code changes from GitHub.

Usage:
    python update_project.py

What it does:
  1. Aborts any pending git merge conflict (safe no-op if none exists).
  2. Fetches the latest commits from origin/main.
  3. Force-resets the local branch to match origin/main exactly.
  4. Optionally reinstalls pip dependencies if requirements.txt changed.

Your local user data (users/ directory) is git-ignored and will NEVER
be touched or overwritten by this script.
"""

import subprocess
import sys
import os


def run_cmd(args, check=True, capture=True):
    return subprocess.run(
        args,
        capture_output=capture,
        text=True,
        check=check,
    )


def main():
    print("=" * 55)
    print("  Connectify: Updating project from GitHub")
    print("=" * 55)

    # ── 1. Abort any stale merge conflict ────────────────────
    try:
        run_cmd(["git", "merge", "--abort"], check=False)
    except Exception:
        pass

    try:
        # ── 2. Fetch latest from origin ───────────────────────
        print("\n[1/3] Fetching latest changes from GitHub...")
        run_cmd(["git", "fetch", "origin"])
        print("      ✓ Fetch complete.")

        # ── 3. Check what changed ─────────────────────────────
        diff_result = run_cmd(["git", "diff", "--name-only", "HEAD", "origin/main"])
        changed_files = [f.strip() for f in diff_result.stdout.splitlines() if f.strip()]
        requirements_changed = "requirements.txt" in changed_files

        # ── 4. Reset to origin/main ───────────────────────────
        print("\n[2/3] Resetting local branch to match origin/main...")
        result = run_cmd(["git", "reset", "--hard", "origin/main"])
        print("      ✓ Reset complete.")
        if result.stdout.strip():
            print(f"      {result.stdout.strip()}")

        # ── 5. Show summary of changed files ─────────────────
        if changed_files:
            print(f"\n      Updated {len(changed_files)} file(s):")
            for f in changed_files[:15]:
                print(f"        • {f}")
            if len(changed_files) > 15:
                print(f"        ... and {len(changed_files) - 15} more.")
        else:
            print("\n      Already up to date — no changes pulled.")

        # ── 6. Reinstall dependencies if requirements changed ─
        if requirements_changed:
            print("\n[3/3] requirements.txt changed — reinstalling dependencies...")
            pip_result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
                capture_output=False,  # stream output live
                text=True,
                check=False,
            )
            if pip_result.returncode == 0:
                print("      ✓ Dependencies updated.")
            else:
                print("      ⚠ pip install exited with errors. Check output above.")
        else:
            print("\n[3/3] No dependency changes detected — skipping pip install.")

        print("\n" + "=" * 55)
        print("  ✅  Project successfully updated to latest version!")
        print("=" * 55)

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
