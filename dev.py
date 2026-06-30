"""
DEPRECATED: Use hot_reloader.py instead.
This file does not rebuild Rust components on change.
Kept for reference only.

Hot-reload development server.

Watches .py files for changes and automatically restarts the bot process.
Usage: uv run dev
"""
import os
import signal
import subprocess
import sys
from pathlib import Path

from watchfiles import watch

# Directories to ignore
IGNORED_DIRS: set[str] = {
    "__pycache__", ".venv", "logs", "bot_data",
    "qdrant_storage", ".git", "node_modules", "dat",
}
# Files to ignore
IGNORED_FILES: set[str] = {"dev.py", "desktop.ini"}


def should_ignore(path: str) -> bool:
    """Check if a changed path should be ignored."""
    parts = Path(path).parts
    for part in parts:
        if part in IGNORED_DIRS:
            return True
    if Path(path).name in IGNORED_FILES:
        return True
    return False


def run_bot() -> subprocess.Popen[bytes]:
    """Start the bot as a subprocess."""
    return subprocess.Popen(
        [sys.executable, "discord_bot.py"],
        cwd=str(Path(__file__).parent),
        stdout=sys.stdout,
        stderr=sys.stderr,
    )


def main() -> None:
    """Watch for .py file changes and restart the bot."""
    project_dir = Path(__file__).parent
    print(f"[dev] Watching {project_dir} for changes...")
    print("[dev] Press Ctrl+C to stop.")

    proc = run_bot()

    try:
        for changes in watch(
            str(project_dir),
            stop_event=signal.Event(),  # type: ignore[arg-type]
        ):
            # Filter out ignored paths
            relevant = {
                change for change in changes
                if not should_ignore(change[1])
            }

            if not relevant:
                continue

            changed_files = {Path(c[1]).name for c in relevant}
            print(f"\n[dev] Changes detected: {', '.join(changed_files)}")
            print("[dev] Restarting bot...")

            # Graceful shutdown: send SIGTERM, then SIGKILL after 5s
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

            print("[dev] Bot stopped. Starting new instance...")
            proc = run_bot()
            print("[dev] Bot restarted. Watching for changes...")

    except KeyboardInterrupt:
        print("\n[dev] Shutting down...")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        print("[dev] Done.")
        sys.exit(0)


if __name__ == "__main__":
    main()
