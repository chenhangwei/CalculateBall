"""尾翼与气动模型（与界面无关，纯 Python）。

飞艇艇身 + 尾翼在攻角 α 下的法向力、升力与附加阻力，以及尾翼的几何、摩擦阻力和稳定性力矩比。

方法（均为经典工程关系，适用小到中等攻角、低速不可压）：
- 尾翼升力线斜率：低展弦比机翼 Helmbold 公式 CLα = 2π·AR /(2 + √(4 + AR²))；尾翼根部贴艇身，按镜像面取有效展弦比 2·AR，
  再乘翼身干扰系数（充气尾翼变形取 0.9）。十字/X 形布置时对攻角有效的面积为总平面面积的一半（Σcos² = n/2）。
- 尾翼型阻：2·Cf(Re_c)·(1 + 2t/c + 60(t/c)⁴)（Hoerner，参考平面面积）并计 10% 翼身干扰。
- 艇身法向力：Allen–Perkins 横流法 N = η·Cdc·A_plan·sin²α（封闭艇身的势流升力为零，升力来自分离横流与尾翼）。
- 机体轴力分解：升力 = N·cosα − A₀·sinα，阻力增量 = A₀·(cosα − 1) + N·sinα（A₀ 为零攻角轴向阻力，面积量纲）。
- Munk 失稳力矩：M = 2(k₂ − k₁)·q·V·sinα·cosα（k₁、k₂ 为长椭球附加质量系数，Lamb）。

以上结果为设计估算；风洞或飞行试验数据始终优先，手动输入 CLα、K、尾翼阻力系数会覆盖本模型。
"""
import math

from aerostat_drag import flat_plate_cf, reynolds

CROSSFLOW_ETA = 0.68        # Allen–Perkins 横流修正，长径比 4～6 取 0.6～0.7
CROSSFLOW_CD = 1.2          # 圆柱横流阻力系数（亚临界～临界，取偏大）
FIN_INTERFERENCE = 0.9      # 翼身干扰与充气翼变形折减
FIN_STALL_RAD = math.radians(15.0)
FIN_FRICTION_INTERFERENCE = 0.10
SECTION_AREA_COEFF = 0.685  # 对称翼型截面积 ≈ 0.685·t·c（NACA 00xx）；充气尾翼形状不同，仅作量级校核


def munk_factors(fineness):
    """长椭球附加质量系数 (k1 轴向, k2 横向)。"""
    fineness = max(fineness, 1.05)
    e = math.sqrt(1.0 - 1.0 / (fineness * fineness))
    ln_term = math.log((1.0 + e) / (1.0 - e))
    alpha0 = 2.0 * (1.0 - e * e) / e ** 3 * (0.5 * ln_term - e)
    beta0 = 1.0 / (e * e) - (1.0 - e * e) / (2.0 * e ** 3) * ln_term
    return alpha0 / (2.0 - alpha0), beta0 / (2.0 - beta0)


def fin_lift_slope(aspect_ratio, reflection=True):
    """单片尾翼升力线斜率（1/rad，参考单片平面面积）。"""
    ar = max(aspect_ratio, 0.05) * (2.0 if reflection else 1.0)
    return 2.0 * math.pi * ar / (2.0 + math.sqrt(4.0 + ar * ar))


def fin_profile_cd(re_chord, thickness_ratio):
    """尾翼零攻角型阻系数（参考平面面积，含 10% 干扰）。"""
    tc = max(thickness_ratio, 0.0)
    return 2.0 * flat_plate_cf(re_chord) * (1.0 + 2.0 * tc + 60.0 * tc ** 4) * (1.0 + FIN_FRICTION_INTERFERENCE)


def design_tail(volume, length, diameter, hull_surface, tail_wetted_area, fin_count, aspect_ratio, thickness_ratio,
                speed, density, temp_c, hull_axial_area, aoa_deg, manual_tail_cd=None):
    """尾翼几何、阻力、升力与稳定性。

    hull_axial_area：艇身零攻角阻力面积（CD·A_f，m²）。返回 dict，面积量纲均为 m²（力 = q × 面积）。
    """
    fin_count = max(int(fin_count), 1)
    planform = max(tail_wetted_area, 0.0) / 2.0
    per_fin = planform / fin_count
    span = math.sqrt(max(aspect_ratio, 0.05) * per_fin) if per_fin > 0 else 0.0
    chord = per_fin / span if span > 0 else 0.0
    re_chord = reynolds(speed, chord, density, temp_c) if chord > 0 else 0.0
    cd_auto = fin_profile_cd(re_chord, thickness_ratio) if re_chord > 0 else 0.0
    cd_tail = cd_auto if manual_tail_cd is None else manual_tail_cd
    profile_area = cd_tail * planform

    cl_fin = fin_lift_slope(aspect_ratio) * FIN_INTERFERENCE
    effective_area = 0.5 * planform
    alpha = math.radians(max(aoa_deg, 0.0))
    fin_normal = cl_fin * effective_area * min(alpha, FIN_STALL_RAD)
    hull_plan = math.pi / 4.0 * length * diameter
    hull_normal = CROSSFLOW_ETA * CROSSFLOW_CD * hull_plan * math.sin(alpha) ** 2
    normal = fin_normal + hull_normal
    axial = hull_axial_area + profile_area
    lift_area = normal * math.cos(alpha) - axial * math.sin(alpha)
    drag_extra = axial * (math.cos(alpha) - 1.0) + normal * math.sin(alpha)

    volume_geo = planform * SECTION_AREA_COEFF * thickness_ratio * chord
    ref = volume ** (2.0 / 3.0) if volume > 0 else 0.0
    if alpha > 1e-9 and ref > 0:
        cl_alpha_eq = lift_area / (alpha * ref)
    else:
        cl_alpha_eq = cl_fin * effective_area / ref if ref > 0 else 0.0

    k1, k2 = munk_factors(length / diameter if diameter > 0 else 4.0)
    lever = max(0.5 * length - 0.75 * chord, 0.1 * length)
    fin_moment = cl_fin * effective_area * lever
    munk_moment = 2.0 * (k2 - k1) * volume
    return {
        "planform": planform, "fin_count": fin_count, "span": span, "chord": chord, "re_chord": re_chord,
        "cd_tail_auto": cd_auto, "cd_tail": cd_tail, "profile_area": profile_area,
        "cl_fin": cl_fin, "effective_area": effective_area,
        "fin_normal_area": fin_normal, "hull_normal_area": hull_normal, "normal_area": normal,
        "lift_area": lift_area, "drag_extra_area": drag_extra,
        "area_ratio": planform / ref if ref > 0 else 0.0, "cl_alpha_eq": cl_alpha_eq,
        "volume_geo": volume_geo,
        "k1": k1, "k2": k2, "lever": lever, "moment_ratio": fin_moment / munk_moment if munk_moment > 0 else 0.0,
        "span_to_diameter": span / diameter if diameter > 0 else 0.0,
    }
