import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aerostat_tail as tail  # noqa: E402
import aerostat_wind as aw  # noqa: E402


def design(**overrides):
    length, diameter = 32.0, 8.0
    volume = math.pi / 6.0 * diameter * diameter * length
    params = dict(volume=volume, length=length, diameter=diameter, hull_surface=650.0, tail_wetted_area=200.0,
                  fin_count=4, aspect_ratio=1.0, thickness_ratio=0.15, speed=10.0, density=1.2, temp_c=15.0,
                  hull_axial_area=3.0, aoa_deg=5.0)
    params.update(overrides)
    return tail.design_tail(**params)


class MunkTests(unittest.TestCase):
    def test_sphere_limit_and_reference_values(self):
        k1, k2 = tail.munk_factors(1.05)
        self.assertAlmostEqual(k1, 0.5, delta=0.04)
        self.assertAlmostEqual(k2, 0.5, delta=0.04)
        k1, k2 = tail.munk_factors(4.0)
        self.assertAlmostEqual(k1, 0.082, delta=0.005)
        self.assertAlmostEqual(k2, 0.86, delta=0.01)

    def test_slender_body_limits(self):
        k1, k2 = tail.munk_factors(20.0)
        self.assertLess(k1, 0.02)
        self.assertGreater(k2, 0.95)


class FinTests(unittest.TestCase):
    def test_lift_slope_increases_with_aspect_ratio_and_stays_below_two_pi(self):
        values = [tail.fin_lift_slope(ar) for ar in (0.5, 1.0, 1.5, 2.0, 4.0)]
        self.assertEqual(values, sorted(values))
        self.assertLess(values[-1], 2 * math.pi)
        self.assertAlmostEqual(tail.fin_lift_slope(1.0), 2.60, delta=0.02)

    def test_profile_drag_matches_the_usual_order_of_magnitude(self):
        self.assertGreater(tail.fin_profile_cd(3e6, 0.15), 0.008)
        self.assertLess(tail.fin_profile_cd(3e6, 0.15), 0.015)
        self.assertGreater(tail.fin_profile_cd(3e6, 0.25), tail.fin_profile_cd(3e6, 0.10))

    def test_geometry_is_consistent(self):
        result = design()
        self.assertAlmostEqual(result["planform"], 100.0, places=9)
        self.assertAlmostEqual(result["span"] * result["chord"] * 4, result["planform"], places=9)
        self.assertAlmostEqual(result["span"] ** 2 / (result["planform"] / 4), 1.0, places=9)


class AeroTests(unittest.TestCase):
    def test_zero_angle_gives_no_lift_and_no_extra_drag(self):
        result = design(aoa_deg=0.0)
        self.assertEqual(result["lift_area"], 0.0)
        self.assertEqual(result["drag_extra_area"], 0.0)

    def test_lift_grows_with_angle_and_extra_drag_is_positive(self):
        low, high = design(aoa_deg=3.0), design(aoa_deg=10.0)
        self.assertGreater(high["lift_area"], low["lift_area"])
        self.assertGreater(low["lift_area"], 0.0)
        self.assertGreater(high["drag_extra_area"], 0.0)

    def test_force_decomposition(self):
        result = design(aoa_deg=8.0)
        alpha = math.radians(8.0)
        axial = 3.0 + result["profile_area"]
        self.assertAlmostEqual(result["lift_area"], result["normal_area"] * math.cos(alpha) - axial * math.sin(alpha), places=9)
        self.assertAlmostEqual(result["drag_extra_area"],
                               axial * (math.cos(alpha) - 1.0) + result["normal_area"] * math.sin(alpha), places=9)

    def test_fins_dominate_at_small_angle_and_hull_crossflow_grows_quadratically(self):
        small = design(aoa_deg=4.0)
        self.assertGreater(small["fin_normal_area"], 5.0 * small["hull_normal_area"])
        double = design(aoa_deg=8.0)
        self.assertAlmostEqual(double["hull_normal_area"] / small["hull_normal_area"], 4.0, delta=0.15)

    def test_bigger_fins_give_more_lift_and_drag(self):
        small, big = design(tail_wetted_area=100.0), design(tail_wetted_area=300.0)
        self.assertGreater(big["lift_area"], small["lift_area"])
        self.assertGreater(big["profile_area"], small["profile_area"])

    def test_manual_tail_drag_overrides_the_model(self):
        auto = design()
        manual = design(manual_tail_cd=0.02)
        self.assertEqual(manual["cd_tail"], 0.02)
        self.assertAlmostEqual(manual["profile_area"], 0.02 * auto["planform"], places=9)
        self.assertEqual(manual["cd_tail_auto"], auto["cd_tail_auto"])

    def test_stability_moment_ratio_increases_with_fin_area(self):
        self.assertGreater(design(tail_wetted_area=400.0)["moment_ratio"], design(tail_wetted_area=100.0)["moment_ratio"])


class TotalsTests(unittest.TestCase):
    def test_area_ratio_is_the_total_of_all_fins(self):
        three, four = design(fin_count=3), design(fin_count=4)
        self.assertEqual(three["planform"], four["planform"])
        self.assertAlmostEqual(three["span"] ** 2 / (three["planform"] / 3), 1.0, places=9)
        self.assertAlmostEqual(four["span"] ** 2 / (four["planform"] / 4), 1.0, places=9)

    def test_geometric_volume_is_a_reference_value(self):
        result = design()
        expected = result["planform"] * 0.685 * 0.15 * result["chord"]
        self.assertAlmostEqual(result["volume_geo"], expected, places=9)


class BeaufortTests(unittest.TestCase):
    def test_names_cover_every_level(self):
        for level in range(0, 18):
            self.assertTrue(aw.beaufort_name(level))
        self.assertEqual(aw.beaufort_name(aw.beaufort_level(10.7)), "清劲风")
        self.assertEqual(aw.beaufort_name(aw.beaufort_level(18.3)), "大风")


if __name__ == "__main__":
    unittest.main()

