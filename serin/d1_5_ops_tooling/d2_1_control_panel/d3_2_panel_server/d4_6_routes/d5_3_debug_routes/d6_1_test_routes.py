from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

from fastapi import FastAPI

_logger = logging.getLogger("control_panel")

_background_tasks: set[asyncio.Task[Any]] = set()


def register_test_routes(app: FastAPI, bot_state: dict[str, Any]) -> None:
    @app.post("/api/tests/run")
    async def run_tests(data: dict[str, Any]) -> Any:
        test_path = data.get("test_path", "tests/")
        verbose = data.get("verbose", True)
        try:
            cmd = ["python", "-m", "pytest", test_path, "-v" if verbose else "", "--tb=short", "-q"]
            cmd = [c for c in cmd if c]
            start = time.perf_counter()
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120.0)
            except TimeoutError:
                proc.kill()
                await proc.wait()
                return {"success": False, "error": "timeout", "output": "Test execution timed out after 120 seconds"}
            duration = round(time.perf_counter() - start, 2)
            output = stdout.decode() + stderr.decode()
            return _parse_test_output(output, duration)
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.get("/api/tests/list")
    async def list_test_files() -> Any:
        try:
            test_files = []
            base = "tests/"
            if not os.path.isdir(base):
                return {"test_files": []}
            for root, _dirs, files in os.walk(base):
                for f in files:
                    if f.startswith("test_") and f.endswith(".py"):
                        rel = os.path.join(root, f)
                        test_files.append(rel)
            return {"test_files": sorted(test_files)}
        except Exception as e:
            return {"error": str(e), "test_files": []}

    @app.post("/api/tests/run-single")
    async def run_single_test(data: dict[str, Any]) -> Any:
        test_file = data.get("test_file", "")
        test_name = data.get("test_name", "")
        if not test_file.startswith("tests/"):
            return {"success": False, "error": "Invalid test file path"}
        if not os.path.isfile(test_file):
            return {"success": False, "error": f"Test file not found: {test_file}"}
        try:
            target = f"{test_file}::{test_name}" if test_name else test_file
            cmd = ["python", "-m", "pytest", target, "-v", "--tb=short", "-q"]
            start = time.perf_counter()
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120.0)
            except TimeoutError:
                proc.kill()
                await proc.wait()
                return {"success": False, "error": "timeout", "output": "Test execution timed out after 120 seconds"}
            duration = round(time.perf_counter() - start, 2)
            output = stdout.decode() + stderr.decode()
            return _parse_test_output(output, duration)
        except Exception as e:
            return {"success": False, "error": str(e)}

    _logger.info("Registered: test routes")


def _parse_test_output(output: str, duration: float) -> dict[str, Any]:
    summary: dict[str, int] = {"total": 0, "passed": 0, "failed": 0, "errors": 0, "skipped": 0}
    for line in output.split("\n"):
        parts = line.strip().split()
        if "passed" in line and "failed" in line:
            for p in parts:
                if p.isdigit():
                    summary["total"] += int(p)
        if line.startswith("FAILED") or "FAILED " in line:
            summary["failed"] += 1
        if "ERROR" in line and "failed" not in line.lower():
            summary["errors"] += 1
        if "skipped" in line:
            for p in parts:
                if p.isdigit():
                    summary["skipped"] += int(p)
    import re
    m = re.search(r"=+ ([\d]+) passed", output)
    if m:
        summary["passed"] = int(m.group(1))
    m = re.search(r"([\d]+) failed", output)
    if m:
        summary["failed"] = int(m.group(1))
    m = re.search(r"([\d]+) error", output)
    if m:
        summary["errors"] = int(m.group(1))
    m = re.search(r"([\d]+) skipped", output)
    if m:
        summary["skipped"] = int(m.group(1))
    summary["total"] = summary["passed"] + summary["failed"] + summary["errors"] + summary["skipped"]
    return {
        "success": True,
        "output": output,
        "summary": summary,
        "duration_seconds": duration,
    }
