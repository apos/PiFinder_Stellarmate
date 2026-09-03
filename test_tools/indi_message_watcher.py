"""Tails INDI <message> traffic for one device by speaking the plain INDI
client protocol directly (a raw TCP connection + getProperties, per the
protocol spec) - not a custom logging channel. LOGF_INFO/LOGF_WARN/LOG_ERROR
(INDI::Logger's DBG_SESSION/DBG_WARNING/DBG_ERROR priorities) are ALWAYS
broadcast to every connected client as <message> elements, regardless of
this driver's own DEBUG.ENABLE switch - addDebugControl() only gates
DBG_DEBUG. Written 2026-09-03 chasing a "mount jumps to RA0/Dec0" bug where
Mount Bridge's own explanatory LOGF_WARN/LOGF_INFO calls (already present
throughout pifinder_mount_bridge.cpp) had nowhere durable to land - EKOS/
KStars' own log viewer shows them live but nothing was tailing/persisting
them to a file for after-the-fact diagnosis.
"""

import socket
import sys
import time
import xml.sax.saxutils as saxutils
from pathlib import Path

HOST = "127.0.0.1"
PORT = 7624
DEVICE = sys.argv[1] if len(sys.argv) > 1 else "PiFinder Mount Bridge"
OUT_PATH = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(
    "/tmp/claude-1000/-home-stellarmate/4395e939-5e43-4a6d-aa71-a40f6119ea5a/scratchpad/mount_bridge_messages.log"
)


def main():
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    print(f"Watching <message> traffic for device={DEVICE!r}, appending to {OUT_PATH}")
    with open(OUT_PATH, "a", buffering=1) as f:
        while True:
            f.write(f"\n--- watcher (re)connected {time.strftime('%Y-%m-%dT%H:%M:%S')} ---\n")
            try:
                sock = socket.create_connection((HOST, PORT), timeout=10)
                sock.sendall(f'<getProperties version="1.7" device="{saxutils.escape(DEVICE)}"/>\n'.encode())
                buf = b""
                while True:
                    chunk = sock.recv(65536)
                    if not chunk:
                        # Driver restarts (self-heal, manual FIFO stop/start) close
                        # this socket - found live 2026-09-03 chasing the very
                        # restart-storm this watcher exists to diagnose: a
                        # non-reconnecting watcher goes silent right when a
                        # restart is the most interesting thing to see.
                        f.write(f"--- connection closed {time.strftime('%Y-%m-%dT%H:%M:%S')} - reconnecting ---\n")
                        break
                    buf += chunk
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        text = line.decode(errors="replace").strip()
                        if text.startswith("<message") and f'device="{DEVICE}"' in text:
                            stamped = f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {text}"
                            print(stamped)
                            f.write(stamped + "\n")
            except OSError as e:
                f.write(f"--- connect failed: {e} - retrying in 2s ---\n")
                time.sleep(2)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
