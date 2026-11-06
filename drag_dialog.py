"""风阻系数选型对话框：结果、构成、依据曲线与影响因素一览。"""
import math

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PyQt5.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QTextBrowser, QVBoxLayout,
                             QWidget)

import aerostat_drag as drag

FACTORS = (
    ("雷诺数（风速×尺寸）", "圆球 Re>2×10⁵ 出现阻力危机，CD 可从 0.47 骤降到 0.1～0.3；艇身摩擦系数随 Re 缓慢下降",
     "球体不计危机降阻；艇身按 Cf(Re) 计入"),
    ("长径比", "太短：压差阻力大；太长：湿面积大。同体积下 CD_V 最小约在长径比 4～6", "Hoerner 形状因子 + 湿面积"),
    ("表面粗糙度 / 接缝", "TPU 焊缝带、瓣缝、皱褶使摩擦阻力增加 10%～40%", "艇身：等效粗糙度 ks；球体：并入基准与不确定度"),
    ("来流湍流", "大气边界层湍流强度 10%～25%，使圆球临界雷诺数大幅降低，降阻不可复现", "球体不计危机降阻"),
    ("囊体饱满度 / 欠压", "内压低于来流动压时迎风面凹陷、尾流变宽：球体 +15%，艇身 +30%（上限）", "按内压 ÷ 动压折算（工程假设）"),
    ("附件、吊带、绳索连接", "拉点、吊带、充气口、阀门等附加阻力，约 +0.01～0.03", "附件阻力增量 ΔCD（输入）"),
    ("攻角 / 侧滑", "艇身阻力随攻角显著增大", "诱导阻力另计；此处为零攻角 CD"),
    ("尾翼 / 控制面", "尾翼自身摩擦与干扰阻力", "尾翼阻力系数另计"),
    ("阵风与风切变", "峰值风压为平均风压的 β 倍", "阵风系数 β 另计，CD 取准定常值"),
    ("涡激振动 / 侧向力", "圆球 Re 10⁵～10⁶ 有周期性侧向力，系留气球易横向摆动", "未计入阻力，请留足安全系数"),
    ("雨、冰、污染", "增加表面粗糙度与迎风面积", "未计入，必要时加大 ks 与 ΔCD"),
)

REFERENCES = (
    "Hoerner S.F., Fluid-Dynamic Drag, 1965：圆球 0.47；回转体阻力公式 CD,f = Cf·[1 + 1.5(d/l)^1.5 + 7(d/l)^3]·S_wet/A_f",
    "Achenbach E., Experiments on the flow past spheres at very high Reynolds numbers, J. Fluid Mech. 54 (1972)：粗糙度使阻力危机提前、超临界 CD 升高",
    "Morrison F.A., Data Correlation for Drag Coefficient for Sphere (2013)：光滑圆球 CD–Re 相关式，Re ≤ 10⁶",
    "Schlichting H., Boundary-Layer Theory：湍流平板摩擦 Cf = 0.455/(lg Re)^2.58；粗糙平板 Cf = (1.89 + 1.62 lg(l/ks))^-2.5",
    "Khoury G.A.（编），Airship Technology：艇身以 V^(2/3) 为参考面积的阻力系数 CD_V，典型约 0.02～0.04",
)


class ChartWidget(QWidget):
    """简易折线图：支持对数横轴、水平线、阴影带、竖直标记和标注点。"""

    def __init__(self, title, xlabel, ylabel, logx=False, parent=None):
        super().__init__(parent)
        self.title, self.xlabel, self.ylabel, self.logx = title, xlabel, ylabel, logx
        self.series, self.hlines, self.bands, self.vmarkers, self.points = [], [], [], [], []
        self.xrange = (0.0, 1.0)
        self.yrange = (0.0, 1.0)
        self.setMinimumSize(460, 300)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def _tx(self, x, rect):
        lo, hi = self.xrange
        if self.logx:
            x, lo, hi = math.log10(max(x, 1e-12)), math.log10(lo), math.log10(hi)
        return rect.left() + (x - lo) / (hi - lo) * rect.width()

    def _ty(self, y, rect):
        lo, hi = self.yrange
        return rect.bottom() - (y - lo) / (hi - lo) * rect.height()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#ffffff"))
        painter.setFont(QFont("Microsoft YaHei", 9))
        rect = QRectF(58, 34, self.width() - 78, self.height() - 92)
        painter.setPen(QColor("#1f2d3d"))
        title_font = QFont("Microsoft YaHei", 10)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.drawText(QRectF(0, 6, self.width(), 24), Qt.AlignHCenter | Qt.AlignVCenter, self.title)
        painter.setFont(QFont("Microsoft YaHei", 9))

        for y0, y1, color, label in self.bands:
            top, bottom = self._ty(y1, rect), self._ty(y0, rect)
            painter.fillRect(QRectF(rect.left(), top, rect.width(), bottom - top), QColor(color))
        painter.setPen(QPen(QColor("#e3e8ee"), 1))
        for tick in self._yticks():
            y = self._ty(tick, rect)
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
        for tick in self._xticks():
            x = self._tx(tick, rect)
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
        painter.setPen(QPen(QColor("#5f6b7a"), 1))
        painter.drawRect(rect)
        for tick in self._yticks():
            painter.drawText(QRectF(0, self._ty(tick, rect) - 9, rect.left() - 6, 18), Qt.AlignRight | Qt.AlignVCenter,
                             f"{tick:g}")
        for tick in self._xticks():
            label = f"{tick:.0e}".replace("e+0", "×10^").replace("e+", "×10^") if self.logx else f"{tick:g}"
            painter.drawText(QRectF(self._tx(tick, rect) - 40, rect.bottom() + 4, 80, 18), Qt.AlignCenter, label)
        painter.drawText(QRectF(rect.left(), self.height() - 26, rect.width(), 20), Qt.AlignCenter, self.xlabel)
        painter.save()
        painter.translate(14, rect.center().y())
        painter.rotate(-90)
        painter.drawText(QRectF(-rect.height() / 2, -10, rect.height(), 20), Qt.AlignCenter, self.ylabel)
        painter.restore()

        painter.setClipRect(rect.adjusted(-1, -1, 1, 1))
        for y, label, color in self.hlines:
            painter.setPen(QPen(QColor(color), 1.6, Qt.DashLine))
            painter.drawLine(QPointF(rect.left(), self._ty(y, rect)), QPointF(rect.right(), self._ty(y, rect)))
        for name, color, pts in self.series:
            painter.setPen(QPen(QColor(color), 2.2))
            polygon = QPolygonF([QPointF(self._tx(x, rect), self._ty(y, rect)) for x, y in pts])
            painter.drawPolyline(polygon)
        for x, label, color in self.vmarkers:
            painter.setPen(QPen(QColor(color), 1.6, Qt.DashDotLine))
            xx = min(max(self._tx(x, rect), rect.left()), rect.right())
            painter.drawLine(QPointF(xx, rect.top()), QPointF(xx, rect.bottom()))
        painter.setClipping(False)
        for x, y, label, color in self.points:
            px = min(max(self._tx(x, rect), rect.left()), rect.right())
            py = min(max(self._ty(y, rect), rect.top()), rect.bottom())
            painter.setPen(QPen(QColor(color), 2))
            painter.setBrush(QColor(color))
            painter.drawEllipse(QPointF(px, py), 5, 5)
            painter.setPen(QColor(color))
            align = Qt.AlignLeft if px < rect.center().x() else Qt.AlignRight
            box = QRectF(px + 8, py - 22, 230, 18) if align == Qt.AlignLeft else QRectF(px - 238, py - 22, 230, 18)
            painter.drawText(box, align | Qt.AlignVCenter, label)

        legend_x, legend_y = rect.left() + 8, rect.top() + 6
        entries = [(name, color) for name, color, _ in self.series] + [(label, color) for _, label, color in self.hlines] \
            + [(label, color) for _, _, color, label in self.bands if label] + [(label, color) for _, label, color in self.vmarkers]
        for label, color in entries:
            painter.setPen(QColor("#1f2d3d"))
            painter.fillRect(QRectF(legend_x, legend_y + 5, 14, 4), QColor(color))
            painter.drawText(QRectF(legend_x + 20, legend_y - 2, 330, 18), Qt.AlignLeft | Qt.AlignVCenter, label)
            legend_y += 18
        painter.end()

    def _yticks(self):
        lo, hi = self.yrange
        step = (hi - lo) / 5.0
        magnitude = 10 ** math.floor(math.log10(step))
        step = min((m * magnitude for m in (1, 2, 2.5, 5, 10) if m * magnitude >= step), default=step)
        first = math.ceil(lo / step) * step
        ticks, value = [], first
        while value <= hi + 1e-12:
            ticks.append(round(value, 10))
            value += step
        return ticks

    def _xticks(self):
        lo, hi = self.xrange
        if self.logx:
            return [10 ** e for e in range(math.ceil(math.log10(lo)), math.floor(math.log10(hi)) + 1)]
        step = (hi - lo) / 6.0
        magnitude = 10 ** math.floor(math.log10(step))
        step = min((m * magnitude for m in (1, 2, 2.5, 5, 10) if m * magnitude >= step), default=step)
        first = math.ceil(lo / step) * step
        ticks, value = [], first
        while value <= hi + 1e-12:
            ticks.append(round(value, 10))
            value += step
        return ticks


def _fmt_re(re):
    exponent = int(math.floor(math.log10(re))) if re > 0 else 0
    return f"{re / 10 ** exponent:.2f}×10<sup>{exponent}</sup>"


def report_html(report):
    result = report["result"]
    kind = "圆球" if report["kind"] == "sphere" else "飞艇艇身"
    rows = "".join(
        f"<tr><td>{c.name}</td><td align='right'><b>{c.value:.4f}</b></td><td>{c.basis}</td></tr>"
        for c in result.components)
    manual = ""
    if report["manual"] is not None:
        manual = (f"<p style='color:#ef6c00'>当前为<b>手动</b>输入 CD = {report['manual']:.3f}，"
                  f"与选型模型推荐值 {result.cd:.3f} 相差 {report['manual'] - result.cd:+.3f}。</p>")
    extra = ""
    if report["kind"] == "airship":
        e = result.extra
        extra = (f"<p>长径比 λ = {e['fineness']:.2f}；形状因子 = {e['form_factor']:.3f}；湿面积/最大截面积 = {e['wet_ratio']:.1f}；"
                 f"体积基准 CD<sub>V</sub>（参考面积 V<sup>2/3</sup>）= <b>{e['cd_volume']:.4f}</b>"
                 "（艇身典型 0.02～0.04）。</p>")
    else:
        smooth = result.extra.get("smooth_cd")
        extra = ("<p>光滑圆球理论值（Morrison 相关式）："
                 + (f"{smooth:.3f}" if smooth is not None else "Re 超出相关式适用范围（>10⁶），超临界光滑球约 0.1～0.3")
                 + "。设计值不采用该降阻。</p>")
    notes = "".join(f"<li>{n}</li>" for n in result.notes)
    notes = f"<p><b>提示</b></p><ul>{notes}</ul>" if notes else ""
    factors = "".join(f"<tr><td>{a}</td><td>{b}</td><td>{c}</td></tr>" for a, b, c in FACTORS)
    references = "".join(f"<li>{r}</li>" for r in REFERENCES)
    return (
        "<body style='font-family:Microsoft YaHei; font-size:10pt'>"
        f"<h3>{kind}风阻系数选型结果：CD = {report['used']:.3f}"
        f"（合理范围 {result.low:.3f} ～ {result.high:.3f}）</h3>"
        f"<p>工作风速（目标高度）{report['speed']:.1f} m/s，空气密度 {report['density']:.3f} kg/m³，"
        f"特征长度 {(report['length'] if report['kind'] == 'airship' else report['diameter']):.2f} m，"
        f"雷诺数 Re = {_fmt_re(result.reynolds)}；{result.regime}。</p>"
        f"{manual}"
        "<table border='1' cellspacing='0' cellpadding='4' width='100%'>"
        "<tr bgcolor='#e3f2fd'><th>构成</th><th>CD</th><th>依据</th></tr>" + rows +
        f"<tr bgcolor='#f5f5f5'><td><b>合计</b></td><td align='right'><b>{result.cd:.4f}</b></td><td></td></tr></table>"
        f"{extra}{notes}"
        "<h4>影响风阻系数的因素及模型处理</h4>"
        "<table border='1' cellspacing='0' cellpadding='4' width='100%'>"
        "<tr bgcolor='#e3f2fd'><th>因素</th><th>影响方向与量级</th><th>模型处理</th></tr>" + factors + "</table>"
        "<h4>数据依据</h4><ul>" + references + "</ul>"
        "<p style='color:#8a6d3b'>说明：以上为文献中的经典经验关系，适用于定常来流、Ma&lt;0.1；"
        "公式未在本机联网复核原文，重要设计请以风洞/飞行试验数据为准，并可在输入框手动覆盖。</p></body>")


def build_charts(report):
    """按页面类型生成依据曲线。"""
    result = report["result"]
    charts = []
    if report["kind"] == "sphere":
        chart = ChartWidget("圆球阻力系数随雷诺数变化（光滑球曲线与设计值）", "雷诺数 Re", "阻力系数 CD", logx=True)
        chart.xrange, chart.yrange = (1e2, 1e7), (0.0, 1.2)
        chart.series.append(("光滑圆球（Morrison，Re≤10⁶）", "#1976d2", drag.sphere_curve(120, 1e2, 1e6)))
        low, high = drag.SPHERE_DESIGN_BAND
        chart.bands.append((low, high, "#e8f5e9", "经验范围 0.45～0.50"))
        chart.hlines.append((result.cd, f"设计值 {result.cd:.3f}", "#d32f2f"))
        chart.vmarkers.append((max(result.reynolds, 1e2), f"当前 Re = {result.reynolds:.2e}", "#ef6c00"))
        chart.points.append((min(result.reynolds, 1e7), result.cd, "当前工况（不计阻力危机降阻）", "#d32f2f"))
        charts.append(chart)
    else:
        volume = report["volume"]
        speed = max(report["speed"], 0.1)
        sweep = drag.airship_fineness_sweep(volume, speed, report["density"], report["temp"], report["ks"])
        lam = result.extra["fineness"]
        c1 = ChartWidget("等体积艇身阻力系数 CD,V（参考面积 V^(2/3)）随长径比变化", "长径比 L/D", "CD,V")
        c1.xrange = (1.5, 10.0)
        values = [row[2] for row in sweep]
        c1.yrange = (0.0, max(values) * 1.15)
        c1.series.append(("艇身（不含附件）", "#1976d2", [(r[0], r[2]) for r in sweep]))
        best = min(sweep, key=lambda r: r[2])
        c1.points.append((best[0], best[2], f"最小 λ≈{best[0]:.2f}", "#2e7d32"))
        c1.vmarkers.append((lam, f"当前 λ = {lam:.2f}", "#ef6c00"))
        c1.points.append((lam, result.extra["cd_volume"], f"当前（含附件）{result.extra['cd_volume']:.4f}", "#d32f2f"))
        charts.append(c1)
        c2 = ChartWidget("等体积艇身阻力系数 CD,f（参考面积 最大截面积）随长径比变化", "长径比 L/D", "CD,f")
        c2.xrange = (1.5, 10.0)
        values = [row[1] for row in sweep]
        c2.yrange = (0.0, max(values) * 1.15)
        c2.series.append(("艇身（不含附件）", "#1976d2", [(r[0], r[1]) for r in sweep]))
        c2.vmarkers.append((lam, f"当前 λ = {lam:.2f}", "#ef6c00"))
        c2.points.append((lam, result.cd, f"当前（含附件）{result.cd:.4f}", "#d32f2f"))
        charts.append(c2)
    return charts


class DragDialog(QDialog):
    def __init__(self, report, apply_value, clear_value, parent=None):
        super().__init__(parent)
        self.setWindowTitle("风阻系数选型模型")
        self.resize(1180, 760)
        self._apply_value, self._clear_value = apply_value, clear_value
        self._report = report
        layout = QHBoxLayout(self)
        left = QVBoxLayout()
        for chart in build_charts(report):
            left.addWidget(chart, 1)
        buttons = QHBoxLayout()
        apply_button = QPushButton("采用推荐值（写入输入框）")
        auto_button = QPushButton("恢复自动")
        close_button = QPushButton("关闭")
        apply_button.clicked.connect(self._apply)
        auto_button.clicked.connect(self._auto)
        close_button.clicked.connect(self.accept)
        for button in (apply_button, auto_button, close_button):
            buttons.addWidget(button)
        left.addLayout(buttons)
        layout.addLayout(left, 5)
        text = QTextBrowser()
        text.setOpenExternalLinks(False)
        text.setHtml(report_html(report))
        layout.addWidget(text, 6)

    def _apply(self):
        self._apply_value(f"{self._report['result'].cd:.3f}")
        self.accept()

    def _auto(self):
        self._clear_value()
        self.accept()
