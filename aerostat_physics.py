"""系留浮空器物理基础：标准大气、浮力、气体膨胀与压力高度、系留缆绳分段平衡。

单位约定：力 kN、质量 kg、压力 kPa（= kN/m²）、长度 m、温度 ℃。
浮力以“质量当量 kg”给出（calculate_buoyant_lift），用 kg_to_kn() 转为力。
"""
import math

KELVIN = 273.15
LAPSE_RATE = 0.00649  # 对流层温度递减率 ℃/m
G = 9.80665           # 重力加速度 m/s²
KGF_PER_KN = 1000.0 / G


def kg_to_kn(mass_kg):
    """质量（kg）对应的重力 / 浮力（kN）。"""
    return mass_kg * G / 1000.0


def kn_to_kg(force_kn):
    return force_kn * 1000.0 / G


def _to_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------- 大气模型
def calculate_temperature(altitude_m):
    """标准大气温度（℃），NASA Glenn 对流层近似。"""
    h = max(0.0, _to_float(altitude_m))
    return 15.04 - LAPSE_RATE * h if h < 11000.0 else -56.46


def calculate_air_pressure(altitude_m):
    """标准大气压力（kPa）。"""
    h = max(0.0, _to_float(altitude_m))
    if h < 11000.0:
        return 101.29 * ((calculate_temperature(h) + 273.1) / 288.08) ** 5.256
    return 22.65 * math.exp(1.73 - 0.000157 * h)


def calculate_air_density(altitude_m):
    """标准大气密度（kg/m³）。"""
    return calculate_air_pressure(altitude_m) / (0.2869 * (calculate_temperature(altitude_m) + 273.1))


def actual_temperature(abs_altitude_m, field_altitude_m, field_temp_c):
    """以场地实测温度为基准，按递减率推算任意海拔的环境温度（℃）。"""
    return field_temp_c - LAPSE_RATE * (abs_altitude_m - field_altitude_m)


def calculate_corrected_air_density(abs_altitude_m, field_altitude_m, field_temp_c):
    """标准气压 + 实际温度下的空气密度（kg/m³）。"""
    t_k = actual_temperature(abs_altitude_m, field_altitude_m, field_temp_c) + KELVIN
    if t_k <= 0:
        return calculate_air_density(abs_altitude_m)
    return calculate_air_pressure(abs_altitude_m) / (0.2869 * t_k)


# ---------------------------------------------------------------- 浮力
def calculate_buoyant_lift(volume, altitude_m, gas_type, env_temp_c=None, superheat_k=0.0, purity_percent=99.0):
    """毛浮力的质量当量（kg）：lift = V·(ρ_air − ρ_gas_mix)。

    superheat_k：气体温度高出环境温度的数值（日照过热），杂质按同温空气计。
    """
    h = _to_float(altitude_m)
    if volume <= 0:
        return 0.0

    if env_temp_c is not None and env_temp_c + KELVIN > 0:
        t_env_k = env_temp_c + KELVIN
        rho_air = calculate_air_pressure(h) / (0.2869 * t_env_k)
    else:
        t_env_k = calculate_temperature(h) + KELVIN
        rho_air = calculate_air_density(h)

    m_air = 0.028964
    gas_text = str(gas_type) if gas_type is not None else ""
    if "氢" in gas_text:
        m_gas = 0.002016
    elif "热空气" in gas_text or "热气" in gas_text:
        m_gas = m_air
    else:
        m_gas = 0.0040026

    t_gas_k = max(t_env_k + _to_float(superheat_k), 1.0)
    p = min(max(_to_float(purity_percent, 99.0) / 100.0, 0.0), 1.0)

    rho_hot_air = rho_air * (t_env_k / t_gas_k)
    rho_gas_mix = p * rho_hot_air * (m_gas / m_air) + (1.0 - p) * rho_hot_air
    return max(volume * (rho_air - rho_gas_mix), 0.0)


def gas_molar_ratio(gas_type):
    """气体与空气的摩尔质量比 μ = M_gas / M_air。"""
    gas_text = str(gas_type) if gas_type is not None else ""
    m_air = 0.028964
    if "氢" in gas_text:
        return 0.002016 / m_air
    if "热空气" in gas_text or "热气" in gas_text:
        return 1.0
    return 0.0040026 / m_air


def gas_cell_lift(max_volume, gas_volume_fill, purity_fraction, field_altitude_m, fill_temp_c,
                  height_abs_m, air_temp_c, superheat_k, gas_type):
    """质量守恒的气囊升力（主气囊）。

    gas_volume_fill：充装状态（场地气压、充装温度）下的混合气体积（含杂质空气）；purity_fraction：纯度（体积分数）。
    目标高度白天最高气温 air_temp_c、气体过热 superheat_k：气体膨胀超过容积 max_volume 即排出，
    保留质量决定升力；升力按气体与环境同温计算，不计过热增益（偏保守）。
    返回 dict：lift_kg、retained_mass、vented_mass、gas_volume（同温下气体体积）、vented。
    """
    mu = gas_molar_ratio(gas_type)
    p = min(max(purity_fraction, 1e-6), 1.0)
    t_fill_k = fill_temp_c + KELVIN
    t_air_k = air_temp_c + KELVIN
    t_gas_k = t_air_k + superheat_k
    if gas_volume_fill <= 0 or max_volume <= 0 or t_fill_k <= 0 or t_air_k <= 0 or t_gas_k <= 0:
        return {"lift_kg": 0.0, "retained_mass": 0.0, "vented_mass": 0.0, "gas_volume": 0.0, "vented": False}
    mixture = p * mu + 1.0 - p
    rho_air_fill = calculate_air_pressure(field_altitude_m) / (0.2869 * t_fill_k)
    mass_fill = gas_volume_fill * rho_air_fill * mixture
    rho_air_gas = calculate_air_pressure(height_abs_m) / (0.2869 * t_gas_k)
    capacity_mass = max_volume * rho_air_gas * mixture
    retained = min(mass_fill, capacity_mass)
    rho_air_amb = calculate_air_pressure(height_abs_m) / (0.2869 * t_air_k)
    return {
        "lift_kg": max(retained * (1.0 / mixture - 1.0), 0.0),
        "retained_mass": retained,
        "vented_mass": mass_fill - retained,
        "gas_volume": retained / (rho_air_amb * mixture),
        "vented": mass_fill > capacity_mass,
    }

def calculate_altitude_loss(volume, altitude_m, gas_type, env_temp_c=None, superheat_k=0.0, purity_percent=99.0):
    """同一体积由海平面移到场地海拔的毛浮力损失（kg 当量）。"""
    lift0 = calculate_buoyant_lift(volume, 0.0, gas_type, env_temp_c, superheat_k, purity_percent)
    lift_h = calculate_buoyant_lift(volume, altitude_m, gas_type, env_temp_c, superheat_k, purity_percent)
    return max(lift0 - lift_h, 0.0) if lift0 > 0 else 0.0


def gas_expansion_ratio(field_altitude_m, height_m, field_temp_c, temp_diff_c=0.0, superheat_k=0.0, fill_temp_c=None):
    """气体由充装状态升至 height_m 白天最高温（含日照过热）时的体积膨胀比。

    V2/V1 = (P_场地/P_高空)·(T_气体,高空/T_气体,充装)，充装时气体与环境同温；
    fill_temp_c 缺省取场地夜间最低温（场地环境温度 − 昼夜温差/2）。
    """
    t_fill = (field_temp_c - temp_diff_c / 2.0 if fill_temp_c is None else fill_temp_c) + KELVIN
    t_gas = (actual_temperature(field_altitude_m + height_m, field_altitude_m, field_temp_c)
             + temp_diff_c / 2.0 + _to_float(superheat_k) + KELVIN)
    p_field = calculate_air_pressure(field_altitude_m)
    p_height = calculate_air_pressure(field_altitude_m + height_m)
    if t_fill <= 0 or t_gas <= 0 or p_height <= 0:
        return 1.0
    return (p_field / p_height) * (t_gas / t_fill)


def aux_ratio_from_fill(fill, margin=0.05):
    """已知充盈度时的副气囊比例：1 − 充盈度 + 余量（限 0～0.95）。"""
    return min(max(1.0 - fill + max(margin, 0.0), 0.0), 0.95)


def fill_contraction_ratio(field_temp_c, temp_diff_c=0.0, fill_temp_c=None):
    """充装后降到场地夜间最低温时氦气体积 ÷ 充装体积（≤ 1）；夜间充气时为 1。"""
    if fill_temp_c is None:
        return 1.0
    t_cold = field_temp_c - temp_diff_c / 2.0 + KELVIN
    t_fill = fill_temp_c + KELVIN
    if t_cold <= 0 or t_fill <= 0:
        return 1.0
    return min(t_cold / t_fill, 1.0)


def recommend_auxiliary_ratio(field_altitude_m, target_height_m, field_temp_c=20.0, temp_diff_c=0.0, superheat_k=0.0,
                              fill_temp_c=None, leak_ratio=0.0):
    """推荐副气囊比例（0~0.8）：目标高度白天最热时氦气刚好充满容积，夜间最冷时副气囊刚好装满。

    比例 = 1 − 收缩比/膨胀比 + 滞空逸出体积占比；夜间充气时收缩比为 1。
    """
    expansion = gas_expansion_ratio(field_altitude_m, target_height_m, field_temp_c, temp_diff_c, superheat_k, fill_temp_c)
    contraction = fill_contraction_ratio(field_temp_c, temp_diff_c, fill_temp_c)
    return min(max(1.0 - contraction / expansion + max(leak_ratio, 0.0), 0.0), 0.8)


def calculate_pressure_height(field_altitude_m, field_temp_c, temp_diff_c, superheat_k, aux_ratio, max_height_m=20000.0,
                              fill_temp_c=None):
    """压力高度（离地 m）：主气囊气体膨胀至充满全部容积的高度，超过后开始排气。"""
    if aux_ratio <= 0:
        return 0.0
    if aux_ratio >= 1:
        return max_height_m
    target = 1.0 / (1.0 - aux_ratio)

    def expansion(z):
        return gas_expansion_ratio(field_altitude_m, z, field_temp_c, temp_diff_c, superheat_k, fill_temp_c)

    if expansion(max_height_m) < target:
        return max_height_m
    lo, hi = 0.0, max_height_m
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if expansion(mid) < target:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


# ---------------------------------------------------------------- 系留缆绳
def solve_tether_equilibrium(base_net_buoyancy, body_drag, wind_pressure_at, cable_diameter_m,
                             cable_unit_weight, target_height, cable_drag_coeff=1.2, segments=400):
    """分段积分求解系留缆绳平衡（力、压力、线重须量纲一致，如 kN、kPa、kN/m）。

    从浮空器连接点向下沿缆长积分，每段计入自重与横流风阻：
        dTx/ds = q(z)·Cd·d·sin³φ
        dTz/ds = -w - q(z)·Cd·d·sin²φ·cosφ
    φ 为缆绳局部与地面夹角，q(z) 为离地高度 z 处的风压（常数或函数）。
    """
    q_at = wind_pressure_at if callable(wind_pressure_at) else (lambda z: wind_pressure_at)
    cdd = cable_drag_coeff * cable_diameter_m
    w = cable_unit_weight

    result = {
        "flyable": False,
        "angle_deg": 0.0,
        "top_angle_deg": math.degrees(math.atan2(base_net_buoyancy, body_drag)),
        "cable_length": target_height,
        "cable_weight": w * target_height,
        "cable_drag_h": 0.0,
        "cable_drag_v": 0.0,
        "horizontal": body_drag,
        "net_buoyancy": base_net_buoyancy - w * target_height,
        "tension": math.hypot(body_drag, base_net_buoyancy),
        "anchor_tension": 0.0,
        "drift": 0.0,
    }
    if base_net_buoyancy <= 0 or target_height <= 0:
        return result

    def deriv(tx, tz, z):
        phi = math.atan2(tz, tx)
        s, c = math.sin(phi), math.cos(phi)
        f = q_at(max(z, 0.0)) * cdd * s * s
        # dTx, dTz, dz, dx, 水平风阻, 向下风阻（均为每米缆长）
        return f * s, -w - f * c, -s, c, f * s, f * c

    tx, tz, z = body_drag, base_net_buoyancy, target_height
    length = drift = drag_h = drag_v = 0.0
    ds = target_height / segments
    path = [(0.0, target_height)]   # (距浮空器的水平距离, 离地高度)，供示意图使用
    keep_every = max(segments // 60, 1)
    steps = 0
    max_length = 50.0 * target_height

    while z > 1e-9:
        if tz <= 0 or length > max_length:
            result.update({"cable_length": length, "cable_weight": w * length, "net_buoyancy": tz})
            return result
        h = ds
        for _ in range(2):
            k1 = deriv(tx, tz, z)
            k2 = deriv(tx + 0.5 * h * k1[0], tz + 0.5 * h * k1[1], z + 0.5 * h * k1[2])
            if z + h * k2[2] >= 0:
                break
            h = z / -k2[2]
        tx += h * k2[0]
        tz += h * k2[1]
        z = max(z + h * k2[2], 0.0)
        drift += h * k2[3]
        drag_h += h * k2[4]
        drag_v += h * k2[5]
        length += h
        steps += 1
        if steps % keep_every == 0 or z <= 1e-9:
            path.append((drift, z))

    if tz <= 0:
        result.update({"cable_length": length, "cable_weight": w * length, "net_buoyancy": tz})
        return result

    result.update({
        "flyable": True,
        "angle_deg": math.degrees(math.atan2(tz, tx)),
        "cable_length": length,
        "cable_weight": w * length,
        "cable_drag_h": drag_h,
        "cable_drag_v": drag_v,
        "horizontal": tx,
        "net_buoyancy": tz,
        "anchor_tension": math.hypot(tx, tz),
        "drift": drift,
        "path": path,
    })
    return result
