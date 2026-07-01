import os
import sys
import time
import signal
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

WATCH_DIRS = [
    PROJECT_ROOT,
]
WATCH_FILES = [
    PROJECT_ROOT / "serin_core" / "src" / "lib.rs",
]
# Rust voice receiver source directory — changes here trigger cargo build
RUST_RECEIVER_SRC = PROJECT_ROOT / "voice" / "rust_receiver" / "src"
SIGNAL_FILE = Path("/tmp/serin-restart.signal")
BOT_DIR = PROJECT_ROOT
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
    # Track Rust voice receiver source files (.rs and Cargo.toml)
    cargo_toml = RUST_RECEIVER_SRC.parent / "Cargo.toml"
    if cargo_toml.exists():
        try:
            mtimes[cargo_toml] = cargo_toml.stat().st_mtime
        except FileNotFoundError:
            pass
    if RUST_RECEIVER_SRC.is_dir():
        for rs_file in RUST_RECEIVER_SRC.rglob("*.rs"):
            try:
                mtimes[rs_file] = rs_file.stat().st_mtime
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
        ["uv", "run", "-m", "serin"],
        cwd=str(BOT_DIR),
        stdout=sys.stdout,
        stderr=sys.stderr,
    )


def handle_maturin_change() -> None:
    """Handle change in serin-core Rust lib (maturin build)."""
    log("serin-core Rust source changed, building maturin release...")
    result = subprocess.run(
        ["maturin", "develop", "--release"],
        cwd=str(PROJECT_ROOT / "serin_core"),
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


def handle_voice_receiver_build() -> None:
    """Handle change in voice receiver Rust source (cargo build)."""
    log("Voice receiver Rust source changed, building cargo release...")
    result = subprocess.run(
        ["cargo", "build", "--release"],
        cwd=str(RUST_RECEIVER_SRC.parent),
        capture_output=True,
        text=True,
        timeout=300,  # 5 min timeout for Rust builds
    )
    if result.stdout:
        for line in result.stdout.splitlines()[-5:]:
            print(f"  [cargo] {line}")
    if result.stderr:
        # Only print errors/warnings, not full compilation output
        for line in result.stderr.splitlines():
            if line.startswith("error") or line.startswith("warning"):
                print(f"  [cargo] {line}", file=sys.stderr)
    if result.returncode != 0:
        log(f"cargo build failed with exit code {result.returncode}")
    else:
        log("cargo build succeeded — voice_receiver binary updated")
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
        voice_receiver_triggered = False

        for path, mtime in current_mtimes.items():
            old = prev_mtimes.get(path)
            if old is not None and mtime > old:
                # Voice receiver Rust source (.rs or Cargo.toml under voice/rust_receiver/src/)
                if path.suffix == ".rs" and RUST_RECEIVER_SRC in path.parents:
                    if not voice_receiver_triggered:
                        voice_receiver_triggered = True
                        ts = time.strftime("%Y-%m-%d %H:%M:%S")
                        log(f"{ts} - Voice receiver source changed: {path.name}")
                        handle_voice_receiver_build()
                        prev_mtimes = get_mtimes()
                        break
                elif path.name == "Cargo.toml" and path.parent == RUST_RECEIVER_SRC.parent:
                    if not voice_receiver_triggered:
                        voice_receiver_triggered = True
                        ts = time.strftime("%Y-%m-%d %H:%M:%S")
                        log(f"{ts} - Voice receiver Cargo.toml changed")
                        handle_voice_receiver_build()
                        prev_mtimes = get_mtimes()
                        break
                # serin-core Rust source (maturin)
                elif path.suffix == ".rs":
                    if not rust_triggered:
                        rust_triggered = True
                        handle_maturin_change()
                        prev_mtimes = get_mtimes()
                        break
                # Python files
                elif path.suffix == ".py":
                    if not py_triggered:
                        py_triggered = True
                        ts = time.strftime("%Y-%m-%d %H:%M:%S")
                        log(f"{ts} - Change detected in {path}, restarting...")
                        handle_restart()
                        prev_mtimes = get_mtimes()
                        break

        if not rust_triggered and not py_triggered and not voice_receiver_triggered:
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
    log(f"  Python: {WATCH_DIRS}")
    log(f"  Voice receiver Rust: {RUST_RECEIVER_SRC}")
    log(f"  serin-core Rust: {PROJECT_ROOT / 'serin_core' / 'src' / 'lib.rs'}")
    start_bot()
    watch_loop()


if __name__ == "__main__":
    main()
