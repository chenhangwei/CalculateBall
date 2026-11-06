import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aerostat_physics as ap  # noqa: E402


class AtmosphereTests(unittest.TestCase):
    def test_sea_level_density(self):
        self.assertAlmostEqual(ap.calculate_air_density(0), 1.2256, delta=0.003)

    def test_unit_conversion(self):
        self.assertAlmostEqual(ap.kg_to_kn(100.0), 0.980665, places=9)
        self.assertAlmostEqual(ap.kn_to_kg(ap.kg_to_kn(37.0)), 37.0, places=9)

    def test_field_temperature_is_used_as_measured(self):
        rho = ap.calculate_corrected_air_density(2000, 2000, 20.0)
        expected = ap.calculate_air_pressure(2000) / (0.2869 * (20.0 + ap.KELVIN))
        self.assertAlmostEqual(rho, expected, places=9)
        self.assertAlmostEqual(ap.actual_temperature(2100, 2000, 20.0), 20.0 - 0.649, places=9)


class BuoyancyTests(unittest.TestCase):
    def test_lift_decreases_with_altitude(self):
        low = ap.calculate_buoyant_lift(1000, 0, "氦气", 15.0)
        high = ap.calculate_buoyant_lift(1000, 3000, "氦气", 15.0)
        self.assertGreater(low, high)
        self.assertAlmostEqual(low, 1000 * 1.2252 * 0.99 * (1 - 4.0026 / 28.964), delta=2)

    def test_superheat_reduces_lift_by_ambient_temperature_ratio(self):
        cold = ap.calculate_buoyant_lift(1000, 500, "氦气", 15.0, 0.0, 100.0)
        hot = ap.calculate_buoyant_lift(1000, 500, "氦气", 15.0, 20.0, 100.0)
        t = 15.0 + ap.KELVIN
        rho_air = ap.calculate_air_pressure(500) / (0.2869 * t)
        expected = 1000 * rho_air * (1 - (4.0026 / 28.964) * t / (t + 20.0))
        self.assertAlmostEqual(hot, expected, delta=1e-6 * expected + 1e-6)
        # 同一体积下气体越热越轻，毛浮力略增（设计中不计此增益）
        self.assertGreater(hot, cold)

    def test_purity_reduces_lift(self):
        pure = ap.calculate_buoyant_lift(1000, 0, "氦气", 15.0, 0.0, 100.0)
        dirty = ap.calculate_buoyant_lift(1000, 0, "氦气", 15.0, 0.0, 95.0)
        self.assertAlmostEqual(dirty, pure * 0.95, delta=1e-6 * pure)


class GasExpansionTests(unittest.TestCase):
    def test_expansion_is_one_at_field_without_temperature_swing(self):
        self.assertAlmostEqual(ap.gas_expansion_ratio(500, 0.0, 20.0, 0.0, 0.0), 1.0, places=9)

    def test_temperature_swing_and_superheat_increase_expansion(self):
        base = ap.gas_expansion_ratio(500, 800, 20.0, 0.0, 0.0)
        swing = ap.gas_expansion_ratio(500, 800, 20.0, 15.0, 0.0)
        heated = ap.gas_expansion_ratio(500, 800, 20.0, 15.0, 10.0)
        self.assertLess(base, swing)
        self.assertLess(swing, heated)

    def test_recommended_ratio_matches_pressure_height(self):
        for dt, sh in ((0.0, 0.0), (15.0, 0.0), (15.0, 10.0)):
            ratio = ap.recommend_auxiliary_ratio(500, 800, 15.0, dt, sh)
            self.assertAlmostEqual(ap.calculate_pressure_height(500, 15.0, dt, sh, ratio), 800, delta=0.5)

    def test_warm_fill_recommendation_covers_cold_night(self):
        dt, sh, fill_t = 15.0, 5.0, 25.0
        ratio = ap.recommend_auxiliary_ratio(500, 800, 15.0, dt, sh, fill_t)
        x = ap.gas_expansion_ratio(500, 800, 15.0, dt, sh, fill_t)
        x_min = ap.fill_contraction_ratio(15.0, dt, fill_t)
        self.assertLess(x_min, 1.0)
        self.assertAlmostEqual(ratio, 1.0 - x_min / x, places=12)
        self.assertAlmostEqual(ratio, ap.recommend_auxiliary_ratio(500, 800, 15.0, dt, sh), places=12)
        free = 1.0 - (1.0 - ratio) / x_min
        self.assertAlmostEqual(ap.calculate_pressure_height(500, 15.0, dt, sh, free, fill_temp_c=fill_t), 800, delta=0.5)


class AuxRatioFromFillTests(unittest.TestCase):
    def test_ratio_is_one_minus_fill_plus_margin_and_clamped(self):
        self.assertAlmostEqual(ap.aux_ratio_from_fill(0.7, 0.05), 0.35, places=12)
        self.assertAlmostEqual(ap.aux_ratio_from_fill(0.9, 0.5), 0.6, places=12)
        self.assertEqual(ap.aux_ratio_from_fill(1.0, 0.0), 0.0)
        self.assertEqual(ap.aux_ratio_from_fill(0.01, 0.5), 0.95)
        self.assertGreater(ap.aux_ratio_from_fill(0.8, 0.05), 1.0 - 0.8)


class TetherTests(unittest.TestCase):
    def test_no_wind_on_cable_matches_catenary(self):
        drag, lift, w, height = 0.58, 4.9, 0.005, 300.0
        r = ap.solve_tether_equilibrium(lift, drag, 0.0, 0.005, w, height)
        tz_bottom = math.sqrt((math.hypot(drag, lift) - w * height) ** 2 - drag ** 2)
        self.assertAlmostEqual(r["net_buoyancy"], tz_bottom, delta=1e-6)
        self.assertAlmostEqual(r["cable_length"], (lift - tz_bottom) / w, delta=1e-5)
        x_exact = drag / w * (math.asinh(lift / drag) - math.asinh(tz_bottom / drag))
        self.assertAlmostEqual(r["drift"], x_exact, delta=1e-3)

    def test_force_balance_with_wind(self):
        r = ap.solve_tether_equilibrium(5.0, 0.58, lambda z: 0.14 + 0.0002 * z, 0.005, 0.00025, 100.0)
        self.assertAlmostEqual(r["horizontal"], 0.58 + r["cable_drag_h"], places=9)
        self.assertAlmostEqual(5.0, r["net_buoyancy"] + r["cable_weight"] + r["cable_drag_v"], places=6)

    def test_overweight_is_not_flyable(self):
        self.assertFalse(ap.solve_tether_equilibrium(-0.01, 0.1, 0.05, 0.005, 0.0002, 100.0)["flyable"])

    def test_cable_too_heavy_grounds(self):
        r = ap.solve_tether_equilibrium(0.3, 0.2, 0.1, 0.006, 0.003, 100.0)
        self.assertFalse(r["flyable"])


class TetherPathTests(unittest.TestCase):
    def test_path_runs_from_balloon_to_anchor(self):
        from aerostat_physics import solve_tether_equilibrium
        result = solve_tether_equilibrium(1.0, 2.0, 0.05, 0.006, 0.0003, 100.0, 1.2, 400)
        self.assertTrue(result["flyable"])
        path = result["path"]
        self.assertEqual(path[0], (0.0, 100.0))
        self.assertAlmostEqual(path[-1][1], 0.0, places=9)
        self.assertAlmostEqual(path[-1][0], result["drift"], places=9)
        heights = [z for _, z in path]
        self.assertEqual(heights, sorted(heights, reverse=True))
        self.assertLess(len(path), 400)


if __name__ == "__main__":
    unittest.main()
