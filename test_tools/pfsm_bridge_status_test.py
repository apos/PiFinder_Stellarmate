#!/usr/bin/env python3
"""PiFinder's pfsm_bridge_status module (the Mount Bridge's positioning status on PiFinder's title bar).

    ~/PiFinder/python/.venv/bin/python test_tools/pfsm_bridge_status_test.py

Loads the module from the PiFinder checkout (or from PFSM_BRIDGE_STATUS_MODULE) so it tests what is installed there.
"""
import importlib.util
import os
import tempfile
import unittest

MODULE = os.environ.get("PFSM_BRIDGE_STATUS_MODULE", os.path.expanduser("~/PiFinder/python/PiFinder/pfsm_bridge_status.py"))
spec = importlib.util.spec_from_file_location("pfsm_bridge_status", MODULE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


T0 = 1795703866.0  # a real Unix time: the first version dropped timestamps above 1e9 and every status looked stale


def status(phase="REFINING", **o):
    d = {"phase": phase, "attempt": 1, "attempts_max": 3, "residual_arcmin": 7.7, "to_go_deg": 0}
    d.update(o)
    return d


class BridgeStatusTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "status.json")
        m._cache["mtime"] = None
        m._cache["data"] = None

    def test_clean_accepts_a_status_and_derives_hands_off(self):
        self.assertTrue(m.clean(status("SLEWING"))["hands_off"])
        self.assertTrue(m.clean(status("VERIFYING"))["hands_off"])
        self.assertTrue(m.clean(status("REFINING"))["hands_off"])
        self.assertFalse(m.clean(status("ON_TARGET"))["hands_off"])
        self.assertFalse(m.clean(status("GAVE_UP"))["hands_off"])

    def test_the_posted_hands_off_flag_is_not_trusted(self):
        self.assertFalse(m.clean(dict(status("ON_TARGET"), hands_off=True))["hands_off"])

    def test_clean_rejects_what_is_not_a_status(self):
        for bad in (None, [], "x", {}, {"phase": "NOPE"}, {"phase": ""}):
            self.assertIsNone(m.clean(bad))

    def test_clean_survives_junk_numbers(self):
        c = m.clean(status(residual_arcmin="x", attempt=None, to_go_deg=float("nan")))
        self.assertEqual((c["residual_arcmin"], c["attempt"], c["to_go_deg"]), (0.0, 0, 0.0))

    def test_hands_off_in_the_title_bar_while_fresh(self):
        m.write(status("REFINING"), self.path, now=T0)
        self.assertEqual(m.titlebar(self.path, now=T0 + 3.0), ("HANDS OFF", True))
        m.write(status("SLEWING"), self.path, now=T0)
        self.assertEqual(m.titlebar(self.path, now=T0 + 3.0), ("HANDS OFF", True))

    def test_a_stale_hands_off_is_ignored(self):
        """The fail-safe: a Bridge that stopped posting must not leave HANDS OFF on the screen."""
        m.write(status("SLEWING"), self.path, now=T0)
        self.assertIsNotNone(m.titlebar(self.path, now=T0 + m.FRESH_SEC - 0.1))
        self.assertIsNone(m.titlebar(self.path, now=T0 + m.FRESH_SEC + 0.1))

    def test_on_target_shows_for_a_while_not_inverted(self):
        m.write(status("ON_TARGET", residual_arcmin=0.7), self.path, now=T0)
        self.assertEqual(m.titlebar(self.path, now=T0 + 5.0), ("ON TARGET", False))
        self.assertIsNone(m.titlebar(self.path, now=T0 + m.SHOW_DONE_SEC + 1))

    def test_gave_up_says_the_hand_controller_is_free(self):
        m.write(status("GAVE_UP", residual_arcmin=2.4), self.path, now=T0)
        self.assertEqual(m.titlebar(self.path, now=T0 + 10.0), ("Hand OK 2.4'", False))
        self.assertIsNone(m.titlebar(self.path, now=T0 + m.SHOW_GAVE_UP_SEC + 1))

    def test_idle_and_holding_leave_the_normal_title(self):
        for phase in ("IDLE", "HOLDING"):
            m.write(status(phase), self.path, now=T0)
            self.assertIsNone(m.titlebar(self.path, now=T0 + 1.0))

    def test_no_file_or_a_broken_file_is_the_normal_title(self):
        self.assertIsNone(m.titlebar(self.path, now=1.0))
        with open(self.path, "w") as f:
            f.write("{not json")
        self.assertIsNone(m.titlebar(self.path, now=1.0))

    def test_a_newer_post_replaces_the_old_one(self):
        m.write(status("SLEWING"), self.path, now=T0)
        self.assertEqual(m.titlebar(self.path, now=T0 + 1.0)[0], "HANDS OFF")
        os.utime(self.path, (1.0, 1.0))  # make sure the mtime differs for the cache
        m.write(status("ON_TARGET", residual_arcmin=0.5), self.path, now=T0 + 2.0)
        self.assertEqual(m.titlebar(self.path, now=T0 + 3.0), ("ON TARGET", False))

    def test_a_real_world_timestamp_survives_the_round_trip(self):
        stored = m.write(status("SLEWING"), self.path)
        self.assertGreater(stored["ts"], 1.7e9)
        self.assertEqual(m.titlebar(self.path), ("HANDS OFF", True))

    def test_the_title_fits_the_title_bar(self):
        """The title bar holds about 13 characters on a 128 px display; longer text is cut with an ellipsis (seen live)."""
        for phase, extra in (("SLEWING", {}), ("REFINING", {"residual_arcmin": 123.4}), ("ON_TARGET", {}), ("GAVE_UP", {"residual_arcmin": 123.4})):
            m.write(status(phase, **extra), self.path, now=T0)
            self.assertLessEqual(len(m.titlebar(self.path, now=T0 + 1.0)[0]), 13, phase)

    def test_register_posts_and_rejects(self):
        try:
            import flask
        except ImportError:
            self.skipTest("flask not available")
        app = flask.Flask("t")
        m.PATH = self.path
        m.write.__defaults__ = (self.path, None)
        m.register(app)
        client = app.test_client()
        self.assertEqual(client.post("/api/bridge_positioning", json=status("SLEWING")).status_code, 200)
        self.assertEqual(client.post("/api/bridge_positioning", json={"phase": "X"}).status_code, 400)
        self.assertEqual(client.post("/api/bridge_positioning", data="not json").status_code, 400)


if __name__ == "__main__":
    unittest.main()
