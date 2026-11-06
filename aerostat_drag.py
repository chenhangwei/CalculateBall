"""风阻系数选型模型（与界面无关，纯 Python）。

球体：以大型系留气球的工程基准 CD = 0.47（Hoerner 亚临界圆球值，与 0.45～0.5 的经验范围一致）为底，
      叠加附件/吊带/接缝与欠压变形增量。光滑圆球在雷诺数 3×10⁵ 附近的“阻力危机”降阻（CD 可降到 0.1～0.25）
      对表面粗糙度、来流湍流、囊体变形都极敏感，系留气球不计入该降阻。
飞艇：Hoerner 回转体阻力公式  CD,f = Cf·[1 + 1.5(d/l)^1.5 + 7(d/l)^3]·S_wet/A_f（以最大截面积 A_f 为参考），
      Cf 取全湍流平板摩擦系数（Schlichting），并按表面等效粗糙度修正；再叠加附件与欠压变形增量。
      尾翼阻力与攻角诱导阻力由主程序另行计入，本模块给出的是零攻角艇身阻力系数。

经验公式的适用范围与不确定度见各函数说明；风洞或飞行试验数据始终优先。
"""
import math
from dataclasses import dataclass, field

KELVIN = 273.15

# ------------------------------------------------------------------ 常量（可由界面调整的默认值）
SPHERE_BASE_CD = 0.47            # 圆球亚临界/工程基准
SPHERE_DESIGN_BAND = (0.45, 0.50)  # 使用者给出的经验范围，作为选型结果的核对带
SPHERE_DENT_MAX = 0.15           # 欠压（内压 < 动压）时 CD 的最大增量（工程假设）
HULL_DENT_FRACTION = 0.30        # 欠压时艇身 CD 的最大相对增量（工程假设）
FITTING_DEFAULT = {"sphere": 0.02, "airship": 0.01}
ROUGHNESS_PRESETS_MM = (
    ("TPU 焊接，表面光滑", 0.05),
    ("TPU 焊接，接缝带/瓣缝明显", 0.3),
    ("TPU 有轻微皱褶/松弛", 1.0),
    ("PVC/涂层布缝制", 0.5),
)


# ------------------------------------------------------------------ 空气性质与雷诺数
def air_viscosity(temp_c):
    """空气动力黏度 Pa·s（Sutherland 公式）。"""
    t = max(temp_c + KELVIN, 1.0)
    return 1.458e-6 * t ** 1.5 / (t + 110.4)


def reynolds(speed, length, density, temp_c):
    return density * max(speed, 0.0) * length / air_viscosity(temp_c)


# ------------------------------------------------------------------ 圆球
def sphere_cd_smooth(re):
    """光滑圆球阻力系数随雷诺数变化（Morrison 2013 相关式，适用 Re ≤ 10⁶，含阻力危机）。"""
    if re <= 0:
        return float("inf")
    return (24.0 / re
            + 2.6 * (re / 5.0) / (1.0 + (re / 5.0) ** 1.52)
            + 0.411 * (re / 2.63e5) ** -7.94 / (1.0 + (re / 2.63e5) ** -8.0)
            + 0.25 * (re / 1e6) / (1.0 + re / 1e6))


def sphere_regime(re):
    if re < 2e5:
        return "亚临界（层流边界层，CD 约 0.4～0.5）"
    if re < 5e5:
        return "临界（阻力危机区，CD 对粗糙度/湍流极敏感）"
    return "超临界/跨临界（光滑球 CD 约 0.1～0.3，但受湍流、接缝、变形影响大）"


@dataclass
class Component:
    name: str
    value: float
    basis: str


@dataclass
class DragResult:
    kind: str
    cd: float
    low: float
    high: float
    reynolds: float
    regime: str
    components: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    extra: dict = field(default_factory=dict)


def _dent_ratio(overpressure_pa, dynamic_pressure_pa):
    """囊内超压与来流动压之比；超压未知（自动）视为足够，返回 None。"""
    if overpressure_pa is None or dynamic_pressure_pa is None or dynamic_pressure_pa <= 0:
        return None
    return overpressure_pa / dynamic_pressure_pa


def sphere_design(diameter, speed, density, temp_c, fitting_delta=None, overpressure_pa=None, dynamic_pressure_pa=None):
    """圆球设计阻力系数（参考面积：迎风投影面积）。"""
    re = reynolds(speed, diameter, density, temp_c)
    fitting = FITTING_DEFAULT["sphere"] if fitting_delta is None else max(fitting_delta, 0.0)
    ratio = _dent_ratio(overpressure_pa, dynamic_pressure_pa)
    dent = 0.0 if ratio is None or ratio >= 1.0 else SPHERE_DENT_MAX * (1.0 - max(ratio, 0.0))
    comps = [
        Component("圆球基准", SPHERE_BASE_CD, "Hoerner《Fluid-Dynamic Drag》圆球亚临界值 0.47；大型系留气球经验 0.45～0.5"),
        Component("附件/吊带/接缝", fitting, "拉点、吊带、充气口、阀门、接缝带等的附加阻力（输入）"),
        Component("欠压变形", dent, "内压低于来流动压时迎风面凹陷、尾流变宽；增量 = 0.15 × (1 − 内压/动压)（工程假设）"),
    ]
    cd = sum(c.value for c in comps)
    notes = []
    smooth = sphere_cd_smooth(re) if re <= 1e6 else None
    if re >= 2e5:
        notes.append("雷诺数已进入阻力危机或其后，光滑圆球的理论 CD 会降到 0.1～0.3；"
                     "该降阻对表面粗糙度（TPU 焊缝、皱褶）、大气湍流（10～25%）和囊体变形极敏感，不可靠，故不计入。")
    if ratio is not None and ratio < 1.0:
        notes.append(f"内压仅为来流动压的 {ratio:.2f} 倍，迎风面会凹陷，风阻增大；建议提高内部恒定压强。")
    return DragResult("sphere", cd, SPHERE_BASE_CD - 0.07 + fitting, SPHERE_BASE_CD + 0.08 + fitting + dent, re,
                      sphere_regime(re), comps, notes, {"smooth_cd": smooth, "fitting": fitting, "dent": dent,
                                                        "pressure_ratio": ratio})


# ------------------------------------------------------------------ 平板摩擦与艇身
def flat_plate_cf(re):
    """全湍流光滑平板摩擦系数（Prandtl–Schlichting，Re 10⁵～10⁹）。"""
    re = max(re, 1e5)
    return 0.455 / math.log10(re) ** 2.58


def rough_plate_cf(length, ks):
    """完全粗糙平板摩擦系数（Schlichting），ks 为等效沙粒粗糙度（m）。"""
    if ks <= 0 or length <= 0:
        return 0.0
    return (1.89 + 1.62 * math.log10(length / ks)) ** -2.5


def hull_form_factor(fineness):
    """Hoerner 回转体形状因子（摩擦 + 压差）：1 + 1.5(d/l)^1.5 + 7(d/l)^3。"""
    ratio = 1.0 / max(fineness, 1.0)
    return 1.0 + 1.5 * ratio ** 1.5 + 7.0 * ratio ** 3


def prolate_spheroid_surface(length, diameter):
    """长椭球表面积（长轴 = 总长，短轴 = 最大直径）。"""
    a, b = length / 2.0, diameter / 2.0
    if abs(a - b) < 1e-12:
        return 4.0 * math.pi * b * b
    if a < b:  # 扁椭球
        e = math.sqrt(1.0 - (a * a) / (b * b))
        return 2.0 * math.pi * b * b * (1.0 + (1.0 - e * e) / e * math.atanh(e))
    e = math.sqrt(1.0 - (b * b) / (a * a))
    return 2.0 * math.pi * b * b * (1.0 + a / (b * e) * math.asin(e))


def airship_design(length, diameter, surface_area, volume, speed, density, temp_c, ks_mm=0.3, fitting_delta=None,
                   overpressure_pa=None, dynamic_pressure_pa=None):
    """艇身零攻角阻力系数（参考面积：最大截面积 π·d²/4）。"""
    frontal = math.pi * diameter * diameter / 4.0
    fineness = length / diameter
    re = reynolds(speed, length, density, temp_c)
    cf_smooth = flat_plate_cf(re)
    cf_rough = rough_plate_cf(length, max(ks_mm, 0.0) / 1000.0)
    cf = max(cf_smooth, cf_rough)
    ff = hull_form_factor(fineness)
    wet = surface_area / frontal
    friction = cf_smooth * wet
    form = cf_smooth * (ff - 1.0) * wet
    rough = (cf - cf_smooth) * ff * wet
    fitting = FITTING_DEFAULT["airship"] if fitting_delta is None else max(fitting_delta, 0.0)
    clean = friction + form + rough
    ratio = _dent_ratio(overpressure_pa, dynamic_pressure_pa)
    dent = 0.0 if ratio is None or ratio >= 1.0 else HULL_DENT_FRACTION * clean * (1.0 - max(ratio, 0.0))
    comps = [
        Component("摩擦阻力", friction, f"全湍流平板 Cf = 0.455/(lg Re)^2.58 = {cf_smooth:.5f}（Re = {re:.2e}），× 湿面积/最大截面积 {wet:.1f}"),
        Component("形状（压差）阻力", form, f"Hoerner 形状因子 1 + 1.5(d/l)^1.5 + 7(d/l)^3 = {ff:.3f}（长径比 {fineness:.2f}）"),
        Component("表面粗糙度", rough, f"等效粗糙度 ks = {ks_mm:g} mm，Schlichting 完全粗糙 Cf = {cf_rough:.5f}，取与光滑值较大者"),
        Component("附件/吊带/接缝", fitting, "拉点、吊带、充气口、阀门等附加阻力（输入）"),
        Component("欠压变形", dent, "内压低于来流动压时艇身变形、阻力增大；增量 = 0.3 × 艇身阻力 × (1 − 内压/动压)（工程假设）"),
    ]
    cd = sum(c.value for c in comps)
    notes = []
    if fineness < 2.0 or fineness > 10.0:
        notes.append(f"长径比 {fineness:.2f} 超出 Hoerner 公式常用范围 2～10，结果仅供参考。")
    if ratio is not None and ratio < 1.0:
        notes.append(f"内压仅为来流动压的 {ratio:.2f} 倍，艇身会变形，阻力增大。")
    ref_v = volume ** (2.0 / 3.0) if volume > 0 else 0.0
    cd_v = cd * frontal / ref_v if ref_v > 0 else 0.0
    return DragResult("airship", cd, 0.75 * clean + fitting, 1.25 * clean + fitting + dent, re,
                      "全湍流（大型柔性艇身，不计层流段减阻）", comps, notes,
                      {"fineness": fineness, "cd_volume": cd_v, "cf": cf, "cf_smooth": cf_smooth, "cf_rough": cf_rough,
                       "form_factor": ff, "wet_ratio": wet, "frontal": frontal, "pressure_ratio": ratio})


# ------------------------------------------------------------------ 曲线数据（供界面作图）
def sphere_curve(points=80, re_min=1e2, re_max=1e6):
    step = (math.log10(re_max) - math.log10(re_min)) / (points - 1)
    return [(10 ** (math.log10(re_min) + i * step), sphere_cd_smooth(10 ** (math.log10(re_min) + i * step)))
            for i in range(points)]


def airship_fineness_sweep(volume, speed, density, temp_c, ks_mm=0.3, fineness_values=None):
    """等体积下艇身阻力系数随长径比的变化：[(λ, CD_front, CD_V)]；CD_V 的参考面积为 V^(2/3)，反映同体积下的实际阻力。"""
    values = fineness_values or [1.5 + 0.25 * i for i in range(35)]
    out = []
    for lam in values:
        diameter = (6.0 * volume / (math.pi * lam)) ** (1.0 / 3.0)
        length = lam * diameter
        surface = prolate_spheroid_surface(length, diameter)
        result = airship_design(length, diameter, surface, volume, speed, density, temp_c, ks_mm, fitting_delta=0.0)
        out.append((lam, result.cd, result.extra["cd_volume"]))
    return out
