"""计算控制器：读取界面输入 → 组装 DesignInputs → analyze() → 写回界面。球体页与飞艇页共用。"""
import logging
import math

from PyQt5.QtCore import QTimer

import aerostat_drag
import aerostat_tail
from aerostat_model import (BOTTOM_ANGLE_WARNING_DEG, CableSpec, DesignInputs, Requirements, analyze,
                            hull_aero_areas)
from aerostat_physics import (KGF_PER_KN, actual_temperature, aux_ratio_from_fill, calculate_corrected_air_density,
                              kg_to_kn, kn_to_kg, recommend_auxiliary_ratio)
from aerostat_wind import (MODE_REF10, MODE_TABLE, MODE_TARGET, WindProfile, beaufort_level, beaufort_name, beaufort_text,
                           parse_profile_table)
from Airship import Airship
from Sphere import Sphere

STYLE_OK = "color: #2e7d32; font-weight: bold;"
STYLE_WARN = "color: #ef6c00; font-weight: bold;"
STYLE_BAD = "color: #d32f2f; font-weight: bold;"
INVALID = "数据无效"
GROUNDED = "拖地"

ui = None
_aux_state = {"Sphere": {"manual": False, "updating": False}, "AirShip": {"manual": False, "updating": False}}
_timers = {}
_drag_reports = {}
_last = {}
_sweeping = set()


def bind(ui_object):
    global ui
    ui = ui_object


# ---------------------------------------------------------------- 防抖与自动/手动副气囊
def _schedule(func):
    timer = _timers.get(func)
    if timer is None:
        timer = QTimer()
        timer.setSingleShot(True)
        timer.setInterval(150)
        timer.timeout.connect(func)
        _timers[func] = timer
    timer.start()


def SphereCalculateRealTime():
    _schedule(SphereCalculate)


def AirShipCalculateRealTime():
    _schedule(AirShipCalculate)


def SphereAuxRatioManualEdit():
    if not _aux_state["Sphere"]["updating"]:
        _aux_state["Sphere"]["manual"] = True


def AirShipAuxRatioManualEdit():
    if not _aux_state["AirShip"]["updating"]:
        _aux_state["AirShip"]["manual"] = True


def ResetSphereAuxRatioMode():
    _aux_state["Sphere"]["manual"] = False


def ResetAirShipAuxRatioMode():
    _aux_state["AirShip"]["manual"] = False


def aux_manual(prefix):
    return _aux_state[prefix]["manual"]


def set_aux_manual(prefix, manual):
    _aux_state[prefix]["manual"] = bool(manual)


def last(prefix):
    """最近一次成功计算的上下文 {"inp", "res", "geometry", "seq"}；尚未成功计算过则为 None。"""
    return _last.get(prefix)


def calculate_now(prefix):
    """跳过防抖立即计算；返回本次是否成功产生了新结果（输入不完整或有误时为 False）。"""
    func = SphereCalculate if prefix == "Sphere" else AirShipCalculate
    timer = _timers.get(func)
    if timer is not None:
        timer.stop()
    before = _last.get(prefix, {}).get("seq", 0)
    func()
    return _last.get(prefix, {}).get("seq", 0) != before


# ---------------------------------------------------------------- 读写工具
def widget(prefix, name):
    for suffix in ("LineEdit", "ComboBox"):
        found = getattr(ui, f"{prefix}{name}{suffix}", None)
        if found is not None:
            return found
    return None


def put(prefix, name, text, style=None):
    target = widget(prefix, name)
    if target is None:
        return
    target.setText(text)
    if style is not None:
        target.setStyleSheet(style)


def number(prefix, name, default=None, required=False):
    """读取浮点数；留空取 default。"""
    target = widget(prefix, name)
    text = target.text().strip() if target is not None else ""
    if not text:
        if required and default is None:
            raise ValueError(f"{name} 未填写")
        return default
    return float(text)


def ensure_default(prefix, name, value):
    target = widget(prefix, name)
    if target is not None and not target.text().strip():
        target.setText(str(value))


def kgf(force_kn):
    """内部力为 kN，界面统一显示 kgf。"""
    return None if force_kn is None else force_kn * KGF_PER_KN


def fmt(value, digits=2):
    return f"{value:.{digits}f}"


def fmt_or_invalid(valid, value, digits=2):
    return fmt(value, digits) if valid else INVALID


def checked(name):
    box = getattr(ui, name, None)
    return box is None or box.isChecked()


# ---------------------------------------------------------------- 质量清单
EQUIPMENT = ["NetBag", "RotateConnector", "ForceSensor", "Platform", "AirFan", "SafetyValve", "EscapeValve",
             "PowerBoard", "WindMeter", "ControlBox", "InflationPort", "ObservationWindow"]
ROPES = ["MoorRope1", "MoorRope2", "MoorRope3", "MoorMainRope", "TetherRope1", "TetherRope2", "TetherRope3"]


def equipment_mass(prefix, name):
    box = getattr(ui, f"{prefix}{name}CheckBox", None)
    if box is not None and not box.isChecked():
        return 0.0
    unit = number(prefix, name, 0.0) or 0.0
    quantity = number(prefix, f"{name}Quantity", 1.0)
    return unit * (quantity if quantity is not None else 1.0)


def rope_mass(prefix, name):
    if not checked(f"checkBox_{prefix}{name}Enable"):
        return 0.0
    return (number(prefix, f"{name}Weight", 0.0) or 0.0) * (number(prefix, f"{name}Length", 0.0) or 0.0) \
        * (number(prefix, f"{name}Count", 1.0) or 0.0)


def mass_budget(prefix):
    """返回 (附件质量, 绳组与拉点质量, 拉点数量)，并刷新两个汇总框。拉点数量只要填了就用于载荷校核，勾选才计入重量。"""
    accessories = sum(equipment_mass(prefix, name) for name in EQUIPMENT)
    pull_enabled = checked(f"checkBox_{prefix}PullPointEnable")
    pull_count = int(number(prefix, "PullPoint", 0.0) or 0)
    pull_mass = (number(prefix, "PullPointWeight", 0.0) or 0.0) * pull_count if pull_enabled else 0.0
    ropes = pull_mass + sum(rope_mass(prefix, name) for name in ROPES)
    put(prefix, "AccessoryCheckedWeight", fmt(accessories))
    put(prefix, "RopeGroupCheckedWeight", fmt(ropes))
    return accessories, ropes, pull_count


# ---------------------------------------------------------------- 风、缆绳与要求
def build_wind(prefix, terrain, target_height):
    mode = widget(prefix, "WindMode").currentIndex()
    work_speed = number(prefix, "WindPressure", 10.0)
    survival_speed = number(prefix, "SurvivalWind", 20.0)
    if mode == MODE_TABLE:
        work = WindProfile(MODE_TABLE, terrain, target_height, table=parse_profile_table(widget(prefix, "WindTable").text()))
        survival_text = widget(prefix, "SurvivalWindTable").text().strip()
        survival = WindProfile(MODE_TABLE, terrain, target_height,
                               table=parse_profile_table(survival_text)) if survival_text else work
    else:
        work = WindProfile(mode, terrain, target_height, speed=work_speed)
        survival = WindProfile(mode, terrain, target_height, speed=survival_speed)
    return work, survival


def drag_report(prefix):
    """最近一次风阻系数选型的结果与输入环境（供选型对话框使用）。"""
    return _drag_reports.get(prefix)


def resolve_drag(prefix, kind, diameter, length=None, surface=None, volume=None):
    """按选型模型给出本体风阻系数；风阻系数输入框留空 = 自动，填数值 = 手动覆盖。"""
    altitude = number(prefix, "Altitude", 100.0)
    height = number(prefix, "TargetHeight", 100.0)
    field_temp = number(prefix, "GroundTemperature", 20.0)
    work, _ = build_wind(prefix, widget(prefix, "WindTerrain").currentText(), height)
    speed = work.speed(height)
    z_abs = altitude + height
    density = calculate_corrected_air_density(z_abs, altitude, field_temp)
    temp = actual_temperature(z_abs, altitude, field_temp)
    q = 0.5 * density * speed * speed
    fitting = number(prefix, "FittingDrag", None)
    overpressure = number(prefix, "OverPressure", None)
    if kind == "sphere":
        result = aerostat_drag.sphere_design(diameter, speed, density, temp, fitting, overpressure, q)
    else:
        ks = number(prefix, "SurfaceRoughness", 0.3)
        result = aerostat_drag.airship_design(length, diameter, surface, volume, speed, density, temp, ks, fitting,
                                              overpressure, q)
    manual = number(prefix, "DragCoefficient", None)
    used = result.cd if manual is None else manual
    outside = manual is not None and not result.low <= manual <= result.high
    put(prefix, "DragUsed", fmt(used, 3) + ("（手动）" if manual is not None else "（自动）"),
        STYLE_WARN if outside else "")
    put(prefix, "DragRange", f"{result.low:.3f} ～ {result.high:.3f}")
    _drag_reports[prefix] = {"result": result, "used": used, "manual": manual, "kind": kind, "diameter": diameter,
                             "length": length, "surface": surface, "volume": volume, "speed": speed,
                             "density": density, "temp": temp, "ks": number(prefix, "SurfaceRoughness", 0.3),
                             "q": q, "overpressure": overpressure}
    return used


def build_cable_and_requirements(prefix):
    cable = CableSpec(
        diameter_m=number(prefix, "CableDiameter", 5.0) / 1000.0,
        unit_weight_kg_m=number(prefix, "CableUnitWeight", 0.026),
        drag_coeff=number(prefix, "CableDragCoeff", 1.2),
        breaking_force_kn=kg_to_kn(number(prefix, "CableBreakingForce", 0.0)),
        strength_factor=number(prefix, "CableStrengthFactor", 0.8),
    )
    requirements = Requirements(
        cable_sf=number(prefix, "RequiredSafetyFactor", 5.0),
        film_sf=number(prefix, "ReqFilmSF", 4.0),
        survival_sf=number(prefix, "SurvivalSF", 2.5),
        min_angle_deg=number(prefix, "MinAngle", 0.0),
        overpressure_k=number(prefix, "OverPressureK", 1.2),
    )
    return cable, requirements


def common_inputs(prefix, geometry, shape, fixed_mass, drag_area, lift_area, film_unit_weight, max_radius):
    altitude = number(prefix, "Altitude", 100.0)
    height = number(prefix, "TargetHeight", 100.0)
    terrain = widget(prefix, "WindTerrain").currentText()
    work, survival = build_wind(prefix, terrain, height)
    cable, requirements = build_cable_and_requirements(prefix)
    gust_text = widget(prefix, "GustFactor").text().strip()
    overpressure = number(prefix, "OverPressure", None)
    aux_film = number(prefix, "AuxiliaryFilmUnitWeight", film_unit_weight)
    ratio_text = widget(prefix, "AuxiliaryAirbagRatio").text()
    fill_end = number(prefix, "FillEndTarget", None)
    if fill_end is not None and not 0.0 < fill_end <= 1.0:
        raise ValueError("末期充盈度应在 0～1 之间")
    fill_text = widget(prefix, "FillFraction").text().strip()
    fill_fraction = float(fill_text) if fill_text else None
    if fill_fraction is not None and not 0.0 < fill_fraction <= 1.0:
        raise ValueError("气体充盈度应在 0～1 之间")
    return DesignInputs(
        shape=shape, volume=geometry["volume"], surface_area=geometry["surface"], max_radius=max_radius,
        aux_geometry=geometry["aux_geometry"], aux_unit_weight=aux_film, fixed_mass=fixed_mass,
        drag_area=drag_area, lift_area=lift_area, altitude=altitude, target_height=height,
        field_temp_c=number(prefix, "GroundTemperature", 20.0), temp_diff_c=number(prefix, "TempDiff", 0.0),
        gas_type=widget(prefix, "GasType").currentText(), purity=number(prefix, "GasPurity", 99.0),
        superheat_k=number(prefix, "GasTemperature", 0.0), aux_ratio=float(ratio_text) if ratio_text.strip() else 0.2,
        fill_fraction=fill_fraction, fill_end_target=fill_end, fill_temp_c=number(prefix, "FillTemperature", None),
        climb_speed=number(prefix, "ClimbSpeed", 1.0),
        leakage_rate=number(prefix, "HeliumLeakageRate", 0.0), stay_days=number(prefix, "StayDays", 0.0),
        purity_decay_per_day=number(prefix, "PurityDecay", 0.0), work_wind=work, survival_wind=survival,
        terrain=terrain, gust_override=float(gust_text) if gust_text else None,
        free_turbulence=number(prefix, "FreeTurbulence", 0.07), cable=cable, requirements=requirements,
        film_strength_n5cm=number(prefix, "FilmStrength", 0.0), seam_efficiency=number(prefix, "SeamEfficiency", 0.7),
        overpressure_kpa=(overpressure / 1000.0) if overpressure is not None else None,
        pull_points=0, bridle_half_angle_deg=number(prefix, "BridleAngle", 30.0),
        load_nonuniformity=number(prefix, "LoadNonUniformity", 1.5),
        pull_point_rating_kn=kg_to_kn(number(prefix, "PullRating", 0.0)),
    )


def leak_ratio_of(inp):
    """滞空期间氦气逸出体积 ÷ 总容积。"""
    if inp.volume <= 0:
        return 0.0
    return inp.surface_area * max(inp.leakage_rate, 0.0) * max(inp.stay_days, 0.0) / inp.volume


def explicit_fill(inp):
    """用户指定的初始充盈度（手填或由末期充盈度反推）；未指定返回 None。"""
    if inp.fill_end_target is not None:
        return min(min(max(inp.fill_end_target, 0.01), 1.0) + leak_ratio_of(inp), 1.0)
    return inp.fill_fraction


def update_auto_aux_ratio(prefix, altitude, height, temp, temp_diff, superheat, fill_temp=None, leak_ratio=0.0,
                          fill=None, margin=0.05):
    """未手动修改时自动设定副气囊比例：指定了充盈度 → 1 − 充盈度 + 余量；否则按高度、温差、逸出量推荐。"""
    state = _aux_state[prefix]
    if state["manual"]:
        return
    if fill is not None:
        ratio = aux_ratio_from_fill(fill, margin)
        ratio = math.ceil(ratio * 100.0 - 1e-9) / 100.0
    else:
        recommended = recommend_auxiliary_ratio(altitude, height, temp, temp_diff, superheat, fill_temp, leak_ratio)
        ratio = min(math.ceil(recommended * 100.0 - 1e-9) / 100.0, 0.8)
    state["updating"] = True
    widget(prefix, "AuxiliaryAirbagRatio").setText(fmt(min(ratio, 0.95)))
    state["updating"] = False


# ---------------------------------------------------------------- 结果显示
def _sf_style(value, required):
    return STYLE_OK if value is not None and value >= required else STYLE_BAD


def _text_or_dash(value, digits=2, empty="—"):
    return fmt(value, digits) if value is not None else empty


def _conclusion(result_case, extra_warnings, missing_notes, extra_failures=()):
    failures = list(extra_failures) + list(result_case["failures"])
    if failures:
        return "不合格：" + "；".join(failures), STYLE_BAD
    notes = list(extra_warnings) + list(result_case["warnings"]) + list(missing_notes)
    if notes:
        return "合格（注意：" + "；".join(notes) + "）", STYLE_WARN
    return "合格", STYLE_OK


def wind_level_tip(prefix, name, speed_10, where):
    """在风速框的悬停提示末尾追加当前风速对应的风力等级（风级按离地 10 m 定义）。"""
    target = widget(prefix, name)
    if target is None:
        return
    _append_tip(prefix, name, f"{where}等效离地 10 m 风速 {speed_10:.1f} m/s = {beaufort_text(speed_10)}")


def _append_tip(prefix, name, extra):
    """在固定悬停提示末尾追加一行随计算变化的说明（固定部分保存在 baseTip 属性中）。"""
    target = widget(prefix, name)
    base = target.property("baseTip")
    if base is None:
        base = target.toolTip()
        target.setProperty("baseTip", base)
    if base.endswith("</div>"):
        target.setToolTip(base[:-6] + f"<br><b>{extra}</b></div>")
    else:
        target.setToolTip(f"{base}\n{extra}")


def show_results(prefix, inp, res, geometry):
    gas, work, survival, max_wind = res["gas"], res["work"], res["survival"], res["max_wind"]
    req = inp.requirements

    put(prefix, "Volume", fmt(geometry["volume"]))
    put(prefix, "WindwardArea", fmt(geometry["windward"]))
    put(prefix, "SewArea", fmt(geometry["sew"]))
    put(prefix, "FilmWeight", fmt(geometry["film_mass"]))
    for name in ("Area", "SurfaceArea"):
        put(prefix, name, fmt(geometry["surface"]))
    put(prefix, "FillUsed", fmt(gas["fill_fraction"], 3))
    put(prefix, "FillVolume", fmt(gas["initial_gas_volume"]))
    put(prefix, "TargetFill", fmt(gas["fill_target_raw"], 3), STYLE_BAD if gas["alarms"] else "")
    put(prefix, "FillRecommended", fmt(gas["fill_recommended"], 3))
    put(prefix, "FillEnd", fmt(gas["fill_end"], 3), STYLE_WARN if inp.stay_days > 0 and gas["leak_volume"] > 0 else "")
    put(prefix, "TargetFillEnd", fmt(gas["fill_target_end_raw"], 3), STYLE_WARN if inp.stay_days > 0 and gas["leak_volume"] > 0 else "")
    put(prefix, "AuxAirCold", fmt(gas["aux_air_cold"]))
    put(prefix, "AuxFlow", fmt(gas["aux_flow_m3_min"]))
    put(prefix, "AuxAirTarget", fmt(gas["aux_air_target"]))
    put(prefix, "AuxExchange", fmt(gas["aux_exchange"]))
    put(prefix, "AuxiliaryAirbagHeight", fmt(gas["aux_height"]))
    put(prefix, "AuxiliaryAirbagVolume", fmt(gas["aux_volume"]))
    put(prefix, "AuxiliaryAirbagArea", fmt(gas["aux_area"]))
    put(prefix, "AuxiliaryAirbagWeight", fmt(gas["aux_mass"]))
    put(prefix, "TotalEscapeVolume", fmt(gas["leak_volume"], 4))
    put(prefix, "Temperature", fmt(inp.field_temp_c - 0.00649 * inp.target_height))
    put(prefix, "TotalLift", fmt(gas["field_total_lift_kg"]))
    put(prefix, "AltitudeLoss", fmt(gas["altitude_loss_kg"]))
    steps = {key: delta for key, _, delta in gas["lift_steps"]}
    for name, key in (("LiftStepFill", "fill"), ("LiftStepFillTemp", "fill_temp"), ("LiftStepVent", "vent"),
                      ("LiftStepLeak", "leak"), ("LiftStepPurity", "purity")):
        put(prefix, name, f"{steps.get(key, 0.0):+.2f}")
    put(prefix, "EffectiveLift", fmt(gas["lift_start_kg"]))
    put(prefix, "EndLift", fmt(gas["lift_end_kg"]), STYLE_WARN if inp.stay_days > 0 else "")
    put(prefix, "StaticNet", fmt(res["static_net_kg"]), STYLE_OK if res["static_net_kn"] > 0 else STYLE_BAD)
    over_height = inp.target_height > gas["pressure_height"]
    put(prefix, "PressureHeight", f"{gas['pressure_height']:.0f}", STYLE_BAD if over_height else "")

    mean, peak = work["mean"], work["peak"]
    flyable = mean["flyable"]
    angle_ok = flyable and mean["angle_deg"] >= req.min_angle_deg
    put(prefix, "SpeedTarget", fmt(work["wind"]["speed_target"], 1))
    wind_level_tip(prefix, "SpeedTarget", work["wind"]["speed_10"], "工作风：")
    wind_level_tip(prefix, "WindPressure", work["wind"]["speed_10"], "工作风：")
    put(prefix, "ActualWindPressure", fmt(work["wind"]["pressure_target_kpa"] * 1000.0, 1))
    put(prefix, "GustTarget", fmt(work["wind"]["gust_target"]))
    put(prefix, "HorizontalForce", fmt(kgf(work["body_drag"]), 1))
    put(prefix, "CableDrag", fmt_or_invalid(flyable, kgf(mean["cable_drag_h"]), 1))
    put(prefix, "TotalHorizontalForce", fmt_or_invalid(flyable, kgf(mean["horizontal"]), 1))
    put(prefix, "TetherTension", fmt(kgf(mean["tension"]), 1))
    put(prefix, "AnchorTension", fmt_or_invalid(flyable, kgf(mean["anchor_tension"]), 1))
    put(prefix, "PeakTension", fmt(kgf(work["peak_tension"]), 1))
    put(prefix, "TopAngle", fmt(mean["top_angle_deg"], 1))
    put(prefix, "CableDrift", fmt_or_invalid(flyable, mean["drift"], 1))
    put(prefix, "CableLength", fmt_or_invalid(flyable, mean["cable_length"]))
    put(prefix, "CableWeight", fmt_or_invalid(flyable, kn_to_kg(mean["cable_weight"])))
    put(prefix, "NetBuoyancy", fmt_or_invalid(flyable, kgf(mean["net_buoyancy"]), 1), STYLE_OK if flyable else STYLE_BAD)
    put(prefix, "IncludedAngle", fmt(mean["angle_deg"], 1) if flyable else GROUNDED,
        (STYLE_WARN if flyable and mean["angle_deg"] < BOTTOM_ANGLE_WARNING_DEG else STYLE_OK) if angle_ok else STYLE_BAD)
    cable_sf = work["cable_sf"]
    put(prefix, "SafetyFactor", _text_or_dash(cable_sf, empty="未输入（④列）"),
        _sf_style(cable_sf, req.cable_sf) if cable_sf is not None else STYLE_WARN)
    film = work["film"]
    put(prefix, "ReqOverPressure", fmt(film["required_kpa"] * 1000.0, 1))
    put(prefix, "FilmStress", _text_or_dash(None if film["stress"] is None else film["stress"] * 0.05, 3))
    put(prefix, "FilmSF", _text_or_dash(film["sf"], empty="未输入（①列）"),
        _sf_style(film["sf"], req.film_sf) if film["sf"] is not None else STYLE_WARN)
    pull_empty = "未设拉点（③列）" if work["pull"]["load"] is None else "未输入（④列）"
    put(prefix, "PullLoad", _text_or_dash(kgf(work["pull"]["load"]), 1, empty="未设拉点（③列）"))
    put(prefix, "PullSF", _text_or_dash(work["pull"]["sf"], empty=pull_empty),
        _sf_style(work["pull"]["sf"], req.film_sf) if work["pull"]["sf"] is not None else STYLE_WARN)

    s_mean = survival["mean"]
    put(prefix, "SurvSpeedTarget", fmt(survival["wind"]["speed_target"], 1))
    wind_level_tip(prefix, "SurvSpeedTarget", survival["wind"]["speed_10"], "生存风：")
    wind_level_tip(prefix, "SurvivalWind", survival["wind"]["speed_10"], "生存风：")
    put(prefix, "SurvActualWindPressure", fmt(survival["wind"]["pressure_target_kpa"] * 1000.0, 1))
    put(prefix, "SurvHeight", fmt(survival["height"], 1), STYLE_WARN if survival["blown_down"] else "")
    put(prefix, "SurvDrift", fmt_or_invalid(s_mean["flyable"], s_mean["drift"], 1))
    put(prefix, "SurvTetherTension", fmt(kgf(s_mean["tension"]), 1))
    put(prefix, "SurvPeakTension", fmt(kgf(survival["peak_tension"]), 1))
    put(prefix, "SurvAngle", fmt(s_mean["angle_deg"], 1) if s_mean["flyable"] else GROUNDED,
        STYLE_OK if s_mean["flyable"] else STYLE_WARN)
    s_sf = survival["cable_sf"]
    put(prefix, "SurvSafetyFactor", _text_or_dash(s_sf, empty="未输入（④列）"),
        _sf_style(s_sf, req.survival_sf) if s_sf is not None else STYLE_WARN)
    put(prefix, "SurvFilmSF", _text_or_dash(survival["film"]["sf"], empty="未输入（①列）"),
        _sf_style(survival["film"]["sf"], req.survival_sf) if survival["film"]["sf"] is not None else STYLE_WARN)
    put(prefix, "SurvPullSF", _text_or_dash(survival["pull"]["sf"], empty=pull_empty),
        _sf_style(survival["pull"]["sf"], req.survival_sf) if survival["pull"]["sf"] is not None else STYLE_WARN)

    gas_notes = list(gas["warnings"])
    missing = []
    if work["cable_sf"] is None:
        missing.append("未校核缆绳强度")
    if film["sf"] is None:
        missing.append("未校核膜材强度")
    text, style = _conclusion(work, gas_notes, missing, gas["alarms"])
    put(prefix, "Conclusion", text, style)
    widget(prefix, "Conclusion").setToolTip(text)
    text, style = _conclusion(survival, [], [], gas["alarms"])
    put(prefix, "SurvConclusion", text, style)
    widget(prefix, "SurvConclusion").setToolTip(text)

    if gas["alarms"]:
        wind_text = "无效（存在充盈度/副气囊报警，请先解决）"
    elif max_wind["scale"] <= 0:
        wind_text = "无（静风即不满足）"
    else:
        level = beaufort_level(max_wind["speed_10"])
        prefix_text = "≥ " if max_wind["unbounded"] else ""
        wind_text = (f"{prefix_text}离地10 m {max_wind['speed_10']:.1f} m/s（{level}级）；"
                     f"目标高度 {max_wind['speed_target']:.1f} m/s")
    put(prefix, "MaxWindSpeed", wind_text)
    max_tip = wind_text
    if not gas["alarms"] and max_wind["scale"] > 0:
        max_tip += f"\n离地 10 m：{beaufort_text(max_wind['speed_10'])}"
    widget(prefix, "MaxWindSpeed").setToolTip(max_tip)
    _last[prefix] = {"inp": inp, "res": res, "geometry": geometry, "seq": _last.get(prefix, {}).get("seq", 0) + 1}
    _push_diagrams(prefix, inp, res, geometry)
    return work


# ---------------------------------------------------------------- 示意图
def _tether_state(name, color, case):
    mean = case["mean"]
    tension = kgf(mean["tension"])
    top = math.radians(mean["top_angle_deg"])
    return {"name": name, "color": color, "path": mean.get("path"), "flyable": mean["flyable"], "height": case["height"],
            "drift": mean["drift"], "angle": mean["angle_deg"], "top_angle": mean["top_angle_deg"], "tension": tension,
            "anchor_tension": kgf(mean["anchor_tension"]), "drag": tension * math.cos(top), "lift": tension * math.sin(top),
            "cable_length": mean["cable_length"], "speed10": case["wind"]["speed_10"],
            "blown_down": case["blown_down"]}


def _push_diagrams(prefix, inp, res, geometry):
    panel = getattr(ui, f"{prefix}Diagrams", None)
    if panel is None or prefix in _sweeping:
        return
    work, survival, gas = res["work"], res["survival"], res["gas"]
    shape = dict(geometry["shape"])
    survival_wind = inp.survival_wind or inp.work_wind
    sphere = shape["kind"] == "sphere"
    half = (shape["b"], shape["a"]) if sphere else (0.5 * (shape["a1"] + shape["a2"]), shape["b"])
    panel.tether.set_data({
        "states": [_tether_state("工作风", "work", work), _tether_state("生存风", "surv", survival)],
        "target": inp.target_height, "balloon": half,
        "wind_fns": [(inp.work_wind.speed, "work"), (survival_wind.speed, "surv")]})

    aux_area, aux_h = geometry["aux_geometry"](inp.aux_ratio)
    shape["aux_h"] = aux_h
    volume, surface = geometry["volume"], geometry["surface"]
    aux_volume = inp.aux_ratio * volume
    if sphere:
        info = [("直径 D", f"{2 * shape['b']:.2f} m"), ("高径比", f"{shape['a'] / shape['b']:.2f}"),
                ("体积", f"{volume:.1f} m³"), ("表面积", f"{surface:.1f} m²"), ("迎风投影面积", f"{geometry['windward']:.1f} m²"),
                ("开片数量", f"{shape['divide']} 片")]
    else:
        info = [("长度 L", f"{shape['a1'] + shape['a2']:.2f} m"), ("直径 D", f"{2 * shape['b']:.2f} m"),
                ("高径比 D/L", f"{2 * shape['b'] / (shape['a1'] + shape['a2']):.3f}"),
                ("最大截面位置", f"距鼻端 {shape['a1']:.2f} m"), ("体积", f"{volume:.1f} m³"),
                ("表面积", f"{surface:.1f} m²"), ("迎风投影面积", f"{geometry['windward']:.1f} m²"),
                ("尾翼总平面面积", f"{shape['planform']:.1f} m²")]
    info += [("副气囊比例", f"{inp.aux_ratio:.3f}"), ("副气囊体积", f"{aux_volume:.1f} m³"),
             ("主气囊容积", f"{volume - aux_volume:.1f} m³"), ("副气囊面积", f"{aux_area:.1f} m²")]
    shape["info"] = info
    panel.shape.set_data(shape)

    target = inp.target_height
    z_max = max(math.ceil(target * 1.3 / 10.0) * 10.0, 30.0)
    work_marks = [(10.0, "10 m：{v:.1f} m/s"), (target, "目标高度：{v:.1f} m/s")]
    surv_marks = [(10.0, "10 m：{v:.1f} m/s")] + ([(survival["height"], "被压低到 " + f"{survival['height']:.0f} m：" + "{v:.1f} m/s")]
                                                  if survival["blown_down"] else [(target, "目标高度：{v:.1f} m/s")])
    panel.wind.set_data({"z_max": z_max, "target": target, "curves": [
        ("工作风", "work", inp.work_wind.speed, work_marks), ("生存风", "surv", survival_wind.speed, surv_marks)]})

    items = [("场地总浮升力", gas["field_total_lift_kg"], "total")]
    items += [(label, abs(delta), "gain" if delta > 0 else "loss") for _, label, delta in gas["lift_steps"]
              if abs(delta) >= 0.05]
    items += [("毛浮力", gas["lift_governing_kg"], "total")]
    items += [(name, kg, "loss") for name, kg in geometry["budget"] if kg > 1e-9]
    items += [("副气囊膜材", gas["aux_mass"], "loss"), ("静净浮力", res["static_net_kg"], "total")]
    mean = work["mean"]
    if mean["flyable"]:
        aero = kn_to_kg(work["aero_lift"])
        if aero > 0.5:
            items.append(("气动升力", aero, "gain"))
        net_after = kn_to_kg(mean["net_buoyancy"])
        items += [("缆绳重量/风阻", res["static_net_kg"] + max(aero, 0.0) - net_after, "loss"), ("锚点净浮力", net_after, "total")]
    panel.budget.set_data({"items": items})
    panel.volume.set_data({"states": gas["volume_states"], "volume": geometry["volume"], "capacity": gas["aux_volume"]})


_REASONS = (("超重", "浮力不足"), ("拖地", "浮力不足"), ("缆绳安全系数", "缆绳强度"), ("膜材安全系数", "膜材强度"),
            ("拉点安全系数", "拉点强度"), ("超压", "超压不足"), ("锚点夹角", "锚点角过小"), ("充盈度", "充盈度报警"))


def _short_reason(texts):
    for text in texts:
        for key, label in _REASONS:
            if key in text:
                return label
    return "其他"


def _sweep_verdict(res):
    """返回 (ok/survival/fail, 简短原因)。"""
    if res["gas"]["alarms"]:
        return "fail", "充盈度报警"
    if not res["work"]["ok"]:
        return "fail", _short_reason(res["work"]["failures"])
    if not res["survival"]["ok"]:
        return "survival", _short_reason(res["survival"]["failures"])
    if res["max_wind"]["scale"] <= 0:
        return "still", "静风不合格"   # 靠风产生的气动升力才能悬空缆绳
    return "ok", ""


def run_sweep(prefix, low_factor, high_factor, points=11):
    """依次改变直径/长度并完整计算，收集选型曲线数据；结束后恢复输入。"""
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QApplication
    panel = getattr(ui, f"{prefix}Diagrams")
    name, calc = ("Diameter", SphereCalculate) if prefix == "Sphere" else ("Length", AirShipCalculate)
    field = widget(prefix, name)
    original = field.text()
    try:
        base = float(original)
    except ValueError:
        return
    rows = []
    panel.button.setEnabled(False)
    QApplication.setOverrideCursor(Qt.WaitCursor)
    _sweeping.add(prefix)
    field.blockSignals(True)
    try:
        for index in range(points):
            x = base * (low_factor + (high_factor - low_factor) * index / (points - 1))
            field.setText(f"{x:.4g}")
            before = _last.get(prefix, {}).get("seq", 0)
            calc()
            ctx = _last.get(prefix)
            if ctx is None or ctx["seq"] == before:
                continue
            rows.append((float(field.text()), ctx))
            QApplication.processEvents()
    finally:
        field.setText(original)
        field.blockSignals(False)
        _sweeping.discard(prefix)
        calc()
        QApplication.restoreOverrideCursor()
        panel.button.setEnabled(True)
    if len(rows) < 2:
        return
    last_inp = rows[-1][1]["inp"]
    work_v10 = _last[prefix]["res"]["work"]["wind"]["speed_10"]
    verdict, reason = [], []
    for _, ctx in rows:
        kind, text = _sweep_verdict(ctx["res"])
        verdict.append(kind)
        reason.append(text)
    recommended = next((i for i, v in enumerate(verdict) if v == "ok"), None)
    recommended_kind = "ok"
    if recommended is None:
        recommended = next((i for i, v in enumerate(verdict) if v in ("survival", "still")), None)
        recommended_kind = "work" if recommended is not None else None
    max_wind, net = [], []
    for _, ctx in rows:
        res = ctx["res"]
        valid = not res["gas"]["alarms"] and res["max_wind"]["scale"] > 0
        max_wind.append(res["max_wind"]["speed_10"] if valid else 0.0)
        mean = res["work"]["mean"]
        net.append(kn_to_kg(mean["net_buoyancy"]) if mean["flyable"] else None)
    panel.sweep.set_data({
        "xs": [x for x, _ in rows], "current": base, "xlabel": "直径 m" if prefix == "Sphere" else "长度 m",
        "max_wind": max_wind, "work_v10": work_v10, "verdict": verdict, "reason": reason,
        "recommended": recommended, "recommended_kind": recommended_kind, "unit": "m",
        "sf_work": [c["res"]["work"]["cable_sf"] for _, c in rows], "sf_surv": [c["res"]["survival"]["cable_sf"] for _, c in rows],
        "req_work": last_inp.requirements.cable_sf, "req_surv": last_inp.requirements.survival_sf,
        "static_net": [c["res"]["static_net_kg"] for _, c in rows], "net": net,
        })


def connect_diagrams():
    for prefix in ("Sphere", "AirShip"):
        panel = getattr(ui, f"{prefix}Diagrams", None)
        if panel is not None:
            panel.sweepRequested.connect(lambda lo, hi, p=prefix: run_sweep(p, lo, hi))


# ---------------------------------------------------------------- 球体
def SphereCalculate():
    prefix = "Sphere"
    try:
        for name, value in (("Diameter", 10), ("Ratio", 1), ("Altitude", 100), ("FilmUnitWeight", 0.2),
                            ("AuxiliaryFilmUnitWeight", 0.2),
                            ("HeliumLeakageRate", 0.002), ("StayDays", 15), ("WindPressure", 10),
                            ("TargetHeight", 100), ("CableUnitWeight", 0.026),
                            ("CableDiameter", 5), ("GroundTemperature", 20)):
            ensure_default(prefix, name, value)
        diameter = number(prefix, "Diameter")
        ratio = number(prefix, "Ratio")
        sphere = Sphere(diameter, ratio, float(widget(prefix, "DivideNumber").currentText()),
                        float(widget(prefix, "SewWidth").currentText()))
        volume = sphere.Calculate_volume()
        surface = sphere.Calculate_surface_area()
        windward = sphere.Calculate_windwardArea()
        sew = sphere.Calculate_sewArea()
        film_unit = number(prefix, "FilmUnitWeight")
        film_mass = film_unit * (surface + sew)

        accessories, ropes, pull_count = mass_budget(prefix)
        other = number(prefix, "OtherWeight", 0.0)
        customer = number(prefix, "CustomerLoad", 0.0)

        sail_mass = sail_lift_area = sail_drag_area = 0.0
        sail_type = ui.sailButtonGroup.checkedId() if hasattr(ui, "sailButtonGroup") else 0
        if sail_type in (1, 2):
            kind = "PocketSail" if sail_type == 1 else "WingSail"
            area = surface * number("", f"{kind}AreaRatio")
            put("", f"{kind}Area", fmt(area))
            material = number("", f"{kind}Material")
            sail_mass = area * material
            put("", f"{kind}Weight", fmt(sail_mass))
            if sail_type == 2:
                rod_text = widget("", "WingSailRodLength").text().strip()
                rod_length = float(rod_text) if rod_text else diameter * 4
                if not rod_text:
                    widget("", "WingSailRodLength").setText(fmt(rod_length))
                rod_mass = rod_length * (number("", "WingSailRodUnitWeight", 0.0) or 0.0)
                put("", "WingSailRodWeight", fmt(rod_mass))
                sail_mass += rod_mass
            sail_lift_area = area * number("", f"{kind}LiftCoeff")
            sail_drag_area = area * number("", f"{kind}DragCoeff")

        geometry = {"volume": volume, "surface": surface, "windward": windward, "sew": sew, "film_mass": film_mass,
                    "aux_geometry": sphere.auxiliary_geometry,
                    "budget": [("球体膜材", film_mass), ("帆", sail_mass), ("附件设备", accessories), ("绳组/拉点", ropes),
                               ("其他重量", other), ("客户负载", customer)],
                    "shape": {"kind": "sphere", "a": sphere.a, "b": sphere.b,
                              "divide": int(float(widget(prefix, "DivideNumber").currentText()))}}
        fixed_mass = film_mass + other + customer + accessories + ropes + sail_mass
        drag_area = resolve_drag(prefix, "sphere", diameter) * windward + sail_drag_area
        inp = common_inputs(prefix, geometry, "sphere", fixed_mass, drag_area, sail_lift_area, film_unit, diameter / 2)
        inp.membrane_shapes = [(diameter / 2, diameter / 2 * ratio)]
        update_auto_aux_ratio(prefix, inp.altitude, inp.target_height, inp.field_temp_c, inp.temp_diff_c, inp.superheat_k,
                              inp.fill_temp_c, leak_ratio_of(inp), explicit_fill(inp), number(prefix, "AuxMargin", 0.05))
        inp.aux_ratio = number(prefix, "AuxiliaryAirbagRatio", 0.2)
        inp.pull_points = pull_count

        put(prefix, "Height", fmt(diameter * ratio))
        res = analyze(inp)
        work = show_results(prefix, inp, res, geometry)
        if sail_type == 1:
            put("", "PocketSailLift", fmt(kgf(work["aero_lift"]), 1))
        elif sail_type == 2:
            put("", "WingSailLift", fmt(kgf(work["aero_lift"]), 1))
    except ValueError as error:
        _report_input_error(prefix, error)
    except Exception as error:  # noqa: BLE001
        logging.exception(error)


# ---------------------------------------------------------------- 飞艇
def AirShipCalculate():
    prefix = "AirShip"
    try:
        for name, value in (("Length", 10), ("DLRatio", 0.25), ("CenterRatio", 0.3), ("Altitude", 100),
                            ("FilmUnitWeight", 0.2), ("AuxiliaryFilmUnitWeight", 0.2),
                            ("HeliumLeakageRate", 0.002), ("StayDays", 15), ("WindPressure", 10),
                            ("TargetHeight", 100), ("CableUnitWeight", 0.026),
                            ("CableDiameter", 5), ("GroundTemperature", 20)):
            ensure_default(prefix, name, value)
        length = number(prefix, "Length")
        dl_ratio = number(prefix, "DLRatio")
        ship = Airship(length, dl_ratio, number(prefix, "CenterRatio"), float(widget(prefix, "DivideNumber").currentText()),
                       float(widget(prefix, "SewWidth").currentText()))
        diameter = length * dl_ratio
        volume = ship.calculate_volume()
        surface = ship.calculate_surface_area()
        windward = (diameter / 2) ** 2 * 3.141592653589793
        sew = ship.calculate_sewArea()
        film_unit = number(prefix, "FilmUnitWeight")
        film_mass = film_unit * (surface + sew)

        accessories, ropes, pull_count = mass_budget(prefix)
        other = number(prefix, "OtherWeight", 0.0)
        customer = number(prefix, "CustomerLoad", 0.0)

        # 尾翼自重与尾翼浮力按相互抵消处理，不计入浮力系统和重量清单；尾翼面积只用于气动计算
        tail_area_ratio = number(prefix, "TailSurfaceAreaRatio", 0.31) if widget(prefix, "TailSurfaceAreaRatio") else 0.31
        tail_area = surface * tail_area_ratio
        put(prefix, "TailSurfaceArea", fmt(tail_area))
        put(prefix, "TailWeight", fmt(tail_area * film_unit))

        hull_cd = resolve_drag(prefix, "airship", diameter, length, surface, volume)
        env = drag_report(prefix)
        aoa = number(prefix, "AoA", 5.0)
        manual_tail_cd = number(prefix, "TailDragCoeff", None)
        tail = aerostat_tail.design_tail(
            volume, length, diameter, surface, tail_area, number(prefix, "FinCount", 4.0), number(prefix, "FinAspect", 1.0),
            number(prefix, "FinThickness", 0.15), env["speed"], env["density"], env["temp"], hull_cd * windward, aoa,
            manual_tail_cd)
        manual_cl, manual_k = number(prefix, "CLAlpha", None), number(prefix, "InducedK", None)
        if manual_cl is not None or manual_k is not None:
            lift_area, drag_extra = hull_aero_areas(volume, aoa, 1.2 if manual_cl is None else manual_cl,
                                                    0.4 if manual_k is None else manual_k)
        else:
            lift_area, drag_extra = tail["lift_area"], tail["drag_extra_area"]
        drag_area = hull_cd * windward + tail["profile_area"] + drag_extra
        show_tail(prefix, tail, manual_tail_cd, manual_cl is not None or manual_k is not None, lift_area, volume, aoa)

        geometry = {"volume": volume, "surface": surface, "windward": windward, "sew": sew, "film_mass": film_mass,
                    "aux_geometry": ship.auxiliary_geometry,
                    "budget": [("艇体膜材", film_mass), ("附件设备", accessories),
                               ("绳组/拉点", ropes), ("其他重量", other), ("客户负载", customer)],
                    "shape": {"kind": "airship", "a1": ship.a1, "a2": ship.a2, "b": ship.b, "fin_count": tail["fin_count"],
                              "span": tail["span"], "chord": tail["chord"], "planform": tail["planform"],
                              "thickness": number(prefix, "FinThickness", 0.15)}}
        fixed_mass = film_mass + other + customer + accessories + ropes
        inp = common_inputs(prefix, geometry, "airship", fixed_mass, drag_area, lift_area, film_unit, ship.b)
        inp.membrane_shapes = [(ship.b, ship.a1), (ship.b, ship.a2)]
        update_auto_aux_ratio(prefix, inp.altitude, inp.target_height, inp.field_temp_c, inp.temp_diff_c, inp.superheat_k,
                              inp.fill_temp_c, leak_ratio_of(inp), explicit_fill(inp), number(prefix, "AuxMargin", 0.05))
        inp.aux_ratio = number(prefix, "AuxiliaryAirbagRatio", 0.2)
        inp.pull_points = pull_count

        put(prefix, "Diameter", fmt(diameter))
        res = analyze(inp)
        work = show_results(prefix, inp, res, geometry)
        put(prefix, "AeroLift", fmt(kgf(work["aero_lift"]), 1))
    except ValueError as error:
        _report_input_error(prefix, error)
    except Exception as error:  # noqa: BLE001
        logging.exception(error)


def show_tail(prefix, tail, manual_tail_cd, manual_aero, lift_area, volume, aoa):
    put(prefix, "FinPlanform", fmt(tail["planform"]))
    put(prefix, "FinSpan", fmt(tail["span"]))
    put(prefix, "FinChord", fmt(tail["chord"]))
    put(prefix, "FinAreaRatio", fmt(tail["area_ratio"], 3))
    put(prefix, "FinVolumeGeo", fmt(tail["volume_geo"], 1))
    put(prefix, "TailDragUsed", fmt(tail["cd_tail"], 4) + ("*" if manual_tail_cd is not None else ""))
    ref = volume ** (2.0 / 3.0)
    equivalent = lift_area / (math.radians(aoa) * ref) if aoa > 1e-6 and ref > 0 else tail["cl_alpha_eq"]
    put(prefix, "CLAlphaUsed", fmt(equivalent, 3) + ("*" if manual_aero else ""))
    put(prefix, "StabilityMargin", fmt(tail["moment_ratio"], 2))


def _report_input_error(prefix, error):
    message = str(error)
    # 输入过程中的半截数字（如 "1."）不打扰用户；只提示风廓线等格式错误
    if "风廓线" in message or "条目" in message or "高度" in message:
        put(prefix, "Conclusion", f"输入有误：{message}", STYLE_BAD)
    logging.error(message)
