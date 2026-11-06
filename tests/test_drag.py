import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aerostat_drag as drag  # noqa: E402


class SphereTests(unittest.TestCase):
    def test_smooth_sphere_matches_classic_reference_points(self):
        self.assertAlmostEqual(drag.sphere_cd_smooth(100.0), 1.09, delta=0.1)
        self.assertAlmostEqual(drag.sphere_cd_smooth(1e3), 0.47, delta=0.05)
        self.assertAlmostEqual(drag.sphere_cd_smooth(1e4), 0.40, delta=0.05)
        self.assertAlmostEqual(drag.sphere_cd_smooth(1e5), 0.45, delta=0.06)

    def test_drag_crisis_is_reproduced(self):
        self.assertLess(drag.sphere_cd_smooth(4e5), 0.2)
        self.assertGreater(drag.sphere_cd_smooth(1e5), 2.0 * drag.sphere_cd_smooth(4e5))
        self.assertGreater(drag.sphere_cd_smooth(1e6), drag.sphere_cd_smooth(5e5))

    def test_design_value_is_inside_engineering_band_and_independent_of_reynolds(self):
        slow = drag.sphere_design(10.0, 3.0, 1.2, 15.0)
        fast = drag.sphere_design(10.0, 25.0, 1.2, 15.0)
        low, high = drag.SPHERE_DESIGN_BAND
        self.assertGreaterEqual(slow.cd, low)
        self.assertLessEqual(slow.cd, high)
        self.assertEqual(slow.cd, fast.cd)
        self.assertGreater(fast.reynolds, slow.reynolds)
        self.assertTrue(fast.notes)

    def test_components_sum_to_design_value(self):
        result = drag.sphere_design(10.0, 10.0, 1.2, 15.0, fitting_delta=0.03, overpressure_pa=200.0,
                                    dynamic_pressure_pa=400.0)
        self.assertAlmostEqual(sum(c.value for c in result.components), result.cd, places=12)
        self.assertAlmostEqual(result.extra["dent"], 0.15 * 0.5, places=12)
        self.assertLess(result.low, result.cd)
        self.assertGreater(result.high, result.cd)

    def test_under_inflation_raises_drag_and_adequate_pressure_does_not(self):
        base = drag.sphere_design(10.0, 10.0, 1.2, 15.0).cd
        dented = drag.sphere_design(10.0, 10.0, 1.2, 15.0, overpressure_pa=100.0, dynamic_pressure_pa=400.0)
        firm = drag.sphere_design(10.0, 10.0, 1.2, 15.0, overpressure_pa=800.0, dynamic_pressure_pa=400.0)
        self.assertGreater(dented.cd, base)
        self.assertEqual(firm.cd, base)
        self.assertTrue(dented.notes)


class HullTests(unittest.TestCase):
    def hull(self, length, diameter, speed=10.0, ks=0.3, **kw):
        surface = drag.prolate_spheroid_surface(length, diameter)
        volume = math.pi / 6.0 * diameter * diameter * length
        return drag.airship_design(length, diameter, surface, volume, speed, 1.2, 15.0, ks, **kw)

    def test_flat_plate_friction_reference_value(self):
        self.assertAlmostEqual(drag.flat_plate_cf(1e7), 0.0030, delta=0.0002)
        self.assertLess(drag.flat_plate_cf(1e8), drag.flat_plate_cf(1e7))

    def test_form_factor_is_monotonic_in_fineness(self):
        values = [drag.hull_form_factor(l) for l in (2, 3, 4, 6, 8)]
        self.assertEqual(values, sorted(values, reverse=True))
        self.assertAlmostEqual(drag.hull_form_factor(4.0), 1.0 + 1.5 * 0.125 + 7.0 / 64.0, places=12)

    def test_volume_based_coefficient_has_minimum_between_fineness_3_and_8(self):
        sweep = drag.airship_fineness_sweep(2000.0, 10.0, 1.2, 15.0, ks_mm=0.05)
        best = min(sweep, key=lambda row: row[2])
        self.assertGreaterEqual(best[0], 3.5)
        self.assertLessEqual(best[0], 7.0)
        self.assertLess(best[2], 0.03)
        self.assertGreater(sweep[0][2], 1.4 * best[2])

    def test_typical_airship_hull_is_in_published_order_of_magnitude(self):
        result = self.hull(32.0, 8.0, ks=0.05, fitting_delta=0.0)
        self.assertGreater(result.extra["cd_volume"], 0.018)
        self.assertLess(result.extra["cd_volume"], 0.035)

    def test_roughness_and_fittings_increase_drag(self):
        smooth = self.hull(32.0, 8.0, ks=0.01, fitting_delta=0.0).cd
        rough = self.hull(32.0, 8.0, ks=1.0, fitting_delta=0.0).cd
        fitted = self.hull(32.0, 8.0, ks=0.01, fitting_delta=0.02).cd
        self.assertGreater(rough, smooth)
        self.assertAlmostEqual(fitted - smooth, 0.02, places=12)

    def test_components_sum_and_under_inflation(self):
        firm = self.hull(32.0, 8.0, overpressure_pa=800.0, dynamic_pressure_pa=400.0)
        soft = self.hull(32.0, 8.0, overpressure_pa=100.0, dynamic_pressure_pa=400.0)
        self.assertAlmostEqual(sum(c.value for c in firm.components), firm.cd, places=12)
        self.assertGreater(soft.cd, firm.cd)
        self.assertLess(firm.low, firm.cd)
        self.assertGreater(firm.high, firm.cd)

    def test_prolate_spheroid_surface_limits(self):
        self.assertAlmostEqual(drag.prolate_spheroid_surface(2.0, 2.0), 4.0 * math.pi, places=9)
        near = drag.prolate_spheroid_surface(2.0001, 2.0)
        self.assertAlmostEqual(near, 4.0 * math.pi, delta=1e-3)
        long = drag.prolate_spheroid_surface(40.0, 4.0)
        self.assertGreater(long, 2.0 * math.pi * 2.0 * 20.0 * 0.9)

    def test_reynolds_uses_sutherland_viscosity(self):
        self.assertAlmostEqual(drag.air_viscosity(15.0), 1.80e-5, delta=0.03e-5)
        self.assertAlmostEqual(drag.reynolds(10.0, 10.0, 1.2, 15.0), 1.2 * 10 * 10 / drag.air_viscosity(15.0), places=6)


if __name__ == "__main__":
    unittest.main()
