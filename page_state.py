"""计算页的保存 / 打开：采集页面全部输入控件，写入或读回 datafile 定义的文本数据文件。"""
import os

from PyQt5.QtWidgets import (QAbstractSpinBox, QCheckBox, QComboBox, QFileDialog, QLineEdit, QMessageBox,
                             QRadioButton)

import calc_controller
import datafile

PAGES = {"Sphere": "SpherePage", "AirShip": "AirshipPage"}
FILE_FILTER = "计算数据文件 (*.txt);;全部文件 (*)"
# 页面顶部结论条中供人阅读的关键结果：(summary 里的名称, 控件键)
SUMMARY_FIELDS = (("工作风结论", "Conclusion"), ("生存风结论", "SurvConclusion"), ("静净浮力 kgf", "StaticNet"),
                  ("扣缆绳净浮力 kgf", "NetBuoyancy"), ("最大允许风速", "MaxWindSpeed"),
                  ("缆绳安全系数·工作", "SafetyFactor"), ("缆绳安全系数·生存", "SurvSafetyFactor"),
                  ("膜材安全系数", "FilmSF"), ("锚点悬链角 °", "IncludedAngle"))
# 与数据文件一起保存/恢复的“报告信息”读写入口，由主程序在报告页建好后挂上
hooks = {"get_info": None, "set_info": None}


def _page(ui, prefix):
    return getattr(ui, PAGES[prefix])


def _is_input(widget):
    name = widget.objectName()
    if not name or name.startswith("qt_"):
        return False
    if isinstance(widget, QLineEdit):
        return not widget.isReadOnly() and not isinstance(widget.parent(), (QAbstractSpinBox, QComboBox))
    return isinstance(widget, (QComboBox, QCheckBox, QRadioButton))


def input_widgets(ui, prefix):
    """页面内全部输入控件：{对象名: 控件}。"""
    found = {}
    for widget in _page(ui, prefix).findChildren(QLineEdit) + _page(ui, prefix).findChildren(QComboBox) \
            + _page(ui, prefix).findChildren(QCheckBox) + _page(ui, prefix).findChildren(QRadioButton):
        if _is_input(widget):
            found.setdefault(widget.objectName(), widget)
    return found


def _value_of(widget):
    if isinstance(widget, QLineEdit):
        return widget.text()
    if isinstance(widget, QComboBox):
        return widget.currentText()
    return widget.isChecked()


def collect_inputs(ui, prefix):
    return {name: _value_of(widget) for name, widget in sorted(input_widgets(ui, prefix).items())}


def collect_summary(ui, prefix):
    summary = {}
    for title, key in SUMMARY_FIELDS:
        widget = getattr(ui, f"{prefix}{key}LineEdit", None)
        if widget is not None and widget.text().strip():
            summary[title] = widget.text().strip()
    return summary


def build_payload(ui, prefix):
    info = hooks["get_info"]() if hooks["get_info"] else {}
    return datafile.build_payload(prefix, collect_inputs(ui, prefix),
                                  {"aux_ratio_manual": calc_controller.aux_manual(prefix)},
                                  collect_summary(ui, prefix), info)


def apply_payload(ui, payload):
    """把数据文件内容回填到对应页面并触发重新计算；返回 (未找到的控件名, 无法匹配的下拉项)。"""
    prefix = payload["kind"]
    widgets = input_widgets(ui, prefix)
    missing, unmatched = [], []
    for name, value in payload["inputs"].items():
        widget = widgets.get(name)
        if widget is None:
            missing.append(name)
        elif isinstance(widget, QLineEdit):
            widget.setText(str(value))
        elif isinstance(widget, QComboBox):
            index = widget.findText(str(value))
            if index < 0:
                unmatched.append(f"{name} = {value}")
            else:
                widget.setCurrentIndex(index)
        elif value is True:
            widget.setChecked(True)
        elif value is False and not isinstance(widget, QRadioButton):
            widget.setChecked(False)
    calc_controller.set_aux_manual(prefix, bool(payload["state"].get("aux_ratio_manual", False)))
    if hooks["set_info"] and payload.get("report_info"):
        hooks["set_info"](payload["report_info"])
    calc_controller.calculate_now(prefix)
    return missing, unmatched


def default_filename(ui, prefix):
    size_key, label = ("Diameter", "直径") if prefix == "Sphere" else ("Length", "长度")
    widget = getattr(ui, f"{prefix}{size_key}LineEdit", None)
    size = widget.text().strip() if widget is not None else ""
    safe = "".join(c for c in size if c.isdigit() or c == ".")
    return f"{datafile.KIND_NAMES[prefix]}设计数据" + (f"_{label}{safe}m" if safe else "") + ".txt"


def save_page(ui, prefix, parent=None):
    """弹出保存对话框并写文件；返回保存路径，取消或失败返回 None。"""
    parent = parent or _page(ui, prefix)
    path, _ = QFileDialog.getSaveFileName(parent, "保存计算数据", default_filename(ui, prefix), FILE_FILTER)
    if not path:
        return None
    if not os.path.splitext(path)[1]:
        path += ".txt"
    try:
        datafile.write_file(path, build_payload(ui, prefix))
    except OSError as error:
        QMessageBox.critical(parent, "保存失败", f"无法写入文件：\n{path}\n\n{error}")
        return None
    return path


def open_file(ui, parent=None):
    """弹出打开对话框并回填；数据属于另一页时自动切换到该页。返回打开的路径，取消或失败返回 None。"""
    parent = parent or ui.SpherePage
    path, _ = QFileDialog.getOpenFileName(parent, "打开计算数据", "", FILE_FILTER)
    if not path:
        return None
    return load_path(ui, path, parent)


def load_path(ui, path, parent=None):
    parent = parent or ui.SpherePage
    try:
        payload = datafile.read_file(path)
    except (OSError, datafile.DataFileError) as error:
        QMessageBox.critical(parent, "打开失败", f"{os.path.basename(path)}\n\n{error}")
        return None
    prefix = payload["kind"]
    if hasattr(ui, "tabWidget"):
        ui.tabWidget.setCurrentWidget(_page(ui, prefix))
    missing, unmatched = apply_payload(ui, payload)
    if missing or unmatched:
        lines = [f"已载入 {os.path.basename(path)}，但部分项目未能恢复："]
        if unmatched:
            lines.append("下拉选项在当前程序中不存在：\n  " + "\n  ".join(unmatched))
        if missing:
            lines.append("当前程序没有这些输入项（可能来自其他版本）：\n  " + "\n  ".join(missing[:20])
                         + ("\n  ……" if len(missing) > 20 else ""))
        QMessageBox.warning(parent, "部分恢复", "\n".join(lines))
    return path
