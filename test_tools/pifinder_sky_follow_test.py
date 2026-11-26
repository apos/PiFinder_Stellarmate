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


if __name__ == "__main__":
    unittest.main()
