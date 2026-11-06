import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Airship import Airship  # noqa: E402
from Sphere import Sphere, simpson  # noqa: E402

PI = math.pi


class SphereGeometryTests(unittest.TestCase):
    def test_volume_area_windward(self):
        s = Sphere(10, 1, 32, 40)
        self.assertAlmostEqual(s.Calculate_volume(), 4 / 3 * PI * 125, places=9)
        self.assertAlmostEqual(s.Calculate_surface_area(), 4 * PI * 25, places=6)
        self.assertAlmostEqual(s.Calculate_windwardArea(), PI * 25, places=9)

    def test_aux_cap_volume_equals_ratio_times_total_volume(self):
        for ratio_axis in (1.0, 0.7, 1.3):
            s = Sphere(10, ratio_axis, 32, 40)
            for r in (0.05, 0.08, 0.3, 0.6):
                _, h = s.auxiliary_geometry(r)
                self.assertAlmostEqual(s._cap_volume(h), r * s.Calculate_volume(), places=7)

    def test_sphere_cap_area_is_2_pi_R_h(self):
        s = Sphere(10, 1, 32, 40)
        area, h = s.auxiliary_geometry(0.08)
        self.assertAlmostEqual(area, 2 * PI * 5 * h, places=3)
        self.assertAlmostEqual(h, 1.74, delta=0.01)
        self.assertAlmostEqual(area, 54.6, delta=0.1)

    def test_cap_area_of_full_ellipsoid_is_surface_area(self):
        s = Sphere(10, 0.7, 32, 40)
        self.assertAlmostEqual(s._cap_lateral_area(2 * s.a), s.Calculate_surface_area(), delta=0.01 * s.Calculate_surface_area())

    def test_meridian_length_of_oblate_ellipsoid(self):
        s = Sphere(10, 0.7, 32, 40)
        self.assertAlmostEqual(s.meridian_length(), 13.46, delta=0.01)
        self.assertAlmostEqual(Sphere(10, 1, 32, 40).meridian_length(), PI * 5, places=9)


class AirshipGeometryTests(unittest.TestCase):
    def setUp(self):
        self.ship = Airship(32, 0.25, 0.3, 24, 40)

    def test_volume_and_surface_area(self):
        v = 2 / 3 * PI * 4 ** 2 * 32
        self.assertAlmostEqual(self.ship.calculate_volume(), v, places=9)
        # 与数值积分对照：绕长轴旋转体表面积
        def surface(a, b):
            return 2 * simpson(lambda x: 2 * PI * b * math.sqrt(max(1 - x * x / (a * a), 0)) *
                               math.sqrt(1 + (b * x / (a * a)) ** 2 / max(1 - x * x / (a * a), 1e-12)), 0, a * (1 - 1e-9), 20000) / 2
        numeric = surface(self.ship.a1, 4) + surface(self.ship.a2, 4)
        self.assertAlmostEqual(self.ship.calculate_surface_area(), numeric / 1.0, delta=0.01 * numeric)

    def test_aux_cap_volume_equals_ratio_times_total_volume(self):
        for r in (0.05, 0.08, 0.3, 0.6):
            _, h = self.ship.auxiliary_geometry(r)
            self.assertAlmostEqual(self.ship._cap_volume(h), r * self.ship.calculate_volume(), places=7)

    def test_cap_area_of_full_height_is_surface_area(self):
        s = self.ship
        full = s._half_spheroid_cap_area(s.a1, s.b, 2 * s.b) + s._half_spheroid_cap_area(s.a2, s.b, 2 * s.b)
        self.assertAlmostEqual(full, s.calculate_surface_area(), delta=0.005 * full)

    def test_sphere_limit_of_airship_cap_area(self):
        # a1 = a2 = b 时退化为球：帽面积 2πRh
        ship = Airship(8, 1.0, 0.5, 24, 40)
        _, h = ship.auxiliary_geometry(0.1)
        area = ship._half_spheroid_cap_area(4, 4, h) * 2
        self.assertAlmostEqual(area, 2 * PI * 4 * h, delta=0.002 * area)

    def test_aux_values_for_reference_airship(self):
        area, h = self.ship.auxiliary_geometry(0.08)
        self.assertGreater(h, 0)
        self.assertAlmostEqual(self.ship._cap_volume(h), 0.08 * self.ship.calculate_volume(), places=7)
        self.assertGreater(area, 0)

    def test_zero_ratio(self):
        self.assertEqual(self.ship.auxiliary_geometry(0), (0.0, 0.0))
        self.assertEqual(Sphere(10, 1, 32, 40).auxiliary_geometry(0), (0.0, 0.0))


if __name__ == "__main__":
    unittest.main()
