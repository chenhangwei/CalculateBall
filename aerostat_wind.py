"""风模型：地貌风速剖面、设计风速输入方式、随高度变化的阵风系数、动压。

单位：风速 m/s，高度 m（离地），动压 kPa（= kN/m²）。
参考：GB 50009-2012 第 8 章（风压高度变化系数 μz、阵风系数 βgz、梯度风高度）。
"""
import math

from aerostat_physics import calculate_corrected_air_density

RHO_REF = 1.22583  # 风级表口径：q = v²/16 kgf/m²，对应海平面标准空气密度 kg/m³
G_PEAK = 2.5       # GB 50009 峰值因子 g
FREE_ATMOSPHERE_TURBULENCE = 0.07  # 自由大气湍流强度的工程假设值，需按站点实测校准

# 地貌参数：(μz 系数 c, μz 指数 e, 截断高度, 梯度风高度, 10 m 湍流强度 I10, 湍流指数 α)
TERRAIN_PARAMS = {
    "A": (1.284, 0.24, 5.0, 300.0, 0.12, 0.12),
    "B": (1.000, 0.30, 10.0, 350.0, 0.14, 0.15),
    "C": (0.544, 0.44, 15.0, 450.0, 0.23, 0.22),
    "D": (0.262, 0.60, 30.0, 550.0, 0.39, 0.30),
}
TERRAIN_OPTIONS = [
    "A类（海面/海岛/沙漠）",
    "B类（田野/乡村/丛林）",
    "C类（密集建筑群城市）",
    "D类（密集高层城市）",
    "不修正（风速不随高度变化）",
]
WIND_MODES = [
    "10 m 参考风速（风级表）",
    "目标高度设计风速",
    "自定义风廓线表",
]
MODE_REF10, MODE_TARGET, MODE_TABLE = 0, 1, 2


def _terrain(terrain_text):
    return TERRAIN_PARAMS.get(str(terrain_text)[:1])


def gradient_height(terrain_text):
    params = _terrain(terrain_text)
    return params[3] if params else None


def height_factor(z, terrain_text):
    """风压高度变化系数 μz（参考风压为 B 类地貌离地 10 m 处值）。"""
    params = _terrain(terrain_text)
    if params is None:
        return 1.0
    coeff, exponent, z_min, z_gradient = params[:4]
    z = min(max(float(z), z_min), z_gradient)
    return coeff * (z / 10.0) ** exponent


def speed_shape(z, terrain_text):
    """风速剖面形状 √μz；梯度风高度以上为常数，各地貌在此汇合。"""
    return math.sqrt(height_factor(z, terrain_text))


def turbulence_intensity(z, terrain_text, free_atmosphere=FREE_ATMOSPHERE_TURBULENCE):
    """湍流强度 I(z)：梯度高度以下按 GB 50009，其上在 [zg, 2zg] 内平滑过渡到自由大气值。"""
    params = _terrain(terrain_text)
    if params is None:
        return free_atmosphere
    z_min, z_gradient, i10, alpha = params[2], params[3], params[4], params[5]
    z = max(float(z), z_min)
    if z <= z_gradient:
        return i10 * (z / 10.0) ** (-alpha)
    i_gradient = i10 * (z_gradient / 10.0) ** (-alpha)
    t = min((z - z_gradient) / z_gradient, 1.0)
    smooth = t * t * (3.0 - 2.0 * t)
    return i_gradient + (free_atmosphere - i_gradient) * smooth


def gust_factor(z, terrain_text, free_atmosphere=FREE_ATMOSPHERE_TURBULENCE):
    """阵风系数 β(z) = 1 + 2·g·I(z)（峰值阵风压 / 平均风压）。"""
    return 1.0 + 2.0 * G_PEAK * turbulence_intensity(z, terrain_text, free_atmosphere)


def parse_profile_table(text):
    """解析 "高度:风速, 高度:风速"（也接受换行、分号、中文标点），返回按高度升序的 [(m, m/s)]。"""
    cleaned = (str(text).replace("：", ":").replace("，", ",").replace("；", ",")
               .replace(";", ",").replace("\n", ",").replace("\t", " "))
    points = []
    for item in cleaned.split(","):
        item = item.strip()
        if not item:
            continue
        parts = item.replace(" ", ":").split(":") if ":" not in item else item.split(":")
        parts = [p for p in parts if p.strip()]
        if len(parts) != 2:
            raise ValueError(f"无法解析风廓线条目：{item!r}")
        height, speed = float(parts[0]), float(parts[1])
        if height < 0 or speed < 0:
            raise ValueError("高度与风速不能为负")
        points.append((height, speed))
    if not points:
        raise ValueError("风廓线表为空")
    points.sort()
    heights = [p[0] for p in points]
    if len(set(heights)) != len(heights):
        raise ValueError("风廓线表中存在重复高度")
    return points


class WindProfile:
    """平均风速剖面 V(z)。

    mode 0：speed 为离地 10 m 标准地貌参考风速，V(z) = V10·√μz(z)；
    mode 1：speed 为目标高度处的设计风速，地貌只决定梯度风高度以下的剖面形状；
    mode 2：table 为 [(高度, 风速)]，线性插值；表下方按地貌形状外推，表上方取常数。
    scale 用于整体缩放，便于反算最大允许风速。
    """

    def __init__(self, mode, terrain_text, target_height, speed=0.0, table=None, scale=1.0):
        self.mode = mode
        self.terrain = terrain_text
        self.target_height = float(target_height)
        self.speed_ref = float(speed)
        self.table = list(table) if table else None
        self.scale = float(scale)
        if mode == MODE_TABLE and not self.table:
            raise ValueError("自定义风廓线表为空")

    def speed(self, z):
        z = max(float(z), 0.0)
        if self.mode == MODE_REF10:
            if _terrain(self.terrain) is None:
                value = self.speed_ref
            else:
                value = self.speed_ref * speed_shape(z, self.terrain)
        elif self.mode == MODE_TARGET:
            denominator = speed_shape(self.target_height, self.terrain)
            value = self.speed_ref * speed_shape(z, self.terrain) / denominator if denominator > 0 else self.speed_ref
        else:
            value = self._table_speed(z)
        return value * self.scale

    def _table_speed(self, z):
        table = self.table
        if z <= table[0][0]:
            h0, v0 = table[0]
            shape0 = speed_shape(max(h0, 1e-6), self.terrain)
            return v0 * speed_shape(z, self.terrain) / shape0 if shape0 > 0 else v0
        if z >= table[-1][0]:
            return table[-1][1]
        for (h1, v1), (h2, v2) in zip(table, table[1:]):
            if h1 <= z <= h2:
                return v1 + (v2 - v1) * (z - h1) / (h2 - h1)
        return table[-1][1]

    def scaled(self, factor):
        return WindProfile(self.mode, self.terrain, self.target_height, self.speed_ref, self.table,
                           self.scale * factor)


class WindField:
    """动压 q(z) 与阵风系数 β(z) 的组合：q = ½ρ(z)V(z)²/1000（kPa），ρ 按场地气温递减修正。"""

    def __init__(self, profile, field_altitude, field_temp_c, terrain_text,
                 gust_override=None, free_turbulence=FREE_ATMOSPHERE_TURBULENCE):
        self.profile = profile
        self.field_altitude = float(field_altitude)
        self.field_temp_c = float(field_temp_c)
        self.terrain = terrain_text
        self.gust_override = gust_override
        self.free_turbulence = free_turbulence

    def density(self, z):
        return calculate_corrected_air_density(self.field_altitude + z, self.field_altitude, self.field_temp_c)

    def pressure(self, z):
        return 0.5 * self.density(z) * self.profile.speed(z) ** 2 / 1000.0

    def gust(self, z):
        if self.gust_override is not None:
            return max(float(self.gust_override), 1.0)
        return gust_factor(z, self.terrain, self.free_turbulence)

    def peak_pressure(self, z):
        return self.gust(z) * self.pressure(z)

    def scaled(self, factor):
        return WindField(self.profile.scaled(factor), self.field_altitude, self.field_temp_c, self.terrain,
                         self.gust_override, self.free_turbulence)


BEAUFORT_UPPER = [0.2, 1.5, 3.3, 5.4, 7.9, 10.7, 13.8, 17.1, 20.7, 24.4, 28.4, 32.6, 36.9, 41.4, 46.1, 50.9, 56.0, 61.2]


def beaufort_level(speed_m_s):
    return sum(1 for limit in BEAUFORT_UPPER if speed_m_s > limit)


BEAUFORT_NAMES = ("静风", "软风", "轻风", "微风", "和风", "清劲风", "强风", "疾风", "大风", "烈风", "狂风", "暴风",
                  "飓风", "台风", "强台风", "强台风", "超强台风", "超强台风")
BEAUFORT_DESCRIPTIONS = ("烟直上", "烟能表示风向", "感觉有风、树叶微响", "树叶和细枝摇动不息", "吹起尘土和纸张、小树枝摇动",
                         "有叶的小树摇摆", "大树枝摇动、举伞困难", "全树摇动、迎风步行不便", "折毁树枝、人行前进阻力大",
                         "烟囱和房屋有小损", "拔起树木、摧毁房屋", "陆上少见、破坏力大", "摧毁力极大", "", "", "", "", "")


def beaufort_name(level):
    return BEAUFORT_NAMES[min(max(int(level), 0), len(BEAUFORT_NAMES) - 1)]


def beaufort_text(speed_m_s):
    """如 “5 级（清劲风：有叶的小树摇摆）”。"""
    level = beaufort_level(speed_m_s)
    description = BEAUFORT_DESCRIPTIONS[min(level, len(BEAUFORT_DESCRIPTIONS) - 1)]
    return f"{level} 级（{beaufort_name(level)}" + (f"：{description}" if description else "") + "）"
