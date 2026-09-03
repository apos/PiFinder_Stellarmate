"""Waits for PiFinder Mount Bridge to become briefly unresponsive on its INDI
port (the pre-existing, previously-unresolved "Mount Bridge wurde
unresponsive" issue - basic-memory pifinder-stellarmate/00105 #4: a real,
reproducible hang recurring every ~2-5 minutes, not explained by test-tool
polling load - confirmed live 2026-09-03) and, the moment a responsiveness
check fails, immediately attaches gdb (batch mode, detaches again
afterwards - never kills/pauses the process for the user) to capture a full
backtrace of every thread while the hang is actually happening. The earlier
manual "gdb -p <pid>" attempt from a previous session landed too late to
catch the hang in the act; this polls tightly enough to attach within
~1-2s of the failure being detected.

Responsiveness check: a fresh TCP connect + getProperties for the device,
with a short timeout - exactly what the Control Center's own readiness
watchdog does (indi_client.mount_bridge_status()), so a "hang" here is
believed to be the same condition that triggers the watchdog's own restart.
"""

import socket
import subprocess
import sys
import time
from pathlib import Path

HOST = "127.0.0.1"
PORT = 7624
DEVICE = "PiFinder Mount Bridge"
CHECK_TIMEOUT = 2.0
POLL_INTERVAL = 1.0
OUT_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    "/tmp/claude-1000/-home-stellarmate/4395e939-5e43-4a6d-aa71-a40f6119ea5a/scratchpad/hang_captures"
)


def get_pid() -> int | None:
    try:
        out = subprocess.run(["pgrep", "-f", "-o", "indi_pifinder_mount_bridge"],
                              capture_output=True, text=True, timeout=3)
        line = out.stdout.strip().splitlines()
        return int(line[0]) if line else None
    except Exception:
        return None


def check_responsive() -> bool:
    try:
        sock = socket.create_connection((HOST, PORT), timeout=CHECK_TIMEOUT)
        sock.sendall(f'<getProperties version="1.7" device="{DEVICE}"/>\n'.encode())
        sock.settimeout(CHECK_TIMEOUT)
        chunk = sock.recv(4096)
        sock.close()
        return len(chunk) > 0
    except OSError:
        return False


INDISERVER_PID = 1425  # found live 2026-09-03 - Mount Bridge's own two threads were
# both cleanly parked in select() at the moment a responsiveness check failed
# (looks like healthy idle, not a deadlock) - capturing indiserver itself
# alongside it now, to see whether IT is what's actually slow to relay under
# its current connection load, rather than Mount Bridge being "hung" at all.


def _gdb_backtrace(pid: int, f):
    try:
        subprocess.run(
            ["sudo", "gdb", "-p", str(pid), "--batch",
             "-ex", "set pagination off",
             "-ex", "info threads",
             "-ex", "thread apply all bt full",
             "-ex", "detach",
             "-ex", "quit"],
            stdout=f, stderr=subprocess.STDOUT, timeout=20,
        )
    except subprocess.TimeoutExpired:
        f.write("\n[gdb itself timed out after 20s]\n")


def capture(pid: int, reason: str):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%S")
    out_path = OUT_DIR / f"hang_{stamp}_pid{pid}.txt"
    print(f"[{time.strftime('%H:%M:%S')}] {reason} - capturing gdb backtraces (mount bridge {pid} + indiserver {INDISERVER_PID}) -> {out_path}")
    with open(out_path, "w") as f:
        f.write(f"reason: {reason}\ntime: {time.strftime('%Y-%m-%dT%H:%M:%S')}\npid: {pid}\n\n")
        f.flush()
        f.write("=== indiserver (pid %d) - captured FIRST, before touching mount bridge ===\n" % INDISERVER_PID)
        f.flush()
        _gdb_backtrace(INDISERVER_PID, f)
        f.write("\n\n=== indi_pifinder_mount_bridge (pid %d) ===\n" % pid)
        f.flush()
        _gdb_backtrace(pid, f)
        f.write("\n\n--- top -bn1 (CPU snapshot at capture time) ---\n")
        try:
            top = subprocess.run(["top", "-bn1"], capture_output=True, text=True, timeout=5)
            f.write(top.stdout)
        except Exception as e:
            f.write(f"(top failed: {e})\n")
        f.write("\n--- /proc status (mount bridge) ---\n")
        try:
            f.write(Path(f"/proc/{pid}/status").read_text())
        except OSError as e:
            f.write(f"(unreadable: {e})\n")
        f.write("\n--- ss -tnp for indiserver port ---\n")
        try:
            ss = subprocess.run(["ss", "-tnp"], capture_output=True, text=True, timeout=5)
            f.write(ss.stdout)
        except Exception as e:
            f.write(f"(ss failed: {e})\n")
    print(f"[{time.strftime('%H:%M:%S')}] capture written to {out_path}")


def main():
    print("Watching PiFinder Mount Bridge responsiveness - waiting for a hang to catch live.")
    consecutive_fail = 0
    last_pid = get_pid()
    print(f"Initial pid: {last_pid}")
    while True:
        ok = check_responsive()
        now_pid = get_pid()
        if now_pid != last_pid:
            print(f"[{time.strftime('%H:%M:%S')}] pid changed {last_pid} -> {now_pid} (driver restarted)")
            last_pid = now_pid
            consecutive_fail = 0
        if ok:
            consecutive_fail = 0
        else:
            consecutive_fail += 1
            print(f"[{time.strftime('%H:%M:%S')}] responsiveness check FAILED ({consecutive_fail})")
            if consecutive_fail == 1 and last_pid is not None:
                capture(last_pid, "first failed responsiveness check")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
