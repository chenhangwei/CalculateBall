"""界面组装：声明式字段登记 + 按设计流程把现有行重新分组。

页面结构（气球页 / 飞艇页相同）：
    顶部    设计结论条（工作风、生存风、最大允许风速）
    四列    ① 外形与材料  ② 场地·气体·浮力  ③ 重量清单  ④ 系留缆绳与风
    底部    ⑤ 校核结果（工作风 | 生存风），⑥ 设计示意图（受力姿态、外形、风廓线、浮力重量、选型曲线）
输入项统一蓝底，只读结果统一灰底；力的单位为 kgf，质量为 kg，风压为 Pa。
"""
import logging

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (QComboBox, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                             QScrollArea, QSizePolicy, QTextEdit, QVBoxLayout, QWidget)

from aerostat_wind import TERRAIN_OPTIONS, WIND_MODES
from diagrams import DiagramPanel
from ui_tips import apply_tips

INPUT_STYLE = "background-color: rgb(83, 209, 255);"
ROW_STRETCH = (4, 6, 1)
PAGE_DEFAULTS = {"Sphere": {"FittingDrag": "0.02"}, "AirShip": {"FittingDrag": "0.01"}}


def _f(kind, label, unit="", default="", tip="", placeholder="", items=None):
    return dict(kind=kind, label=label, unit=unit, default=default, tip=tip, placeholder=placeholder, items=items)


# 新增字段登记：键 → 规格。对象名为 f"{前缀}{键}LineEdit"（下拉框为 ComboBox）。
FIELDS = {
    # ---- 风 ----
    "WindMode": _f("combo", "风速输入方式：", items=WIND_MODES,
                   tip="10 m 参考风速：风级表口径，适用目标高度不超过梯度风高度（约 300～550 m）；\n"
                       "目标高度设计风速：直接给工作高度处风速（建议 >500 m 时使用，取自站点探空统计）；\n"
                       "自定义风廓线表：逐点给出高度—平均风速。"),
    "SurvivalWind": _f("in", "生存风速：", "m/s", "20", "与工作风速同一参考位置的生存（极端）工况平均风速"),
    "WindTable": _f("in", "工作风廓线：", "", "", "格式 高度:风速，用逗号分隔，例：10:8, 300:15, 1000:22（m，m/s，平均风）",
                    "10:8, 300:15, 1000:22"),
    "SurvivalWindTable": _f("in", "生存风廓线：", "", "", "格式同工作风廓线", "10:15, 300:28, 1000:40"),
    "WindTerrain": _f("combo", "地面粗糙度：", items=TERRAIN_OPTIONS,
                      tip="GB 50009-2012 地面粗糙度类别：只决定梯度风高度以下的剖面形状与湍流强度"),
    "GustFactor": _f("in", "阵风系数：", "", "", "留空 = 自动（GB 50009 随高度、地貌变化）；填数值 = 全高度取定值",
                     "自动（随高度）"),
    "FreeTurbulence": _f("in", "自由大气湍流强度：", "", "0.07",
                         "梯度风高度以上湍流强度渐变到该值（工程假设，建议用站点实测阵风数据校准）"),
    # ---- 气体 / 浮力 ----
    "GasPurity": _f("in", "气体纯度：", "%", "99"),
    "PurityDecay": _f("in", "纯度衰减：", "%/天", "0", "仅在有实测纯度记录时填写；已按透氦率填了氦气逃逸率时保持 0"),
    "EffectiveLift": _f("out", "目标高度毛浮力（初期）：", "kgf", tip="白天最高气温、含日照过热与排气后的毛浮力"),
    "LiftStepFill": _f("out", " 未充满容积：", "kgf", tip="充盈度小于 1 时少充的部分"),
    "LiftStepFillTemp": _f("out", " 充装温度：", "kgf", tip="充装温度修正"),
    "LiftStepVent": _f("out", " 高温膨胀排气：", "kgf", tip="目标高度白天最热时氦气超容排出的部分"),
    "LiftStepLeak": _f("out", " 氦气逸出：", "kgf", tip="滞空期间氦气逸出损失"),
    "LiftStepPurity": _f("out", " 纯度衰减：", "kgf", tip="滞空期间纯度衰减损失"),
    "EndLift": _f("out", "滞空末期毛浮力：", "kgf", tip="计入氦气逃逸与纯度衰减；设计以末期为准"),
    "StaticNet": _f("out", "静净浮力（未计缆绳）：", "kgf", tip="毛浮力 − 膜材 − 副气囊 − 设备 − 负载 − 绳组"),
    "PressureHeight": _f("out", "压力高度（离地）：", "m", tip="主气囊气体膨胀至充满全部容积的高度，超过后开始排气"),
    # ---- 膜材 / 超压 / 拉点 ----
    "FilmStrength": _f("in", "膜材抗拉强度：", "N/5cm", "", "经向、纬向较小者；从膜材库选择时自动填入", "从膜材库选择或输入"),
    "SeamEfficiency": _f("in", "接缝效率：", "", "0.7", "接缝强度/母材强度，焊接 0.7～0.9，缝合粘贴 0.5～0.7"),
    "FillFraction": _f("in", "气体充盈度：", "", "", "充装气体体积 ÷ 总容积。例：副气囊比例 0.2、充盈度 0.9，则实际充气 0.9 倍总容积，浮力只比满充少 0.1 倍总容积；留空 = 1 − 副气囊比例", "自动"),
    "FillVolume": _f("out", "初始充气体积：", "m³", tip="场地充装时的混合气体积 = 充盈度 × 总容积"),
    "FillEndTarget": _f("in", "末期充盈度（反推初始）：", "", "", "希望滞空末期（地面）保持的充盈度；填写后按 初始 = 末期 + 逸出体积÷总容积 反推初始充气量，并忽略“气体充盈度”", "可选"),
    "FillUsed": _f("out", "实际初始充盈度：", "", tip="计算采用的初始充盈度（手填、反推或默认）"),
    "AuxMargin": _f("in", "副气囊余量：", "", "0.05", "指定充盈度时，副气囊比例自动 = 1 − 充盈度 + 余量；默认 0.05"),
    "FillTemperature": _f("in", "充气时气温：", "℃", "", "充气时的环境温度；留空 = 夜间最低温（场地环境温度 − 昼夜温差/2）。白天充气则填白天气温，夜间氦气收缩，需要更大的副气囊", "自动"),
    "FillRecommended": _f("out", "建议充盈度：", "", tip="到达目标高度（白天最热）时氦气刚好充满囊体的充盈度 = 1 ÷ 膨胀比"),
    "AuxAirCold": _f("out", "夜间副气囊最大空气量：", "m³", tip="滞空末期、夜间最冷时副气囊需容纳的空气（含氦气逸出让出的体积），不得超过副气囊容积"),
    "ClimbSpeed": _f("in", "升降速度：", "m/s", "1", "绞车收放速度，用于估算副气囊换气流量"),
    "AuxFlow": _f("out", "换气流量：", "m³/min", tip="升降换气量 ÷ 升降时间；按全部换气量都在升降过程中完成计算，偏保守"),
    "DragUsed": _f("out", "实际采用的风阻系数：", "", tip="计算采用的本体风阻系数"),
    "DragRange": _f("out", "合理范围：", "", tip="选型模型给出的不确定度范围"),
    "FittingDrag": _f("in", "附件阻力增量 ΔCD：", "", "0.02", "拉点、吊带、充气口、阀门、接缝带等的附加阻力系数"),
    "SurfaceRoughness": _f("in", "表面等效粗糙度：", "mm", "0.3", "艇身表面等效沙粒粗糙度"),
    "TargetFill": _f("out", "目标高度氦气充盈度：", "", tip="白天最热时氦气体积 ÷ 总容积 = 充盈度 × 膨胀比（最大 1，超过即排氦）"),
    "FillEnd": _f("out", "滞空末期充盈度（地面）：", "", tip="充盈度 − 滞空期间氦气逸出体积 ÷ 总容积；逸出的氦气由副气囊空气补位"),
    "TargetFillEnd": _f("out", "滞空末期目标高度充盈度：", "", tip="滞空末期、白天最热时氦气体积 ÷ 总容积；小于 1 说明囊体已不饱满，设计浮力按此末期值计算"),
    "AuxAirTarget": _f("out", "目标高度副气囊空气量：", "m³", tip="白天最热、到达目标高度时副气囊内剩余空气；为 0 表示囊体已被氦气充满"),
    "AuxExchange": _f("out", "升降换气量：", "m³", tip="地面与目标高度之间副气囊需排出（上升）/补入（下降）的空气体积，用于安全阀与风机选型"),
    "OverPressureK": _f("in", "超压系数 k：", "", "1.2", "运行超压 ≥ k × 阵风动压，否则迎风面凹陷；一般取 1.0～1.5"),
    "OverPressure": _f("in", "内部恒定压强：", "Pa", "800", "副气囊充放气维持的囊体内外压差（运行超压），默认 800 Pa；留空 = 自动取 k × 工作阵风动压", "自动"),
    "ReqFilmSF": _f("in", "膜材/拉点要求安全系数：", "", "4"),
    "SurvivalSF": _f("in", "生存工况要求安全系数：", "", "2.5", "缆绳、膜材、拉点在生存风下的最低安全系数"),
    "CableStrengthFactor": _f("in", "缆绳强度折减：", "", "0.8", "接头效率 × 老化/蠕变折减；插接 0.8～0.9，打结 0.5"),
    "BridleAngle": _f("in", "吊带半角：", "°", "30", "吊带与缆绳轴线夹角"),
    "LoadNonUniformity": _f("in", "载荷不均系数：", "", "1.5", "拉点间载荷分配不均，一般取 1.3～2.0"),
    "PullRating": _f("in", "拉点额定拉力：", "kgf", "", "单个拉点/吊带破断力；留空则不校核", "可选"),
    # ---- 飞艇气动 ----
    "AoA": _f("in", "配平攻角：", "°", "5", "系留飞艇迎风配平攻角，通常 3～12°"),
    "CLAlpha": _f("in", "升力线斜率 CLα：", "/rad", "", "留空由尾翼+艇身模型自动计算；手动填写则覆盖", "自动（模型）"),
    "InducedK": _f("in", "诱导阻力因子 K：", "", "", "留空自动；手动填写则覆盖", "自动（模型）"),
    "FinCount": _f("in", "尾翼片数：", "片", "4", "十字或 X 形 4 片，三片式 3 片"),
    "FinAspect": _f("in", "尾翼展弦比 AR：", "", "1.0", "单片展长² ÷ 单片面积；充气尾翼约 0.8～1.5"),
    "FinThickness": _f("in", "尾翼相对厚度 t/c：", "", "0.15", "充气尾翼约 0.12～0.25"),
    "FinPlanform": _f("out", "尾翼总平面面积：", "㎡", tip="尾翼总平面面积"),
    "FinSpan": _f("out", "单片翼展：", "m", tip="单片尾翼翼展"),
    "FinChord": _f("out", "单片平均弦长：", "m", tip="单片尾翼平均弦长"),
    "FinAreaRatio": _f("out", "尾翼总面积 ÷ V^(2/3)：", "", tip="尾翼总平面面积比"),
    "FinVolumeGeo": _f("out", "尾翼几何体积（参考）：", "m³", tip="按几何估算的尾翼体积，不计入浮力"),
    "TailDragUsed": _f("out", "采用的尾翼阻力系数：", "", tip="尾翼阻力系数"),
    "CLAlphaUsed": _f("out", "采用的升力线斜率：", "/rad", tip="升力线斜率"),
    "StabilityMargin": _f("out", "尾翼/Munk 力矩比：", "", tip="尾翼恢复力矩比"),
    "CableDragCoeff": _f("in", "缆绳风阻系数：", "", "1.2",
                       "圆柱横流：光滑护套缆 1.0～1.1，编织/钢丝绳 1.2～1.3，考虑涡激振动取 1.5"),
    "CableBreakingForce": _f("in", "缆绳破断力（新缆）：", "kgf", "", "从缆绳库选择时自动填入", "从缆绳库选择或输入"),
    "RequiredSafetyFactor": _f("in", "缆绳要求安全系数：", "", "5", "缆绳有效破断力与阵风峰值拉力之比的下限（工作风）"),
    "MinAngle": _f("in", "底部最小离地角：", "°", "0",
                 "锚点处缆绳与地面夹角的下限。默认 0：只要求缆绳不拖地；小于 5° 时仅提示贴地风险"),
    "AeroLift": _f("out", "气动升力（向上）：", "kgf", tip="工作风下由配平攻角产生的气动升力，已计入缆绳受力"),
    # ---- 结果：结论 ----
    "Conclusion": _f("text", "工作风结论：", tip="工作风 + 阵风下全部校核"),
    "SurvConclusion": _f("text", "生存风结论：", tip="生存风 + 阵风下强度校核；拖地仅提示"),
    "MaxWindSpeed": _f("out", "最大允许风速：", tip="满足工作风全部校核的最大风速，给出离地 10 m 与目标高度两个值"),
    # ---- 结果：工作风 ----
    "SpeedTarget": _f("out", "目标高度风速：", "m/s"),
    "ActualWindPressure": _f("out", "目标高度风压：", "Pa", tip="½ρV²，ρ 按场地气温递减修正（夜间最低气温，偏保守）"),
    "GustTarget": _f("out", "目标高度阵风系数：", ""),
    "CableDrag": _f("out", "缆绳风阻：", "kgf", tip="全缆风阻水平分量，沿缆分段按局部倾角与局部风压积分"),
    "TotalHorizontalForce": _f("out", "总水平力（锚点）：", "kgf", tip="本体风阻 + 缆绳风阻"),
    "TetherTension": _f("out", "缆绳顶端拉力：", "kgf", tip="平均风下浮空器连接点拉力"),
    "AnchorTension": _f("out", "锚点拉力：", "kgf", tip="用于地锚/绞盘选型"),
    "PeakTension": _f("out", "阵风峰值拉力：", "kgf", tip="阵风压下缆绳最大拉力"),
    "SafetyFactor": _f("out", "缆绳安全系数：", "", tip="缆绳破断力 × 强度折减 ÷ 阵风峰值拉力"),
    "TopAngle": _f("out", "缆绳顶端夹角：", "°"),
    "CableDrift": _f("out", "水平漂移距离：", "m", tip="浮空器相对锚点的下风向水平距离"),
    "ReqOverPressure": _f("out", "所需超压：", "Pa", tip="k × 阵风动压"),
    "FilmStress": _f("out", "膜应力：", "kN/5cm", tip="每 5 cm 宽度膜材承受的拉力：球体 Δp·R/2；艇身环向 Δp·r，再乘 0.05 m；与膜材抗拉强度（N/5cm）同口径"),
    "FilmSF": _f("out", "膜材安全系数：", "", tip="抗拉强度 × 接缝效率 ÷ 膜应力"),
    "PullLoad": _f("out", "单点载荷：", "kgf", tip="峰值拉力 × 不均系数 ÷ (拉点数 × cos 吊带半角)"),
    "PullSF": _f("out", "拉点安全系数：", ""),
    # ---- 结果：生存风 ----
    "SurvSpeedTarget": _f("out", "浮空器处风速：", "m/s"),
    "SurvActualWindPressure": _f("out", "浮空器处风压：", "Pa"),
    "SurvHeight": _f("out", "浮空器高度：", "m"),
    "SurvDrift": _f("out", "水平漂移距离：", "m"),
    "SurvTetherTension": _f("out", "缆绳顶端拉力：", "kgf"),
    "SurvPeakTension": _f("out", "阵风峰值拉力：", "kgf"),
    "SurvSafetyFactor": _f("out", "缆绳安全系数：", ""),
    "SurvFilmSF": _f("out", "膜材安全系数：", ""),
    "SurvPullSF": _f("out", "拉点安全系数：", ""),
    "SurvAngle": _f("out", "锚点悬链角：", "°"),
}

# 现有字段的标签/单位覆盖（键 → {"label":…, "unit":…}）
OVERRIDES = {
    "TotalLift": {"label": "场地总浮升力：", "unit": "kgf"},
    "AltitudeLoss": {"label": "海拔损耗：", "unit": "kgf"},
    "Temperature": {"label": "目标高度平均气温："},
    "GroundTemperature": {"label": "场地环境温度："},
    "TempDiff": {"label": "昼夜温差："},
    "GasTemperature": {"label": "气体过热度：", "unit": "K"},
    "WindPressure": {"label": "工作风速：", "unit": "m/s"},
    "HorizontalForce": {"label": "本体风阻：", "unit": "kgf"},
    "NetBuoyancy": {"label": "净浮力（扣缆绳）：", "unit": "kgf"},
    "IncludedAngle": {"label": "锚点悬链角："},
    "CableWeight": {"label": "缆绳质量：", "unit": "kg"},
    "CableLength": {"label": "缆绳悬空长度："},
    "TargetHeight": {"label": "目标高度（离地）："},
    "CableUnitWeight": {"label": "缆绳米重："},
    "RequiredSafetyFactor": {"label": "缆绳要求安全系数："},
    "MinAngle": {"label": "底部最小离地角："},
    "CableBreakingForce": {"label": "缆绳破断力（新缆）："},
    "OtherWeight": {"label": "其他重量："},
    "DragCoefficient": {"label": "风阻系数 CD（留空=自动）：", "placeholder": "自动（选型模型）"},
}

EQUIPMENT = ["NetBag", "RotateConnector", "ForceSensor", "Platform", "AirFan", "SafetyValve", "EscapeValve",
             "PowerBoard", "WindMeter", "ControlBox", "InflationPort", "ObservationWindow"]
ROPES = ["MoorRope1Weight", "MoorRope2Weight", "MoorRope3Weight", "MoorMainRopeWeight",
         "TetherRope1Weight", "TetherRope2Weight", "TetherRope3Weight"]

# 约定：“#标题” 开始一节，“#标题|折叠” 默认折叠；“^键” 是节头下始终可见的汇总行；“-” 为分隔线
_COMMON_COL3 = ["#副气囊与充气", "AuxiliaryAirbagRatio", "AuxMargin", "FillFraction", "FillEndTarget", "FillRecommended", "FillUsed",
                "FillVolume", "PressureHeight",
                "#副气囊隔层", "AuxiliaryAirbagHeight", "AuxiliaryAirbagVolume", "AuxiliaryAirbagArea",
                "AuxiliaryFilmUnitWeight", "AuxiliaryAirbagWeight",
                "#货物与负载", "CustomerLoad", "OtherWeight",
                "#设备|折叠", "^AccessoryCheckedWeight"] + EQUIPMENT + [
                "#拉点与绳组配件|折叠", "^RopeGroupCheckedWeight", "PullPointWeight"] + ROPES[:4] + ["-"] + ROPES[4:]
_COMMON_COL2 = ["#场地与环境", "Altitude", "GroundTemperature", "TempDiff", "FillTemperature", "Temperature",
                "#气体", "GasType", "GasPurity", "GasTemperature", "PurityDecay",
                "#逃逸与滞空", "HeliumLeakageRate", "StayDays", "TotalEscapeVolume",
                "#浮力（kgf）", "TotalLift", "AltitudeLoss", "LiftStepFill", "LiftStepFillTemp", "LiftStepVent", "EffectiveLift",
                "LiftStepLeak", "LiftStepPurity", "EndLift",
                "#氦气充盈度与换气", "TargetFill", "FillEnd", "TargetFillEnd", "AuxAirTarget", "AuxAirCold",
                "AuxExchange", "ClimbSpeed", "AuxFlow"]
_COMMON_COL4 = ["#目标与缆绳", "TargetHeight", "CableUnitWeight", "CableDiameter", "CableDragCoeff",
                "CableBreakingForce", "CableStrengthFactor",
                "#风与阵风", "WindMode", "WindPressure", "SurvivalWind", "WindTable", "SurvivalWindTable",
                "WindTerrain", "GustFactor", "FreeTurbulence",
                "#风阻系数选型", "DragCoefficient", "DragUsed", "DragRange", "FittingDrag", "SurfaceRoughness",
                "#校核要求", "RequiredSafetyFactor", "ReqFilmSF", "SurvivalSF", "MinAngle", "OverPressureK",
                "OverPressure", "#拉点强度", "BridleAngle", "LoadNonUniformity", "PullRating"]
_RESULT_FORCE = ["#风", "SpeedTarget", "ActualWindPressure", "GustTarget",
                 "#水平力", "HorizontalForce", "CableDrag", "TotalHorizontalForce",
                 "#缆绳受力", "TetherTension", "AnchorTension", "PeakTension"]
_RESULT_STATE = ["#姿态", "TopAngle", "CableDrift", "CableLength", "CableWeight",
                 "#膜材与拉点", "ReqOverPressure", "FilmStress", "PullLoad", "PullSF"]
_RESULT_SURV = ["#风", "SurvSpeedTarget", "SurvActualWindPressure",
                "#姿态（缆长不变）", "SurvHeight", "SurvDrift", "SurvAngle",
                "#缆绳受力", "SurvTetherTension", "SurvPeakTension",
                "#膜材与拉点", "SurvFilmSF", "SurvPullSF"]

# 固定在页面顶部的“设计结论与关键指标”：(键, 行, 列, 占行, 占列)，共 12 列
HEADER_GRID = (("Conclusion", 0, 0, 1, 12), ("SurvConclusion", 1, 0, 1, 12),
               ("StaticNet", 2, 0, 1, 3), ("NetBuoyancy", 2, 3, 1, 3), ("MaxWindSpeed", 2, 6, 1, 6),
               ("SafetyFactor", 3, 0, 1, 3), ("SurvSafetyFactor", 3, 3, 1, 3), ("FilmSF", 3, 6, 1, 3),
               ("IncludedAngle", 3, 9, 1, 3))
HEADER_LABELS = {"StaticNet": "静净浮力（未计缆）：", "NetBuoyancy": "净浮力（扣缆绳）：",
                 "SafetyFactor": "缆绳安全系数·工作：", "SurvSafetyFactor": "缆绳安全系数·生存：",
                 "FilmSF": "膜材安全系数：", "IncludedAngle": "锚点悬链角："}

PLANS = {
    "Sphere": {
        "page": "SpherePage",
        "main": "horizontalLayout_SphereMain",
        "columns": [
            ("groupBox_SphereGeometry", "① 外形与材料",
             ["#外形", "Diameter", "Ratio", "Height", "Volume", "Area", "WindwardArea",
              "#缝制与开片", "DivideNumber", "SewWidth", "SewArea",
              "#膜材", "FilmUnitWeight", "FilmWeight", "FilmStrength", "SeamEfficiency",
              "#帆配置", ("obj", "layout_SailType"), ("obj", "widget_PocketSail"), ("obj", "widget_WingSail")]),
            ("groupBox_SphereMaterial", "② 场地·气体·浮力", _COMMON_COL2),
            ("groupBox_SphereLoad", "③ 副气囊与重量清单", _COMMON_COL3),
            ("groupBox_SphereCable", "④ 系留缆绳与风", [k for k in _COMMON_COL4 if k != "SurfaceRoughness"]),
        ],
    },
    "AirShip": {
        "page": "AirshipPage",
        "main": "horizontalLayout_AirShipMain",
        "columns": [
            ("groupBox_AirShipGeometry", "① 外形与材料",
             ["#外形", "Length", "DLRatio", "CenterRatio", "Diameter", "Volume", "SurfaceArea", "WindwardArea",
              "#缝制与开片", "DivideNumber", "SewWidth", "SewArea",
              "#膜材", "FilmUnitWeight", "FilmWeight", "FilmStrength", "SeamEfficiency",
              "#尾翼", ("obj", "widget_AirShipTail"), "FinCount", "FinAspect", "FinThickness", "FinPlanform", "FinSpan",
              "FinChord", "FinAreaRatio", "FinVolumeGeo", "TailDragUsed",
              "#气动与稳定性", "AoA", "CLAlpha", "InducedK", "CLAlphaUsed", "StabilityMargin"]),
            ("groupBox_AirShipMaterial", "② 场地·气体·浮力", _COMMON_COL2),
            ("groupBox_AirShipLoad", "③ 副气囊与重量清单", _COMMON_COL3),
            ("groupBox_AirShipCable", "④ 系留缆绳与风", _COMMON_COL4),
        ],
    },
}
for _prefix in PLANS:
    PLANS[_prefix]["banner"] = [cell[0] for cell in HEADER_GRID]
    force = list(_RESULT_FORCE)
    if _prefix == "AirShip":
        force.insert(force.index("TotalHorizontalForce") + 1, "AeroLift")
    PLANS[_prefix]["results"] = [("⑤-1 工作风 · 风与受力", force), ("⑤-2 工作风 · 姿态与强度", _RESULT_STATE),
                                 ("⑤-3 生存风校核", _RESULT_SURV)]


# ----------------------------------------------------------------- 布局工具
def find_item(layout, target):
    """在布局树中查找 target（控件或子布局），返回 (父布局, 下标)。"""
    if layout is None:
        return None
    for index in range(layout.count()):
        item = layout.itemAt(index)
        if item is None:
            continue
        if item.widget() is target or item.layout() is target:
            return layout, index
        child = item.layout()
        if child is None and item.widget() is not None:
            inner = item.widget()
            if isinstance(inner, QScrollArea) and inner.widget() is not None:
                inner = inner.widget()
            child = inner.layout()
        if child is not None:
            found = find_item(child, target)
            if found:
                return found
    return None


def take_row(root_layout, widget):
    """取出包含 widget 的行布局（从原位置移除并断开父级），失败返回 None。"""
    found = find_item(root_layout, widget)
    if not found:
        return None
    row, _ = found
    parent = find_item(root_layout, row)
    if not parent:
        return None
    parent_layout, index = parent
    item = parent_layout.takeAt(index)
    taken = item.layout()
    if taken is not None:
        taken.setParent(None)
    return taken


def row_widgets(row):
    return [row.itemAt(i).widget() for i in range(row.count()) if row.itemAt(i).widget() is not None]


def set_row_visible(row, visible):
    for widget in row_widgets(row):
        widget.setVisible(visible)


def _first_label(row):
    for widget in row_widgets(row):
        if isinstance(widget, QLabel):
            return widget
    return None


def _unit_label(row, field):
    widgets = row_widgets(row)
    if field in widgets:
        position = widgets.index(field)
        for widget in widgets[position + 1:]:
            if isinstance(widget, QLabel):
                return widget
    return None


class SectionLabel(QLabel):
    """可点击的节标题，点击展开/折叠本节。"""
    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


def _section_row(title, page):
    collapsed = title.endswith("|折叠")
    title = title.replace("|折叠", "")
    row = QHBoxLayout()
    row.setObjectName("horizontalLayout_Section")
    label = SectionLabel(("▸ " if collapsed else "▾ ") + title, page)
    label.setObjectName("SectionLabel_" + title)
    label.setCursor(Qt.PointingHandCursor)
    label.setToolTip("点击展开 / 折叠本节")
    label.setProperty("title", title)
    label.setProperty("collapsed", collapsed)
    row.addWidget(label)
    return row


def _separator(page):
    line = QFrame(page)
    line.setFrameShape(QFrame.HLine)
    line.setObjectName("line_group")
    return line


class ConclusionBox(QTextEdit):
    """只读、自动换行、高度随文字行数变化的结论框；接口与 QLineEdit 一致（setText / text）。"""
    MAX_LINES = 4

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setLineWrapMode(QTextEdit.WidgetWidth)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.document().setDocumentMargin(3)
        self._fitting = False
        self._fit()

    def setText(self, text):
        self.setPlainText(text)
        self._fit()

    def text(self):
        return self.toPlainText()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit()

    def _fit(self):
        if self._fitting:
            return
        self._fitting = True
        try:
            width = self.viewport().width()
            if width > 20:
                self.document().setTextWidth(width)
            line = self.fontMetrics().lineSpacing()
            content = int(self.document().size().height()) + 2 * self.frameWidth()
            self.setFixedHeight(min(max(content, line + 10), self.MAX_LINES * line + 10))
        finally:
            self._fitting = False


def _make_field(page, prefix, key, spec, recalc):
    """创建输入/输出/下拉字段，返回 (行布局, 控件)。"""
    row = QHBoxLayout()
    row.setObjectName(f"horizontalLayout_{prefix}{key}")
    row.addWidget(QLabel(spec["label"], page))
    if spec["kind"] == "combo":
        field = QComboBox(page)
        field.setObjectName(f"{prefix}{key}ComboBox")
        field.addItems(spec["items"])
        field.setStyleSheet(INPUT_STYLE)
        if key == "WindTerrain":
            field.setCurrentIndex(1)
        field.currentTextChanged.connect(recalc)
        setattr_ui(page, f"{prefix}{key}ComboBox", field)
    elif spec["kind"] == "text":
        field = ConclusionBox(page)
        field.setObjectName(f"{prefix}{key}LineEdit")
        setattr_ui(page, f"{prefix}{key}LineEdit", field)
    else:
        field = QLineEdit(page)
        field.setObjectName(f"{prefix}{key}LineEdit")
        if spec["kind"] == "in":
            field.setText(PAGE_DEFAULTS.get(prefix, {}).get(key, spec["default"]))
            field.setStyleSheet(INPUT_STYLE)
            field.setPlaceholderText(spec["placeholder"])
            field.textChanged.connect(recalc)
        else:
            field.setReadOnly(True)
        setattr_ui(page, f"{prefix}{key}LineEdit", field)
    if spec["tip"]:
        field.setToolTip(spec["tip"])
    field.setProperty("autoBound", True)
    row.addWidget(field)
    row.addWidget(QLabel(spec["unit"], page))
    for index, value in enumerate(ROW_STRETCH):
        row.setStretch(index, value)
    return row, field


_UI = {}


def setattr_ui(page, name, widget):
    setattr(_UI["ui"], name, widget)


def _resolve_existing(ui, prefix, key):
    for name in (f"{prefix}{key}LineEdit", f"{prefix}{key}ComboBox", f"{key}LineEdit"):
        widget = getattr(ui, name, None)
        if widget is not None:
            return widget
    return None


def _apply_override(row, field, override):
    if not override:
        return
    if "label" in override:
        label = _first_label(row)
        if label is not None:
            label.setText(override["label"])
    if "unit" in override:
        unit = _unit_label(row, field)
        if unit is not None:
            unit.setText(override["unit"])
    if "placeholder" in override and hasattr(field, "setPlaceholderText"):
        field.setPlaceholderText(override["placeholder"])


def _clear_group(group):
    layout = group.layout()
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None and isinstance(widget, QFrame):
            widget.hide()
        child = item.layout()
        if child is not None:
            child.setParent(None)


def _new_group(page, name, title):
    group = QGroupBox(title, page)
    group.setObjectName(name)
    layout = QVBoxLayout(group)
    layout.setContentsMargins(10, 10, 10, 10)
    layout.setSpacing(4)
    return group, layout


def _fill(ui, page, prefix, layout, items, recalc, rows):
    for item in items:
        if isinstance(item, tuple) and item[0] == "obj":
            obj = getattr(ui, item[1], None)
            if obj is None:
                logging.error(f"界面对象 {item[1]} 不存在")
                continue
            found = find_item(page.layout(), obj)
            if found:
                taken = found[0].takeAt(found[1])
                if taken.layout() is not None:
                    taken.layout().setParent(None)
            if isinstance(obj, QWidget):
                layout.addWidget(obj)
            else:
                layout.addLayout(obj)
            continue
        if item == "-":
            layout.addWidget(_separator(page))
            continue
        if item.startswith("#"):
            layout.addLayout(_section_row(item[1:], page))
            continue
        summary = item.startswith("^")
        item = item.lstrip("^")
        widget = _resolve_existing(ui, prefix, item)
        if widget is not None:
            row = take_row(page.layout(), widget)
            if row is None:
                logging.error(f"未找到 {item} 所在行")
                continue
            _apply_override(row, widget, OVERRIDES.get(item))
        else:
            spec = FIELDS.get(item)
            if spec is None:
                logging.error(f"字段 {item} 既不存在也未登记")
                continue
            row, _ = _make_field(page, prefix, item, spec, recalc)
        row.setProperty("summary", summary)
        layout.addLayout(row)
        rows[item] = row


def _vertical_root(page):
    """页面根布局必须是纵向的；飞艇页原为横向布局，需把原有内容套入一个纵向容器。"""
    layout = page.layout()
    if isinstance(layout, QVBoxLayout):
        return layout
    container = QWidget(page)
    container.setObjectName("widget_PageContainer")
    vertical = QVBoxLayout(container)
    vertical.setContentsMargins(0, 0, 0, 0)
    vertical.setSpacing(layout.spacing())
    items = []
    while layout.count():
        items.append(layout.takeAt(0))
    for item in items:
        if item.layout() is not None:
            item.layout().setParent(None)
            vertical.addLayout(item.layout())
        elif item.widget() is not None:
            vertical.addWidget(item.widget())
        else:
            vertical.addItem(item)
    layout.addWidget(container)
    return vertical


_SECTIONS = {}


def _set_section(label, body, expanded):
    body.setVisible(expanded)
    label.setText(("▾ " if expanded else "▸ ") + label.property("title"))


def set_all_sections(prefix, expanded):
    for label, body in _SECTIONS.get(prefix, []):
        _set_section(label, body, expanded)


def _assemble_column(prefix, group_layout, holder):
    """把一列的行按“节头 + 汇总行 + 可折叠正文”放入分组。"""
    section = None

    def flush():
        if section is None:
            return
        header, summaries, body_items = section
        group_layout.addLayout(header)
        for row in summaries:
            group_layout.addLayout(row)
        body = QWidget()
        body.setProperty("sectionBody", True)
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(4)
        for item in body_items:
            if item.layout() is not None:
                item.layout().setParent(None)
                body_layout.addLayout(item.layout())
            elif item.widget() is not None:
                body_layout.addWidget(item.widget())
        group_layout.addWidget(body)
        label = header.itemAt(0).widget()
        collapsed = bool(label.property("collapsed"))
        _set_section(label, body, not collapsed)
        label.clicked.connect(lambda lb=label, bd=body: _set_section(lb, bd, bd.isHidden()))
        _SECTIONS.setdefault(prefix, []).append((label, body))

    while holder.count():
        item = holder.takeAt(0)
        lay = item.layout()
        if lay is not None and lay.objectName() == "horizontalLayout_Section":
            flush()
            lay.setParent(None)
            section = (lay, [], [])
        elif section is None:
            if lay is not None:
                lay.setParent(None)
                group_layout.addLayout(lay)
            elif item.widget() is not None:
                group_layout.addWidget(item.widget())
        elif lay is not None and lay.property("summary"):
            lay.setParent(None)
            section[1].append(lay)
        else:
            section[2].append(item)
    flush()


def _build_header(page, prefix, rows, recalc, ui):
    """页面顶部固定的结论与关键指标（网格），含全部展开/折叠按钮。"""
    header = QGroupBox("设计结论与关键指标", page)
    header.setObjectName(f"groupBox_{prefix}Banner")
    grid = QGridLayout(header)
    grid.setContentsMargins(10, 10, 10, 6)
    grid.setHorizontalSpacing(14)
    grid.setVerticalSpacing(2)
    for column in range(12):
        grid.setColumnStretch(column, 1)
    for key, r, c, rs, cs in HEADER_GRID:
        row = rows.get(key)
        if row is None:
            continue
        label = _first_label(row)
        if label is not None and key in HEADER_LABELS:
            label.setText(HEADER_LABELS[key])
        grid.addLayout(row, r, c, rs, cs)
    expand = QPushButton("全部展开", header)
    collapse = QPushButton("全部折叠", header)
    for button, flag in ((expand, True), (collapse, False)):
        button.setObjectName(f"ToggleAllButton_{prefix}_{int(flag)}")
        button.setFixedWidth(92)
        button.setToolTip("展开 / 折叠本页全部分节")
        button.clicked.connect(lambda _=False, f=flag: set_all_sections(prefix, f))
    grid.addWidget(expand, 0, 12)
    grid.addWidget(collapse, 1, 12)
    for row_index, (key, text, tip) in enumerate((
            ("Save", "保存数据", "把本页全部输入保存为文本数据文件（.txt），以后可用“打开数据”恢复"),
            ("Open", "打开数据", "读取之前保存的数据文件并重新计算；文件属于另一类浮空器时自动切换到对应页面"))):
        button = QPushButton(text, header)
        button.setObjectName(f"{key}DataButton_{prefix}")
        button.setFixedWidth(92)
        button.setToolTip(tip)
        setattr(ui, f"{prefix}{key}DataButton", button)
        grid.addWidget(button, 2 + row_index, 12)
    grid.setColumnStretch(12, 0)
    return header


def build_page(ui, prefix, recalc):
    """按 PLANS 重组页面；返回 {键: 行布局}，供显示/隐藏使用。

    页面 = 固定顶部（结论与关键指标）+ 可滚动正文（四列输入 + 校核结果明细）。
    """
    _UI["ui"] = ui
    plan = PLANS[prefix]
    page = getattr(ui, plan["page"])
    rows = {}
    _SECTIONS[prefix] = []
    root = _vertical_root(page)
    groups = [getattr(ui, name) for name, _, _ in plan["columns"]]

    # 先按计划把全部行（含结论条、校核结果）取出并放入临时容器，再清空原分组，最后按序放回
    staging = {}
    for (name, title, items), group in zip(plan["columns"], groups):
        holder_layout = QVBoxLayout()
        _fill(ui, page, prefix, holder_layout, items, recalc, rows)
        staging[name] = holder_layout

    header_holder = QVBoxLayout()
    _fill(ui, page, prefix, header_holder, plan["banner"], recalc, rows)
    result_boxes = []
    for index, (title, items) in enumerate(plan["results"]):
        box, box_layout = _new_group(page, f"groupBox_{prefix}Result{index + 1}", title)
        setattr(ui, f"groupBox_{prefix}Result{index + 1}", box)
        holder = QVBoxLayout()
        _fill(ui, page, prefix, holder, items, recalc, rows)
        _assemble_column(prefix, box_layout, holder)
        box_layout.addStretch(1)
        result_boxes.append(box)

    for group in groups:
        _clear_group(group)
    for (name, title, _), group in zip(plan["columns"], groups):
        group.setTitle(title)
        _assemble_column(prefix, group.layout(), staging[name])
        group.layout().addStretch(1)

    main = getattr(ui, plan["main"])
    for index in range(main.count()):
        main.setStretch(index, 1)

    while header_holder.count():
        header_holder.takeAt(0).layout().setParent(None)
    header = _build_header(page, prefix, rows, recalc, ui)
    setattr(ui, f"groupBox_{prefix}Banner", header)
    root.insertWidget(0, header)
    results = QHBoxLayout()
    results.setObjectName(f"horizontalLayout_{prefix}Results")
    for box in result_boxes:
        results.addWidget(box, 1)
    main_index = find_item(root, main)
    results_pos = (main_index[1] + 1) if main_index and main_index[0] is root else root.count()
    root.insertLayout(results_pos, results)
    diagram_box, diagram_layout = _new_group(page, f"groupBox_{prefix}Diagrams", "⑥ 设计示意图")
    panel = DiagramPanel("直径" if prefix == "Sphere" else "长度")
    diagram_layout.addWidget(panel)
    setattr(ui, f"{prefix}Diagrams", panel)
    root.insertWidget(results_pos + 1, diagram_box)

    for widget in page.findChildren(QLineEdit):
        widget.setMinimumWidth(0)
    missing = apply_tips(ui, page, prefix)
    if missing:
        logging.warning(f"以下控件缺少悬停提示：{', '.join(missing)}")

    # 顶部固定，其余放入可滚动正文
    items = []
    while root.count() > 1:
        items.append(root.takeAt(1))
    body = QWidget(page)
    body.setObjectName(f"widget_{prefix}Body")
    body_layout = QVBoxLayout(body)
    body_layout.setContentsMargins(0, 0, 0, 0)
    body_layout.setSpacing(root.spacing())
    for item in items:
        if item.layout() is not None:
            item.layout().setParent(None)
            body_layout.addLayout(item.layout())
        elif item.widget() is not None:
            body_layout.addWidget(item.widget())
        else:
            body_layout.addItem(item)
    scroll = QScrollArea(page)
    scroll.setObjectName(f"scrollArea_{prefix}Body")
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.setWidget(body)
    root.addWidget(scroll, 1)
    return rows


def update_wind_mode_rows(ui, prefix, rows, mode_index):
    """按风速输入方式切换风速/风廓线行的可见性与标签。"""
    set_row_visible(rows["SurvivalWind"], mode_index != 2)
    set_row_visible(rows["WindPressure"], mode_index != 2)
    set_row_visible(rows["WindTable"], mode_index == 2)
    set_row_visible(rows["SurvivalWindTable"], mode_index == 2)
    label = _first_label(rows["WindPressure"])
    survival_label = _first_label(rows["SurvivalWind"])
    if mode_index == 0:
        label.setText("工作风速（离地10 m）：")
        survival_label.setText("生存风速（离地10 m）：")
    elif mode_index == 1:
        label.setText("工作风速（目标高度）：")
        survival_label.setText("生存风速（目标高度）：")
