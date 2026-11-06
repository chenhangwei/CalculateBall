import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aerostat_wind as aw  # noqa: E402
from aerostat_model import (CableSpec, DesignInputs, Requirements, analyze, hull_aero_areas)  # noqa: E402
from aerostat_physics import KELVIN, calculate_buoyant_lift, gas_cell_lift, kg_to_kn  # noqa: E402
from Airship import Airship  # noqa: E402
from Sphere import Sphere  # noqa: E402

A, B, C, D, NONE = aw.TERRAIN_OPTIONS


def sphere_inputs(**overrides):
    sphere = Sphere(10, 1, 32, 40)
    base = dict(
        shape="sphere", volume=sphere.Calculate_volume(), surface_area=sphere.Calculate_surface_area(),
        max_radius=5.0, aux_geometry=sphere.auxiliary_geometry, aux_unit_weight=0.2, fixed_mass=60.0,
        drag_area=0.5 * sphere.Calculate_windwardArea(), altitude=100.0, target_height=100.0, field_temp_c=20.0,
        aux_ratio=0.08, terrain=B,
        work_wind=aw.WindProfile(aw.MODE_REF10, B, 100.0, speed=8.0),
        survival_wind=aw.WindProfile(aw.MODE_REF10, B, 100.0, speed=20.0),
        cable=CableSpec(diameter_m=0.006, unit_weight_kg_m=0.026, breaking_force_kn=31.9),
        requirements=Requirements(),
    )
    base.update(overrides)
    return DesignInputs(**base)


def marginal_mass(net_kg):
    """使静净浮力约为 net_kg 的固定质量（kg）。"""
    base = analyze(sphere_inputs(fixed_mass=0.0))
    return base["gas"]["lift_governing_kg"] - base["gas"]["aux_mass"] - net_kg


class MembraneStressTests(unittest.TestCase):
    def test_sphere_matches_pr_over_two(self):
        from aerostat_model import membrane_stress
        result = membrane_stress(5.0, 5.0, 0.8)
        self.assertAlmostEqual(result["max"], 0.8 * 5.0 / 2.0, places=9)
        self.assertAlmostEqual(result["hoop"], result["meridional"], places=9)

    def test_prolate_equator_hoop_matches_closed_form_and_is_the_maximum(self):
        from aerostat_model import membrane_stress
        a, b, p = 4.0, 16.0, 0.8
        result = membrane_stress(a, b, p)
        expected = p * a / 2.0 * (2.0 - a * a / (b * b))
        self.assertAlmostEqual(result["hoop"], expected, places=9)
        self.assertAlmostEqual(result["max"], expected, places=6)
        self.assertEqual(result["where"], "赤道")
        self.assertLess(result["max"], p * a)  # 小于圆柱极限 p·r
        self.assertGreater(result["max"], 0.95 * p * a)

    def test_oblate_beyond_root_two_has_compressive_hoop_at_equator(self):
        from aerostat_model import membrane_stress
        flat = membrane_stress(5.0, 3.0, 0.8)
        self.assertLess(flat["hoop_min"], 0.0)
        self.assertAlmostEqual(flat["hoop"], 0.8 * 5.0 / 2.0 * (2.0 - 25.0 / 9.0), places=9)
        mild = membrane_stress(5.0, 4.0, 0.8)
        self.assertGreater(mild["hoop_min"], 0.0)

    def test_pole_forces_equal_for_any_spheroid(self):
        from aerostat_model import membrane_stress
        for a, b in ((5.0, 3.0), (4.0, 16.0)):
            pole = 0.8 * a * a / (2.0 * b)
            self.assertLessEqual(pole, membrane_stress(a, b, 0.8)["max"] + 1e-9)

    def test_analyze_uses_spheroid_and_warns_when_too_flat(self):
        round_sphere = analyze(sphere_inputs(overpressure_kpa=0.8, film_strength_n5cm=4000.0, membrane_shapes=[(5.0, 5.0)]))
        self.assertAlmostEqual(round_sphere["work"]["film"]["stress"], 0.8 * 5.0 / 2.0, places=9)
        flat = analyze(sphere_inputs(overpressure_kpa=0.8, film_strength_n5cm=4000.0, membrane_shapes=[(5.0, 3.0)]))
        self.assertTrue(any("压应力" in w for w in flat["work"]["warnings"]))
        self.assertFalse(any("压应力" in w for w in round_sphere["work"]["warnings"]))

    def test_airship_takes_the_larger_of_the_two_half_bodies(self):
        inp = sphere_inputs(overpressure_kpa=0.8, film_strength_n5cm=4000.0, shape="airship",
                            membrane_shapes=[(4.0, 8.0), (4.0, 24.0)])
        stress = analyze(inp)["work"]["film"]["stress"]
        from aerostat_model import membrane_stress
        self.assertAlmostEqual(stress, max(membrane_stress(4.0, 8.0, 0.8)["max"], membrane_stress(4.0, 24.0, 0.8)["max"]),
                               places=9)


class LiftDefinitionTests(unittest.TestCase):
    """四个浮力量的物理定义，与理想气体闭式解独立对照。"""

    MU = 0.0040026 / 0.028964

    def air_density(self, altitude, temp_c):
        from aerostat_physics import calculate_air_pressure
        return calculate_air_pressure(altitude) / (0.2869 * (temp_c + KELVIN))

    def test_field_total_lift_and_altitude_loss(self):
        inp = sphere_inputs(altitude=800.0, field_temp_c=20.0, purity=98.0, fill_fraction=0.9)
        gas = analyze(inp)["gas"]
        mix = 0.98 * self.MU + 0.02
        site = inp.volume * self.air_density(800.0, 20.0) * (1.0 - mix)
        sea = inp.volume * self.air_density(0.0, 20.0) * (1.0 - mix)
        self.assertAlmostEqual(gas["field_total_lift_kg"], site, delta=1e-9 * site)
        self.assertAlmostEqual(gas["altitude_loss_kg"], sea - site, delta=1e-9 * sea)
        self.assertAlmostEqual(gas["field_total_lift_kg"] + gas["altitude_loss_kg"], sea, delta=1e-9 * sea)

    def test_target_lift_is_helium_mass_times_constant(self):
        inp = sphere_inputs(altitude=800.0, field_temp_c=20.0, temp_diff_c=10.0, purity=98.0, fill_fraction=0.9)
        gas = analyze(inp)["gas"]
        mix = 0.98 * self.MU + 0.02
        t_fill = 20.0 - 5.0
        expected = 0.9 * inp.volume * self.air_density(800.0, t_fill) * (1.0 - mix)
        self.assertFalse(gas["vented"])
        self.assertAlmostEqual(gas["lift_start_kg"], expected, delta=1e-9 * expected)
        hotter = analyze(sphere_inputs(altitude=800.0, field_temp_c=20.0, temp_diff_c=10.0, purity=98.0,
                                       fill_fraction=0.9, target_height=300.0))["gas"]
        self.assertAlmostEqual(hotter["lift_start_kg"], gas["lift_start_kg"], delta=1e-9 * expected)

    def test_end_of_stay_lift_removes_escaped_helium_and_purity(self):
        inp = sphere_inputs(altitude=800.0, purity=98.0, fill_fraction=0.9, leakage_rate=0.003, stay_days=10.0,
                            purity_decay_per_day=0.1)
        gas = analyze(inp)["gas"]
        leak = inp.surface_area * 0.003 * 10.0
        mix_end = 0.97 * self.MU + 0.03
        expected = (0.9 * inp.volume - leak) * self.air_density(800.0, 20.0) * (1.0 - mix_end)
        self.assertAlmostEqual(gas["lift_end_kg"], expected, delta=1e-9 * expected)

    def test_static_net_is_governing_lift_minus_fixed_and_ballonet_mass(self):
        inp = sphere_inputs(fill_fraction=0.9, leakage_rate=0.003, stay_days=10.0)
        res = analyze(inp)
        self.assertAlmostEqual(res["static_net_kg"], res["gas"]["lift_end_kg"] - inp.fixed_mass - res["gas"]["aux_mass"],
                               places=9)

    def test_superheat_reduces_cell_capacity_consistently_with_expansion(self):
        cool = analyze(sphere_inputs(aux_ratio=0.1, fill_fraction=0.99))["gas"]
        warm = analyze(sphere_inputs(aux_ratio=0.1, fill_fraction=0.99, superheat_k=10.0))["gas"]
        self.assertGreater(warm["expansion_ratio"], cool["expansion_ratio"])
        self.assertEqual(bool(warm["alarms"]), warm["fill_target_raw"] > 1.0)
        self.assertEqual(warm["vented"], warm["fill_target_raw"] > 1.0)
        self.assertEqual(cool["vented"], cool["fill_target_raw"] > 1.0)


class GasTests(unittest.TestCase):
    def test_without_swing_or_loss_matches_closed_form(self):
        inp = sphere_inputs(aux_ratio=0.0, gas_type="氦气", purity=99.0)
        r = analyze(inp)
        z = inp.altitude + inp.target_height
        t = 20.0 - 0.00649 * inp.target_height
        expected = calculate_buoyant_lift(inp.volume, z, "氦气", t, 0.0, 99.0)
        self.assertAlmostEqual(r["gas"]["lift_governing_kg"], expected, delta=1e-6 * expected)

    def test_gas_cell_matches_buoyant_lift_when_not_vented(self):
        cell = gas_cell_lift(1000.0, 800.0, 0.99, 0.0, 15.0, 0.0, 15.0, 0.0, "氦气")
        self.assertFalse(cell["vented"])
        self.assertAlmostEqual(cell["lift_kg"], calculate_buoyant_lift(800.0, 0.0, "氦气", 15.0, 0.0, 99.0), delta=1e-6)

    def test_venting_limits_lift_and_superheat_vents_more(self):
        no_vent = gas_cell_lift(1000.0, 800.0, 0.99, 0.0, 15.0, 800.0, 11.0, 0.0, "氦气")
        vent = gas_cell_lift(1000.0, 950.0, 0.99, 0.0, 15.0, 800.0, 11.0, 0.0, "氦气")
        hot = gas_cell_lift(1000.0, 950.0, 0.99, 0.0, 15.0, 800.0, 11.0, 20.0, "氦气")
        self.assertTrue(vent["vented"] and hot["vented"])
        self.assertGreater(vent["vented_mass"], 0)
        self.assertLess(hot["lift_kg"], vent["lift_kg"])
        self.assertGreater(no_vent["lift_kg"], 0)

    def test_hot_day_lowers_lift(self):
        mean = analyze(sphere_inputs(aux_ratio=0.0))["gas"]["lift_governing_kg"]
        hot = analyze(sphere_inputs(aux_ratio=0.0, temp_diff_c=20.0))["gas"]["lift_governing_kg"]
        self.assertLess(hot, mean)

    def test_end_of_stay_is_governing_and_lower(self):
        inp = sphere_inputs(leakage_rate=0.002, stay_days=15.0, purity_decay_per_day=0.2)
        gas = analyze(inp)["gas"]
        self.assertLess(gas["lift_end_kg"], gas["lift_start_kg"])
        self.assertEqual(gas["lift_governing_kg"], gas["lift_end_kg"])
        self.assertAlmostEqual(gas["purity_end"], 99.0 - 3.0, places=9)
        self.assertAlmostEqual(gas["leak_volume"], inp.surface_area * 0.002 * 15.0, places=9)
        self.assertAlmostEqual(gas["aux_ratio_capacity"], 0.08, places=12)
        no_loss = analyze(sphere_inputs())["gas"]
        self.assertEqual(no_loss["lift_governing_kg"], no_loss["lift_start_kg"])

    def test_default_fill_is_recommended_fill_when_aux_bag_is_large_enough(self):
        default = analyze(sphere_inputs(aux_ratio=0.2))["gas"]
        self.assertAlmostEqual(default["fill_fraction"], default["fill_recommended"], places=12)
        self.assertFalse(default["vented"])
        self.assertEqual(default["alarms"], [])
        # 副气囊偏小：充盈度不变，只提示副气囊容积不足，不会靠排氦解决
        small = analyze(sphere_inputs(aux_ratio=0.0, temp_diff_c=30.0))["gas"]
        self.assertAlmostEqual(small["fill_fraction"], small["fill_recommended"], places=12)
        self.assertEqual(len(small["alarms"]), 1)
        self.assertIn("必须大于", small["alarms"][0])
        self.assertTrue(small["warnings"])

    def test_aux_ratio_must_exceed_one_minus_fill(self):
        bad = analyze(sphere_inputs(aux_ratio=0.1, fill_fraction=0.85))["gas"]
        self.assertTrue(any("必须大于" in text for text in bad["alarms"]))
        edge = analyze(sphere_inputs(aux_ratio=0.15, fill_fraction=0.85))["gas"]
        self.assertFalse(any("必须大于" in text for text in edge["alarms"]))
        good = analyze(sphere_inputs(aux_ratio=0.2, fill_fraction=0.85))["gas"]
        self.assertEqual(good["alarms"], [])
        no_ballonet = analyze(sphere_inputs(aux_ratio=0.0, fill_fraction=1.0))["gas"]
        self.assertFalse(any("必须大于" in text for text in no_ballonet["alarms"]))

    def test_recommended_ratio_satisfies_the_constraint(self):
        from aerostat_physics import recommend_auxiliary_ratio
        base = sphere_inputs(temp_diff_c=20.0, leakage_rate=0.002, stay_days=15.0)
        leak_ratio = base.surface_area * 0.002 * 15.0 / base.volume
        ratio = recommend_auxiliary_ratio(base.altitude, base.target_height, base.field_temp_c, 20.0, 0.0, None, leak_ratio)
        gas = analyze(sphere_inputs(aux_ratio=ratio, temp_diff_c=20.0, leakage_rate=0.002, stay_days=15.0))["gas"]
        self.assertEqual(gas["alarms"], [])

    def test_fill_above_one_at_target_raises_alarm(self):
        over = analyze(sphere_inputs(aux_ratio=0.1, fill_fraction=0.95, temp_diff_c=30.0))["gas"]
        self.assertGreater(over["fill_target_raw"], 1.0)
        self.assertAlmostEqual(over["fill_target_raw"], 0.95 * over["expansion_ratio"], places=12)
        self.assertEqual(len(over["alarms"]), 1)
        self.assertIn("充盈度大于 1", over["alarms"][0])
        ok = analyze(sphere_inputs(aux_ratio=0.2, fill_fraction=0.85, temp_diff_c=30.0))["gas"]
        self.assertLessEqual(ok["fill_target_raw"], 1.0)
        self.assertEqual(ok["alarms"], [])
        back = analyze(sphere_inputs(aux_ratio=0.3, fill_end_target=0.99, temp_diff_c=30.0))["gas"]
        self.assertTrue(back["alarms"])

    def test_aux_geometry_follows_the_typed_ratio_exactly(self):
        volume = sphere_inputs().volume
        previous = None
        for ratio in (0.05, 0.1, 0.2, 0.3, 0.4):
            for extra in ({}, {"fill_fraction": 0.9}, {"fill_end_target": 0.6, "leakage_rate": 0.004, "stay_days": 20.0},
                          {"leakage_rate": 0.004, "stay_days": 20.0}):
                inp = sphere_inputs(aux_ratio=ratio, **extra)
                gas = analyze(inp)["gas"]
                area, _ = inp.aux_geometry(ratio)
                self.assertAlmostEqual(gas["aux_volume"], ratio * volume, places=9)
                self.assertAlmostEqual(gas["aux_area"], area, places=9)
                self.assertAlmostEqual(gas["aux_mass"], area * inp.aux_unit_weight, places=9)
            if previous is not None:
                self.assertGreater(gas["aux_volume"], previous)
            previous = gas["aux_volume"]

    def test_fill_fraction_sets_lift_independently_of_aux_ratio(self):
        base = analyze(sphere_inputs(aux_ratio=0.2, fill_fraction=0.8))["gas"]
        filled = analyze(sphere_inputs(aux_ratio=0.2, fill_fraction=0.9))["gas"]
        self.assertAlmostEqual(filled["lift_start_kg"] / base["lift_start_kg"], 0.9 / 0.8, places=9)
        self.assertAlmostEqual(filled["initial_gas_volume"], 0.9 * sphere_inputs().volume, places=9)
        self.assertEqual(filled["aux_ratio_capacity"], base["aux_ratio_capacity"])
        self.assertEqual(filled["warnings"], [])

    def test_pressure_height_follows_free_volume_not_aux_ratio(self):
        filled = analyze(sphere_inputs(aux_ratio=0.2, fill_fraction=0.9))["gas"]
        free_tenth = analyze(sphere_inputs(aux_ratio=0.1, fill_fraction=0.9))["gas"]
        self.assertAlmostEqual(filled["pressure_height"], free_tenth["pressure_height"], places=6)

    def test_free_volume_larger_than_aux_bag_warns(self):
        gas = analyze(sphere_inputs(aux_ratio=0.1, fill_fraction=0.7))["gas"]
        self.assertTrue(gas["warnings"])
        self.assertAlmostEqual(gas["aux_ratio_capacity"], 0.1, places=12)
        self.assertGreater(gas["aux_air_cold"], gas["aux_volume"])

    def test_ballonet_exchange_follows_helium_expansion(self):
        gas = analyze(sphere_inputs(aux_ratio=0.3, fill_fraction=0.8, temp_diff_c=30.0))["gas"]
        volume = sphere_inputs().volume
        x = gas["expansion_ratio"]
        self.assertLess(0.8 * x, 1.0)
        self.assertAlmostEqual(gas["fill_target"], 0.8 * x, places=12)
        self.assertAlmostEqual(gas["aux_air_target"], (1.0 - 0.8 * x) * volume, places=9)
        self.assertAlmostEqual(gas["aux_exchange"], 0.8 * (x - 1.0) * volume, places=9)
        self.assertFalse(gas["vented"])

    def test_ballonet_empty_and_helium_vented_beyond_pressure_height(self):
        gas = analyze(sphere_inputs(aux_ratio=0.1, fill_fraction=0.95, temp_diff_c=30.0))["gas"]
        volume = sphere_inputs().volume
        self.assertGreater(0.95 * gas["expansion_ratio"], 1.0)
        self.assertEqual(gas["fill_target"], 1.0)
        self.assertEqual(gas["aux_air_target"], 0.0)
        self.assertAlmostEqual(gas["aux_exchange"], 0.05 * volume, places=9)
        self.assertTrue(gas["vented"])

    def test_warm_fill_needs_bigger_ballonet_for_cold_night(self):
        cold = analyze(sphere_inputs(aux_ratio=0.2, temp_diff_c=30.0))["gas"]
        warm = analyze(sphere_inputs(aux_ratio=0.2, temp_diff_c=30.0, fill_temp_c=35.0))["gas"]
        x_min = (20.0 - 15.0 + KELVIN) / (35.0 + KELVIN)
        self.assertAlmostEqual(warm["fill_fraction"], max(1.0 / warm["expansion_ratio"], 0.8 / x_min), places=12)
        self.assertAlmostEqual(warm["aux_ratio_capacity"], 0.2, places=12)
        self.assertAlmostEqual(warm["expansion_ratio"] / x_min, cold["expansion_ratio"], places=12)
        explicit = analyze(sphere_inputs(aux_ratio=0.2, temp_diff_c=30.0, fill_temp_c=35.0, fill_fraction=0.8))["gas"]
        self.assertAlmostEqual(explicit["aux_air_cold"], (1.0 - 0.8 * x_min) * sphere_inputs().volume, places=9)
        self.assertAlmostEqual(explicit["aux_ratio_capacity"], 0.2, places=12)
        self.assertGreater(explicit["aux_air_cold"], explicit["aux_volume"])
        self.assertTrue(explicit["warnings"])

    def test_ballonet_flow_is_exchange_over_climb_time(self):
        inp = sphere_inputs(aux_ratio=0.3, fill_fraction=0.8, temp_diff_c=30.0, climb_speed=2.0, target_height=100.0)
        gas = analyze(inp)["gas"]
        self.assertAlmostEqual(gas["aux_flow_m3_min"], gas["aux_exchange"] / (100.0 / 2.0 / 60.0), places=9)
        self.assertEqual(analyze(sphere_inputs(climb_speed=0.0))["gas"]["aux_flow_m3_min"], 0.0)

    def test_recommended_fill_fills_envelope_at_target(self):
        gas = analyze(sphere_inputs(aux_ratio=0.3, temp_diff_c=30.0))["gas"]
        self.assertAlmostEqual(gas["fill_recommended"] * gas["expansion_ratio"], 1.0, places=12)

    def test_end_of_stay_fill_accounts_for_helium_escape(self):
        inp = sphere_inputs(aux_ratio=0.3, fill_fraction=0.7, leakage_rate=0.004, stay_days=20.0)
        gas = analyze(inp)["gas"]
        leak_ratio = gas["leak_volume"] / inp.volume
        self.assertGreater(leak_ratio, 0.0)
        self.assertAlmostEqual(gas["fill_end"], 0.7 - leak_ratio, places=12)
        self.assertAlmostEqual(gas["fill_target_end"], min(gas["fill_end"] * gas["expansion_ratio"], 1.0), places=12)
        self.assertAlmostEqual(gas["lift_end_kg"] / gas["lift_start_kg"], gas["fill_end"] / 0.7, places=9)

    def test_initial_fill_back_computed_from_end_of_stay_fill(self):
        inp = sphere_inputs(aux_ratio=0.3, fill_end_target=0.7, leakage_rate=0.004, stay_days=20.0)
        gas = analyze(inp)["gas"]
        leak_ratio = gas["leak_volume"] / inp.volume
        self.assertAlmostEqual(gas["fill_fraction"], 0.7 + leak_ratio, places=12)
        self.assertAlmostEqual(gas["fill_end"], 0.7, places=12)
        self.assertEqual(gas["warnings"], [])
        ignored = analyze(sphere_inputs(aux_ratio=0.3, fill_end_target=0.7, fill_fraction=0.5, leakage_rate=0.004,
                                        stay_days=20.0))["gas"]
        self.assertAlmostEqual(ignored["fill_fraction"], gas["fill_fraction"], places=12)
        self.assertTrue(ignored["warnings"])

    def test_end_of_stay_fill_beyond_full_is_capped_with_warning(self):
        inp = sphere_inputs(aux_ratio=0.3, fill_end_target=0.98, leakage_rate=0.004, stay_days=20.0)
        gas = analyze(inp)["gas"]
        self.assertEqual(gas["fill_fraction"], 1.0)
        self.assertLess(gas["fill_end"], 0.98)
        self.assertTrue(gas["warnings"])

    def test_vented_excess_is_not_recovered_during_stay(self):
        inp = sphere_inputs(aux_ratio=0.0, fill_fraction=1.0, temp_diff_c=30.0, leakage_rate=0.004, stay_days=20.0)
        gas = analyze(inp)["gas"]
        leak_ratio = gas["leak_volume"] / inp.volume
        self.assertGreater(gas["expansion_ratio"], 1.0)
        v_effective = 1.0 / gas["expansion_ratio"]
        self.assertAlmostEqual(gas["fill_end"], v_effective - leak_ratio, places=9)
        self.assertAlmostEqual(gas["lift_end_kg"] / gas["lift_start_kg"], (v_effective - leak_ratio) / v_effective, places=9)

    def test_recommended_ratio_includes_leak_so_capacity_is_enough(self):
        from aerostat_physics import recommend_auxiliary_ratio
        base = sphere_inputs(leakage_rate=0.002, stay_days=15.0, temp_diff_c=15.0)
        leak_ratio = base.surface_area * 0.002 * 15.0 / base.volume
        ratio = recommend_auxiliary_ratio(base.altitude, base.target_height, base.field_temp_c, 15.0, 0.0, None, leak_ratio)
        gas = analyze(sphere_inputs(aux_ratio=ratio, leakage_rate=0.002, stay_days=15.0, temp_diff_c=15.0))["gas"]
        self.assertEqual(gas["warnings"], [])
        self.assertFalse(gas["vented"])
        short = analyze(sphere_inputs(aux_ratio=ratio - 0.02, leakage_rate=0.002, stay_days=15.0, temp_diff_c=15.0))["gas"]
        self.assertTrue(short["warnings"])

    def test_aux_mass_follows_geometry_and_capacity(self):
        inp = sphere_inputs(leakage_rate=0.002, stay_days=15.0)
        gas = analyze(inp)["gas"]
        area, _ = inp.aux_geometry(gas["aux_ratio_capacity"])
        self.assertAlmostEqual(gas["aux_mass"], area * 0.2, places=9)
        self.assertAlmostEqual(gas["aux_volume"], gas["aux_ratio_capacity"] * inp.volume, places=9)


class CaseTests(unittest.TestCase):
    def test_static_net_in_kn(self):
        r = analyze(sphere_inputs())
        self.assertAlmostEqual(r["static_net_kn"], kg_to_kn(r["static_net_kg"]), places=12)
        self.assertAlmostEqual(r["static_net_kg"], r["gas"]["lift_governing_kg"] - 60.0 - r["gas"]["aux_mass"], places=9)

    def test_survival_wind_gives_larger_loads_and_lower_safety(self):
        r = analyze(sphere_inputs())
        self.assertGreater(r["survival"]["peak_tension"], r["work"]["peak_tension"])
        self.assertLess(r["survival"]["cable_sf"], r["work"]["cable_sf"])

    def test_cable_safety_factor_formula(self):
        r = analyze(sphere_inputs())["work"]
        self.assertAlmostEqual(r["cable_sf"], 31.9 * 0.8 / r["peak_tension"], places=9)

    def test_gust_peak_exceeds_mean(self):
        r = analyze(sphere_inputs())["work"]
        self.assertGreater(r["peak_tension"], r["mean"]["tension"])
        self.assertGreater(r["wind"]["gust_target"], 1.0)

    def test_film_safety_factor_for_sphere(self):
        inp = sphere_inputs(overpressure_kpa=0.4, film_strength_n5cm=1000.0, seam_efficiency=0.7)
        film = analyze(inp)["work"]["film"]
        self.assertAlmostEqual(film["stress"], 0.4 * 5.0 / 2.0, places=12)
        self.assertAlmostEqual(film["strength"], 1000.0 * 0.02 * 0.7, places=12)
        self.assertAlmostEqual(film["sf"], 14.0 / 1.0, places=9)

    def test_film_stress_for_airship_is_hoop(self):
        ship = Airship(32, 0.25, 0.3, 24, 40)
        inp = sphere_inputs(shape="airship", max_radius=ship.b, overpressure_kpa=0.3)
        self.assertAlmostEqual(analyze(inp)["work"]["film"]["stress"], 0.3 * 4.0, places=12)

    def test_auto_overpressure_tracks_gust_dynamic_pressure(self):
        r = analyze(sphere_inputs())["work"]
        wind = r["wind"]
        self.assertAlmostEqual(r["film"]["required_kpa"], 1.2 * wind["gust_target"] * wind["pressure_target_kpa"], places=12)
        self.assertEqual(r["film"]["operating_kpa"], r["film"]["required_kpa"])

    def test_insufficient_overpressure_fails_working_but_only_warns_in_survival(self):
        r = analyze(sphere_inputs(overpressure_kpa=0.001))
        self.assertTrue(any("超压" in f for f in r["work"]["failures"]))
        self.assertFalse(any("超压" in f for f in r["survival"]["failures"]))
        self.assertTrue(any("超压" in w for w in r["survival"]["warnings"]))

    def test_weak_film_fails(self):
        r = analyze(sphere_inputs(film_strength_n5cm=30.0))
        self.assertTrue(any("膜材安全系数" in f for f in r["work"]["failures"]))

    def test_pull_point_load_and_safety(self):
        inp = sphere_inputs(pull_points=16, bridle_half_angle_deg=30.0, load_nonuniformity=1.5, pull_point_rating_kn=5.0)
        r = analyze(inp)["work"]
        expected = r["peak"]["tension"] * 1.5 / (16 * math.cos(math.radians(30.0)))
        self.assertAlmostEqual(r["pull"]["load"], expected, places=12)
        self.assertAlmostEqual(r["pull"]["sf"], 5.0 / expected, places=12)

    def test_grounded_cable_fails_working_with_deficit_and_only_warns_in_survival(self):
        inp = sphere_inputs(fixed_mass=marginal_mass(1.5))   # 浮力不足以托起缆绳
        r = analyze(inp)
        self.assertFalse(r["work"]["mean"]["flyable"])
        self.assertTrue(any("拖地" in f or "超重" in f for f in r["work"]["failures"]))
        self.assertGreater(r["work"]["lift_deficit"], 0)
        self.assertFalse(r["survival"]["failures"] and any("拖地" in f for f in r["survival"]["failures"]))

    def test_survival_keeps_work_cable_length_and_blows_balloon_down(self):
        r = analyze(sphere_inputs(fixed_mass=marginal_mass(120.0)))
        work, survival = r["work"], r["survival"]
        self.assertTrue(work["mean"]["flyable"])
        self.assertTrue(survival["blown_down"])
        self.assertLess(survival["height"], 100.0)
        self.assertTrue(survival["mean"]["flyable"])
        self.assertAlmostEqual(survival["mean"]["cable_length"], work["mean"]["cable_length"], delta=0.02 * work["mean"]["cable_length"])
        self.assertAlmostEqual(survival["wind"]["pressure_target_kpa"],
                               analyze(sphere_inputs(fixed_mass=marginal_mass(120.0)))["survival"]["wind"]["pressure_target_kpa"], places=12)

    def test_survival_equal_to_work_wind_stays_at_target_height(self):
        profile = aw.WindProfile(aw.MODE_REF10, B, 100.0, speed=8.0)
        r = analyze(sphere_inputs(survival_wind=profile))
        self.assertFalse(r["survival"]["blown_down"])
        self.assertEqual(r["survival"]["height"], 100.0)
        self.assertAlmostEqual(r["survival"]["mean"]["tension"], r["work"]["mean"]["tension"], places=9)

    def test_leak_plus_purity_decay_warns_about_double_counting(self):
        both = analyze(sphere_inputs(stay_days=15.0, leakage_rate=0.00082, purity_decay_per_day=0.2))["gas"]
        self.assertTrue(any("重复" in w for w in both["warnings"]))
        for kw in (dict(stay_days=15.0, leakage_rate=0.00082), dict(stay_days=15.0, purity_decay_per_day=0.2)):
            self.assertFalse(any("重复" in w for w in analyze(sphere_inputs(**kw))["gas"]["warnings"]))

    def test_deficit_makes_cable_fly(self):
        inp = sphere_inputs(fixed_mass=marginal_mass(1.5))
        deficit = analyze(inp)["work"]["lift_deficit"]
        extra_mass = deficit * 1000.0 / 9.80665
        fixed = analyze(sphere_inputs(fixed_mass=marginal_mass(1.5) - extra_mass * 1.01))
        self.assertTrue(fixed["work"]["mean"]["flyable"])

    def test_max_wind_is_boundary_of_acceptance(self):
        inp = sphere_inputs()
        base = analyze(inp)
        mw = base["max_wind"]
        self.assertGreater(mw["speed_target"], 0)
        for scale, expected in ((0.97, True), (1.05, False)):
            profile = inp.work_wind.scaled(mw["scale"] * scale)
            probe = sphere_inputs(work_wind=profile, survival_wind=profile)
            self.assertEqual(analyze(probe)["work"]["ok"], expected, scale)
        self.assertAlmostEqual(mw["speed_10"], inp.work_wind.speed(10) * mw["scale"], places=9)

    def test_max_wind_two_references(self):
        inp = sphere_inputs(work_wind=aw.WindProfile(aw.MODE_TARGET, B, 100.0, speed=8.0))
        mw = analyze(inp)["max_wind"]
        self.assertLess(mw["speed_10"], mw["speed_target"])


class AirshipAeroTests(unittest.TestCase):
    def test_hull_aero_areas(self):
        lift_area, induced = hull_aero_areas(1000.0, 5.0, 1.2, 0.4)
        cl = 1.2 * math.radians(5.0)
        self.assertAlmostEqual(lift_area, cl * 100.0, places=9)
        self.assertAlmostEqual(induced, 0.4 * cl * cl * 100.0, places=9)
        self.assertEqual(hull_aero_areas(1000.0, 0.0, 1.2, 0.4), (0.0, 0.0))

    def test_aero_lift_raises_net_buoyancy_at_tether(self):
        base = analyze(sphere_inputs())["work"]["mean"]["net_buoyancy"]
        with_lift = analyze(sphere_inputs(lift_area=3.0))["work"]["mean"]["net_buoyancy"]
        self.assertGreater(with_lift, base)


class LiftStepsTests(unittest.TestCase):
    CASES = ({}, {"fill_fraction": 0.8}, {"fill_fraction": 1.0, "altitude": 2000.0, "target_height": 1500.0},
             {"fill_temp_c": 32.0, "temp_diff_c": 12.0, "superheat_k": 6.0},
             {"stay_days": 15.0, "leakage_rate": 0.002, "purity_decay_per_day": 0.1},
             {"fill_end_target": 0.9, "stay_days": 30.0, "leakage_rate": 0.003})

    def test_steps_add_up_to_the_governing_lift(self):
        for case in self.CASES:
            gas = analyze(sphere_inputs(**case))["gas"]
            total = gas["field_total_lift_kg"] + sum(delta for _, _, delta in gas["lift_steps"])
            self.assertAlmostEqual(total, gas["lift_governing_kg"], places=6, msg=str(case))

    def test_start_lift_is_reached_before_the_leak_steps(self):
        gas = analyze(sphere_inputs(stay_days=15.0, leakage_rate=0.002))["gas"]
        steps = {key: delta for key, _, delta in gas["lift_steps"]}
        self.assertAlmostEqual(gas["field_total_lift_kg"] + steps["fill"] + steps["fill_temp"] + steps["vent"],
                               gas["lift_start_kg"], places=6)
        self.assertLess(steps["leak"], 0.0)

    def test_no_leak_steps_without_stay(self):
        gas = analyze(sphere_inputs(fill_fraction=1.0, altitude=0.0, target_height=1.0, temp_diff_c=0.0))["gas"]
        self.assertEqual([key for key, _, _ in gas["lift_steps"]], ["fill", "fill_temp", "vent"])
        self.assertAlmostEqual(gas["lift_start_kg"], gas["field_total_lift_kg"], delta=0.01 * gas["field_total_lift_kg"])

    def test_colder_fill_temperature_adds_lift_and_underfill_removes_it(self):
        steps = {key: d for key, _, d in analyze(sphere_inputs(fill_fraction=0.8, fill_temp_c=5.0))["gas"]["lift_steps"]}
        self.assertLess(steps["fill"], 0.0)
        self.assertGreater(steps["fill_temp"], 0.0)

    def test_tail_is_not_part_of_the_buoyancy_system(self):
        self.assertFalse(hasattr(sphere_inputs(), "tail_volume"))


class VolumeStatesTests(unittest.TestCase):
    def states(self, **overrides):
        inp = sphere_inputs(**overrides)
        gas = analyze(inp)["gas"]
        return inp, gas, {s["key"]: s for s in gas["volume_states"]}

    def test_helium_plus_air_is_always_the_fixed_total_volume(self):
        for case in LiftStepsTests.CASES:
            inp, gas, _ = self.states(**case)
            for s in gas["volume_states"]:
                self.assertAlmostEqual(s["helium"] + s["air"], inp.volume, places=9, msg=str(case))

    def test_helium_expands_with_height_and_heat_so_the_air_shrinks(self):
        inp, gas, s = self.states(fill_fraction=0.8, temp_diff_c=10.0)
        self.assertAlmostEqual(s["fill"]["fill"], 0.8, places=9)
        self.assertGreater(s["hot"]["fill"], s["fill"]["fill"])
        self.assertLess(s["hot"]["air"], s["fill"]["air"])
        self.assertAlmostEqual(s["hot"]["fill"], min(gas["fill_target_raw"], 1.0), places=9)
        self.assertGreater(s["hot"]["helium"], s["cold"]["helium"])

    def test_night_state_matches_the_ballonet_air_requirement(self):
        _, gas, s = self.states(fill_fraction=0.9, fill_temp_c=30.0, temp_diff_c=10.0, stay_days=20.0, leakage_rate=0.003,
                                aux_ratio=0.3)
        self.assertAlmostEqual(s["night"]["air"], gas["aux_air_cold"], places=9)
        self.assertAlmostEqual(s["hot_end"]["fill"], min(gas["fill_target_end_raw"], 1.0), places=9)

    def test_too_small_a_ballonet_is_flagged(self):
        _, _, s = self.states(fill_fraction=0.7, aux_ratio=0.1)
        self.assertFalse(s["fill"]["fits"])
        _, _, ok = self.states(fill_fraction=0.9, aux_ratio=0.3)
        self.assertTrue(ok["fill"]["fits"])

    def test_lift_does_not_change_with_height_when_nothing_is_vented(self):
        low = analyze(sphere_inputs(fill_fraction=0.7, aux_ratio=0.35, target_height=50.0))["gas"]["lift_start_kg"]
        high = analyze(sphere_inputs(fill_fraction=0.7, aux_ratio=0.35, target_height=800.0))["gas"]["lift_start_kg"]
        self.assertAlmostEqual(low, high, places=6)


if __name__ == "__main__":
    unittest.main()
