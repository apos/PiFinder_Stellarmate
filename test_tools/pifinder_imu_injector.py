#!/usr/bin/env python3
"""Feed synthetic IMU orientation samples into PiFinder's own /api/fake_imu
while the simulated mount is actively slewing, so ImuDeadReckoning can
interpolate a smoothly-tracking position *between* pifinder_truth_injector.py's
slower (~2s) /api/fake_solve injections - instead of PiFinder's reported
position sitting frozen and then jumping discretely at each injection, which
Mount Bridge's own drift-plausibility check correctly (but unhelpfully) flags
as an implausible external reposition.

See docs/concepts/full_simulation_imu_dead_reckoning.md for the full design
and the derivation this implements. Independently runnable alongside (not
instead of) pifinder_truth_injector.py - the two share this directory's small
polling primitives (pifinder_indi_polling.py) rather than one importing the
other, so either can run/be understood on its own.

Math summary (see the concept doc's §3 for the full derivation): every
integrator.py FakeSolve re-anchors q_eq2x around whatever q_x2imu this script
happened to be reporting at that instant - so this script only needs to track
rotation *relative to its own last reset*, not the true anchor from the other
script's exact injection moment. It resets that local baseline (sending
q_x2imu = identity) whenever the mount starts moving and periodically while
still moving, comfortably under the fake-solve interval, so any residual
misalignment between the two scripts' anchors never accumulates beyond one
such cycle.
"""

import argparse
import json
import math
import time
import urllib.error
import urllib.request

from pifinder_indi_polling import is_mount_busy, read_ra_dec

DEFAULT_DEVICE = "PiFinder Simulator"
# Re-derive the local baseline (see module docstring) comfortably under
# pifinder_truth_injector.py's own DEFAULT_INTERVAL (2.0s) - not tied to it
# programmatically (the two scripts are independent on purpose), just picked
# with enough margin that a couple of dropped/slow polls here still land
# safely inside one real fake-solve cycle.
DEFAULT_REANCHOR_INTERVAL = 1.5
IDENTITY = (1.0, 0.0, 0.0, 0.0)

# ---- minimal quaternion math (scalar-first w, x, y, z) - no numpy/quaternion
# package dependency, matching this directory's existing "small,
# dependency-free tool" precedent (pifinder_truth_injector.py's own
# docstring). Mirrors PiFinder/python/PiFinder/pointing_model/
# quaternion_transforms.py and imu_dead_reckoning.py's _q_imu2cam table
# exactly - keep in sync if those change.


def q_mul(a, b):
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return (
        aw * bw - ax * bx - ay * by - az * bz,
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
    )


def q_conj(q):
    w, x, y, z = q
    return (w, -x, -y, -z)


def axis_angle2quat(axis, theta):
    ax, ay, az = axis
    norm = math.sqrt(ax * ax + ay * ay + az * az)
    ax, ay, az = ax / norm, ay / norm, az / norm
    s = math.sin(theta / 2)
    return (math.cos(theta / 2), ax * s, ay * s, az * s)


def radec2q_eq(ra_rad, dec_rad, roll_rad=0.0):
    """Port of quaternion_transforms.py's radec2q_eq() - see that function's
    own docstring for the frame convention. roll defaults to 0 (unused by
    this script - Mount Bridge only ever consumes RA/Dec)."""
    q_ra = axis_angle2quat((0, 0, 1), ra_rad)
    q_dec = axis_angle2quat((0, 1, 0), math.pi / 2 - dec_rad)
    q_roll = axis_angle2quat((0, 0, 1), math.pi / 2 + roll_rad)
    return q_mul(q_mul(q_ra, q_dec), q_roll)


def q_imu2cam(screen_direction):
    """Port of imu_dead_reckoning.py's ImuDeadReckoning._q_imu2cam() table -
    fixed IMU-to-camera rotation for PiFinder's hardware geometry presets."""
    table = {
        "left": ((1, 0, 0), math.pi / 2, (0, 0, 1), math.pi / 2),
        "right": ((1, 0, 0), -math.pi / 2, (0, 0, 1), math.pi / 2),
        "straight": ((0, 1, 0), math.pi, (0, 0, 1), -math.pi / 2),
        "flat3": ((0, 1, 0), -math.pi * 2 / 3, (0, 0, 1), -math.pi / 2),
        "flat": ((0, 1, 0), -math.pi / 2, (0, 0, 1), -math.pi / 2),
        "as_bloom": ((0, 1, 0), math.pi, (0, 0, 1), math.pi),
        "as_heart": ((1, 0, 0), math.pi / 2, (0, 0, 1), math.pi),
        "rev4_left": ((1, 0, 0), math.pi / 2, (0, 0, 1), -math.pi / 2),
        "rev4_right": ((1, 0, 0), -math.pi / 2, (0, 0, 1), -math.pi / 2),
        "rev4_straight": ((0, 1, 0), math.pi / 4, (0, 0, 1), -math.pi * 3 / 4),
    }
    if screen_direction not in table:
        raise ValueError(f"Unsupported screen_direction: {screen_direction}")
    axis1, angle1, axis2, angle2 = table[screen_direction]
    return q_mul(axis_angle2quat(axis1, angle1), axis_angle2quat(axis2, angle2))


def relative_x2imu(anchor_ra_h, anchor_dec_deg, target_ra_h, target_dec_deg, imu2cam):
    """q_x2imu that makes ImuDeadReckoning.predict() report (target_ra,
    target_dec) given a q_eq2x established with q_x2imu=IDENTITY at
    (anchor_ra, anchor_dec) - see the module docstring / concept doc §3 for
    the derivation."""
    q_anchor = radec2q_eq(math.radians(anchor_ra_h * 15.0), math.radians(anchor_dec_deg))
    q_target = radec2q_eq(math.radians(target_ra_h * 15.0), math.radians(target_dec_deg))
    relative = q_mul(q_conj(q_anchor), q_target)
    return q_mul(q_mul(imu2cam, relative), q_conj(imu2cam))


def inject_fake_imu(host: str, port: int, q, timeout: float) -> bool:
    w, x, y, z = q
    body = json.dumps({"w": w, "x": x, "y": y, "z": z}).encode()
    req = urllib.request.Request(
        f"http://{host}:{port}/api/fake_imu",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except urllib.error.URLError as e:
        print(f"fake_imu POST failed: {e}")
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--indi-host", default="localhost")
    parser.add_argument("--indi-port", type=int, default=7624)
    parser.add_argument("--indi-device", default=DEFAULT_DEVICE,
                         help="Device whose live position drives the fake IMU - same device "
                              "pifinder_truth_injector.py polls (default: %(default)s)")
    parser.add_argument("--mount-device", default="Telescope Simulator",
                         help="Device whose EQUATORIAL_EOD_COORD._STATE decides 'is it currently "
                              "moving' (default: %(default)s) - deliberately NOT --indi-device: "
                              "'PiFinder Simulator' has no simulated slew time of its own (see its "
                              "own header comment) and never reports Busy, even while correctly "
                              "dead-reckoning-following a real mount slew.")
    parser.add_argument("--pifinder-host", default="localhost")
    parser.add_argument("--pifinder-port", type=int, default=8080)
    parser.add_argument("--screen-direction", required=True,
                         help="Must match this PiFinder unit's actual screen_direction config "
                              "(e.g. 'right') - see PiFinder Mount Bridge's own "
                              "PIFINDER_ORIENTATION.SCREEN_DIRECTION INDI property to read the "
                              "currently-configured value.")
    parser.add_argument("--reanchor-interval", type=float, default=DEFAULT_REANCHOR_INTERVAL,
                         help="Seconds between local-baseline resets while continuously moving "
                              "(default: %(default)s)")
    parser.add_argument("--poll-interval", type=float, default=0.0,
                         help="Minimum seconds between polls (default: 0 - poll as fast as "
                              "indi_getprop's own round-trip allows; measure the achieved rate "
                              "from this script's own printed timestamps and raise this if a "
                              "slower, steadier cadence is wanted instead)")
    args = parser.parse_args()

    imu2cam = q_imu2cam(args.screen_direction)

    print(f"Polling '{args.indi_device}' on {args.indi_host}:{args.indi_port}, "
          f"injecting IMU samples into PiFinder at {args.pifinder_host}:{args.pifinder_port} "
          f"while it's Busy (screen_direction={args.screen_direction}). Ctrl-C to stop.")

    anchor = None  # (ra_hours, dec_deg, monotonic_time_of_reset) or None while not moving
    was_busy = False
    sample_count = 0
    last_rate_report = time.monotonic()

    while True:
        start = time.monotonic()
        busy = is_mount_busy(args.indi_host, args.indi_port, args.mount_device, timeout=1.0)
        pos = read_ra_dec(args.indi_host, args.indi_port, args.indi_device, timeout=1.0)

        if busy and pos is not None:
            ra, dec = pos
            now = time.monotonic()
            needs_reset = (
                anchor is None
                or not was_busy
                or (now - anchor[2]) >= args.reanchor_interval
            )
            if needs_reset:
                anchor = (ra, dec, now)
                inject_fake_imu(args.pifinder_host, args.pifinder_port, IDENTITY, timeout=1.0)
            else:
                q = relative_x2imu(anchor[0], anchor[1], ra, dec, imu2cam)
                inject_fake_imu(args.pifinder_host, args.pifinder_port, q, timeout=1.0)
            sample_count += 1
        else:
            # Mount still (or state unreadable) - stop injecting; imu_fake.py's
            # own debounce (FAKE_MOVING_TIMEOUT_SEC) reports "not moving" on
            # its own once samples stop arriving. Clear the anchor so the
            # *next* motion starts a fresh baseline rather than reusing a
            # stale one from possibly a while ago.
            anchor = None

        was_busy = bool(busy)

        now = time.monotonic()
        if now - last_rate_report >= 5.0:
            elapsed = now - last_rate_report
            print(f"[{time.strftime('%H:%M:%S')}] {sample_count} samples in {elapsed:.1f}s "
                  f"(~{sample_count / elapsed:.1f} Hz), busy={busy}")
            sample_count = 0
            last_rate_report = now

        elapsed = time.monotonic() - start
        time.sleep(max(0.0, args.poll_interval - elapsed))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
