import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aerostat_wind as aw  # noqa: E402
from aerostat_physics import calculate_corrected_air_density  # noqa: E402

A, B, C, D, NONE = aw.TERRAIN_OPTIONS


class TerrainTests(unittest.TestCase):
    def test_height_factor_matches_gb50009_table(self):
        for terrain, z, expected in ((B, 10, 1.00), (B, 100, 2.00), (B, 500, 2.91), (A, 100, 2.23),
                                     (C, 10, 0.65), (D, 100, 1.04)):
            self.assertAlmostEqual(aw.height_factor(z, terrain), expected, delta=0.015)
        self.assertEqual(aw.height_factor(100, NONE), 1.0)

    def test_all_terrains_converge_at_gradient_height(self):
        values = [aw.speed_shape(aw.gradient_height(t), t) for t in (A, B, C, D)]
        for v in values:
            self.assertAlmostEqual(v, values[0], delta=0.005)
        for t in (A, B, C, D):
            self.assertAlmostEqual(aw.speed_shape(5000, t), values[0], delta=0.005)

    def test_gust_factor_matches_gb50009_near_ground(self):
        self.assertAlmostEqual(aw.gust_factor(10, B), 1.70, delta=0.01)
        self.assertAlmostEqual(aw.gust_factor(100, B), 1.50, delta=0.01)
        self.assertAlmostEqual(aw.gust_factor(10, D), 2.40, delta=0.01)
        self.assertAlmostEqual(aw.gust_factor(30, D), 2.40, delta=0.01)

    def test_turbulence_is_continuous_and_decays_to_free_atmosphere(self):
        for terrain in (A, B, C, D):
            zg = aw.gradient_height(terrain)
            below = aw.turbulence_intensity(zg - 1e-6, terrain)
            above = aw.turbulence_intensity(zg + 1e-6, terrain)
            self.assertAlmostEqual(below, above, places=5)
            self.assertAlmostEqual(aw.turbulence_intensity(2 * zg, terrain), aw.FREE_ATMOSPHERE_TURBULENCE, places=9)
            self.assertAlmostEqual(aw.turbulence_intensity(5000, terrain), aw.FREE_ATMOSPHERE_TURBULENCE, places=9)
            self.assertGreater(aw.gust_factor(10, terrain), aw.gust_factor(2 * zg, terrain))

    def test_gust_factor_never_below_one_and_terrain_effect_vanishes_aloft(self):
        high = [aw.gust_factor(3000, t) for t in (A, B, C, D)]
        for g in high:
            self.assertAlmostEqual(g, high[0], places=9)
            self.assertGreater(g, 1.0)


class ProfileTests(unittest.TestCase):
    def test_ref10_mode(self):
        p = aw.WindProfile(aw.MODE_REF10, B, 100, speed=10.0)
        self.assertAlmostEqual(p.speed(10), 10.0, places=9)
        self.assertAlmostEqual(p.speed(100), 10.0 * aw.speed_shape(100, B), places=9)
        self.assertAlmostEqual(p.speed(1000), 10.0 * aw.speed_shape(350, B), places=9)
        self.assertAlmostEqual(aw.WindProfile(aw.MODE_REF10, NONE, 100, speed=10.0).speed(300), 10.0, places=9)

    def test_target_mode_pins_speed_at_target_height_for_every_terrain(self):
        for terrain in (A, B, C, D):
            for height in (60.0, 800.0):
                p = aw.WindProfile(aw.MODE_TARGET, terrain, height, speed=15.0)
                self.assertAlmostEqual(p.speed(height), 15.0, places=9)
                self.assertLessEqual(p.speed(10.0), p.speed(height) + 1e-9)

    def test_target_mode_terrain_only_matters_below_gradient_height(self):
        speeds = [aw.WindProfile(aw.MODE_TARGET, t, 800.0, speed=18.0).speed(800.0) for t in (A, B, C, D)]
        self.assertTrue(all(abs(s - 18.0) < 1e-9 for s in speeds))
        near = [aw.WindProfile(aw.MODE_TARGET, t, 800.0, speed=18.0).speed(30.0) for t in (A, D)]
        self.assertGreater(near[0], near[1])

    def test_table_mode(self):
        table = aw.parse_profile_table("100:10, 500:18, 1000:24")
        p = aw.WindProfile(aw.MODE_TABLE, B, 500, table=table)
        self.assertAlmostEqual(p.speed(300), 14.0, places=9)
        self.assertAlmostEqual(p.speed(2000), 24.0, places=9)
        self.assertAlmostEqual(p.speed(100), 10.0, places=9)
        self.assertLess(p.speed(20), 10.0)
        self.assertAlmostEqual(p.scaled(2.0).speed(500), 36.0, places=9)

    def test_parse_variants_and_errors(self):
        self.assertEqual(aw.parse_profile_table("10：8，300：15；1000:22\n2000 : 30"),
                         [(10, 8), (300, 15), (1000, 22), (2000, 30)])
        for bad in ("", "abc", "100:10:5", "100:10,100:12", "-5:3"):
            with self.assertRaises(ValueError):
                aw.parse_profile_table(bad)


class WindFieldTests(unittest.TestCase):
    def test_pressure_matches_wind_table_convention(self):
        profile = aw.WindProfile(aw.MODE_REF10, NONE, 100, speed=10.0)
        field = aw.WindField(profile, 0.0, 15.04, NONE)
        # 风级表 q = v²/16 kgf/m² → 6.25 × 9.80665 Pa
        self.assertAlmostEqual(field.pressure(0) * 1000, 6.25 * 9.80665, delta=0.3)

    def test_pressure_scales_with_density_and_speed_squared(self):
        profile = aw.WindProfile(aw.MODE_REF10, NONE, 100, speed=10.0)
        low = aw.WindField(profile, 2000.0, 20.0, NONE).pressure(0)
        sea = aw.WindField(profile, 0.0, 20.0, NONE).pressure(0)
        ratio = calculate_corrected_air_density(2000, 2000, 20.0) / calculate_corrected_air_density(0, 0, 20.0)
        self.assertAlmostEqual(low / sea, ratio, places=9)
        doubled = aw.WindField(profile.scaled(2.0), 0.0, 20.0, NONE).pressure(0)
        self.assertAlmostEqual(doubled / sea, 4.0, places=9)

    def test_gust_override(self):
        profile = aw.WindProfile(aw.MODE_REF10, B, 100, speed=10.0)
        auto = aw.WindField(profile, 0.0, 15.0, B)
        fixed = aw.WindField(profile, 0.0, 15.0, B, gust_override=1.5)
        self.assertEqual(fixed.gust(900), 1.5)
        self.assertAlmostEqual(auto.gust(100), aw.gust_factor(100, B), places=9)
        self.assertAlmostEqual(fixed.peak_pressure(100), 1.5 * fixed.pressure(100), places=12)


if __name__ == "__main__":
    unittest.main()
