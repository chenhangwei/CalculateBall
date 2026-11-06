"""系留浮空器设计分析流水线（与界面无关）：浮力 → 风 → 系留平衡 → 强度校核 → 最大允许风速。

单位：力 kN、质量 kg、压力 kPa、长度 m。
最不利组合：升力取白天最高气温（含日照过热）、风压取夜间最低气温（空气密度最大）。
"""
import math
from dataclasses import dataclass
from typing import Callable, Optional

from aerostat_physics import (
    KELVIN, actual_temperature, calculate_air_pressure, calculate_altitude_loss, calculate_buoyant_lift,
    calculate_pressure_height, fill_contraction_ratio, gas_cell_lift, gas_expansion_ratio, gas_molar_ratio, kg_to_kn,
    kn_to_kg, solve_tether_equilibrium,
)
from aerostat_wind import WindField, WindProfile

BOTTOM_ANGLE_WARNING_DEG = 5.0   # 底部悬链角低于此值仅提示，不判不合格
MAX_SEARCH_SPEED = 70.0          # 最大允许风速搜索上限（目标高度处，m/s）
FILM_N_PER_5CM_TO_KN_PER_M = 20.0 / 1000.0


@dataclass
class CableSpec:
    diameter_m: float = 0.005
    unit_weight_kg_m: float = 0.026
    drag_coeff: float = 1.2
    breaking_force_kn: float = 0.0   # 新缆最小破断力
    strength_factor: float = 0.8     # 接头效率 × 老化/蠕变折减


@dataclass
class Requirements:
    cable_sf: float = 5.0
    film_sf: float = 4.0
    survival_sf: float = 2.5
    min_angle_deg: float = 0.0       # 0 表示只要求缆绳不拖地
    overpressure_k: float = 1.2      # 运行超压 ≥ k × 阵风动压


@dataclass
class DesignInputs:
    # 几何与质量
    shape: str                       # "sphere" | "airship"
    volume: float
    surface_area: float
    max_radius: float
    aux_geometry: Callable[[float], tuple]
    aux_unit_weight: float
    fixed_mass: float                # 除副气囊、缆绳外的全部质量（kg）
    drag_area: float = 0.0           # Σ(CD·S)，m²，不含诱导阻力的另计项由调用方累加
    lift_area: float = 0.0           # Σ(CL·S)，m²
    # 场地与环境
    altitude: float = 0.0
    target_height: float = 100.0
    field_temp_c: float = 20.0
    temp_diff_c: float = 0.0
    # 气体
    gas_type: str = "氦气"
    purity: float = 99.0
    superheat_k: float = 0.0
    aux_ratio: float = 0.2
    fill_fraction: Optional[float] = None      # 气体充盈度（占总容积）；None = 夜间最冷时副气囊刚好装满
    fill_end_target: Optional[float] = None    # 滞空末期充盈度（地面）；给定时反推初始充盈度 = 末期 + 逸出
    fill_temp_c: Optional[float] = None        # 充气时气温；None = 夜间最低温
    climb_speed: float = 1.0                   # 升降速度 m/s，用于副气囊换气流量
    leakage_rate: float = 0.0        # m³/(m²·天)
    stay_days: float = 0.0
    purity_decay_per_day: float = 0.0  # 百分点/天
    # 风
    work_wind: Optional[WindProfile] = None
    survival_wind: Optional[WindProfile] = None
    terrain: str = "B"
    gust_override: Optional[float] = None
    free_turbulence: float = 0.07
    # 缆绳与要求
    cable: CableSpec = None
    requirements: Requirements = None
    # 膜材与拉点
    film_strength_n5cm: float = 0.0  # 经纬向较小者，N/5cm
    seam_efficiency: float = 0.7
    overpressure_kpa: Optional[float] = None   # None：自动取 k × 工作阵风动压
    pull_points: int = 0
    bridle_half_angle_deg: float = 30.0
    load_nonuniformity: float = 1.5
    pull_point_rating_kn: float = 0.0
    membrane_shapes: Optional[list] = None     # 回转椭球分段 [(赤道半径, 极半轴)]；None 时按 max_radius 的球/圆柱近似


def hull_aero_areas(volume, aoa_deg, cl_alpha, induced_k):
    """艇身随攻角的气动面积：返回 (升力面积 CL·V^(2/3), 诱导阻力面积 K·CL²·V^(2/3))。"""
    reference = volume ** (2.0 / 3.0)
    cl = cl_alpha * math.radians(aoa_deg)
    return cl * reference, induced_k * cl * cl * reference


def _clamp(value, low, high):
    return min(max(value, low), high)


def _gas_state(inp):
    """气体侧：副气囊、初始/末期升力、压力高度。升力取白天最高温（最不利）。

    囊体总容积不变，氦气质量不变：氦气体积随气压降低、温度升高而膨胀，挤出副气囊内的空气（经安全阀排出）；
    氦气收缩（下降、降温、逸出）时由风机向副气囊补气，保持内压和外形。副气囊空气量 = 总容积 − 氦气体积。
    """
    volume = inp.volume
    z_abs = inp.altitude + inp.target_height
    t_hot = actual_temperature(z_abs, inp.altitude, inp.field_temp_c) + inp.temp_diff_c / 2.0
    r_fill = _clamp(inp.aux_ratio, 0.0, 0.95)
    leak = inp.surface_area * max(inp.leakage_rate, 0.0) * max(inp.stay_days, 0.0)
    t_cold = inp.field_temp_c - inp.temp_diff_c / 2.0
    t_fill = t_cold if inp.fill_temp_c is None else inp.fill_temp_c
    x_min = fill_contraction_ratio(inp.field_temp_c, inp.temp_diff_c, inp.fill_temp_c)
    leak_ratio = leak / volume if volume > 0 else 0.0
    expansion = gas_expansion_ratio(inp.altitude, inp.target_height, inp.field_temp_c, inp.temp_diff_c, inp.superheat_k,
                                    inp.fill_temp_c)
    notes = []
    if leak > 0 and inp.purity_decay_per_day > 0 and inp.stay_days > 0:
        notes.append("氦气逃逸率与纯度衰减同时填写，二者叠加计入末期浮力损失，可能重复；"
                     "已按透氦率填了逃逸率时纯度衰减应填 0，有实测纯度记录时才填实测值")
    if inp.fill_end_target is not None:
        wanted = _clamp(inp.fill_end_target, 0.01, 1.0) + leak_ratio
        fill = _clamp(wanted, 0.01, 1.0)
        if wanted > 1.0 + 1e-9:
            notes.append(f"末期充盈度 {inp.fill_end_target:g} 加逸出 {leak_ratio:.3f} 超过满充，初始充盈度已限为 1，实际末期仅 {fill - leak_ratio:.3f}")
        if inp.fill_fraction is not None:
            notes.append("已按末期充盈度反推初始充盈度，忽略所填初始充盈度")
    elif inp.fill_fraction is None:
        # 默认：目标高度白天最热时氦气刚好充满囊体（最大浮力，且不超容）
        fill = _clamp(1.0 / expansion, 0.01, 1.0)
    else:
        fill = _clamp(inp.fill_fraction, 0.01, 1.0)
    r_free = 1.0 - fill
    v0 = volume * fill
    # 氦气只会逸出，不会被排出：目标高度白天最热时氦气体积超过囊体容积即为设计不可行
    fill_target_raw = fill * expansion
    alarms = []
    if fill_target_raw > 1.0 + 1e-9:
        alarms.append(f"氦气充盈度大于 1：目标高度白天最热时氦气体积将达囊体容积的 {fill_target_raw:.3f} 倍，囊体无法容纳"
                      f"（充盈度需 ≤ {1.0 / expansion:.3f}，或降低目标高度、减小昼夜温差与日照过热）")

    def lift_kg(gas_volume_fill, purity):
        cell = gas_cell_lift(volume, gas_volume_fill, purity / 100.0, inp.altitude, t_fill,
                             z_abs, t_hot, inp.superheat_k, inp.gas_type)
        return cell["lift_kg"], cell

    lift_start, cell_start = lift_kg(v0, inp.purity)
    # 首个高温日超容排出的氦气不会再回来，之后只有逸出
    total_mass = cell_start["retained_mass"] + cell_start["vented_mass"]
    v_effective = v0 * cell_start["retained_mass"] / total_mass if total_mass > 0 else 0.0
    purity_end = max(inp.purity - max(inp.purity_decay_per_day, 0.0) * max(inp.stay_days, 0.0), 0.0)
    lift_end, cell_end = lift_kg(max(v_effective - leak, 0.0), purity_end)
    governing = lift_end if inp.stay_days > 0 else lift_start
    cell_gov = cell_end if inp.stay_days > 0 else cell_start

    # 毛浮力逐项分解（kg）：场地总浮升力 + 各项变化 = 设计毛浮力。氦气浮力只取决于氦气质量，高度、气温只通过排气影响它
    field_total = calculate_buoyant_lift(volume, inp.altitude, inp.gas_type, inp.field_temp_c, 0.0, inp.purity)
    purity_fraction = _clamp(inp.purity / 100.0, 1e-6, 1.0)
    mixture = purity_fraction * gas_molar_ratio(inp.gas_type) + 1.0 - purity_fraction
    lift_filled = (cell_start["retained_mass"] + cell_start["vented_mass"]) * (1.0 / mixture - 1.0)
    lift_steps = [("fill", "未充满容积", fill * field_total - field_total),
                  ("fill_temp", "充装温度", lift_filled - fill * field_total),
                  ("vent", "高温膨胀排气", lift_start - lift_filled)]
    if inp.stay_days > 0:
        lift_leak, _ = lift_kg(max(v_effective - leak, 0.0), inp.purity)
        lift_steps += [("leak", "氦气逸出", lift_leak - lift_start), ("purity", "纯度衰减", lift_end - lift_leak)]

    # 副气囊容积严格取用户输入的比例；滞空末期、夜间最冷时需容纳氦气收缩、排氦与逸出让出的体积
    r_cap = _clamp(r_fill, 0.0, 0.95) if volume > 0 else 0.0
    r_required = 1.0 - (v_effective / volume if volume > 0 else 0.0) * x_min + leak_ratio
    if r_fill < r_free - 1e-9:
        alarms.append(f"副气囊比例 {r_fill:.3f} 必须大于（1 − 充盈度）= {r_free:.3f}：副气囊装不下充装时的空余体积"
                      "（请增大副气囊比例或提高充盈度）")
    if r_required > r_cap + 1e-9:
        notes.append(f"副气囊容积不足：滞空末期夜间需容纳总容积的 {r_required:.3f}，当前 {r_cap:.3f}，"
                     "囊体将失去饱满度，请增大副气囊比例或减少逸出")

    aux_area, aux_height = inp.aux_geometry(r_cap)

    # 各工况下氦气与副气囊空气的体积：总容积不变，氦气体积随气压、气温变化，空气 = 总容积 − 氦气
    p_field, p_target = calculate_air_pressure(inp.altitude), calculate_air_pressure(z_abs)
    t_fill_k = t_fill + KELVIN
    t_target_cold_k = actual_temperature(z_abs, inp.altitude, inp.field_temp_c) - inp.temp_diff_c / 2.0 + KELVIN
    v_left = max(v_effective - leak, 0.0)
    capacity = r_cap * volume

    def volume_state(key, label, helium):
        helium = _clamp(helium, 0.0, volume)
        return {"key": key, "label": label, "helium": helium, "air": volume - helium,
                "fill": helium / volume if volume > 0 else 0.0, "fits": volume - helium <= capacity + 1e-9}

    after = "（滞空末期）" if inp.stay_days > 0 else ""
    volume_states = [volume_state("fill", "充装（场地）", v0),
                     volume_state("hot", "目标高度·白天最热", v0 * expansion),
                     volume_state("cold", "目标高度·夜间最冷", v_effective * p_field / p_target * t_target_cold_k / t_fill_k),
                     volume_state("night", "地面·夜间最冷" + after, v_effective * x_min - leak)]
    if inp.stay_days > 0:
        volume_states.append(volume_state("hot_end", "目标高度·白天最热（滞空末期）", v_left * expansion))
    fill_target = min(fill_target_raw, 1.0)
    air_cold = (1.0 - fill * x_min) * volume
    air_target = (1.0 - fill_target) * volume
    exchange = max(air_cold - air_target, 0.0)
    climb_time_min = inp.target_height / inp.climb_speed / 60.0 if inp.climb_speed > 0 and inp.target_height > 0 else 0.0
    fill_end = max(v_effective / volume - leak_ratio, 0.0) if volume > 0 else 0.0
    return {
        "fill_end": fill_end,
        "alarms": alarms,
        "fill_target_raw": fill_target_raw,
        "fill_target_end_raw": fill_end * expansion,
        "fill_target_end": min(fill_end * expansion, 1.0),
        "fill_recommended": min(1.0 / expansion, 1.0) if expansion > 0 else 1.0,
        "aux_air_cold": max(r_required, 0.0) * volume,
        "aux_flow_m3_min": exchange / climb_time_min if climb_time_min > 0 else 0.0,
        "fill_target": fill_target,
        "aux_air_target": air_target,
        "aux_exchange": exchange,
        "t_target_hot_c": t_hot,
        "aux_ratio_fill": r_fill,
        "fill_fraction": fill,
        "warnings": notes,
        "aux_ratio_capacity": r_cap,
        "aux_volume": r_cap * volume,
        "aux_area": aux_area,
        "aux_height": aux_height,
        "aux_mass": aux_area * inp.aux_unit_weight,
        "initial_gas_volume": v0,
        "expansion_ratio": expansion,
        "leak_volume": leak,
        "purity_end": purity_end,
        "lift_start_kg": lift_start,
        "lift_end_kg": lift_end,
        "lift_governing_kg": governing,
        "lift_steps": lift_steps,
        "volume_states": volume_states,
        "gas_volume_target": cell_gov["gas_volume"],
        "vented": cell_gov["vented"],
        "vented_mass_kg": cell_gov["vented_mass"],
        "pressure_height": calculate_pressure_height(inp.altitude, inp.field_temp_c, inp.temp_diff_c,
                                                     inp.superheat_k, r_free, fill_temp_c=inp.fill_temp_c),
        "field_total_lift_kg": field_total,
        "altitude_loss_kg": calculate_altitude_loss(volume, inp.altitude, inp.gas_type, inp.field_temp_c, 0.0,
                                                    inp.purity),
    }


def membrane_stress(equatorial, polar, pressure, samples=721):
    """回转椭球内压下的薄膜应力合力（力/长度），薄膜理论。

    t 为参数角（赤道 t=0，极点 t=90°）：
      R2 = a²·√(cos²t/a² + sin²t/b²)          （平行圆方向的曲率半径，沿法线到轴线的距离）
      R1 = (a²sin²t + b²cos²t)^1.5 /(a·b)     （子午线方向的曲率半径）
      N_φ（子午向）= p·R2/2；  N_θ（环向）= N_φ·(2 − R2/R1)
    球体 a=b=R：N = pR/2；赤道环向 N_θ = (p·a/2)(2 − a²/b²)，a/b > √2（扁球）时为压应力。
    返回最大拉力合力、位置与最小环向合力。
    """
    a, b = float(equatorial), float(polar)
    if a <= 0 or b <= 0:
        return {"max": 0.0, "where": "赤道", "hoop_min": 0.0, "meridional": 0.0, "hoop": 0.0}
    best, where = -math.inf, 0.0
    hoop_min, hoop_equator, meridional_equator = math.inf, 0.0, 0.0
    for i in range(samples):
        t = 0.5 * math.pi * i / (samples - 1)
        sin_t, cos_t = math.sin(t), math.cos(t)
        r2 = a * a * math.sqrt(cos_t * cos_t / (a * a) + sin_t * sin_t / (b * b))
        r1 = (a * a * sin_t * sin_t + b * b * cos_t * cos_t) ** 1.5 / (a * b)
        n_phi = pressure * r2 / 2.0
        n_theta = n_phi * (2.0 - r2 / r1)
        if i == 0:
            hoop_equator, meridional_equator = n_theta, n_phi
        hoop_min = min(hoop_min, n_theta)
        for value in (n_phi, n_theta):
            if value > best:
                best, where = value, t
    if abs(a - b) < 1e-9 * a:
        place = "各处相等"
    else:
        place = "赤道" if where < 0.05 else ("极点" if where > 0.5 * math.pi - 0.05 else "中纬度")
    return {"max": best, "where": place, "hoop_min": hoop_min, "meridional": meridional_equator, "hoop": hoop_equator}


def _film_stress_kn_per_m(inp, overpressure_kpa):
    """膜应力（kN/m）：有椭球分段时取各段薄膜理论最大值；否则球体 Δp·R/2、艇身环向 Δp·r（偏保守）。"""
    if inp.membrane_shapes:
        return max(membrane_stress(a, b, overpressure_kpa)["max"] for a, b in inp.membrane_shapes)
    if inp.shape == "sphere":
        return overpressure_kpa * inp.max_radius / 2.0
    return overpressure_kpa * inp.max_radius


def _evaluate_case(inp, static_net_kn, wind, req_sf, working, segments=400, compute_deficit=True,
                   auto_overpressure_kpa=None, fixed_length=None):
    """单一风工况评估。wind：WindField；working 决定判据（工作：拖地即不合格；生存：拖地仅提示）。

    fixed_length 给定时（生存风）：缆绳长度不变，浮空器被风压低到缆长刚好够到的高度，
    此后的风压、阵风、拉力都按该平衡高度计算；缆长够用时仍取目标高度。
    """
    h = inp.target_height
    cable = inp.cable
    req = inp.requirements
    w_kn_m = kg_to_kn(cable.unit_weight_kg_m)

    def solve(pressure_at, scale, extra_lift=0.0, height=None, n=segments):
        hh = h if height is None else height
        q_body = pressure_at(hh) * scale
        return solve_tether_equilibrium(
            static_net_kn + extra_lift + inp.lift_area * q_body, inp.drag_area * q_body,
            lambda z: pressure_at(z), cable.diameter_m, w_kn_m, hh, cable.drag_coeff, n)

    blown_down = False
    if fixed_length is not None and static_net_kn > 0:
        limit = fixed_length * 1.005   # 粗分段与正式求解的长度差

        def length_needed(height):
            r = solve(wind.pressure, 1.0, 0.0, height, 120)
            return r["cable_length"] if r["flyable"] else math.inf

        if length_needed(h) > limit:
            blown_down = True
            lo, hi = 0.5, h
            if length_needed(lo) > limit:
                h = lo
            else:
                for _ in range(30):
                    mid = 0.5 * (lo + hi)
                    lo, hi = (mid, hi) if length_needed(mid) <= limit else (lo, mid)
                h = lo
    q_t = wind.pressure(h)
    beta_t = wind.gust(h)

    mean = solve(wind.pressure, 1.0)
    peak = solve(wind.peak_pressure, 1.0)

    def lift_deficit():
        hi = max(1.0, abs(static_net_kn))
        while not solve(wind.pressure, 1.0, hi)["flyable"]:
            hi *= 2
            if hi > 1e6:
                return None
        lo = 0.0
        for _ in range(40):
            mid = 0.5 * (lo + hi)
            lo, hi = (lo, mid) if solve(wind.pressure, 1.0, mid)["flyable"] else (mid, hi)
        return hi

    failures, warnings = [], []
    deficit = None
    if not mean["flyable"]:
        deficit = lift_deficit() if compute_deficit else None
        hint = f"，需增加净浮力约 {kn_to_kg(deficit):.0f} kgf" if deficit is not None else ""
        overweight = static_net_kn + inp.lift_area * q_t <= 0
        text = ("超重：净浮力为负" if overweight else "缆绳底部拖地：浮力不足以将缆绳悬空至目标高度") + hint
        (failures if working else warnings).append(text)
    else:
        angle = mean["angle_deg"]
        if working and req.min_angle_deg > 0 and angle < req.min_angle_deg:
            failures.append(f"锚点夹角 {angle:.1f}° 小于要求的 {req.min_angle_deg:g}°")
        elif angle < BOTTOM_ANGLE_WARNING_DEG:
            warnings.append(f"缆绳底部悬链角仅 {angle:.1f}°，近乎贴地，阵风或浮力波动时有拖地风险")
        if not peak["flyable"]:
            (failures if working else warnings).append("阵风下缆绳底部拖地")
        if blown_down:
            warnings.append(f"缆长固定为 {fixed_length:.0f} m，浮空器被压低到 {h:.0f} m（目标 {inp.target_height:.0f} m），"
                            f"向下风漂移 {mean['drift']:.0f} m")

    top_peak = peak["tension"]
    anchor_peak = peak["anchor_tension"]
    peak_tension = max(top_peak, anchor_peak)
    cable_strength = cable.breaking_force_kn * cable.strength_factor
    cable_sf = cable_strength / peak_tension if cable_strength > 0 and peak_tension > 0 else None
    if cable_sf is not None and cable_sf < req_sf:
        failures.append(f"缆绳安全系数 {cable_sf:.2f} 小于要求 {req_sf:g}")

    # 膜材与超压：运行超压 ≥ k × 阵风动压，否则迎风面凹陷
    q_peak_body = beta_t * q_t
    p_required = req.overpressure_k * q_peak_body
    p_operating = inp.overpressure_kpa if inp.overpressure_kpa is not None else (
        p_required if working else auto_overpressure_kpa)
    film = {"required_kpa": p_required, "operating_kpa": p_operating, "stress": None, "sf": None, "strength": None}
    if p_operating is not None and p_operating + 1e-12 < p_required:
        (failures if working else warnings).append(
            f"运行超压 {p_operating * 1000:.0f} Pa 小于所需 {p_required * 1000:.0f} Pa，迎风面有凹陷风险")
    if p_operating is not None:
        film["stress"] = _film_stress_kn_per_m(inp, p_operating)
        if inp.membrane_shapes:
            hoops = [membrane_stress(a, b, p_operating)["hoop_min"] for a, b in inp.membrane_shapes]
            if min(hoops) < -1e-12:
                warnings.append("赤道环向为压应力（外形过扁，a/b > √2），膜面易起皱，建议提高高径比")
        if inp.film_strength_n5cm > 0:
            film["strength"] = inp.film_strength_n5cm * FILM_N_PER_5CM_TO_KN_PER_M * inp.seam_efficiency
            film["sf"] = film["strength"] / film["stress"] if film["stress"] > 0 else None
            if film["sf"] is not None and film["sf"] < req_sf_film(req, working):
                failures.append(f"膜材安全系数 {film['sf']:.2f} 小于要求 {req_sf_film(req, working):g}")

    pull = {"load": None, "sf": None}
    if inp.pull_points > 0:
        pull["load"] = (top_peak * max(inp.load_nonuniformity, 1.0)
                        / (inp.pull_points * math.cos(math.radians(_clamp(inp.bridle_half_angle_deg, 0.0, 80.0)))))
        if inp.pull_point_rating_kn > 0:
            pull["sf"] = inp.pull_point_rating_kn / pull["load"]
            if pull["sf"] < req_sf_film(req, working):
                failures.append(f"拉点安全系数 {pull['sf']:.2f} 小于要求 {req_sf_film(req, working):g}")

    return {
        "wind": {"speed_target": wind.profile.speed(h), "speed_10": wind.profile.speed(10.0),
                 "pressure_target_kpa": q_t, "gust_target": beta_t},
        "mean": mean,
        "peak": peak,
        "height": h,
        "blown_down": blown_down,
        "body_drag": inp.drag_area * q_t,
        "aero_lift": inp.lift_area * q_t,
        "peak_tension": peak_tension,
        "cable_sf": cable_sf,
        "film": film,
        "pull": pull,
        "lift_deficit": deficit,
        "failures": failures,
        "warnings": warnings,
        "ok": not failures,
    }


def req_sf_film(req, working):
    return req.film_sf if working else req.survival_sf


def find_max_wind_scale(evaluate, scale_high, iterations=26):
    """二分搜索满足全部校核的最大风速缩放倍数；evaluate(scale) 返回含 'ok' 的结果。"""
    low = 1e-4
    if not evaluate(low)["ok"]:
        return 0.0
    if evaluate(scale_high)["ok"]:
        return scale_high
    lo, hi = low, scale_high
    for _ in range(iterations):
        mid = 0.5 * (lo + hi)
        if evaluate(mid)["ok"]:
            lo = mid
        else:
            hi = mid
    return lo


def sensitivity_speeds(result, points=13, cap=61.2):
    """敏感性分析的离地 10 m 风速序列：从 0 到工作风与最大允许风速两者的合适上界，取整到 5 m/s。"""
    work_v10 = result["work"]["wind"]["speed_10"]
    max_v10 = result["max_wind"]["speed_10"] if result["max_wind"]["scale"] > 0 else 0.0
    top = max(1.6 * work_v10, 1.25 * max_v10, 5.0)
    top = min(math.ceil(top / 5.0) * 5.0, max(cap, work_v10))
    return [top * i / (points - 1) for i in range(points)]


def wind_sweep(inp, result, speeds_10):
    """工作风按离地 10 m 风速逐点缩放后的关键响应（敏感性分析）；result 为 analyze(inp) 的返回值。

    每个点返回 dict：speed_10、speed_target、flyable、angle_deg、tension、anchor_tension、peak_tension、drift、
    net_buoyancy（kgf，扣缆绳；拖地时为 None）、cable_sf、film_sf、ok。
    """
    work_field = WindField(inp.work_wind, inp.altitude, inp.field_temp_c - inp.temp_diff_c / 2.0, inp.terrain,
                           inp.gust_override, inp.free_turbulence)
    base_10 = work_field.profile.speed(10.0)
    base_target = work_field.profile.speed(inp.target_height)
    reference = base_10 if base_10 > 1e-9 else base_target
    rows = []
    for speed in speeds_10:
        scale = max(speed, 1e-4) / reference if reference > 1e-9 else 1.0
        case = _evaluate_case(inp, result["static_net_kn"], work_field.scaled(scale), inp.requirements.cable_sf, True,
                              160, False)
        mean = case["mean"]
        rows.append({
            "speed_10": speed, "speed_target": case["wind"]["speed_target"], "flyable": mean["flyable"],
            "angle_deg": mean["angle_deg"] if mean["flyable"] else None, "tension": mean["tension"],
            "anchor_tension": mean["anchor_tension"] if mean["flyable"] else None, "peak_tension": case["peak_tension"],
            "drift": mean["drift"] if mean["flyable"] else None,
            "net_buoyancy": kn_to_kg(mean["net_buoyancy"]) if mean["flyable"] else None,
            "cable_sf": case["cable_sf"], "film_sf": case["film"]["sf"], "ok": case["ok"]})
    return rows


def analyze(inp):
    """对一个设计点做完整评估。"""
    inp.cable = inp.cable or CableSpec()
    inp.requirements = inp.requirements or Requirements()
    gas = _gas_state(inp)
    mass_total = inp.fixed_mass + gas["aux_mass"]
    static_net_kg = gas["lift_governing_kg"] - mass_total
    static_net_kn = kg_to_kn(static_net_kg)

    # 风压按夜间最低气温（空气密度最大）取，与升力的白天最高温组合
    t_cold = inp.field_temp_c - inp.temp_diff_c / 2.0

    def field(profile):
        return WindField(profile, inp.altitude, t_cold, inp.terrain, inp.gust_override, inp.free_turbulence)

    work_field = field(inp.work_wind)
    survival_field = field(inp.survival_wind or inp.work_wind)
    req = inp.requirements

    work = _evaluate_case(inp, static_net_kn, work_field, req.cable_sf, True)
    survival = _evaluate_case(inp, static_net_kn, survival_field, req.survival_sf, False,
                              auto_overpressure_kpa=work["film"]["required_kpa"],
                              fixed_length=work["mean"]["cable_length"] if work["mean"]["flyable"] else None)

    speed_h = work_field.profile.speed(inp.target_height)
    scale_high = MAX_SEARCH_SPEED / speed_h if speed_h > 0 else 1.0
    scale = find_max_wind_scale(
        lambda s: _evaluate_case(inp, static_net_kn, work_field.scaled(s), req.cable_sf, True, 80, False), scale_high)
    max_wind = {
        "scale": scale,
        "speed_target": speed_h * scale,
        "speed_10": work_field.profile.speed(10.0) * scale,
        "unbounded": scale >= scale_high,
    }
    return {
        "gas": gas,
        "mass_total_kg": mass_total,
        "static_net_kg": static_net_kg,
        "static_net_kn": static_net_kn,
        "lift_governing_kn": kg_to_kn(gas["lift_governing_kg"]),
        "work": work,
        "survival": survival,
        "max_wind": max_wind,
    }
