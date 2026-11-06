"""设计示意图：全部用 QPainter 绘制（无第三方依赖），数据由 calc_controller 在每次计算后推送。

五张图：受力与姿态（侧视，工作风/生存风）、外形示意、风廓线（含风级）、浮力与重量瀑布图、选型曲线。
"""
import logging
import math

from PyQt5.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter, QPainterPath, QPen, QPolygonF
from PyQt5.QtWidgets import (QDoubleSpinBox, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QTabWidget, QVBoxLayout,
                             QWidget)

from aerostat_model import BOTTOM_ANGLE_WARNING_DEG
from aerostat_physics import KGF_PER_KN
from aerostat_wind import BEAUFORT_UPPER, beaufort_text

_DARK = {"on": False}


def set_dark(flag):
    _DARK["on"] = bool(flag)


def _theme():
    if _DARK["on"]:
        return dict(bg="#1f2a30", fg="#eceff1", muted="#90a4ae", grid="#37474f", band="#26343b", ground="#6d4c41",
                    work="#4fc3f7", surv="#ef5350", gas="#4db6ac", air="#64b5f6", fin="#ffb74d", warn="#ffb74d",
                    ok="#81c784", bad="#ef5350")
    return dict(bg="#ffffff", fg="#263238", muted="#78909c", grid="#dfe5e9", band="#f3f6f8", ground="#a1887f",
                work="#1976d2", surv="#d32f2f", gas="#80cbc4", air="#90caf9", fin="#ffb74d", warn="#ef6c00",
                ok="#2e7d32", bad="#d32f2f")


def _color(value, alpha=255):
    color = QColor(value)
    color.setAlpha(alpha)
    return color


def _nice_step(span, target=5):
    raw = max(span, 1e-9) / target
    magnitude = 10 ** math.floor(math.log10(raw))
    for factor in (1, 2, 2.5, 5, 10):
        if raw <= factor * magnitude:
            return factor * magnitude
    return 10 * magnitude


def _text(p, x, y, s, color, align="l", bold=False, size=None):
    """y 为文字垂直中心；align：l/c/r。返回文字宽度。"""
    p.save()
    font = QFont(p.font())
    font.setBold(bold)
    if size:
        font.setPointSizeF(size)
    p.setFont(font)
    metrics = QFontMetricsF(font)
    width = metrics.horizontalAdvance(s)
    left = x if align == "l" else (x - width / 2 if align == "c" else x - width)
    p.setPen(_color(color))
    p.drawText(QPointF(left, y + metrics.ascent() - metrics.height() / 2), s)
    p.restore()
    return width


def _arrow(p, x1, y1, x2, y2, color, width=2.0, head=8.0):
    p.save()
    p.setPen(QPen(_color(color), width))
    p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
    angle = math.atan2(y2 - y1, x2 - x1)
    tip = QPolygonF([QPointF(x2, y2),
                     QPointF(x2 - head * math.cos(angle - 0.4), y2 - head * math.sin(angle - 0.4)),
                     QPointF(x2 - head * math.cos(angle + 0.4), y2 - head * math.sin(angle + 0.4))])
    p.setBrush(_color(color))
    p.drawPolygon(tip)
    p.restore()


def _dim(p, x1, y1, x2, y2, label, color, above=True):
    """双向尺寸线 + 居中标注。"""
    _arrow(p, (x1 + x2) / 2, (y1 + y2) / 2, x1, y1, color, 1.2, 6)
    _arrow(p, (x1 + x2) / 2, (y1 + y2) / 2, x2, y2, color, 1.2, 6)
    _text(p, (x1 + x2) / 2, (y1 + y2) / 2 + (-9 if above else 10), label, color, "c")


def _dashed(p, x1, y1, x2, y2, color, width=1.0):
    p.save()
    pen = QPen(_color(color), width, Qt.DashLine)
    p.setPen(pen)
    p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
    p.restore()


class Canvas(QWidget):
    """画布基类：统一背景、空数据提示和异常保护。"""

    font_pt = 9.0

    def __init__(self, min_height=320, empty_text="输入参数后自动生成"):
        super().__init__()
        self.setMinimumHeight(min_height)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.data = None
        self.empty_text = empty_text

    def set_data(self, data):
        self.data = data
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        theme = _theme()
        p.fillRect(self.rect(), _color(theme["bg"]))
        font = QFont(self.font())
        font.setPointSizeF(self.font_pt)
        p.setFont(font)
        if not self.data:
            _text(p, self.width() / 2, self.height() / 2, self.empty_text, theme["muted"], "c")
        else:
            try:
                self.draw(p, theme, self.width(), self.height())
            except Exception:  # noqa: BLE001  画图失败不能影响计算
                logging.exception("示意图绘制失败")
        p.end()

    def draw(self, p, t, w, h):
        raise NotImplementedError


# ---------------------------------------------------------------- 1. 受力与姿态
class TetherCanvas(Canvas):
    """侧视图：锚点、缆绳形状、浮空器位置、风、力与角度；工作风与生存风叠加。"""

    def draw(self, p, t, w, h):
        d = self.data
        states = d["states"]
        count = len(states)
        ml, mr, mt, mb = 100, 56, 18 * count + 86, 28 * count + 26
        aw, ah = w - ml - mr, h - mt - mb
        if aw < 100 or ah < 60:
            return
        drift_max = max([s["drift"] for s in states if s["flyable"]] + [0.5 * d["target"]])
        z_max = max([s["height"] for s in states] + [d["target"]]) * 1.06
        scale = min(aw / (drift_max * 1.18), ah / z_max)
        zoom = 1.0
        if z_max * scale < 0.45 * ah:
            zoom = min(3.0, 0.45 * ah / (z_max * scale))
        sz = scale * zoom
        y0 = mt + ah

        def X(x):
            return ml + x * scale

        def Y(z):
            return y0 - z * sz

        step = _nice_step(h and (ah / sz), 4)
        z = step
        while z * sz < ah + mt - 20:
            _dashed(p, ml - 6, Y(z), w - mr, Y(z), t["grid"])
            _text(p, w - mr + 4, Y(z), f"{z:g} m", t["muted"])
            z += step
        p.fillRect(QRectF(0, y0, w, 7), _color(t["ground"]))
        p.setPen(QPen(_color(t["ground"]), 1))
        for x in range(0, w, 9):
            p.drawLine(x, int(y0 + 7), x - 6, int(y0 + 13))
        # 风箭头（逐高度，长度 ∝ 风速）
        fns = [(fn, t[color]) for fn, color in d.get("wind_fns", [])]
        vmax = max([fn(d["target"]) for fn, _ in fns] + [0.1])
        _text(p, 8, y0 - d["target"] * sz - 16, "来风", t["muted"])
        for fraction in (0.25, 0.5, 0.75, 1.0):
            zz = d["target"] * fraction
            for index, (fn, color) in enumerate(fns):
                length = 68 * fn(zz) / vmax
                yy = Y(zz) + index * 5
                _arrow(p, ml - 14 - length, yy, ml - 14, yy, color, 1.6, 6)
        anchor = QPolygonF([QPointF(X(0), y0), QPointF(X(0) - 7, y0 + 10), QPointF(X(0) + 7, y0 + 10)])
        p.setBrush(_color(t["fg"]))
        p.setPen(Qt.NoPen)
        p.drawPolygon(anchor)
        p.setBrush(Qt.NoBrush)
        _text(p, X(0) - 10, y0 + 18, "锚点", t["muted"], "r")

        force_max = max([max(s["drag"], s["lift"]) for s in states] + [1e-9])
        arc_label_x = X(0) + 26 + 16 * count + 10
        for index in reversed(range(count)):
            s = states[index]
            color = t[s["color"]]
            path = s.get("path")
            if s["flyable"] and path:
                top_x = s["drift"]
                polyline = QPolygonF([QPointF(X(top_x - dist), Y(zz)) for dist, zz in path])
                p.setPen(QPen(_color(color), 2.4))
                p.setBrush(Qt.NoBrush)
                p.drawPolyline(polyline)
            else:
                top_x = 0.3 * drift_max
                _dashed(p, X(0), y0, X(top_x), Y(s["height"]), color, 1.6)
                _text(p, X(top_x / 2) + 6, Y(s["height"] / 2), "缆绳拖地（无平衡解）", color)
            cx, cy = X(top_x), Y(s["height"])
            hw, hh = d.get("balloon", (3.0, 3.0))
            rx, ry = min(max(hw * scale, 8), 30), min(max(hh * sz, 8), 30)
            p.setPen(QPen(_color(color), 1.6))
            p.setBrush(_color(color, 70))
            p.drawEllipse(QPointF(cx, cy), rx, ry)
            p.setBrush(Qt.NoBrush)
            _dashed(p, cx, cy + ry, cx, y0, color)
            label = f"H = {s['height']:.0f} m"
            _text(p, cx + 6, (cy + y0) / 2 - 8 + 16 * index, label, color)
            if s["flyable"]:
                yy = y0 + 30 + 24 * index
                _dim(p, X(0), yy, cx, yy, f"漂移 {s['drift']:.0f} m", color, above=False)
                radius = 26 + 16 * index
                p.setPen(QPen(_color(color), 1.4))
                p.drawArc(QRectF(X(0) - radius, y0 - radius, 2 * radius, 2 * radius), 0, int(s["angle"] * 16))
                _text(p, arc_label_x, y0 - 8 - 16 * index, f"锚点角 {s['angle']:.1f}°", color)
            drag_len = 52 * s["drag"] / force_max
            lift_len = 52 * s["lift"] / force_max
            _arrow(p, cx + rx, cy, cx + rx + max(drag_len, 4), cy, color, 2.0)
            _arrow(p, cx, cy - ry, cx, cy - ry - max(lift_len, 4), color, 2.0)
            if index == 0:
                _text(p, cx + rx + 4, cy - 11, f"风阻 {s['drag']:.0f} kgf", color)
                _text(p, cx + 8, cy - ry - max(lift_len, 4) - 4, f"净浮力 {s['lift']:.0f} kgf", color)

        metrics = QFontMetricsF(p.font())
        for index, s in enumerate(states):
            yy = 12 + 18 * index
            p.fillRect(QRectF(10, yy - 5, 12, 10), _color(t[s["color"]]))
            head = f"{s['name']}  离地10 m {s['speed10']:.1f} m/s（{beaufort_text(s['speed10'])}）"
            if s["flyable"]:
                parts = [head, f"浮空器 {s['height']:.0f} m{'（被压低）' if s['blown_down'] else ''}", f"缆长 {s['cable_length']:.0f} m",
                         f"漂移 {s['drift']:.0f} m", f"锚点角 {s['angle']:.1f}°",
                         f"风阻 {s['drag']:.0f} / 净浮力 {s['lift']:.0f} kgf", f"顶端拉力 {s['tension']:.0f} kgf"]
                # 放不下时从末尾整段舍去，避免字段被截断
                while len(parts) > 2 and metrics.horizontalAdvance("｜".join(parts)) > w - 40:
                    parts.pop()
                info = "｜".join(parts)
            else:
                info = f"{head}｜缆绳拖地：浮力撑不起缆绳"
            _text(p, 28, yy, metrics.elidedText(info, Qt.ElideRight, w - 40), t["fg"])
        note = "浮空器符号不按比例；"
        note += f"纵向放大 {zoom:.1f} 倍（角度以数值为准）" if zoom > 1.05 else "横纵比例一致"
        _text(p, w - 8, h - 10, note, t["muted"], "r")


# ---------------------------------------------------------------- 2. 外形示意
class ShapeCanvas(Canvas):
    def draw(self, p, t, w, h):
        if self.data["kind"] == "sphere":
            self._sphere(p, t, w, h)
        else:
            self._airship(p, t, w, h)

    @staticmethod
    def _info(p, t, x, y, items):
        for label, value in items:
            _text(p, x, y, label, t["muted"])
            _text(p, x + 118, y, value, t["fg"], bold=True)
            y += 20

    def _sphere(self, p, t, w, h):
        d = self.data
        a, b, aux_h = d["a"], d["b"], d["aux_h"]
        cx, cy = w * 0.32, h * 0.5 - 6
        s = min((w * 0.58 - 70) / (2 * b), (h - 110) / (2 * a))

        def X(x):
            return cx + x * s

        def Y(z):
            return cy - z * s

        body = QPainterPath()
        body.addEllipse(QRectF(X(-b), Y(a), 2 * b * s, 2 * a * s))
        p.save()
        p.setClipPath(body)
        p.fillRect(QRectF(0, 0, w, h), _color(t["gas"], 150))
        p.fillRect(QRectF(0, Y(-a + aux_h), w, h), _color(t["air"], 190))
        p.setPen(QPen(_color(t["fg"], 160), 1.4, Qt.DashLine))
        p.drawLine(QPointF(X(-b), Y(-a + aux_h)), QPointF(X(b), Y(-a + aux_h)))
        # 开片经线
        divide = max(int(d.get("divide", 0)), 0)
        p.setPen(QPen(_color(t["fg"], 70), 0.8))
        for k in range(1, divide // 2 + 1):
            p.drawEllipse(QPointF(cx, cy), b * abs(math.cos(2 * math.pi * k / divide)) * s, a * s)
        p.restore()
        p.setPen(QPen(_color(t["fg"]), 2))
        p.setBrush(Qt.NoBrush)
        p.drawPath(body)
        _text(p, cx, Y(a / 3), "氦气（主气囊）", t["fg"], "c", bold=True)
        if aux_h > 0:
            _text(p, cx, Y(-a + aux_h / 2), "副气囊（空气）", t["fg"], "c", bold=True)
        _dim(p, X(-b), Y(-a) + 24, X(b), Y(-a) + 24, f"D = {2 * b:.2f} m", t["work"], above=False)
        _dim(p, X(b) + 30, Y(a), X(b) + 30, Y(-a), "", t["work"])
        _text(p, X(b) + 38, cy, f"高 {2 * a:.2f} m", t["work"])
        if aux_h > 0:
            _dim(p, X(-b) - 30, Y(-a + aux_h), X(-b) - 30, Y(-a), "", t["warn"])
            _text(p, X(-b) - 36, Y(-a + aux_h / 2), f"副气囊高 {aux_h:.2f} m", t["warn"], "r")
        _arrow(p, X(-b) - 80, Y(a) + 14, X(-b) - 30, Y(a) + 14, t["muted"], 1.6, 7)
        _text(p, X(-b) - 80, Y(a) - 2, "来风", t["muted"])
        self._info(p, t, w * 0.64, 40, d["info"])

    def _airship(self, p, t, w, h):
        d = self.data
        a1, a2, b, aux_h = d["a1"], d["a2"], d["b"], d["aux_h"]
        length = a1 + a2
        span, chord, count = d["span"], d["chord"], int(d["fin_count"])
        zone = w * 0.60
        s = min((zone - 90) / (length + 0.1 * length), (h - 150) / (2 * (b + span)))
        cx, cy = 62 + a1 * s, h * 0.5 - 12

        def X(x):
            return cx + x * s

        def Y(z):
            return cy - z * s

        def prof(x):
            a = a1 if x < 0 else a2
            return b * math.sqrt(max(1 - (x / a) ** 2, 0.0))

        samples = [(-a1 + length * i / 160) for i in range(161)]
        hull = QPainterPath()
        hull.moveTo(X(samples[0]), Y(0))
        for x in samples:
            hull.lineTo(X(x), Y(prof(x)))
        for x in reversed(samples):
            hull.lineTo(X(x), Y(-prof(x)))
        hull.closeSubpath()

        # 尾翼（侧视）：上翼全高，下方按片数投影
        if span > 0 and chord > 0 and count >= 2:
            xt = a2
            rf, rr = xt - 1.45 * chord, xt - 0.12 * chord
            tf = rf + 0.35 * chord
            tr = tf + 0.67 * chord
            root_mid = prof(xt - 0.8 * chord)
            for sign, factor, alpha in ((1, 1.0, 190), (-1, 0.5 if count == 3 else 1.0, 120 if count == 3 else 190)):
                tip_y = sign * (root_mid + span * factor)
                poly = QPolygonF([QPointF(X(rf), Y(sign * prof(rf))), QPointF(X(tf), Y(tip_y)),
                                  QPointF(X(tr), Y(tip_y)), QPointF(X(rr), Y(sign * prof(rr)))])
                p.setBrush(_color(t["fin"], alpha))
                p.setPen(QPen(_color(t["fg"]), 1.4))
                p.drawPolygon(poly)
        p.save()
        p.setClipPath(hull)
        p.fillRect(QRectF(0, 0, w, h), _color(t["gas"], 150))
        if aux_h > 0:
            p.fillRect(QRectF(0, Y(-b + aux_h), w, h), _color(t["air"], 190))
            p.setPen(QPen(_color(t["fg"], 160), 1.4, Qt.DashLine))
            p.drawLine(QPointF(X(-a1), Y(-b + aux_h)), QPointF(X(a2), Y(-b + aux_h)))
        p.restore()
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(_color(t["fg"]), 2))
        p.drawPath(hull)
        _text(p, X(-0.3 * a1), Y(b / 3), "氦气（主气囊）", t["fg"], "c", bold=True)
        if aux_h > 0:
            _text(p, X(0.45 * a2), Y(-b + aux_h / 2), "副气囊（空气）", t["fg"], "c", bold=True)
        if span > 0:
            _text(p, X(a2 - 0.7 * chord), Y(prof(a2 - 0.8 * chord) + span) - 12, f"尾翼 {count} 片", t["fg"], "c", bold=True)
        # 尺寸
        yb = Y(-b) + 26
        _dim(p, X(-a1), yb, X(0), yb, f"a1 = {a1:.2f} m", t["muted"], above=False)
        _dim(p, X(0), yb, X(a2), yb, f"a2 = {a2:.2f} m", t["muted"], above=False)
        _dim(p, X(-a1), yb + 22, X(a2), yb + 22, f"L = {length:.2f} m", t["work"], above=False)
        _dashed(p, X(0), Y(b) - 8, X(0), Y(-b) + 6, t["muted"])
        _dim(p, X(0) + 22, Y(b), X(0) + 22, Y(-b), "", t["work"])
        _text(p, X(0) + 28, Y(0) + 2, f"D = {2 * b:.2f} m", t["work"])
        _arrow(p, X(-a1) - 56, Y(0), X(-a1) - 8, Y(0), t["muted"], 1.6, 7)
        _text(p, X(-a1) - 56, Y(0) - 12, "来风", t["muted"])
        # 尾视图
        ex, ey = w * 0.70, cy
        radius = b * s
        p.setPen(QPen(_color(t["fg"]), 2))
        p.setBrush(_color(t["gas"], 150))
        p.drawEllipse(QPointF(ex, ey), radius, radius)
        if aux_h > 0:
            p.setBrush(Qt.NoBrush)
        angles = {2: (90, 270), 3: (90, 210, 330), 4: (90, 0, 180, 270)}.get(count) or tuple(90 + 360 * k / max(count, 1) for k in range(max(count, 1)))
        thick = max(3.0, d["thickness"] * chord * s)
        for angle in angles:
            rad = math.radians(angle)
            x1, y1 = ex + radius * math.cos(rad), ey - radius * math.sin(rad)
            x2, y2 = ex + (radius + span * s) * math.cos(rad), ey - (radius + span * s) * math.sin(rad)
            p.setPen(QPen(_color(t["fin"]), thick, Qt.SolidLine, Qt.FlatCap))
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
            p.setPen(QPen(_color(t["fg"]), 1.2))
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
        _text(p, ex, ey + radius + span * s + 16, f"尾视图：{count} 片，单片翼展 {span:.2f} m", t["fg"], "c")
        _text(p, ex, ey + radius + span * s + 34, f"平均弦长 {chord:.2f} m", t["muted"], "c")
        self._info(p, t, w * 0.80, 40, d["info"])


# ---------------------------------------------------------------- 3. 风廓线
class WindCanvas(Canvas):
    def draw(self, p, t, w, h):
        d = self.data
        ml, mr, mt, mb = 60, 24, 34, 44
        aw, ah = w - ml - mr, h - mt - mb
        z_max = d["z_max"]
        v_max = max(fn(z_max) for _, _, fn, _ in d["curves"]) * 1.12
        v_max = max(v_max, 5.0)

        def X(v):
            return ml + v / v_max * aw

        def Y(z):
            return mt + ah - z / z_max * ah

        # 风级色带（风级按离地 10 m 定义）
        lower = 0.0
        for level, upper in enumerate(BEAUFORT_UPPER + [999.0]):
            if lower >= v_max:
                break
            hi = min(upper, v_max)
            if level % 2 == 0:
                p.fillRect(QRectF(X(lower), mt, X(hi) - X(lower), ah), _color(t["band"]))
            if X(hi) - X(lower) > 14:
                _text(p, (X(lower) + X(hi)) / 2, mt - 12, f"{level}", t["muted"], "c")
            lower = upper
        _text(p, ml - 4, mt - 12, "风级", t["muted"], "r")
        step_v, step_z = _nice_step(v_max, 6), _nice_step(z_max, 5)
        v = 0.0
        while v <= v_max + 1e-9:
            _dashed(p, X(v), mt, X(v), mt + ah, t["grid"], 0.8)
            _text(p, X(v), mt + ah + 14, f"{v:g}", t["muted"], "c")
            v += step_v
        z = 0.0
        while z <= z_max + 1e-9:
            _dashed(p, ml, Y(z), ml + aw, Y(z), t["grid"], 0.8)
            _text(p, ml - 6, Y(z), f"{z:g}", t["muted"], "r")
            z += step_z
        p.setPen(QPen(_color(t["fg"]), 1.4))
        p.drawLine(QPointF(ml, mt), QPointF(ml, mt + ah))
        p.drawLine(QPointF(ml, mt + ah), QPointF(ml + aw, mt + ah))
        _text(p, ml + aw / 2, h - 12, "平均风速 m/s（上方数字为蒲福风级，按离地 10 m 风速定义）", t["muted"], "c")
        p.save()
        p.translate(14, mt + ah / 2)
        p.rotate(-90)
        _text(p, 0, 0, "离地高度 m", t["muted"], "c")
        p.restore()
        # 10 m 基准线与目标高度线
        _dashed(p, ml, Y(10), ml + aw, Y(10), t["muted"], 1.2)
        _text(p, ml + aw - 4, Y(10) - 8, "10 m 风级基准高度", t["muted"], "r")
        _dashed(p, ml, Y(d["target"]), ml + aw, Y(d["target"]), t["muted"], 1.2)
        _text(p, ml + aw - 4, Y(d["target"]) - 8, f"目标高度 {d['target']:.0f} m", t["muted"], "r")
        for index, (name, color, fn, marks) in enumerate(d["curves"]):
            pts = [QPointF(X(fn(z_max * i / 80)), Y(z_max * i / 80)) for i in range(81)]
            p.setPen(QPen(_color(t[color]), 2.4))
            p.setBrush(Qt.NoBrush)
            p.drawPolyline(QPolygonF(pts))
            _text(p, X(fn(z_max)) - 6, mt + 10 + 16 * index, name, t[color], "r", bold=True)
            for z, label in marks:
                v = fn(z)
                p.setBrush(_color(t[color]))
                p.setPen(QPen(_color(t["bg"]), 1.2))
                p.drawEllipse(QPointF(X(v), Y(z)), 4.5, 4.5)
                dy = -11 if index == 0 else 12
                if index == 0:
                    _text(p, X(v) - 8, Y(z) + dy, label.format(v=v), t[color], "r")
                else:
                    _text(p, X(v) + 8, Y(z) + dy, label.format(v=v), t[color])


# ---------------------------------------------------------------- 4. 浮力与重量
class BudgetCanvas(Canvas):
    def draw(self, p, t, w, h):
        items = self.data["items"]
        ml, mr, mt, mb = 56, 24, 30, 66
        aw, ah = w - ml - mr, h - mt - mb
        level, bars = 0.0, []
        for label, value, kind in items:
            if kind == "total":
                bars.append((label, 0.0, value, kind, value))
                level = value
            elif kind == "loss":
                bars.append((label, level - value, level, kind, -value))
                level -= value
            elif kind == "gain":
                bars.append((label, level, level + value, kind, value))
                level += value
        lo = min([0.0] + [min(b[1], b[2]) for b in bars])
        hi = max([1.0] + [max(b[1], b[2]) for b in bars])
        pad = (hi - lo) * 0.1
        lo, hi = lo - (pad if lo < 0 else 0), hi + pad

        def Y(value):
            return mt + ah - (value - lo) / (hi - lo) * ah

        step = _nice_step(hi - lo, 6)
        v = math.ceil(lo / step) * step
        while v <= hi:
            _dashed(p, ml, Y(v), ml + aw, Y(v), t["grid"], 0.8)
            _text(p, ml - 6, Y(v), f"{v:g}", t["muted"], "r")
            v += step
        _text(p, 8, mt - 14, "kgf", t["muted"])
        slot = aw / max(len(bars), 1)
        bar_w = min(slot * 0.62, 64)
        metrics = QFontMetricsF(p.font())
        stagger = slot < max(metrics.horizontalAdvance(bar[0]) for bar in bars) + 6 if bars else False
        prev_top = None
        for index, (label, b0, b1, kind, signed) in enumerate(bars):
            x = ml + slot * index + (slot - bar_w) / 2
            low, high = min(b0, b1), max(b0, b1)
            if kind == "total":
                color = t["bad"] if signed < 0 else t["work"]
            else:
                color = t["ok"] if kind == "gain" else t["warn"]
            if prev_top is not None:
                _dashed(p, x - (slot - bar_w), Y(prev_top), x, Y(prev_top), t["muted"], 0.9)
            p.setPen(QPen(_color(color), 1.2))
            p.setBrush(_color(color, 190))
            p.drawRect(QRectF(x, Y(high), bar_w, max(Y(low) - Y(high), 1.5)))
            prev_top = b0 if kind == "loss" else b1
            value_text = f"{signed:+.1f}" if kind in ("loss", "gain") else f"{signed:.1f}"
            _text(p, x + bar_w / 2, Y(high) - 10, value_text, t["fg"], "c", bold=kind == "total")
            _text(p, x + bar_w / 2, mt + ah + 16 + (16 if stagger and index % 2 else 0), label, t["fg"], "c")
        p.setPen(QPen(_color(t["fg"]), 1.4))
        p.drawLine(QPointF(ml, Y(0)), QPointF(ml + aw, Y(0)))
        _text(p, w - 8, h - 10, "毛浮力 = 场地总浮升力 + 充盈度/充装温度/排气/逸出修正；其后重量项逐项扣除，缆绳重取工作风下缆绳平衡时的缆长", t["muted"], "r")


# ---------------------------------------------------------------- 4b. 氦气与副气囊体积
class VolumeCanvas(Canvas):
    """各工况下囊体总容积（不变）被氦气与副气囊空气分割的情况；氦气低于虚线说明副气囊容纳不下。"""

    def draw(self, p, t, w, h):
        d = self.data
        states, volume, capacity = d["states"], d["volume"], d["capacity"]
        ml, mr, mt, mb = 60, 24, 36, 62
        aw, ah = w - ml - mr, h - mt - mb

        def Y(v):
            return mt + ah - v / volume * ah

        step = _nice_step(volume, 5)
        v = 0.0
        while v <= volume + 1e-9:
            _dashed(p, ml, Y(v), ml + aw, Y(v), t["grid"], 0.8)
            _text(p, ml - 6, Y(v), f"{v:g}", t["muted"], "r")
            v += step
        _text(p, 8, mt - 16, "m³", t["muted"])
        slot = aw / max(len(states), 1)
        bar_w = min(slot * 0.56, 90)
        metrics = QFontMetricsF(p.font())
        stagger = slot < max(metrics.horizontalAdvance(s["label"]) for s in states) + 6
        for index, s in enumerate(states):
            x = ml + slot * index + (slot - bar_w) / 2
            he_top = Y(s["helium"])
            p.setPen(QPen(_color(t["fg"], 160), 1.0))
            p.setBrush(_color(t["gas"], 200))
            p.drawRect(QRectF(x, he_top, bar_w, Y(0) - he_top))
            p.setBrush(_color(t["air"], 200))
            p.drawRect(QRectF(x, Y(volume), bar_w, he_top - Y(volume)))
            if not s["fits"]:
                p.setPen(QPen(_color(t["bad"]), 2.4))
                p.setBrush(Qt.NoBrush)
                p.drawRect(QRectF(x, Y(volume), bar_w, Y(0) - Y(volume)))
            cx = x + bar_w / 2
            if Y(0) - he_top > 34:
                _text(p, cx, (he_top + Y(0)) / 2 - 8, f"氦气 {s['helium']:.1f}", t["fg"], "c")
                _text(p, cx, (he_top + Y(0)) / 2 + 8, f"充盈度 {s['fill']:.3f}", t["fg"], "c", bold=True)
            if he_top - Y(volume) > 18:
                _text(p, cx, (he_top + Y(volume)) / 2, f"空气 {s['air']:.1f}", t["fg"], "c")
            elif s["air"] > 0:
                _text(p, cx, Y(volume) - 9, f"空气 {s['air']:.1f}", t["fg"], "c")
            _text(p, cx, mt + ah + 16 + (16 if stagger and index % 2 else 0), s["label"], t["fg"], "c")
        low = Y(volume - capacity)
        _dashed(p, ml, low, ml + aw, low, t["warn"], 1.6)
        _text(p, ml + aw - 2, low - 9, f"副气囊容积 {capacity:.1f} m³：氦气体积须不低于此线", t["warn"], "r")
        p.setPen(QPen(_color(t["fg"]), 1.4))
        p.drawLine(QPointF(ml, Y(0)), QPointF(ml + aw, Y(0)))
        _text(p, w - 8, h - 10, f"囊体总容积 {volume:.1f} m³ 不变；红框 = 副气囊容纳不下；绿 = 氦气，蓝 = 副气囊内空气", t["muted"], "r")


# ---------------------------------------------------------------- 5. 选型曲线
def _wrap(text, metrics, width):
    lines, line = [], ""
    for char in text:
        if metrics.horizontalAdvance(line + char) > width and line:
            lines.append(line)
            line = char
        else:
            line += char
    if line:
        lines.append(line)
    return lines


class SweepCanvas(Canvas):
    """选型曲线：色条给出每个候选尺寸是否合格及不合格原因，下方三张“越高越好”的图配文字说明。"""

    def __init__(self):
        super().__init__(460, "点击上方“计算选型曲线”：逐个尺寸完整计算，给出哪些尺寸合格、推荐多大")

    def draw(self, p, t, w, h):
        d = self.data
        xs, n = d["xs"], len(d["xs"])
        unit = d.get("unit", "m")
        ml, mr = 64, 24
        pw = w - ml - mr
        _text(p, 10, 12, f"读图方法：横轴是{d['xlabel']}，每一列是一个候选尺寸（其余输入不变）。先看色条是否合格，"
                         "再看下面三张“越高越好”的图：曲线高过虚线（要求值）才算满足。", t["muted"])
        # 合格色条
        cell, sy, sh = pw / n, 44, 40
        colors = {"ok": t["ok"], "survival": t["warn"], "still": t["warn"], "fail": t["bad"]}
        _text(p, ml - 6, sy + sh / 2, "是否合格", t["fg"], "r", bold=True)
        for i, (x, verdict, reason) in enumerate(zip(xs, d["verdict"], d["reason"])):
            rect = QRectF(ml + i * cell + 1, sy, cell - 2, sh)
            p.fillRect(rect, _color(colors[verdict], 215))
            head = {"fail": "工作风不合格", "survival": "生存风不合格", "still": "工作风合格"}.get(verdict)
            lines = ["合格"] if verdict == "ok" else [head, reason]
            for k, line in enumerate(lines):
                yy = sy + sh / 2 + (k - (len(lines) - 1) / 2) * 15
                _text(p, rect.center().x(), yy, line, "#ffffff", "c", bold=k == 0)
            _text(p, rect.center().x(), sy + sh + 12, f"{x:g}", t["fg"], "c")
        _text(p, ml - 6, sy + sh + 12, f"{d['xlabel']}", t["muted"], "r")
        if n > 1 and d["xs"][0] <= d["current"] <= d["xs"][-1]:
            pos = (d["current"] - xs[0]) / (xs[-1] - xs[0]) * (n - 1)
            cx = ml + cell * (pos + 0.5)
            p.setBrush(_color(t["fg"]))
            p.setPen(Qt.NoPen)
            p.drawPolygon(QPolygonF([QPointF(cx, sy - 1), QPointF(cx - 6, sy - 10), QPointF(cx + 6, sy - 10)]))
            _text(p, cx + 9, sy - 8, f"当前 {d['current']:g}", t["fg"], bold=True)
        rec, kind = d.get("recommended"), d.get("recommended_kind")
        if kind == "ok":
            _text(p, ml, sy + sh + 32, f"推荐：{xs[rec]:g} {unit}——扫描范围内能同时满足工作风和生存风校核的最小尺寸（再小就不合格）",
                  t["ok"], bold=True)
        elif kind == "work":
            _text(p, ml, sy + sh + 32, f"没有尺寸全部合格；工作风合格的最小尺寸为 {xs[rec]:g} {unit}，但生存风或静风不合格，需另行处理（加强缆绳/减载/收缆）",
                  t["warn"], bold=True)
        else:
            _text(p, ml, sy + sh + 32, "扫描范围内没有合格尺寸：可加大扫描范围，或减小客户负载、降低目标高度、换更强的缆绳", t["bad"], bold=True)

        gap = 48
        cw = (pw - 2 * gap) / 3
        top = sy + sh + 56
        bottom = h - 62
        req_w, req_s = d["req_work"], d["req_surv"]
        sf_cap = 4 * max(req_w, req_s, 1.0)
        charts = [
            ("能抗多大的风？", f"纵轴：最大允许风速（离地 10 m，m/s）。高过蓝色虚线（您设定的工作风 {d['work_v10']:.1f}）才满足；0 表示连静风都不合格。",
             [("最大允许风速", "work", d["max_wind"])], [(d["work_v10"], "work", f"工作风 {d['work_v10']:.1f}")], "above"),
            ("缆绳够不够强？", f"纵轴：缆绳安全系数。工作风需 ≥ {req_w:g}（蓝）、生存风需 ≥ {req_s:g}（红），在虚线之上才合格。",
             [("工作风", "work", d["sf_work"]), ("生存风", "surv", d["sf_surv"])],
             [(req_w, "work", f"工作要求 {req_w:g}"), (req_s, "surv", f"生存要求 {req_s:g}")], "above"),
            ("浮力够不够？", "纵轴：净浮力 kgf。必须大于 0，越大越能把缆绳托起；红色区域表示浮力不足以托起设备和缆绳。",
             [("静净浮力（未计缆）", "ok", d["static_net"]), ("扣缆绳后", "work", d["net"])], [(0.0, "bad", "")], "below"),
        ]
        metrics = QFontMetricsF(p.font())
        for index, (title, sub, series, refs, shade) in enumerate(charts):
            x0 = ml + index * (cw + gap)
            _text(p, x0, top, title, t["fg"], bold=True, size=10.5)
            lines = _wrap(sub, metrics, min(cw + gap - 10, w - mr - x0))
            for k, line in enumerate(lines[:3]):
                _text(p, x0, top + 18 + 14 * k, line, t["muted"])
            plot_top = top + 18 + 14 * 3 + 6
            ph = bottom - plot_top
            if ph < 40:
                continue
            values = [v for _, _, ys in series for v in ys if v is not None]
            ref_values = [r[0] for r in refs]
            y_lo = min(values + ref_values + [0.0])
            y_hi = max(values + ref_values + [1e-9])
            if index == 1:
                y_hi = min(y_hi, sf_cap)
            pad = (y_hi - y_lo) * 0.12 or 1.0
            y_hi += pad
            y_lo = y_lo - pad if y_lo < 0 else 0.0

            def X(x):
                return x0 + (x - xs[0]) / (xs[-1] - xs[0]) * cw if xs[-1] > xs[0] else x0

            def Y(v):
                return plot_top + ph - (min(max(v, y_lo), y_hi) - y_lo) / (y_hi - y_lo) * ph

            p.fillRect(QRectF(x0, plot_top, cw, ph), _color(t["band"]))
            if shade == "above":
                level = refs[0][0] if index == 0 else min(r[0] for r in refs)
                p.fillRect(QRectF(x0, plot_top, cw, Y(level) - plot_top), _color(t["ok"], 38))
            else:
                p.fillRect(QRectF(x0, Y(0), cw, plot_top + ph - Y(0)), _color(t["bad"], 38))
            step = _nice_step(y_hi - y_lo, 5)
            v = math.ceil(y_lo / step) * step
            while v <= y_hi:
                _dashed(p, x0, Y(v), x0 + cw, Y(v), t["grid"], 0.8)
                _text(p, x0 - 4, Y(v), f"{v:g}", t["muted"], "r")
                v += step
            for value, color, label in refs:
                _dashed(p, x0, Y(value), x0 + cw, Y(value), t[color], 1.4)
                if label:
                    _text(p, x0 + cw - 2, Y(value) - 8, label, t[color], "r")
            if d["xs"][0] <= d["current"] <= d["xs"][-1]:
                _dashed(p, X(d["current"]), plot_top, X(d["current"]), plot_top + ph, t["fg"], 1.2)
            for line_index, (name, color, ys) in enumerate(series):
                pts = [(X(x), Y(v), v > y_hi, verdict) for x, v, verdict in zip(xs, ys, d["verdict"]) if v is not None]
                if len(pts) > 1:
                    p.setPen(QPen(_color(t[color]), 2.2))
                    p.setBrush(Qt.NoBrush)
                    p.drawPolyline(QPolygonF([QPointF(a, b) for a, b, _, _ in pts]))
                for a, b, clipped, verdict in pts:
                    p.setBrush(_color(colors[verdict]))
                    p.setPen(QPen(_color(t[color]), 1.2))
                    p.drawEllipse(QPointF(a, b), 3.8, 3.8)
                    if clipped:
                        _text(p, a, b - 9, "▲", t[color], "c")
                _text(p, x0 + 6, plot_top + 12 + 14 * line_index, f"━ {name}", t[color])
            step_x = _nice_step(xs[-1] - xs[0], 5)
            xv = math.ceil(xs[0] / step_x) * step_x
            while xv <= xs[-1] + 1e-9:
                _text(p, X(xv), plot_top + ph + 14, f"{xv:g}", t["muted"], "c")
                xv += step_x
            _text(p, x0 + cw / 2, plot_top + ph + 30, d["xlabel"], t["muted"], "c")
            if index == 1 and all(v is None for _, _, ys in series for v in ys):
                _text(p, x0 + cw / 2, plot_top + ph / 2, "未输入缆绳破断力，无法给出安全系数", t["muted"], "c")
        _text(p, w - 8, h - 8, "色条/圆点：绿 = 全部合格，橙 = 工作风合格但生存风或静风不合格，红 = 工作风不合格；黑色竖虚线 = 当前设计；▲ = 超出坐标范围",
              t["muted"], "r")


# ---------------------------------------------------------------- 6. 风速敏感性（仅用于 Word 报告）
class SensitivityCanvas(Canvas):
    """工作风按离地 10 m 风速缩放后的缆绳拉力、安全系数、净浮力、漂移与锚点角（2×3 小图，第 6 格为读图说明）。"""

    def __init__(self, min_height=320):
        super().__init__(min_height)

    def draw(self, p, t, w, h):
        d = self.data
        rows = d["rows"]
        xs = [r["speed_10"] for r in rows]
        if len(xs) < 2:
            return
        kg = KGF_PER_KN
        vlines = [(d["work_v10"], "work", f"工作风 {d['work_v10']:.1f}")]
        if d.get("max_v10") is not None and d["max_v10"] > 0:
            vlines.append((d["max_v10"], "bad", f"最大允许 {d['max_v10']:.1f}"))

        def column(key, factor=1.0):
            return [None if r[key] is None else r[key] * factor for r in rows]

        panels = [
            ("缆绳拉力 kgf", [("顶端拉力", "work", column("tension", kg)), ("阵风峰值", "surv", column("peak_tension", kg)),
                          ("锚点拉力", "ok", column("anchor_tension", kg))], [], None),
            ("安全系数", [("缆绳（阵风峰值）", "work", column("cable_sf")), ("膜材", "ok", column("film_sf"))],
             [(d["req_cable_sf"], "work", f"缆绳要求 {d['req_cable_sf']:g}"), (d["req_film_sf"], "ok", f"膜材要求 {d['req_film_sf']:g}")],
             6.0 * max(d["req_cable_sf"], d["req_film_sf"], 1.0)),
            ("净浮力（扣缆绳）kgf", [("锚点净浮力", "work", column("net_buoyancy"))], [(0.0, "bad", "")], None),
            ("水平漂移 m", [("向下风漂移", "work", column("drift"))], [], None),
            ("锚点悬链角 °", [("锚点角", "work", column("angle_deg"))], [(BOTTOM_ANGLE_WARNING_DEG, "warn", f"{BOTTOM_ANGLE_WARNING_DEG:g}° 提示线")], None),
        ]
        cols, gap = 3, 14
        cw, ch = (w - gap * (cols + 1)) / cols, (h - gap * 3) / 2
        for index, (title, series, refs, cap) in enumerate(panels):
            r, c = divmod(index, cols)
            self._panel(p, t, QRectF(gap + c * (cw + gap), gap + r * (ch + gap), cw, ch), title, xs, series, refs,
                        vlines, cap, shade_below_zero=index == 2)
        # 第 6 格：读图说明
        x0, y0 = gap + 2 * (cw + gap), gap + ch + gap
        metrics = QFontMetricsF(p.font())
        _text(p, x0, y0 + 12, "读图说明", t["fg"], bold=True)
        notes = [f"横轴：离地 10 m 平均风速 m/s（对应目标高度风速约为其 {d['ratio_target']:.2f} 倍）。",
                 f"蓝色虚线 = 当前设定的工作风（{d['work_v10']:.1f} m/s）"
                 + (f"；红色虚线 = 满足全部校核的最大允许风速（{d['max_v10']:.1f} m/s）。" if d.get("max_v10") else "。"),
                 "安全系数曲线应在虚线（要求值）之上；净浮力应大于 0（红色区域为拖地）。",
                 "曲线中断表示该风速下缆绳无法悬空（拖地），无平衡解。"]
        yy = y0 + 32
        for note in notes:
            for line in _wrap(note, metrics, cw - 6):
                _text(p, x0, yy, line, t["muted"])
                yy += 15
            yy += 4

    @staticmethod
    def _panel(p, t, rect, title, xs, series, refs, vlines, cap, shade_below_zero=False):
        ml, mr, mt, mb = 50, 10, 24, 30
        x0, y0 = rect.left() + ml, rect.top() + mt
        pw, ph = rect.width() - ml - mr, rect.height() - mt - mb
        if pw < 40 or ph < 40:
            return
        _text(p, rect.left() + 2, rect.top() + 8, title, t["fg"], bold=True)
        values = [v for _, _, ys in series for v in ys if v is not None] + [v for v, _, _ in refs]
        y_lo = min(values + [0.0])
        y_hi = max(values + [1e-9])
        if cap is not None:
            y_hi = min(y_hi, cap)
        pad = (y_hi - y_lo) * 0.1 or 1.0
        y_hi += pad
        y_lo = y_lo - pad if y_lo < 0 else 0.0
        x_lo, x_hi = xs[0], xs[-1]

        def X(x):
            return x0 + (x - x_lo) / (x_hi - x_lo) * pw

        def Y(v):
            return y0 + ph - (min(max(v, y_lo), y_hi) - y_lo) / (y_hi - y_lo) * ph

        p.fillRect(QRectF(x0, y0, pw, ph), _color(t["band"]))
        if shade_below_zero:
            p.fillRect(QRectF(x0, Y(0), pw, y0 + ph - Y(0)), _color(t["bad"], 38))
        step = _nice_step(y_hi - y_lo, 4)
        v = math.ceil(y_lo / step) * step
        while v <= y_hi:
            _dashed(p, x0, Y(v), x0 + pw, Y(v), t["grid"], 0.8)
            _text(p, x0 - 4, Y(v), f"{v:g}", t["muted"], "r")
            v += step
        step_x = _nice_step(x_hi - x_lo, 5)
        xv = math.ceil(x_lo / step_x) * step_x
        while xv <= x_hi + 1e-9:
            _text(p, X(xv), y0 + ph + 12, f"{xv:g}", t["muted"], "c")
            xv += step_x
        _text(p, x0 + pw / 2, y0 + ph + 25, "离地 10 m 风速 m/s", t["muted"], "c")
        for x, color, label in vlines:
            if x_lo <= x <= x_hi:
                _dashed(p, X(x), y0, X(x), y0 + ph, t[color], 1.2)
        for value, color, label in refs:
            _dashed(p, x0, Y(value), x0 + pw, Y(value), t[color], 1.4)
        placed = []
        for value, color, label in refs:
            if label:
                # 两条要求线过近时把后一个标签放到线下方，避免重叠
                dy = 10 if any(abs(Y(value) - other) < 16 for other in placed) else -8
                placed.append(Y(value) + dy)
                _text(p, x0 + pw - 2, Y(value) + dy, label, t[color], "r")
        for name, color, ys in series:
            segment = []
            p.setPen(QPen(_color(t[color]), 2.0))
            p.setBrush(Qt.NoBrush)
            for x, value in list(zip(xs, ys)) + [(None, None)]:
                if value is None:
                    if len(segment) > 1:
                        p.drawPolyline(QPolygonF(segment))
                    segment = []
                    continue
                segment.append(QPointF(X(x), Y(value)))
        if len(series) > 1:
            names = [f"━ {name}" for name, _, _ in series]
            box_w = max(QFontMetricsF(p.font()).horizontalAdvance(text) for text in names) + 10
            p.fillRect(QRectF(x0 + 2, y0 + 2, box_w, 16 * len(names) + 4), _color(t["bg"], 215))
            for line_index, (_, color, _) in enumerate(series):
                _text(p, x0 + 6, y0 + 12 + 16 * line_index, names[line_index], t[color])
        p.setPen(QPen(_color(t["fg"]), 1.2))
        p.drawLine(QPointF(x0, y0), QPointF(x0, y0 + ph))
        p.drawLine(QPointF(x0, y0 + ph), QPointF(x0 + pw, y0 + ph))


def render_png(canvas, width, height, scale=2, font_pt=None):
    """把画布离屏渲染成浅色主题的 PNG 字节（Word 报告用）；scale 为清晰度倍数。"""
    dark = _DARK["on"]
    _DARK["on"] = False
    try:
        if font_pt:
            canvas.font_pt = font_pt
        canvas.setFont(QFont("Microsoft YaHei"))
        canvas.resize(width, height)
        image = QImage(width * scale, height * scale, QImage.Format_ARGB32)
        image.setDevicePixelRatio(scale)
        image.fill(Qt.white)
        canvas.render(image)
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.WriteOnly)
        image.save(buffer, "PNG")
        return bytes(data)
    finally:
        _DARK["on"] = dark


# ---------------------------------------------------------------- 面板
class DiagramPanel(QWidget):
    sweepRequested = pyqtSignal(float, float)

    def __init__(self, sweep_name="直径"):
        super().__init__()
        self.tether = TetherCanvas(430, "输入参数后自动生成")
        self.shape = ShapeCanvas(360)
        self.wind = WindCanvas(360)
        self.budget = BudgetCanvas(360)
        self.volume = VolumeCanvas(360)
        self.sweep = SweepCanvas()
        self.tabs = QTabWidget()
        for canvas, title in ((self.tether, "受力与姿态"), (self.shape, "外形示意"), (self.wind, "风廓线与风级"),
                              (self.budget, "浮力与重量"), (self.volume, "氦气与副气囊体积"),
                              (self.sweep_page(sweep_name), "选型曲线")):
            self.tabs.addTab(canvas, title)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tabs)

    def sweep_page(self, sweep_name):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 4, 0, 0)
        row = QHBoxLayout()
        row.addWidget(QLabel(f"按{sweep_name}缩放，从"))
        self.low = QDoubleSpinBox()
        self.low.setRange(0.2, 0.95)
        self.low.setSingleStep(0.1)
        self.low.setValue(0.6)
        self.low.setSuffix(" ×")
        self.low.lineEdit().setObjectName("SweepLowLineEdit")
        row.addWidget(self.low)
        row.addWidget(QLabel("到"))
        self.high = QDoubleSpinBox()
        self.high.setRange(1.05, 5.0)
        self.high.setSingleStep(0.1)
        self.high.setValue(1.6)
        self.high.setSuffix(" ×")
        self.high.lineEdit().setObjectName("SweepHighLineEdit")
        row.addWidget(self.high)
        row.addWidget(QLabel(f"当前{sweep_name}（11 个点，其余输入不变）"))
        self.button = QPushButton("计算选型曲线")
        self.button.setToolTip(f"依次改变{sweep_name}并完整计算，约需数秒；结束后界面输入恢复原值")
        self.button.clicked.connect(lambda: self.sweepRequested.emit(self.low.value(), self.high.value()))
        row.addWidget(self.button)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addWidget(self.sweep, 1)
        return page
