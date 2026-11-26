import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pifinder_sky_follow as f  # noqa: E402

XML = ('<defNumberVector device="Telescope Simulator" name="EQUATORIAL_EOD_COORD" state="Idle" perm="rw">'
       '<defNumber name="RA" format="%010.6m" min="0" max="24" step="0">12.041183844472374886</defNumber>'
       '<defNumber name="DEC" format="%010.6m" min="-90" max="90" step="0">-45</defNumber></defNumberVector>'
       '<setNumberVector device="Other" name="X" state="Ok"><oneNumber name="A">1</oneNumber></setNumberVector>'
       '<setNumberVector device="Telescope Simulator" name="EQUATORIAL_EOD_COORD" state="Busy"><oneNumber name="RA">3.5</oneN')


class PrecessionTest(unittest.TestCase):
    def test_roundtrip(self):
        jd = 2461000.5
        ra, dec = f.j2000_to_jnow(56.75, 24.12, jd)
        ra2, dec2 = f.jnow_to_j2000(ra, dec, jd)
        self.assertAlmostEqual(ra2, 56.75, places=6)
        self.assertAlmostEqual(dec2, 24.12, places=6)

    def test_size_of_precession_after_about_27_years(self):
        jd = 2451545.0 + 27 * 365.25
        ra, dec = f.j2000_to_jnow(0.0, 0.0, jd)
        self.assertAlmostEqual(ra, 0.346, delta=0.003)   # 3.07 s of time = 46.1 arcsec per year in RA at the equinox, times 27
        self.assertAlmostEqual(dec, 0.150, delta=0.005)  # 20.0 arcsec per year in Dec

    def test_no_change_at_j2000(self):
        ra, dec = f.jnow_to_j2000(123.0, -20.0, 2451545.0)
        self.assertAlmostEqual(ra, 123.0, places=9)
        self.assertAlmostEqual(dec, -20.0, places=9)


class ParseTest(unittest.TestCase):
    def test_reads_complete_vectors_and_keeps_the_rest(self):
        vectors, rest = f.parse_number_vectors(XML)
        self.assertEqual(len(vectors), 2)
        device, name, state, values = vectors[0]
        self.assertEqual((device, name, state), ("Telescope Simulator", "EQUATORIAL_EOD_COORD", "Idle"))
        self.assertAlmostEqual(values["RA"], 12.0411838, places=6)
        self.assertEqual(values["DEC"], -45.0)
        self.assertTrue(rest.startswith("<setNumberVector device=\"Telescope Simulator\""))  # the cut-off one stays for later

    def test_sexagesimal_value(self):
        vectors, _ = f.parse_number_vectors('<setNumberVector device="D" name="N" state="Ok"><oneNumber name="RA">12:30:00</oneNumber>'
                                            '<oneNumber name="DEC">-10:30:00</oneNumber></setNumberVector>')
        self.assertAlmostEqual(vectors[0][3]["RA"], 12.5)
        self.assertAlmostEqual(vectors[0][3]["DEC"], -10.5)


class SeparationTest(unittest.TestCase):
    def test_one_degree(self):
        self.assertAlmostEqual(f.angular_sep_deg(10, 0, 11, 0), 1.0, places=6)


class KeepAwakeTest(unittest.TestCase):
    def test_posts_to_the_endpoint_and_reports_success(self):
        import http.server
        import threading
        seen = []

        class H(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                seen.append(self.path)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"ok": true}')

            def log_message(self, *a):
                pass

        srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.handle_request, daemon=True).start()
        self.assertTrue(f.keep_awake(f"http://127.0.0.1:{srv.server_port}/api/keep_awake"))
        self.assertEqual(seen, ["/api/keep_awake"])
        srv.server_close()

    def test_unreachable_is_false_not_an_exception(self):
        self.assertFalse(f.keep_awake("http://127.0.0.1:9/api/keep_awake"))


class MisalignTest(unittest.TestCase):
    def test_offset_east_and_north(self):
        ra, dec = f.offset_position(100.0, 0.0, 6.0, 12.0)
        self.assertAlmostEqual(ra, 100.1, places=6)
        self.assertAlmostEqual(dec, 0.2, places=6)

    def test_east_offset_grows_with_dec_in_ra(self):
        ra, _ = f.offset_position(100.0, 60.0, 6.0, 0.0)
        self.assertAlmostEqual(ra, 100.2, places=6)   # 0.1 deg on the sky is 0.2 deg of RA at Dec 60

    def test_target_pixel_from_config(self):
        import json, tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump({"target_pixel": [300.0, 310.0], "equipment": {"active_telescope_index": 0,
                       "telescopes": [{"target_pixel": [320.5, 330.5]}]}}, fh)
        self.assertEqual(f.read_target_pixel(fh.name), (320.5, 330.5))
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh2:
            json.dump({"target_pixel": [300.0, 310.0], "equipment": {"active_telescope_index": 0, "telescopes": [{"target_pixel": None}]}}, fh2)
        self.assertEqual(f.read_target_pixel(fh2.name), (300.0, 310.0))
        self.assertEqual(f.read_target_pixel("/nonexistent.json"), (256.0, 256.0))


class SyncTest(unittest.TestCase):
    def test_sync_reduces_the_offset_by_the_jump(self):
        prev = (100.0, 20.0, "Ok")
        east, north = 10.0, 5.0
        # the bridge syncs the mount to where PiFinder says it is: 10' east, 5' north of what the mount reported
        cur_ra, cur_dec = f.offset_position(100.0, 20.0, 10.0, 5.0)
        offset, jump = f.absorb_sync(prev, (cur_ra, cur_dec, "Ok"), (east, north))
        self.assertAlmostEqual(jump, math.hypot(10.0, 5.0), delta=0.05)
        self.assertAlmostEqual(offset[0], 0.0, delta=0.05)
        self.assertAlmostEqual(offset[1], 0.0, delta=0.05)

    def test_slew_and_tracking_are_not_syncs(self):
        far = (110.0, 20.0, "Busy")
        self.assertEqual(f.absorb_sync((100.0, 20.0, "Ok"), far, (3.0, 4.0)), ((3.0, 4.0), None))
        self.assertEqual(f.absorb_sync((100.0, 20.0, "Ok"), (100.003, 20.0, "Ok"), (3.0, 4.0)), ((3.0, 4.0), None))
        self.assertEqual(f.absorb_sync(None, far, (3.0, 4.0)), ((3.0, 4.0), None))


class GotoErrorTest(unittest.TestCase):
    def test_reference_slew_lands_the_full_error_off(self):
        self.assertEqual(f.landing_error((8.0, -5.0), 45.0, 45.0, 0.05), (8.0, -5.0))

    def test_the_error_grows_with_the_slew(self):
        e = f.landing_error((8.0, -5.0), 22.5, 45.0, 0.05)
        self.assertAlmostEqual(e[0], 4.0)
        self.assertAlmostEqual(e[1], -2.5)

    def test_a_short_corrective_slew_lands_close_but_not_exactly(self):
        e = f.landing_error((8.0, -5.0), 0.15, 45.0, 0.05)  # about 9': the floor applies
        self.assertAlmostEqual(e[0], 0.4)
        self.assertAlmostEqual(e[1], -0.25)

    def test_a_very_long_slew_is_capped(self):
        e = f.landing_error((8.0, -5.0), 170.0, 45.0, 0.05)
        self.assertAlmostEqual(e[0], 8.0 * f.GOTO_ERROR_CAP)

    def test_unknown_length_counts_as_a_reference_slew(self):
        self.assertEqual(f.landing_error((8.0, -5.0), None, 45.0, 0.05), (8.0, -5.0))

    def test_reference_zero_means_a_fixed_error(self):
        self.assertEqual(f.landing_error((8.0, -5.0), 0.15, 0.0, 0.05), (8.0, -5.0))

    def test_a_perfect_mount_has_none(self):
        self.assertIsNone(f.landing_error(None, 10.0))

    def test_refining_converges(self):
        """Sync to the real position, then GoTo the target again: each corrective slew is shorter, so the error shrinks."""
        error, steps = (8.0, -5.0), []
        for slew_deg in (45.0, 9.4 / 60.0, 0.5 / 60.0):
            error = f.landing_error((8.0, -5.0), slew_deg, 45.0, 0.05)
            steps.append(math.hypot(*error))
        self.assertGreater(steps[0], 9.0)
        self.assertLess(steps[1], 1.0)
        self.assertLess(steps[2], steps[1] + 1e-9)


class WatcherTest(unittest.TestCase):
    """A slew too short for a poll to catch is still seen: the watcher gets every update."""

    def test_counts_every_slew_start_and_remembers_where_it_came_from(self):
        w = f.MountWatcher("x")
        w.on_update(16.0, 36.0, "Ok")
        self.assertEqual((w.slew_count, w.slew_from), (0, None))
        w.on_update(16.0, 36.1, "Busy")
        w.on_update(16.01, 36.2, "Busy")  # still the same slew
        w.on_update(16.02, 36.3, "Ok")
        self.assertEqual((w.slew_count, w.slew_from), (1, (16.0, 36.0)))
        w.on_update(16.02, 36.3, "Busy")   # a second, very short one
        w.on_update(16.0201, 36.3, "Ok")
        self.assertEqual((w.slew_count, w.slew_from), (2, (16.02, 36.3)))

    def test_a_sync_is_not_a_slew(self):
        w = f.MountWatcher("x")
        w.on_update(16.0, 36.0, "Ok")
        w.on_update(16.2, 36.0, "Ok")  # the position jumps, the state stays Ok
        self.assertEqual(w.slew_count, 0)
        self.assertEqual(w.position, (16.2, 36.0, "Ok"))

    def test_the_first_look_may_already_be_busy(self):
        w = f.MountWatcher("x")
        w.on_update(16.0, 36.0, "Busy")
        self.assertEqual((w.slew_count, w.slew_from), (1, None))

if __name__ == "__main__":
    unittest.main()
