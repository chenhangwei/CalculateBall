"""球形（旋转椭球）气球几何：体积、表面积、迎风面积、缝位面积与副气囊（底部隔膜气囊）几何。

椭球绕竖直轴旋转：竖直半轴 a = 直径/2 × 高径比，水平半轴 b = c = 直径/2。
副气囊为底部的空气囊：其体积 = 比例 × 总体积，面积取贴合囊壁的球冠面积。
"""
import math

PI = math.pi


def simpson(func, a, b, n=400):
    """复化辛普森积分（n 取偶数）。"""
    if n % 2:
        n += 1
    h = (b - a) / n
    total = func(a) + func(b)
    for i in range(1, n):
        total += (4 if i % 2 else 2) * func(a + i * h)
    return total * h / 3.0


def bisect_increasing(func, lo, hi, iterations=100):
    """求单调递增函数 func 的零点，要求 func(lo) <= 0 <= func(hi)。"""
    for _ in range(iterations):
        mid = 0.5 * (lo + hi)
        if func(mid) < 0:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


class Sphere:
    def __init__(self, diameter, ratio, divide, sewWidth):
        self.a = diameter / 2 * ratio
        self.b = diameter / 2
        self.c = diameter / 2
        self.divide = divide
        self.sewWidth = sewWidth
        self.ratio = ratio

    def Calculate_volume(self):
        return (4 / 3) * PI * self.a * self.b * self.c

    def Calculate_surface_area(self):
        # Knud Thomsen 公式 p = 1.6075，误差小于 1.061%
        p = 1.6075
        term1 = (self.a * self.b) ** p
        term2 = (self.a * self.c) ** p
        term3 = (self.b * self.c) ** p
        return 4 * PI * ((term1 + term2 + term3) / 3) ** (1 / p)

    def Calculate_windwardArea(self):
        return PI * self.a * self.b

    def meridian_length(self):
        """子午线（极到极）长度：椭圆半周长，Ramanujan 近似。"""
        a, b = self.a, self.b
        return PI * (3 * (a + b) - math.sqrt((3 * a + b) * (a + 3 * b))) / 2

    def Calculate_sewArea(self):
        return self.meridian_length() * self.divide * self.sewWidth * 0.001

    # ---- 副气囊 ----
    def _cap_volume(self, h):
        a, b = self.a, self.b
        return PI * b * b * h * h * (3 * a - h) / (3 * a * a)

    def _cap_height(self, volume):
        if volume <= 0:
            return 0.0
        return bisect_increasing(lambda h: self._cap_volume(h) - volume, 0.0, 2 * self.a)

    def _cap_lateral_area(self, h):
        a, b = self.a, self.b

        def element(z):
            return 2 * PI * math.sqrt(max(b * b * (1 - z * z / (a * a)) + b ** 4 * z * z / a ** 4, 0.0))

        return simpson(element, -a, -a + h, 400)

    def _aux_cap(self, total_volume, ratio):
        ratio = min(max(float(ratio), 0.0), 0.999)
        if ratio == 0:
            return 0.0, 0.0
        h = self._cap_height(ratio * total_volume)
        return self._cap_lateral_area(h), h

    def Calculate_AuxiliaryAirbagHeight(self, sphereVolume, auxiliaryAirbagRatio):
        return self._aux_cap(sphereVolume, auxiliaryAirbagRatio)[1]

    def Calculate_AuxiliaryAirbagArea(self, sphereVolume, auxiliaryAirbagRatio):
        return self._aux_cap(sphereVolume, auxiliaryAirbagRatio)[0]

    def auxiliary_geometry(self, ratio):
        """返回 (副气囊面积 m², 球冠高度 m)，副气囊体积 = ratio × 总体积。"""
        return self._aux_cap(self.Calculate_volume(), ratio)
