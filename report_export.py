"""Word 报告导出：导出页界面、从计算页收集数据、渲染图表并调用 report_docx 生成 .docx。"""
import logging
import os
import re

from PyQt5.QtCore import QSettings, Qt, QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog, QGridLayout, QGroupBox, QLabel, QLineEdit,
                             QMessageBox, QRadioButton, QTextBrowser, QTextEdit, QWidget)

import calc_controller
import diagrams
from aerostat_model import sensitivity_speeds, wind_sweep

# (键, 标签, 提示)
INFO_FIELDS = (("title", "报告标题", "留空则按“尺寸 + 类型 + 设计计算报告”自动生成"), ("project", "项目名称", ""),
               ("number", "报告编号", ""), ("version", "版本", "默认 V1.0"), ("organization", "编制单位", ""),
               ("author", "编制", ""), ("reviewer", "审核", ""), ("approver", "批准", ""))
OPTIONS = (("figures", "包含图表（外形、风廓线、浮力瀑布图、受力姿态）", True),
           ("sensitivity", "包含风速敏感性分析", True),
           ("appendix", "包含附录（全部输入与结果参数清单、假设与符号）", True),
           ("open_after", "导出完成后用 Word 打开", True))
GROUPS = {"Sphere": ("Banner", "Geometry", "Material", "Load", "Cable", "Result1", "Result2", "Result3"),
          "AirShip": ("Banner", "Geometry", "Material", "Load", "Cable", "Result1", "Result2", "Result3")}
PAGES = {"Sphere": "SpherePage", "AirShip": "AirshipPage"}
FIGURE_SIZES = {"shape": (980, 470), "wind": (960, 480), "budget": (1000, 460), "tether": (1000, 520),
                "volume": (1000, 460), "sensitivity": (1000, 580), "sweep": (1000, 700)}
AIRSHIP_SHAPE_SIZE = (800, 440)   # 飞艇外形图的数据面板在报告里由参数表代替，故可更窄
FIGURE_FONT_PT = 11.0


class ReportError(Exception):
    """可直接显示给用户的导出失败原因。"""


def _selected_prefix(ui):
    return "Sphere" if ui.radioButton_PrintSphere.isChecked() else "AirShip"


# ---------------------------------------------------------------- 界面
def setup_report_page(ui):
    """把“打印/导出”页改造成 Word 报告导出页：数据源、报告信息、内容选项、操作按钮与报告摘要预览。"""
    ui.tabWidget.setTabText(ui.tabWidget.indexOf(ui.PrintPage), "导出报告")
    layout = ui.PrintPage.layout()
    for index in range(layout.count() - 1, -1, -1):
        if layout.itemAt(index).spacerItem() is not None:
            layout.removeItem(layout.itemAt(index))
    ui.groupBox_PrintSource.setTitle("选择数据源（使用该计算页当前的输入与结果）")
    ui.groupBox_PrintActions.setTitle("操作")
    ui.pushButton_PrintPreview.setText("刷新预览")
    ui.pushButton_ExportPDF.setText("导出 Word 报告…")
    ui.pushButton_ExportPDF.setToolTip("生成包含摘要、设计输入、计算方法、结果图表、校核结论与附录的 Word 研究报告（.docx）")
    ui.pushButton_Print.setVisible(False)

    info_box = QGroupBox("报告信息", ui.PrintPage)
    info_box.setObjectName("groupBox_ReportInfo")
    grid = QGridLayout(info_box)
    ui.reportInfoEdits = {}
    for index, (key, label, tip) in enumerate(INFO_FIELDS):
        row, column = divmod(index, 2)
        grid.addWidget(QLabel(label + "：", info_box), row, column * 2)
        edit = QLineEdit(info_box)
        edit.setObjectName(f"ReportInfo_{key}")
        if tip:
            edit.setToolTip(tip)
            edit.setPlaceholderText(tip)
        grid.addWidget(edit, row, column * 2 + 1)
        ui.reportInfoEdits[key] = edit
    grid.setColumnStretch(1, 1)
    grid.setColumnStretch(3, 1)

    option_box = QGroupBox("报告内容", ui.PrintPage)
    option_box.setObjectName("groupBox_ReportOptions")
    option_layout = QGridLayout(option_box)
    ui.reportOptionBoxes = {}
    for index, (key, label, default) in enumerate(OPTIONS):
        box = QCheckBox(label, option_box)
        box.setObjectName(f"ReportOption_{key}")
        box.setChecked(default)
        option_layout.addWidget(box, index // 2, index % 2)
        ui.reportOptionBoxes[key] = box

    ui.reportPreview = QTextBrowser(ui.PrintPage)
    ui.reportPreview.setObjectName("ReportPreview")
    ui.reportPreview.setOpenLinks(False)
    position = layout.indexOf(ui.groupBox_PrintActions)
    layout.insertWidget(position, option_box)
    layout.insertWidget(position, info_box)
    layout.addWidget(ui.reportPreview, 1)

    settings = QSettings("CalculateApp", "Report")
    for key, edit in ui.reportInfoEdits.items():
        if key in ("organization", "author", "reviewer", "approver"):
            edit.setText(settings.value(f"info/{key}", "", str))

    refresh = lambda *_: refresh_preview(ui)  # noqa: E731
    ui.pushButton_PrintPreview.clicked.connect(refresh)
    ui.radioButton_PrintSphere.toggled.connect(refresh)
    ui.pushButton_ExportPDF.clicked.connect(lambda: export_dialog(ui))
    ui.tabWidget.currentChanged.connect(lambda index: refresh_preview(ui) if ui.tabWidget.widget(index) is ui.PrintPage else None)


def get_info(ui):
    return {key: edit.text().strip() for key, edit in ui.reportInfoEdits.items()}


def set_info(ui, info):
    for key, edit in ui.reportInfoEdits.items():
        if key in info:
            edit.setText(str(info[key]))


def get_options(ui):
    return {key: box.isChecked() for key, box in ui.reportOptionBoxes.items()}


def refresh_preview(ui):
    prefix = _selected_prefix(ui)
    try:
        if not calc_controller.calculate_now(prefix):
            ui.reportPreview.setHtml("<p>该计算页的输入尚不完整或有误，无法生成报告。请先在计算页填写必要输入。</p>")
            return
        ctx = collect_context(ui, prefix, full=False)
        ui.reportPreview.setHtml(preview_html(ctx))
    except Exception as error:  # noqa: BLE001  预览失败不能影响其他功能
        logging.exception(error)
        ui.reportPreview.setHtml(f"<p>预览生成失败：{error}</p>")


VERDICT_HTML_COLORS = {"合格": "#2e7d32", "不合格": "#c62828", "—": "#999999"}


def preview_html(ctx):
    import report_docx
    report = report_docx.Report(ctx)
    ok, text = report.overall()
    color = "#2e7d32" if ok else "#c62828"
    rows = ""
    for name, value, requirement, verdict in report.key_indicators():
        verdict_color = VERDICT_HTML_COLORS.get(verdict, "#ef6c00")
        rows += (f"<tr><td>{name}</td><td align='center'>{value}</td><td align='center'>{requirement}</td>"
                 f"<td align='center'><b><font color='{verdict_color}'>{verdict}</font></b></td></tr>")
    options = ctx["options"]
    results = "4 计算结果与分析（外形、气体与浮力、重量平衡、风环境、气动力、系留受力、强度校核、最大允许风速"
    results += "、风速敏感性）" if options.get("sensitivity") else "）"
    chapters = ["摘要与主要设计指标", "1 概述", "2 设计输入与设计条件", "3 计算方法与模型", results, "5 结论与建议"]
    if options.get("appendix"):
        chapters.append("附录 A 参数清单 / B 假设 / C 符号")
    outline = "".join(f"<li>{item}</li>" for item in chapters)
    return (f"<h2>{report.title}</h2><p><b><font color='{color}'>综合结论：{text}</font></b></p>"
            "<table border='1' cellspacing='0' cellpadding='4' width='100%'>"
            "<tr bgcolor='#e8eef6'><th>指标</th><th>计算值</th><th>要求</th><th>判定</th></tr>" + rows + "</table>"
            f"<h3>报告章节</h3><ol>{outline}</ol>"
            "<p><font color='#666666'>点击“导出 Word 报告…”生成完整的 .docx 文档（含图表与数据表）。此处仅显示摘要预览。</font></p>")


# ---------------------------------------------------------------- 数据收集
def ui_values(page):
    """页面内全部控件的当前值：{对象名: 文本 / 勾选状态}，含只读结果。"""
    values = {}
    for widget in page.findChildren(QWidget):
        name = widget.objectName()
        if not name or name.startswith("qt_"):
            continue
        if isinstance(widget, QLineEdit):
            values[name] = widget.text()
        elif isinstance(widget, QComboBox):
            values[name] = widget.currentText()
        elif isinstance(widget, QTextEdit):
            values[name] = widget.toPlainText()
        elif isinstance(widget, (QCheckBox, QRadioButton)):
            values[name] = widget.isChecked()
    return values


def input_groups(ui, prefix):
    groups = []
    for name in GROUPS[prefix]:
        box = getattr(ui, f"groupBox_{prefix}{name}", None)
        if box is None:
            continue
        items = extract_data_from_groupbox(box)
        if items:
            groups.append((box.title(), items))
    return groups


def collect_context(ui, prefix, full=True):
    """汇总生成报告所需的全部数据；full=False 时跳过敏感性分析与作图（预览、取文件名用）。"""
    last = calc_controller.last(prefix)
    if last is None:
        raise ReportError("该计算页还没有计算结果，请先在计算页填写输入。")
    options, info = get_options(ui), get_info(ui)
    page = getattr(ui, PAGES[prefix])
    ctx = {"kind": prefix, "inp": last["inp"], "res": last["res"], "geometry": last["geometry"],
           "drag": calc_controller.drag_report(prefix), "info": info, "options": options, "ui": ui_values(page),
           "input_groups": input_groups(ui, prefix) if full and options.get("appendix") else [], "images": {},
           "sensitivity": None}
    if full and options.get("sensitivity"):
        try:
            ctx["sensitivity"] = wind_sweep(last["inp"], last["res"], sensitivity_speeds(last["res"]))
        except Exception as error:  # noqa: BLE001  敏感性分析失败只影响该章节
            logging.exception(error)
    if full and options.get("figures"):
        ctx["images"] = render_figures(ui, prefix, ctx)
    return ctx


def render_figures(ui, prefix, ctx):
    """用与界面相同的画布离屏渲染浅色主题 PNG；某张图失败只缺该图。"""
    panel = getattr(ui, f"{prefix}Diagrams")
    last = calc_controller.last(prefix)
    res, req = last["res"], last["inp"].requirements
    images = {}
    sources = {"shape": (diagrams.ShapeCanvas, panel.shape.data), "wind": (diagrams.WindCanvas, panel.wind.data),
               "budget": (diagrams.BudgetCanvas, panel.budget.data), "tether": (diagrams.TetherCanvas, panel.tether.data),
               "volume": (diagrams.VolumeCanvas, panel.volume.data),
               "sweep": (diagrams.SweepCanvas, panel.sweep.data)}
    rows = ctx.get("sensitivity")
    if ctx["options"].get("sensitivity") and rows:
        wind = res["work"]["wind"]
        sources["sensitivity"] = (diagrams.SensitivityCanvas, {
            "rows": rows, "work_v10": wind["speed_10"], "max_v10": res["max_wind"]["speed_10"] if res["max_wind"]["scale"] > 0 else None,
            "req_cable_sf": req.cable_sf, "req_film_sf": req.film_sf,
            "ratio_target": wind["speed_target"] / wind["speed_10"] if wind["speed_10"] > 0 else 1.0})
    for key, (canvas_class, data) in sources.items():
        if not data:
            continue
        if key == "shape" and prefix == "AirShip":
            data = dict(data, info=[])
        try:
            canvas = canvas_class()
            canvas.set_data(data)
            width, height = AIRSHIP_SHAPE_SIZE if key == "shape" and prefix == "AirShip" else FIGURE_SIZES[key]
            images[key] = diagrams.render_png(canvas, width, height, 2, FIGURE_FONT_PT)
        except Exception as error:  # noqa: BLE001
            logging.exception(error)
    return images


# ---------------------------------------------------------------- 导出
def default_filename(ui, prefix):
    import report_docx
    ctx = collect_context(ui, prefix, full=False)
    title = report_docx.Report(ctx).title
    return re.sub(r'[<>:"/\\|?*]', "", title).strip() or "设计计算报告"


def export_report(ui, prefix, path):
    """重新计算并生成报告到 path；失败抛 ReportError。"""
    import report_docx
    QApplication.setOverrideCursor(Qt.WaitCursor)
    try:
        if not calc_controller.calculate_now(prefix):
            raise ReportError("当前输入不完整或有误，无法计算。请先在计算页填写必要输入。")
        ctx = collect_context(ui, prefix)
        try:
            report_docx.generate(path, ctx)
        except PermissionError as error:
            raise ReportError(f"无法写入文件，可能已在 Word 中打开：\n{path}") from error
    finally:
        QApplication.restoreOverrideCursor()
    settings = QSettings("CalculateApp", "Report")
    for key in ("organization", "author", "reviewer", "approver"):
        settings.setValue(f"info/{key}", ctx["info"].get(key, ""))
    return path


def export_dialog(ui):
    prefix = _selected_prefix(ui)
    try:
        name = default_filename(ui, prefix)
    except ReportError as error:
        QMessageBox.warning(ui.PrintPage, "无法导出", str(error))
        return None
    path, _ = QFileDialog.getSaveFileName(ui.PrintPage, "导出 Word 报告", f"{name}.docx", "Word 文档 (*.docx)")
    if not path:
        return None
    if not path.lower().endswith(".docx"):
        path += ".docx"
    try:
        export_report(ui, prefix, path)
    except ReportError as error:
        QMessageBox.warning(ui.PrintPage, "导出失败", str(error))
        return None
    except Exception as error:  # noqa: BLE001
        logging.exception(error)
        QMessageBox.critical(ui.PrintPage, "导出失败", f"生成报告时出错：\n{error}")
        return None
    if get_options(ui).get("open_after"):
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.abspath(path)))
    else:
        QMessageBox.information(ui.PrintPage, "导出成功", f"报告已保存至：\n{path}")
    return path


# ---------------------------------------------------------------- 把参数从分组框里抽成 (名称, 值, 单位)
def extract_data_from_groupbox(groupbox):
    """从 GroupBox 中提取 (名称, 值, 单位)；子标题以 ("###SUBTITLE###", 标题, "") 表示。"""
    results = []

    def traverse_layout(layout):
        if not layout:
            return
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item.layout():
                sub_layout = item.layout()
                process_row_layout(sub_layout)
                traverse_layout(sub_layout)
            elif item.widget():
                widget = item.widget()
                # 隐藏的控件（如无帆时的兜帆/翼帆参数）不提取；折叠的节正文仍提取
                if widget.isHidden() and not widget.property("sectionBody"):
                    continue
                if isinstance(widget, QGroupBox):
                    if widget.title():
                        results.append(("###SUBTITLE###", widget.title(), ""))
                    traverse_layout(widget.layout())
                elif isinstance(widget, QWidget) and widget.layout():
                    traverse_layout(widget.layout())

    def process_row_layout(layout):
        widgets = []
        has_unchecked_checkbox = False
        for i in range(layout.count()):
            w = layout.itemAt(i).widget()
            if w and not w.isHidden():
                widgets.append(w)
                if isinstance(w, QCheckBox) and not w.isChecked():
                    has_unchecked_checkbox = True
        if not widgets or has_unchecked_checkbox:
            return

        has_input = any(isinstance(w, (QLineEdit, QTextEdit, QComboBox, QRadioButton, QCheckBox)) for w in widgets)
        if not has_input:
            text = " ".join([w.text().strip().lstrip("▾▸ ").strip() for w in widgets if isinstance(w, QLabel) and w.text().strip()])
            if text:
                results.append(("###SUBTITLE###", text, ""))
            return

        radio_buttons = [w for w in widgets if isinstance(w, QRadioButton)]
        if radio_buttons:
            label_text = ""
            for w in widgets:
                if isinstance(w, QLabel):
                    label_text = w.text().strip().replace(":", "").replace("：", "")
                    break
            checked_text = next((rb.text() for rb in radio_buttons if rb.isChecked()), "")
            if label_text and checked_text and not any(r[0] == label_text for r in results):
                results.append((label_text, checked_text, ""))
            return

        for idx, w in enumerate(widgets):
            if not isinstance(w, (QLineEdit, QTextEdit, QComboBox)):
                continue
            value = w.text() if isinstance(w, QLineEdit) else (w.toPlainText() if isinstance(w, QTextEdit) else w.currentText())
            name, unit = "", ""
            for k in range(idx - 1, -1, -1):
                prev_w = widgets[k]
                if isinstance(prev_w, QLabel):
                    # 前一个控件是输入框时，这个标签是它的单位，不是当前控件的名称
                    if k > 0 and isinstance(widgets[k - 1], (QLineEdit, QComboBox)):
                        continue
                    text = prev_w.text().strip().replace(":", "").replace("：", "")
                    if text:
                        name = text
                        break
                elif isinstance(prev_w, QCheckBox):
                    if prev_w.text():
                        name = prev_w.text()
                        break
                elif isinstance(prev_w, (QLineEdit, QComboBox)):
                    break
            if not name and idx > 0 and (w.width() < 60 or "Quantity" in w.objectName()):
                name = "数量"
            if idx + 1 < len(widgets) and isinstance(widgets[idx + 1], QLabel):
                unit = widgets[idx + 1].text().strip()
            if not name:
                continue
            if name == "数量" and results and "数量" not in results[-1][0]:
                name = f"{results[-1][0]} (数量)"
            if not any(r[0] == name for r in results):
                results.append((name, value, unit))

    traverse_layout(groupbox.layout())
    return results
