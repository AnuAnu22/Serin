import os
import sys
import time
import signal
import subprocess
from pathlib import Path

WATCH_DIRS = [
    Path("/home/user3/Documents/SerinBot/Serin"),
]
WATCH_FILES = [
    Path("/mnt/sdc/serin-core/src/lib.rs"),
]
SIGNAL_FILE = Path("/tmp/serin-restart.signal")
BOT_DIR = Path("/home/user3/Documents/SerinBot/Serin")
COOLDOWN_SECS = 1.0
GRACE_SECS = 3.0
POLL_INTERVAL = 1.0

bot_process: subprocess.Popen | None = None
last_restart_time: float = 0.0
watcher_running = True


def log(msg: str) -> None:
    print(f"[HOT-RELOADER] {msg}", flush=True)


def get_py_files() -> list[Path]:
    files: list[Path] = []
    for d in WATCH_DIRS:
        if d.is_dir():
            files.extend(d.rglob("*.py"))
    return files


def get_mtimes() -> dict[Path, float]:
    mtimes: dict[Path, float] = {}
    for p in get_py_files():
        try:
            mtimes[p] = p.stat().st_mtime
        except FileNotFoundError:
            pass
    for p in WATCH_FILES:
        if p.exists():
            try:
                mtimes[p] = p.stat().st_mtime
            except FileNotFoundError:
                pass
    return mtimes


def kill_bot() -> None:
    global bot_process
    if bot_process is None or bot_process.returncode is not None:
        return
    log("Stopping bot...")
    bot_process.terminate()
    try:
        bot_process.wait(timeout=GRACE_SECS)
    except subprocess.TimeoutExpired:
        log("Bot did not stop in time, sending SIGKILL...")
        bot_process.kill()
        bot_process.wait()
    bot_process = None


def start_bot() -> None:
    global bot_process, last_restart_time
    kill_bot()
    last_restart_time = time.monotonic()
    log("Starting bot...")
    bot_process = subprocess.Popen(
        ["uv", "run", "discord_bot.py"],
        cwd=str(BOT_DIR),
        stdout=sys.stdout,
        stderr=sys.stderr,
    )


def handle_rust_change() -> None:
    log("Rust source changed, building maturin release...")
    result = subprocess.run(
        ["maturin", "develop", "--release"],
        cwd="/mnt/sdc/serin-core",
        capture_output=True,
        text=True,
    )
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    if result.returncode != 0:
        log(f"maturin build failed with exit code {result.returncode}")
    else:
        log("maturin build succeeded")
    start_bot()


def handle_restart() -> None:
    now = time.monotonic()
    if now - last_restart_time < COOLDOWN_SECS:
        return
    start_bot()


def handle_signal_file() -> bool:
    if SIGNAL_FILE.exists():
        log("Signal file detected, restarting...")
        SIGNAL_FILE.unlink(missing_ok=True)
        return True
    return False


def watch_loop() -> None:
    global watcher_running
    prev_mtimes = get_mtimes()

    while watcher_running:
        time.sleep(POLL_INTERVAL)
        if not watcher_running:
            break

        current_mtimes = get_mtimes()
        rust_triggered = False
        py_triggered = False

        for path, mtime in current_mtimes.items():
            old = prev_mtimes.get(path)
            if old is not None and mtime > old:
                if path.suffix == ".rs":
                    if not rust_triggered:
                        rust_triggered = True
                        handle_rust_change()
                        prev_mtimes = get_mtimes()
                        break
                elif path.suffix == ".py":
                    if not py_triggered:
                        py_triggered = True
                        ts = time.strftime("%Y-%m-%d %H:%M:%S")
                        log(f"{ts} - Change detected in {path}, restarting...")
                        handle_restart()
                        prev_mtimes = get_mtimes()
                        break

        if not rust_triggered and not py_triggered:
            prev_mtimes = current_mtimes

        if handle_signal_file():
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            log(f"{ts} - Restart triggered by signal file")
            handle_restart()
            prev_mtimes = get_mtimes()


def main() -> None:
    global watcher_running

    def cleanup(signum: int, frame) -> None:
        global watcher_running
        log("Shutting down...")
        watcher_running = False
        kill_bot()
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    log("Watching for changes...")
    start_bot()
    watch_loop()


if __name__ == "__main__":
    main()
