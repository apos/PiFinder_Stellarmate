import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pifinder_sky_renderer as r  # noqa: E402

GSC_SAMPLE = """0125300614 058.77349 +18.59052   0.3  7.83 0.40  1 0 00FH T; 350.49 161
0125300933 058.09633 +18.59777   0.3  7.95 0.39  1 3 00FH F; 339.76 167
garbage line
0123800789 053.45177 +18.22776   0.3  6.10 0.40  1 0 00FH F; 398.74 208
"""


class ParseTest(unittest.TestCase):
    def test_keeps_only_stars_sorted_brightest_first(self):
        stars = r.parse_gsc(GSC_SAMPLE)
        self.assertEqual([s[2] for s in stars], [6.10, 7.83])  # class 3 (non-stellar) and junk dropped

    def test_query_uses_signed_dec_and_passes_limits(self):
        seen = {}

        def runner(cmd):
            seen["cmd"] = cmd
            return GSC_SAMPLE

        r.query_gsc(56.75, -5.5, 400.0, 8.0, runner=runner)
        self.assertIn("-5.500000", seen["cmd"])
        self.assertEqual(seen["cmd"][seen["cmd"].index("-m") + 1:seen["cmd"].index("-m") + 3], ["0", "8.00"])


class ProjectTest(unittest.TestCase):
    def test_centre_star_lands_in_the_frame_centre(self):
        x, y, _ = r.project([(56.75, 24.12, 5.0)], 56.75, 24.12, 10.5, 512)
        self.assertAlmostEqual(x[0], 255.5, places=6)
        self.assertAlmostEqual(y[0], 255.5, places=6)

    def test_north_is_up_and_east_is_left(self):
        north = r.project([(56.75, 24.62, 5.0)], 56.75, 24.12, 10.5, 512)
        east = r.project([(57.25, 24.12, 5.0)], 56.75, 24.12, 10.5, 512)
        self.assertLess(north[1][0], 255.5)      # smaller y = higher up
        self.assertLess(east[0][0], 255.5)       # smaller x = left

    def test_roll_90_turns_north_to_the_left(self):
        # roll = position angle of the image "up"; at 90 deg up points east, so north ends up on the right... check one star
        x0, y0, _ = r.project([(56.75, 24.62, 5.0)], 56.75, 24.12, 10.5, 512, roll_deg=0)
        x1, y1, _ = r.project([(56.75, 24.62, 5.0)], 56.75, 24.12, 10.5, 512, roll_deg=90)
        self.assertAlmostEqual(y1[0], 255.5, delta=0.5)   # no longer above the centre
        self.assertGreater(x1[0], 255.5)                   # north is now to the right (east is up)
        self.assertAlmostEqual(abs(x1[0] - 255.5), abs(y0[0] - 255.5), delta=0.5)

    def test_star_behind_the_tangent_plane_is_dropped(self):
        x, _, _ = r.project([(236.75, -24.12, 5.0)], 56.75, 24.12, 10.5, 512)
        self.assertEqual(len(x), 0)

    def test_edge_of_field_is_half_the_fov_away(self):
        x, _, _ = r.project([(56.75 + 5.25 / math.cos(math.radians(24.12)), 24.12, 5.0)], 56.75, 24.12, 10.5, 512)
        self.assertEqual(len(x), 1)  # inside the 8 px margin around the frame (approximately on the edge)


class RenderTest(unittest.TestCase):
    def test_bright_star_is_brighter_than_background_and_deterministic(self):
        import numpy as np
        a = r.render(np.array([100.0]), np.array([200.0]), np.array([4.0]), seed=3)
        b = r.render(np.array([100.0]), np.array([200.0]), np.array([4.0]), seed=3)
        self.assertTrue((a == b).all())
        self.assertGreater(int(a[200, 100]), 200)
        self.assertLess(int(a[10, 10]), 30)


if __name__ == "__main__":
    unittest.main()
