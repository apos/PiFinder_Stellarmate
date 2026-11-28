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


class ManualMotionTest(unittest.TestCase):
    SAMPLE = ('<setSwitchVector device="Telescope Simulator" name="TELESCOPE_MOTION_NS" state="Ok">'
              '<oneSwitch name="MOTION_NORTH">On</oneSwitch><oneSwitch name="MOTION_SOUTH">Off</oneSwitch></setSwitchVector>'
              '<defSwitchVector device="Telescope Simulator" name="TELESCOPE_MOTION_WE" state="Idle">'
              '<defSwitch name="MOTION_WEST">Off</defSwitch><defSwitch name="MOTION_EAST">Off</defSwitch></defSwitchVector>')

    def test_switch_vectors_are_read(self):
        found = f.parse_switch_vectors(self.SAMPLE)
        self.assertEqual(found[0][:2], ("Telescope Simulator", "TELESCOPE_MOTION_NS"))
        self.assertEqual(found[0][3], {"MOTION_NORTH": "On", "MOTION_SOUTH": "Off"})
        self.assertEqual(found[1][3], {"MOTION_WEST": "Off", "MOTION_EAST": "Off"})

    def test_manual_motion_lasts_a_moment_after_the_switch_goes_off(self):
        w = f.MountWatcher("x")
        self.assertFalse(w.manual_active(now=100.0))
        w.on_motion("TELESCOPE_MOTION_NS", {"MOTION_NORTH": "On", "MOTION_SOUTH": "Off"}, now=100.0)
        self.assertTrue(w.manual_active(now=101.0))
        w.on_motion("TELESCOPE_MOTION_NS", {"MOTION_NORTH": "Off", "MOTION_SOUTH": "Off"}, now=102.0)
        self.assertTrue(w.manual_active(now=102.0 + f.MANUAL_SETTLE_SEC - 0.1))
        self.assertFalse(w.manual_active(now=102.0 + f.MANUAL_SETTLE_SEC + 0.1))

    def test_two_directions_keep_it_active(self):
        w = f.MountWatcher("x")
        w.on_motion("TELESCOPE_MOTION_NS", {"MOTION_NORTH": "On"}, now=1.0)
        w.on_motion("TELESCOPE_MOTION_WE", {"MOTION_EAST": "On"}, now=1.0)
        w.on_motion("TELESCOPE_MOTION_NS", {"MOTION_NORTH": "Off"}, now=2.0)
        self.assertTrue(w.manual_active(now=50.0))

    def test_a_jump_while_moving_by_hand_is_not_a_sync(self):
        far = (100.0, 20.0 + 45 / 60.0, "Ok")
        self.assertEqual(f.absorb_sync((100.0, 20.0, "Ok"), far, (3.0, 4.0), manual=True), ((3.0, 4.0), None))
        offset, jump = f.absorb_sync((100.0, 20.0, "Ok"), far, (3.0, 4.0), manual=False)
        self.assertIsNotNone(jump, "the same jump without the switch on is a Sync")


class NudgeTest(unittest.TestCase):
    def test_a_nudge_is_taken_once(self):
        import json
        import tempfile
        path = os.path.join(tempfile.mkdtemp(), "nudge.json")
        with open(path, "w") as handle:
            json.dump({"east": 12.5, "north": -3}, handle)
        self.assertEqual(f.take_nudge(path), (12.5, -3.0))
        self.assertFalse(os.path.exists(path))
        self.assertIsNone(f.take_nudge(path))

    def test_a_broken_nudge_file_is_removed_and_ignored(self):
        import tempfile
        path = os.path.join(tempfile.mkdtemp(), "nudge.json")
        with open(path, "w") as handle:
            handle.write("{not json")
        self.assertIsNone(f.take_nudge(path))
        self.assertFalse(os.path.exists(path))

    def test_missing_file_is_none(self):
        self.assertIsNone(f.take_nudge("/nonexistent/nudge.json"))


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

class PictureReplacedTest(unittest.TestCase):
    """An update put PiFinder's original test picture back while the simulation ran: the follower must write the sky again."""

    def setUp(self):
        import tempfile
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "pic.png")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_nothing_written_yet_is_not_a_replacement(self):
        self.assertFalse(f.picture_replaced(self.path, None))

    def test_unchanged_file_is_not_replaced(self):
        open(self.path, "wb").write(b"sky")
        self.assertFalse(f.picture_replaced(self.path, f.file_signature(self.path)))

    def test_other_content_is_replaced(self):
        open(self.path, "wb").write(b"sky")
        written = f.file_signature(self.path)
        open(self.path, "wb").write(b"original picture, longer")
        self.assertTrue(f.picture_replaced(self.path, written))

    def test_deleted_file_is_replaced(self):
        open(self.path, "wb").write(b"sky")
        written = f.file_signature(self.path)
        os.unlink(self.path)
        self.assertTrue(f.picture_replaced(self.path, written))


class LostConnectionTest(unittest.TestCase):
    VECTOR = (b'<setNumberVector device="M" name="EQUATORIAL_EOD_COORD" state="Ok"><oneNumber name="RA">%s</oneNumber>'
              b'<oneNumber name="DEC">20.0</oneNumber></setNumberVector>')

    def run_against(self, positions, extra):
        """A fake INDI server that serves one connection per entry of positions (and closes it after a second), then stays away."""
        import socket as sock
        import tempfile
        import threading
        import time
        server = sock.socket()
        server.bind(("127.0.0.1", 0))
        server.listen(4)
        port = server.getsockname()[1]

        def serve():
            for ra in positions:
                c, _ = server.accept()
                c.recv(4096)
                for one in (ra if isinstance(ra, tuple) else (ra,)):   # a tuple: the position changes within one connection
                    c.sendall(self.VECTOR % one)
                    time.sleep(1.0)
                c.close()
            server.close()
        threading.Thread(target=serve, daemon=True).start()
        rendered = []
        saved = f.renderer.render_field, f.write_atomically, f.file_signature
        f.renderer.render_field = lambda ra, *a, **kw: (rendered.append(round(ra)) or None, 0)
        f.write_atomically = lambda *a: None
        f.file_signature = lambda path: None
        try:
            with tempfile.TemporaryDirectory() as d:
                code = f.main(["--device", "M", "--host", "127.0.0.1", "--port", str(port), "--image", d + "/p.png", "--no-keep-awake",
                               "--interval", "0.2"] + extra)
        finally:
            f.renderer.render_field, f.write_atomically, f.file_signature = saved
        return code, rendered

    def test_the_follower_connects_again_and_follows_the_new_position(self):
        code, rendered = self.run_against([b"5.0", b"9.0"], ["--reconnect-sec", "10", "--duration", "4"])
        self.assertEqual(rendered[0], 75)
        self.assertIn(135, rendered)

    def test_start_up_jumps_after_a_reconnect_are_not_syncs(self):
        code, rendered = self.run_against([b"5.0", (b"0.0", b"12.0")], ["--reconnect-sec", "10", "--duration", "5"])
        self.assertEqual(rendered[-1], 180, "the sky follows the restarted mount instead of staying where it was")

    def test_start_up_jumps_after_the_start_are_not_syncs(self):
        code, rendered = self.run_against([(b"0.0", b"12.0")], ["--reconnect-sec", "1", "--duration", "3"])
        self.assertEqual(rendered[-1], 180, "after a reboot the sky follows the mount that is still setting itself up")

    def test_the_follower_ends_when_indi_stays_away(self):
        code, _ = self.run_against([b"5.0"], ["--reconnect-sec", "2", "--duration", "15"])
        self.assertEqual(code, 3)


class RightAscensionRangeTest(unittest.TestCase):
    def test_gsc_is_asked_with_a_right_ascension_inside_0_to_360(self):
        seen = []

        def runner(cmd, **kw):
            seen.append(float(cmd[2]))
            raise StopIteration
        for ra in (452.7, -10.0, 15.0):
            with self.assertRaises(StopIteration):
                f.renderer.query_gsc(ra, 20.0, 60.0, 9.0, runner=runner)
        self.assertEqual([round(v, 1) for v in seen], [92.7, 350.0, 15.0])


class RecentreNudgeTest(unittest.TestCase):
    def test_a_recentre_request_is_read_once(self):
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "n.json")
            open(path, "w").write('{"recentre": true}')
            self.assertEqual(f.take_nudge(path), "recentre")
            self.assertIsNone(f.take_nudge(path))
            open(path, "w").write('{"east": 5, "north": -2}')
            self.assertEqual(f.take_nudge(path), (5.0, -2.0))


class BelowHorizonTest(unittest.TestCase):
    def test_altitude(self):
        self.assertAlmostEqual(f.altitude_deg(3.0, 90.0, 49.4, 8.6), 49.4, places=1)     # the pole stands at the latitude
        self.assertLess(f.altitude_deg(3.0, -60.0, 49.4, 8.6), 0)                        # never rises at 49 degrees north

    def test_no_stars_are_rendered_below_the_horizon(self):
        import socket as sock
        import tempfile
        import threading
        import time
        server = sock.socket()
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]

        def serve():
            c, _ = server.accept()
            c.recv(4096)
            c.sendall(b'<setNumberVector device="M" name="GEOGRAPHIC_COORD" state="Ok"><oneNumber name="LAT">49.4</oneNumber>'
                      b'<oneNumber name="LONG">8.6</oneNumber></setNumberVector>'
                      b'<setNumberVector device="M" name="EQUATORIAL_EOD_COORD" state="Ok"><oneNumber name="RA">5.0</oneNumber>'
                      b'<oneNumber name="DEC">-70.0</oneNumber></setNumberVector>')
            time.sleep(3.0)
            c.close()
        threading.Thread(target=serve, daemon=True).start()
        fields, blanks = [], []
        saved = f.renderer.render_field, f.renderer.render, f.write_atomically, f.file_signature
        f.renderer.render_field = lambda *a, **kw: (fields.append(a) or None, 0)
        f.renderer.render = lambda x, y, mag, **kw: blanks.append(len(x))
        f.write_atomically = lambda *a: None
        f.file_signature = lambda path: None
        try:
            with tempfile.TemporaryDirectory() as d:
                f.main(["--device", "M", "--host", "127.0.0.1", "--port", str(port), "--image", d + "/p.png", "--no-keep-awake",
                        "--interval", "0.2", "--duration", "1.5"])
        finally:
            f.renderer.render_field, f.renderer.render, f.write_atomically, f.file_signature = saved
            server.close()
        self.assertEqual(fields, [])
        self.assertEqual(blanks, [0])


if __name__ == "__main__":
    unittest.main()
