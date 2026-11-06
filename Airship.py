"""流线形飞艇几何：两个半椭球（前半轴 a1、后半轴 a2、半径 b）拼接而成。

副气囊为艇身底部通长的空气囊：体积 = 比例 × 艇身总体积，面积取贴合囊壁的球冠面积（数值积分）。
"""
import math

from Sphere import PI, bisect_increasing, simpson


class Airship:
    def __init__(self, length, ratio, center, divide, sewWidth):
        self.ratio = ratio
        self.center = center
        self.length = length
        self.width = length * ratio
        self.b = self.width / 2
        self.a1 = self.length * center
        self.a2 = self.length * (1 - center)
        self.divide = divide
        self.sewWidth = sewWidth

    def calculate_volume(self):
        return (2.0 / 3.0) * PI * self.b ** 2 * (self.a1 + self.a2)

    @staticmethod
    def _spheroid_surface_area(a, b):
        """旋转椭球（绕 a 轴）整体表面积。"""
        if b <= 0 or a <= 0:
            return 0.0
        if abs(a - b) < 1e-6:
            return 4 * PI * b ** 2
        if a > b:
            e = math.sqrt(1 - b * b / (a * a))
            return 2 * PI * b * b * (1 + a / (b * e) * math.asin(e))
        e = math.sqrt(1 - a * a / (b * b))
        return 2 * PI * b * b + PI * (a * a / e) * math.log((1 + e) / (1 - e))

    def ellipsoid_surface_area1(self):
        return self._spheroid_surface_area(self.a1, self.b)

    def ellipsoid_surface_area2(self):
        return self._spheroid_surface_area(self.a2, self.b)

    def calculate_surface_area(self):
        return self.ellipsoid_surface_area1() / 2 + self.ellipsoid_surface_area2() / 2

    @staticmethod
    def _quarter_perimeter(a, b):
        h = ((a - b) ** 2) / ((a + b) ** 2)
        return PI * (a + b) * (1 + (3 * h) / (10 + math.sqrt(4 - 3 * h))) / 4

    def meridian_length(self):
        """鼻尖到尾尖的子午线长度。"""
        return self._quarter_perimeter(self.a1, self.b) + self._quarter_perimeter(self.a2, self.b)

    def calculate_sewArea(self):
        return self.meridian_length() * self.divide * self.sewWidth * 0.001

    # ---- 副气囊 ----
    def _cap_volume(self, h):
        return 0.5 * PI * self.length * h * h * (3 * self.b - h) / (3 * self.b)

    def _cap_height(self, volume):
        if volume <= 0:
            return 0.0
        return bisect_increasing(lambda h: self._cap_volume(h) - volume, 0.0, 2 * self.b)

    @staticmethod
    def _half_spheroid_cap_area(a, b, h):
        """半椭球（x ≥ 0）表面上高度不超过截面 z = -(b-h) 的部分的面积。"""
        z0 = b - h

        def element(theta):
            rho = b * math.sin(theta)
            if rho <= 1e-12:
                return 0.0
            ratio = z0 / rho
            if ratio >= 1:
                half_angle = 0.0
            elif ratio <= -1:
                half_angle = PI
            else:
                half_angle = math.acos(ratio)
            return rho * math.sqrt(b * b * math.cos(theta) ** 2 + a * a * math.sin(theta) ** 2) * 2 * half_angle

        return simpson(element, 0.0, PI / 2, 2000)

    def _aux(self, ratio):
        ratio = min(max(float(ratio), 0.0), 0.999)
        if ratio == 0:
            return 0.0, 0.0
        h = self._cap_height(ratio * self.calculate_volume())
        area = (self._half_spheroid_cap_area(self.a1, self.b, h)
                + self._half_spheroid_cap_area(self.a2, self.b, h))
        return area, h

    def calculate_AuxiliaryAirbagHeight(self, auxiliaryAirbagRatio):
        return self._aux(auxiliaryAirbagRatio)[1]

    def calculate_AuxiliaryArea(self, auxiliaryAirbagRatio):
        return self._aux(auxiliaryAirbagRatio)[0]

    def auxiliary_geometry(self, ratio):
        """返回 (副气囊面积 m², 球冠高度 m)，副气囊体积 = ratio × 艇身总体积。"""
        return self._aux(ratio)
