"""导出两页各分组内每一行的（标签 | 控件 | 单位），用于界面重组设计。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qt_harness as h  # noqa: E402
from PyQt5 import QtWidgets  # noqa: E402


def rows(layout, depth=0, out=None):
    out = [] if out is None else out
    for i in range(layout.count()):
        item = layout.itemAt(i)
        child = item.layout()
        widget = item.widget()
        if child is not None:
            if isinstance(child, QtWidgets.QHBoxLayout):
                cells = []
                for j in range(child.count()):
                    w = child.itemAt(j).widget()
                    if w is None:
                        continue
                    kind = type(w).__name__
                    text = w.text() if isinstance(w, (QtWidgets.QLabel, QtWidgets.QCheckBox, QtWidgets.QPushButton, QtWidgets.QRadioButton)) else ""
                    cells.append(f"{kind[1:]}:{w.objectName() or text}" + (f"[{text}]" if text and w.objectName() else ""))
                out.append("  " * depth + " | ".join(cells))
            else:
                rows(child, depth + 1, out)
        elif widget is not None:
            if isinstance(widget, QtWidgets.QGroupBox):
                out.append("  " * depth + f"## 子分组 {widget.title()}")
                if widget.layout():
                    rows(widget.layout(), depth + 1, out)
            elif widget.layout() is not None:
                rows(widget.layout(), depth + 1, out)
            else:
                out.append("  " * depth + f"<{type(widget).__name__} {widget.objectName()}>")
    return out


def run_hook(g):
    ui = g["ui"]
    for name in ("groupBox_SphereGeometry", "groupBox_SphereMaterial", "groupBox_SphereLoad", "groupBox_SphereCable",
                 "groupBox_AirShipGeometry", "groupBox_AirShipMaterial", "groupBox_AirShipLoad", "groupBox_AirShipCable"):
        box = getattr(ui, name)
        print(f"\n=== {name}: {box.title()} ===")
        for line in rows(box.layout()):
            print(line)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    import ui_form
    app = QtWidgets.QApplication([])
    window = QtWidgets.QWidget()
    ui = ui_form.Ui_Widget()
    ui.setupUi(window)
    run_hook({"ui": ui})