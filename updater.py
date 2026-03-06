"""
StainlessMax Updater v2
- Waits for target process to exit (psutil-based, reliable)
- Extracts update zip into target directory
- Relaunches application
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path


def _wait_pid_exit(pid: int, timeout: int = 90) -> None:
    """Wait for a process PID to exit. Uses psutil if available, falls back to tasklist."""
    if pid <= 0:
        return

    # Try psutil first (most reliable)
    try:
        import psutil
        start = time.time()
        while time.time() - start < timeout:
            try:
                proc = psutil.Process(pid)
                if not proc.is_running():
                    return
            except psutil.NoSuchProcess:
                return
            time.sleep(0.5)
        # Timeout: force kill if still running
        try:
            psutil.Process(pid).kill()
        except Exception:
            pass
        return
    except ImportError:
        pass

    # Fallback: parse tasklist output (more reliable than exit code)
    start = time.time()
    while time.time() - start < timeout:
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"],
                capture_output=True,
                text=True,
                timeout=10
            )
            # If PID is not in output, process has exited
            if str(pid) not in result.stdout:
                return
        except Exception:
            return
        time.sleep(0.5)


def _safe_extract(zip_path: Path, target_dir: Path) -> None:
    """Safely extract zip to target, replacing existing files."""
    tmp_dir = target_dir / "_update_tmp"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir, ignore_errors=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(tmp_dir)

    # Detect if zip has a single root folder (common packaging pattern)
    extracted_root = tmp_dir
    nested = [p for p in tmp_dir.iterdir() if p.is_dir()]
    if len(nested) == 1 and (nested[0] / "StainlessMax.exe").exists():
        extracted_root = nested[0]

    # Copy files to target, skipping user data files
    SKIP_PATTERNS = {".env", "hesaplar.txt", "settings.json"}

    for item in extracted_root.iterdir():
        if item.name in SKIP_PATTERNS:
            print(f"[UPDATER] Skipping user data file: {item.name}")
            continue
        dest = target_dir / item.name
        if dest.exists():
            if dest.is_dir():
                shutil.rmtree(dest, ignore_errors=True)
            else:
                try:
                    dest.unlink()
                except Exception as e:
                    print(f"[UPDATER] Could not remove {dest}: {e}")
        try:
            if item.is_dir():
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)
        except Exception as e:
            print(f"[UPDATER] Failed to copy {item.name}: {e}")

    shutil.rmtree(tmp_dir, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="StainlessMax Updater v2")
    parser.add_argument("--source", required=True, help="Downloaded update zip path")
    parser.add_argument("--target-dir", required=True, help="Installed app directory")
    parser.add_argument("--wait-pid", type=int, default=0, help="PID to wait before replace")
    parser.add_argument("--start", default="", help="Executable path to relaunch after update")
    args = parser.parse_args()

    source = Path(args.source).resolve()
    target_dir = Path(args.target_dir).resolve()

    if not source.exists() or not source.is_file():
        print(f"[UPDATER] ERROR: Source package not found: {source}")
        return 1

    if not source.suffix.lower() == ".zip":
        print(f"[UPDATER] ERROR: Source must be a .zip file: {source}")
        return 1

    target_dir.mkdir(parents=True, exist_ok=True)

    print(f"[UPDATER] Waiting for process {args.wait_pid} to exit...")
    _wait_pid_exit(args.wait_pid)
    print("[UPDATER] Process exited, starting update...")

    try:
        _safe_extract(source, target_dir)
        print("[UPDATER] Files extracted successfully")
    except Exception as e:
        print(f"[UPDATER] ERROR: Extract failed: {e}")
        return 1

    # Clean up downloaded zip
    try:
        source.unlink()
    except Exception:
        pass

    # Relaunch application
    start_cmd = args.start.strip()
    if start_cmd:
        start_exe = Path(start_cmd)
        if not start_exe.exists():
            start_exe = target_dir / "StainlessMax.exe"
    else:
        start_exe = target_dir / "StainlessMax.exe"

    if start_exe.exists():
        print(f"[UPDATER] Relaunching: {start_exe}")
        try:
            subprocess.Popen([str(start_exe)], cwd=str(start_exe.parent))
            print("[UPDATER] Relaunch successful!")
        except Exception as e:
            print(f"[UPDATER] ERROR: Relaunch failed: {e}")
            return 1
    else:
        print(f"[UPDATER] WARNING: Executable not found: {start_exe}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
