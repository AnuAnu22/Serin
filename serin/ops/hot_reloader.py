import asyncio
import signal
import sys
import time as time_mod
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

WATCH_DIRS = [
    PROJECT_ROOT,
]
WATCH_FILES = [
    PROJECT_ROOT / "serin_core" / "src" / "lib.rs",
]
RUST_RECEIVER_SRC = PROJECT_ROOT / "voice" / "rust_receiver" / "src"
SIGNAL_FILE = PROJECT_ROOT / ".restart.signal"
BOT_DIR = PROJECT_ROOT
COOLDOWN_SECS = 1.0
GRACE_SECS = 3.0
POLL_INTERVAL = 1.0

bot_process: asyncio.subprocess.Process | None = None
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


async def kill_bot() -> None:
    global bot_process
    if bot_process is None or bot_process.returncode is not None:
        return
    log("Stopping bot...")
    bot_process.terminate()
    try:
        await asyncio.wait_for(bot_process.wait(), timeout=GRACE_SECS)
    except TimeoutError:
        log("Bot did not stop in time, sending SIGKILL...")
        bot_process.kill()
        await bot_process.wait()
    bot_process = None


async def start_bot() -> None:
    global bot_process, last_restart_time
    await kill_bot()
    last_restart_time = time_mod.monotonic()
    log("Starting bot...")
    bot_process = await asyncio.create_subprocess_exec(
        "uv", "run", "-m", "serin",
        cwd=str(BOT_DIR),
        stdout=sys.stdout,
        stderr=sys.stderr,
    )


async def _run_cmd(cmd: list[str], cwd: str, timeout: float | None = None) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise
    return proc.returncode or 0, stdout.decode(), stderr.decode()


async def handle_maturin_change() -> None:
    log("serin-core Rust source changed, building maturin release...")
    returncode, stdout, stderr = await _run_cmd(
        ["maturin", "develop", "--release"],
        cwd=str(PROJECT_ROOT / "serin_core"),
    )
    if stdout:
        print(stdout, end="")
    if stderr:
        print(stderr, end="", file=sys.stderr)
    if returncode != 0:
        log(f"maturin build failed with exit code {returncode}")
    else:
        log("maturin build succeeded")
    await start_bot()


async def handle_voice_receiver_build() -> None:
    log("Voice receiver Rust source changed, building cargo release...")
    try:
        returncode, stdout, stderr = await _run_cmd(
            ["cargo", "build", "--release"],
            cwd=str(RUST_RECEIVER_SRC.parent),
            timeout=300,
        )
        if stdout:
            for line in stdout.splitlines()[-5:]:
                print(f"  [cargo] {line}")
        if stderr:
            for line in stderr.splitlines():
                if line.startswith("error") or line.startswith("warning"):
                    print(f"  [cargo] {line}", file=sys.stderr)
        if returncode != 0:
            log(f"cargo build failed with exit code {returncode}")
        else:
            log("cargo build succeeded — voice_receiver binary updated")
    except TimeoutError:
        log("cargo build timed out after 5 minutes")
    await start_bot()


async def handle_restart() -> None:
    now = time_mod.monotonic()
    if now - last_restart_time < COOLDOWN_SECS:
        return
    await start_bot()


def handle_signal_file() -> bool:
    if SIGNAL_FILE.exists():
        log("Signal file detected, restarting...")
        SIGNAL_FILE.unlink(missing_ok=True)
        return True
    return False


async def watch_loop() -> None:
    global watcher_running
    prev_mtimes = get_mtimes()

    while watcher_running:
        await asyncio.sleep(POLL_INTERVAL)
        if not watcher_running:
            break

        current_mtimes = get_mtimes()
        rust_triggered = False
        py_triggered = False
        voice_receiver_triggered = False

        for path, mtime in current_mtimes.items():
            old = prev_mtimes.get(path)
            if old is not None and mtime > old:
                if path.suffix == ".rs" and RUST_RECEIVER_SRC in path.parents:
                    if not voice_receiver_triggered:
                        voice_receiver_triggered = True
                        ts = time_mod.strftime("%Y-%m-%d %H:%M:%S")
                        log(f"{ts} - Voice receiver source changed: {path.name}")
                        await handle_voice_receiver_build()
                        prev_mtimes = get_mtimes()
                        break
                elif path.name == "Cargo.toml" and path.parent == RUST_RECEIVER_SRC.parent:
                    if not voice_receiver_triggered:
                        voice_receiver_triggered = True
                        ts = time_mod.strftime("%Y-%m-%d %H:%M:%S")
                        log(f"{ts} - Voice receiver Cargo.toml changed")
                        await handle_voice_receiver_build()
                        prev_mtimes = get_mtimes()
                        break
                elif path.suffix == ".rs":
                    if not rust_triggered:
                        rust_triggered = True
                        await handle_maturin_change()
                        prev_mtimes = get_mtimes()
                        break
                elif path.suffix == ".py":
                    if not py_triggered:
                        py_triggered = True
                        ts = time_mod.strftime("%Y-%m-%d %H:%M:%S")
                        log(f"{ts} - Change detected in {path}, restarting...")
                        await handle_restart()
                        prev_mtimes = get_mtimes()
                        break

        if not rust_triggered and not py_triggered and not voice_receiver_triggered:
            prev_mtimes = current_mtimes

        if handle_signal_file():
            ts = time_mod.strftime("%Y-%m-%d %H:%M:%S")
            log(f"{ts} - Restart triggered by signal file")
            await handle_restart()
            prev_mtimes = get_mtimes()


def _signal_handler(signum: int, frame) -> None:
    global watcher_running
    log("Shutting down...")
    watcher_running = False


async def main() -> None:
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    log("Watching for changes...")
    log(f"  Python: {WATCH_DIRS}")
    log(f"  Voice receiver Rust: {RUST_RECEIVER_SRC}")
    log(f"  serin-core Rust: {PROJECT_ROOT / 'serin_core' / 'src' / 'lib.rs'}")
    await start_bot()
    await watch_loop()


if __name__ == "__main__":
    asyncio.run(main())
