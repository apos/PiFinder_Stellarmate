#!/usr/bin/env python3
"""The time and location cross-check of gui_installer/clock_status.py, no Pi needed:  python3 test_tools/clock_status_test.py"""
import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "gui_installer"))
import clock_status as cs  # noqa: E402

UTC = datetime.timezone.utc
NOW = datetime.datetime(2026, 11, 28, 8, 6, 7, tzinfo=UTC)
HOME = (49.4776, 8.4508)


def ago(seconds):
    return NOW - datetime.timedelta(seconds=seconds)


def inputs(mount=None, kstars=True, pifinder=None, ntp=True, **mount_values):
    if mount is None:
        mount = {"device": "Mount", "time_utc": ago(100), "offset": 1.0, "location": HOME, "seen_utc": None, "real": None}
        mount.update(mount_values)
    return {"now": NOW, "pi_offset": 1.0, "ntp": ntp, "mount": mount or None, "pifinder": pifinder,
            "kstars": {"location": HOME, "offset": 1.0, "realtime": True} if kstars is True else kstars}


def check(data, **kwargs):
    return cs.evaluate(data, 0.0, {}, immediately=True, **kwargs)


class Compare(unittest.TestCase):
    def test_everything_agrees(self):
        r = check(inputs(pifinder={"location": HOME, "utc": NOW}))
        self.assertEqual(r["current"], [])
        self.assertTrue(r["can_set_mount"])
        self.assertEqual([row["source"] for row in r["rows"]], ["KStars (reference)", "Mount (Mount)", "PiFinder", "This Pi"])

    def test_an_old_time_value_is_no_clock_error(self):
        # found 2026-11-28: TIME_UTC was set at the profile start five hours earlier and does not run on
        r = check(inputs(time_utc=ago(5 * 3600 + 540)))
        self.assertEqual(r["current"], [])
        self.assertIsNone(r["mount_skew_sec"])
        self.assertIn("does not run on", r["rows"][1]["note"])

    def test_a_wrong_time_seen_being_set_counts(self):
        r = check(inputs(time_utc=ago(3 * 3600), seen_utc=ago(30)))
        self.assertEqual(len(r["current"]), 1)
        self.assertIn("3 h behind when it was set", r["current"][0])
        self.assertTrue(r["mount_warn"])

    def test_a_good_time_seen_being_set_stays_good(self):
        r = check(inputs(time_utc=ago(5 * 3600), seen_utc=ago(5 * 3600 - 15)))
        self.assertEqual(r["current"], [])

    def test_a_clock_read_from_the_mount(self):
        self.assertEqual(check(inputs(real={"utc": ago(60), "location": HOME}))["current"], [])
        r = check(inputs(real={"utc": ago(-600), "location": HOME}))
        self.assertIn("own clock is 10 min ahead", r["current"][0])

    def test_mount_location(self):
        r = check(inputs(location=(49.405, 8.640)))
        self.assertEqual(len(r["current"]), 1)
        self.assertIn("16 km from KStars", r["current"][0])
        self.assertEqual(r["rows"][1]["wrong"], ["location"])
        self.assertEqual(check(inputs(location=(49.4800, 8.4520)))["current"], [], "a few hundred metres are fine")

    def test_the_site_stored_in_an_onstep(self):
        self.assertEqual(check(inputs(real={"utc": NOW, "location": (49.4667, 8.45)}))["current"], [], "whole arc minutes")
        r = check(inputs(real={"utc": NOW, "location": (48.0, 8.45)}))
        self.assertIn("stored in the mount", r["current"][0])

    def test_time_zone_offsets(self):
        r = check(inputs(offset=2.0))
        self.assertIn("The mount has UTC+2:00, this Pi's time zone is UTC+1:00 now.", r["current"])
        r = check(inputs(kstars={"location": HOME, "offset": 0.0, "realtime": True}))
        self.assertIn("KStars works with UTC+0:00", r["current"][0])

    def test_a_simulated_kstars_clock_blocks_the_fix(self):
        r = check(inputs(kstars={"location": HOME, "offset": 1.0, "realtime": False}))
        self.assertIn("simulated time", r["current"][0])
        self.assertFalse(r["can_set_mount"])

    def test_without_kstars_nothing_is_guessed(self):
        r = check(inputs(kstars=None, location=(0.0, 0.0)))
        self.assertEqual(r["current"], [])
        self.assertFalse(r["can_set_mount"])
        self.assertIn("not reachable", r["rows"][0]["note"])

    def test_pifinder(self):
        r = check(inputs(pifinder={"location": (47.0, 8.45), "utc": ago(3600)}))
        self.assertEqual(len(r["current"]), 2)
        self.assertFalse(r["mount_warn"])

    def test_no_mount(self):
        r = check(inputs(mount=False))
        self.assertFalse(r["can_set_mount"])
        self.assertEqual(r["current"], [])


class HostAndClient(unittest.TestCase):
    """A Control host with the PiFinder on another computer."""

    def data(self, **peer):
        values = {"host": "pifinder.local", "reachable": True, "time_utc": NOW, "offset": 1.0, "location": HOME, "ntp": True}
        values.update(peer)
        data = inputs(pifinder={"location": HOME, "utc": NOW, "host": "pifinder.local"})
        data["peer"] = values
        return data

    def test_both_agree(self):
        r = check(self.data())
        self.assertEqual(r["current"], [])
        self.assertEqual([row["source"] for row in r["rows"]][-3:],
                         ["PiFinder (pifinder.local)", "PiFinder's computer (pifinder.local)", "This Pi"])

    def test_the_other_computers_clock_offset_and_place(self):
        r = check(self.data(time_utc=ago(900), offset=2.0, location=(47.0, 8.45)))
        self.assertEqual(len(r["current"]), 3)
        self.assertIn("The clock of pifinder.local is 15 min behind.", r["current"])
        self.assertIn("PiFinder takes its location from there", r["current"][2])
        self.assertEqual(sorted(r["rows"][-2]["wrong"]), ["location", "offset", "time"])
        self.assertFalse(r["mount_warn"])

    def test_a_computer_that_does_not_answer_is_said_not_judged(self):
        r = check(self.data(reachable=False, time_utc=None, offset=None, location=None))
        self.assertEqual(r["current"], [])
        self.assertIn("did not answer", r["rows"][-2]["note"])

    def test_reading_another_control_center(self):
        own = cs.evaluate(inputs(mount=False), 0.0, {}, immediately=True)
        peer = cs.parse_peer("other", own)
        self.assertEqual((peer["reachable"], peer["time_utc"], peer["offset"], peer["location"]), (True, NOW, 1.0, HOME))
        old = cs.parse_peer("other", {"pi_time_utc": NOW.isoformat(), "ntp_synced": True})   # a 3.0.0 Control Center
        self.assertEqual((old["time_utc"], old["offset"], old["location"]), (NOW, None, None))
        self.assertFalse(cs.parse_peer("other", None)["reachable"])


class Debounce(unittest.TestCase):
    def test_a_difference_must_last(self):
        seen, wrong = {}, inputs(location=(40.0, 8.0))
        self.assertFalse(cs.evaluate(wrong, 0.0, seen)["mismatch"])
        self.assertEqual(len(cs.evaluate(wrong, 1.0, seen)["current"]), 1, "an open notice shows it at once")
        wrong = inputs(location=(40.0, 8.0))
        self.assertTrue(cs.evaluate(wrong, cs.DEBOUNCE_SEC, seen)["mismatch"])
        self.assertFalse(cs.evaluate(inputs(), cs.DEBOUNCE_SEC + 5, seen)["mismatch"])
        self.assertFalse(cs.evaluate(inputs(location=(40.0, 8.0)), cs.DEBOUNCE_SEC + 10, seen)["mismatch"], "counts anew")

    def test_pi_without_ntp_is_a_note_not_a_notice(self):
        seen = {}
        cs.evaluate(inputs(ntp=False), 0.0, seen)
        r = cs.evaluate(inputs(ntp=False), cs.DEBOUNCE_SEC, seen)
        self.assertTrue(r["pi_clock_warn"])
        self.assertFalse(r["mismatch"])


class Observations(unittest.TestCase):
    def test_only_a_change_between_two_close_looks_counts(self):
        seen = cs.TimeObservations()
        first, second = ago(5000), ago(10)
        seen.observe("M", first, ago(20), 0.0)
        self.assertIsNone(seen.seen_at("M", first), "the first look says nothing")
        seen.observe("M", second, NOW, 20.0)
        self.assertEqual(seen.seen_at("M", second), NOW)
        seen.observe("M", ago(1), NOW, 20.0 + cs.OBSERVATION_MAX_GAP_SEC + 1)
        self.assertIsNone(seen.seen_at("M", ago(1)), "after a blind spell the moment is unknown")

    def test_a_value_written_here(self):
        seen = cs.TimeObservations()
        seen.set_now("M", NOW, NOW, 0.0)
        self.assertEqual(seen.seen_at("M", NOW), NOW)


class Reading(unittest.TestCase):
    def test_onstep_answers(self):
        r = cs.parse_onstep({":GX80#": "08:13:49", ":GX81#": "11/28/26", ":Gt#": "+49*28", ":Gg#": "-008*27"})
        self.assertEqual(r["utc"], datetime.datetime(2026, 11, 28, 8, 13, 49, tzinfo=UTC))
        self.assertAlmostEqual(r["location"][0], 49.4667, places=3)
        self.assertAlmostEqual(r["location"][1], 8.45, places=3, msg="OnStep counts longitude west positive")
        self.assertIsNone(cs.parse_onstep({":GX80#": "0"}))

    def test_kstars_over_dbus(self):
        answers = {"org.kde.kstars.location": '{"latitude":49.47,"longitude":8.45,"tz":1,"elevation":0,"name":"GPS Location"}',
                   "org.kde.kstars.getToggleableActionStates": '{"clock_realtime": true}'}

        class Out:
            def __init__(self, text):
                self.returncode, self.stdout = 0, text

        r = cs.read_kstars(lambda args, **kwargs: Out(answers[args[-1]]))
        self.assertAlmostEqual(r["location"][0], 49.47)
        self.assertAlmostEqual(r["location"][1], 8.45)
        self.assertEqual((r["offset"], r["realtime"]), (1.0, True))

        def gone(args, **kwargs):
            raise OSError("no qdbus")

        self.assertIsNone(cs.read_kstars(gone))

    def test_indi_values(self):
        self.assertAlmostEqual(cs.location("49.4", "351.5")[1], -8.5)
        self.assertIsNone(cs.location("0", "0"))
        self.assertEqual(cs.parse_utc("2026-11-25T20:52:22"), datetime.datetime(2026, 11, 25, 20, 52, 22, tzinfo=UTC))
        self.assertIsNone(cs.parse_utc("garbage"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
