"""Stress-tests PiFinder's real PushTo mechanism end-to-end, repeatedly and
automatically.

Two approaches were tried and rejected before this one (2026-09-04):
  - Writing directly to "PiFinder LX200.TARGET_EOD_COORD" via INDI - refused,
    confirmed perm="ro" via a raw getProperties query. That property is a
    read-only mirror PiFinder's own LX200 driver publishes, not a command
    channel.
  - Opening a second raw TCP client to pos_server.py (port 4030, the
    protocol KStars/SkySafari speak) - pos_server is single-client
    (`listen(1)`, one blocking accept loop); "PiFinder LX200"'s own INDI
    driver already holds a permanent connection there (confirmed live via
    `ss -tnp`, pid of indi_pifinder_lx200), so a second raw socket never
    gets served.

What actually works, confirmed live: writing to "PiFinder LX200"'s standard
INDI mount-interface properties (EQUATORIAL_EOD_COORD + ON_COORD_SET) - the
exact same properties/pattern KStars used for the session's earlier real
PushTo test. The driver forwards this over its own already-open pos_server
connection as `:Sr`/`:Sd`/`:MS`, which calls PiFinder's real
handle_goto_command() (set_new_pushto(True), ui_queue.put("push_object"),
add_recent()) - the same internal chain a real PiFinder-UI push-to triggers -
and PiFinder republishes its own read-only TARGET_EOD_COORD from there,
firing Mount Bridge's Fall-1 PushTo forwarding. Confirmed live before
building this script: pushing RA 13.0h/DEC 40.0d this way produced
"New PiFinder target (RA 12.9994h, DEC 40.0034 deg) ... forwarded Goto to
mount." in Mount Bridge's own log.

Reuses goto_hold_verify.py's j2000_to_jnow()/report()/wait_for_settle() for
consistent, correctly-precessed verification (see that module's own header
comment on why a raw J2000-into-JNow injection would itself look like a bug).
"""

import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from goto_hold_verify import j2000_to_jnow, report, wait_for_settle, TARGETS  # noqa: E402


def indi_set(prop_value: str):
    try:
        subprocess.run(["indi_setprop", "-t", "8", prop_value], capture_output=True, timeout=10)
    except subprocess.TimeoutExpired:
        print(f"  (indi_set timed out: {prop_value})")


def pushto(target_name: str, ra_j2000_h: float, dec_j2000_d: float):
    """Simulates a real external PushTo to PiFinder (the same INDI-property
    write KStars performs), NOT a Mount-Bridge-only shortcut."""
    ra_jnow_h, dec_jnow_d = j2000_to_jnow(ra_j2000_h, dec_j2000_d)
    print(f"\n=== PushTo {target_name} via PiFinder LX200 (INDI): "
          f"J2000 {ra_j2000_h:.4f}h/{dec_j2000_d:.4f} -> JNow {ra_jnow_h:.4f}h/{dec_jnow_d:.4f} ===")
    indi_set("PiFinder LX200.ON_COORD_SET.TRACK=On")
    indi_set(f"PiFinder LX200.EQUATORIAL_EOD_COORD.RA={ra_jnow_h};DEC={dec_jnow_d}")


def main(rounds: int = 3):
    print(f"Starting PiFinder PushTo stress test - {rounds} round(s) over {len(TARGETS)} targets.")
    results = []
    for r in range(rounds):
        for name, j2000_ra, j2000_dec in TARGETS:
            pushto(name, j2000_ra, j2000_dec)
            settled = wait_for_settle(j2000_ra, j2000_dec)
            print(f"  (settled: {settled})")
            ind2, ind3, ind4 = report(name, j2000_ra, j2000_dec)
            ok = settled and all(v <= 2.0 for v in (ind2, ind3, ind4))
            results.append((f"{name} (round {r + 1})", ok, ind2, ind3, ind4))
            time.sleep(1)

        # Re-push the very same target back-to-back once per round - the
        # user's own long-standing "does one push really suffice" question
        # (2026-09-03/04 session), now automated instead of a single manual
        # click.
        name, j2000_ra, j2000_dec = TARGETS[r % len(TARGETS)]
        print(f"\n--- Immediate re-push of the same target ({name}) ---")
        pushto(name, j2000_ra, j2000_dec)
        settled = wait_for_settle(j2000_ra, j2000_dec, max_wait_sec=30)
        ind2, ind3, ind4 = report(f"{name} (re-push)", j2000_ra, j2000_dec)
        ok = settled and all(v <= 2.0 for v in (ind2, ind3, ind4))
        results.append((f"{name} (re-push, round {r + 1})", ok, ind2, ind3, ind4))

    print("\n=== Summary ===")
    for name, ok, ind2, ind3, ind4 in results:
        print(f"{name:28s} Mount-PiFinder={ind2:6.2f}'  Mount-Original={ind3:6.2f}'  "
              f"PiFinder-Original={ind4:6.2f}'  {'PASS' if ok else 'FAIL'}")
    n_fail = sum(1 for _, ok, *_ in results if not ok)
    print(f"\n{len(results) - n_fail}/{len(results)} passed.")


if __name__ == "__main__":
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    main(rounds)
