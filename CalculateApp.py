#region 导入必要的包
"""
CalculateApp - 系留浮空器（球形气球 / 流线形飞艇）设计计算软件

物理计算见 aerostat_physics.py：
- 浮力：标准大气压力 + 场地实测温度，气体质量守恒、超压力高度排气
- 风：10 m 参考风压 × GB 50009 高度变化系数 × 空气密度比
- 系留：缆绳分段积分（自重 + 横流风阻），平均风求姿态、阵风求峰值拉力
"""
from Sphere import Sphere
from Airship import Airship
from calc_controller import (
    AirShipAuxRatioManualEdit, AirShipCalculate, AirShipCalculateRealTime, ResetAirShipAuxRatioMode,
    ResetSphereAuxRatioMode, SphereAuxRatioManualEdit, SphereCalculate, SphereCalculateRealTime, bind as bind_calculator,
    drag_report,
)
from ui_layout import build_page, update_wind_mode_rows
import calc_controller
import page_state
import report_export
import diagrams
import sys 
import math 
from PyQt5.QtWidgets import QAbstractButton # 补充导入 

import webbrowser
import logging                                        
from PyQt5 import QtWidgets # 补充导入
from PyQt5.QtWidgets import QApplication, QMainWindow,QWidget,QMessageBox, QDialog, QVBoxLayout, QTableView, QDialogButtonBox, QCheckBox, QLabel, QHBoxLayout, QButtonGroup, QRadioButton, QAction, QLineEdit, QTextEdit, QToolButton, QSizePolicy, QGroupBox, QPushButton, QComboBox, QHeaderView, QAbstractScrollArea, QAbstractItemView, QFileDialog   # import必要的包
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import Qt,QModelIndex, QTime, QTimer, QSize
import datetime
import ui_form # import GUI的.py文件
from apply_zebra_stripes import apply_zebra_stripes  # 导入斑马纹效果

from ManageWind import ManageWind    #ManageWind
from Wind import Wind #Wind

from ManageFilm import ManageFilm    #ManageFilm
from Film import Film #Film

from ManageCable import ManageCable    #ManageCable
from Cable import Cable #Cable

from ManageTube import ManageTube    #ManageTube
from Tube import Tube #Tube

from PyQt5.QtCore import QUrl

import os
import ctypes
from ctypes import windll, byref, c_int

# 主题配置
current_theme = 'auto'  # 'light', 'dark', 'auto'
auto_theme_enabled = True

ABOUT_HTML_TEMPLATE = """
<div style='font-family: "Microsoft YaHei"; font-size: 10pt; line-height: 1.6; color: {main_color};'>
    <p align='center'><b>本软件专为气球与飞艇设计与计算开发</b></p>
    <p><b>主要功能包括：</b></p>
    <ul style='margin-top: 0px; margin-bottom: 10px;'>
        <li>气球/飞艇几何参数计算</li>
        <li>膜材、缆绳、管材等材料选型与管理</li>
        <li>浮升力、载荷及飞行性能实时评估</li>
        <li>自动化生成计算报告</li>
    </ul>
    <p><b>使用步骤：</b></p>
    <ol style='margin-top: 0px; margin-bottom: 10px;'>
        <li>在“材料管理”页维护基础数据</li>
        <li>在“气球计算”或“飞艇计算”页输入设计参数</li>
        <li>实时查看计算结果与评估结论</li>
    </ol>
    <p align='center' style='margin-top: 20px; color: {footer_color};'>欢迎使用本软件，本软件还在持续更新创作中<br>
    本软件采用Python编写，界面部分采用Qt Creator 编写</p>
</div>
"""

# 定义日间主题样式
LIGHT_THEME = """
QWidget {
    font-family: "Microsoft YaHei";
    font-size: 10pt;
}
QWidget#Widget {
    background-color: #f8f9fa;
}
QGroupBox {
    background-color: #ffffff;
    border: 1px solid #dee2e6;
    border-radius: 8px;
    margin-top: 12px;
    margin-bottom: 4px;
    padding: 10px 8px 8px 8px;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0px 8px;
    background-color: #ffffff;
    color: #1976d2;
    font-size: 12px;
    font-weight: bold;
}
QLabel {
    color: #495057;
    padding: 1px 6px 1px 0px;
    min-height: 26px;
    max-height: 26px;
    line-height: 26px;
}
QLabel[objectName*="Section"] {
    color: #1976d2;
    font-size: 12px;
    font-weight: bold;
    padding: 4px 0px;
    margin-bottom: 2px;
    min-height: 26px;
    max-height: 26px;
}
QLineEdit {
    background-color: #ffffff;
    color: #212529;
    border: 1px solid #ced4da;
    border-radius: 4px;
    padding: 2px 8px;
    padding-right: 22px;
    margin: 1px 0px;
    min-height: 26px;
}
QLineEdit:read-only {
    background-color: #e9ecef;
    color: #6c757d;
    border: 1px solid #dee2e6;
}
QTextEdit[objectName$="ConclusionLineEdit"] {
    background-color: #e9ecef;
    color: #6c757d;
    border: 1px solid #dee2e6;
    border-radius: 4px;
    padding: 0px 4px;
}
QLineEdit:focus {
    border: 2px solid #1976d2;
    background-color: #f0f8ff;
}
QLineEdit#SphereDiameterLineEdit,
QLineEdit#SphereRatioLineEdit,
QLineEdit#AirShipLengthLineEdit,
QLineEdit#AirShipDLRatioLineEdit,
QLineEdit#AirShipCenterRatioLineEdit,
QLineEdit#SphereAltitudeLineEdit,
QLineEdit#SphereTargetHeightLineEdit,
QLineEdit#SphereFilmUnitWeightLineEdit,
QLineEdit#SphereCableUnitWeightLineEdit,
QLineEdit#SphereAuxiliaryFilmUnitWeightLineEdit,
QLineEdit#SphereCustomerLoadLineEdit,
QLineEdit#AirShipAltitudeLineEdit,
QLineEdit#AirShipTargetHeightLineEdit,
QLineEdit#AirShipFilmUnitWeightLineEdit,
QLineEdit#AirShipCableUnitWeightLineEdit,
QLineEdit#AirShipAuxiliaryFilmUnitWeightLineEdit,
QLineEdit#AirShipCustomerLoadLineEdit,
QLineEdit#SphereFillFractionLineEdit,
QLineEdit#AirShipFillFractionLineEdit {
    background-color: #fff8e1;
    border: 2px solid #ff9800;
    color: #e65100;
    font-weight: 500;
}
QComboBox {
    background-color: #ffffff;
    color: #212529;
    border: 1px solid #ced4da;
    border-radius: 4px;
    padding: 2px 8px;
    margin: 1px 0px;
    min-height: 26px;
    max-height: 26px;
}
QComboBox:focus {
    border: 2px solid #1976d2;
    background-color: #f0f8ff;
}
QComboBox::drop-down {
    border: none;
    width: 20px;
}
QComboBox QAbstractItemView {
    background-color: #ffffff;
    color: #212529;
    selection-background-color: #e3f2fd;
    selection-color: #1976d2;
    border: 1px solid #ced4da;
}
/* 斑马纹效果 - 偶数行 */
QLabel[row="even"],
QLineEdit[row="even"],
QComboBox[row="even"],
QPushButton[row="even"] {
    background-color: #d0e4ff;
    margin: 0px;
    padding-top: 2px;
    padding-bottom: 2px;
}
/* 斑马纹效果 - 奇数行 */
QLabel[row="odd"],
QLineEdit[row="odd"],
QComboBox[row="odd"],
QPushButton[row="odd"] {
    background-color: #f5f5f5;
    margin: 0px;
    padding-top: 2px;
    padding-bottom: 2px;
}
/* 强制覆盖斑马纹样式的按钮 */
QPushButton[objectName*="Query"],
QPushButton[objectName*="Apply"],
QPushButton[objectName*="Add"],
QPushButton[objectName*="Delete"],
QPushButton[objectName*="Update"],
QPushButton[objectName*="UpData"] {
    min-width: 0px;
    padding: 4px 8px;
    background-color: #1976d2;
    color: #ffffff;
    border: none;
    margin: 0px; /* Reset margin */
}
QPushButton[objectName*="Query"]:hover,
QPushButton[objectName*="Apply"]:hover,
QPushButton[objectName*="Add"]:hover,
QPushButton[objectName*="Delete"]:hover,
QPushButton[objectName*="Update"]:hover,
QPushButton[objectName*="UpData"]:hover {
    background-color: #1565c0;
}
/* 输入框和下拉框保持原有的左右padding */
QLineEdit[row] {
    padding-left: 8px;
    padding-right: 22px;
}
QComboBox[row] {
    padding-left: 8px;
    padding-right: 8px;
}
/* 只读输入框保持原样式 */
QLineEdit[row="even"]:read-only {
    background-color: #b8d4f1;
}
QLineEdit[row="odd"]:read-only {
    background-color: #e0e0e0;
}
/* 聚焦状态保持统一 */
QLineEdit[row]:focus,
QComboBox[row]:focus {
    background-color: #f0f8ff;
    border: 2px solid #1976d2;
}
QComboBox[objectName*="QueryWind"],
QComboBox[objectName*="QueryFilm"],
QComboBox[objectName*="QueryCable"],
QComboBox[objectName*="QueryTube"] {
    background-color: #fff8e1;
    border: 2px solid #ff9800;
    color: #e65100;
}
QLineEdit[objectName*="Query"] {
}
QPushButton {
    background-color: #1976d2;
    color: #ffffff;
    border-radius: 4px;
    padding: 0px 12px;
    border: none;
    font-weight: 500;
    min-height: 26px;
    max-height: 26px;
}
QPushButton[objectName*="Query"],
QPushButton[objectName*="Apply"],
QPushButton[objectName*="Add"],
QPushButton[objectName*="Delete"],
QPushButton[objectName*="Update"],
QPushButton[objectName*="UpData"] {
    min-width: 0px;
    padding: 4px 8px;
    background-color: #1976d2;
    color: #ffffff;
    border: none;
}
QPushButton:hover {
    background-color: #1565c0;
}
QPushButton:pressed {
    background-color: #0d47a1;
}
QTabWidget::pane {
    border: 1px solid #dee2e6;
    background-color: #ffffff;
    border-radius: 4px;
}
QTabBar::tab {
    background-color: #e9ecef;
    color: #495057;
    padding: 6px 14px;
    border: 1px solid #dee2e6;
    margin: 2px;
}
QTabBar::tab:selected {
    background-color: #ffffff;
    color: #1976d2;
    font-weight: bold;
    border-bottom: 3px solid #1976d2;
}
QToolTip {
    background-color: #fffbe6;
    color: #212529;
    border: 1px solid #c9b458;
    padding: 4px 6px;
    font-size: 10pt;
}
QTableView {
    background-color: #ffffff;
    alternate-background-color: #f1f3f5;
    color: #212529;
    gridline-color: #dee2e6;
}
QHeaderView::section {
    background-color: #f8f9fa;
    color: #495057;
    padding: 5px;
    border: 1px solid #dee2e6;
    font-weight: 600;
}
"""

# 定义夜间主题样式
DARK_THEME = """
QWidget {
    font-family: "Microsoft YaHei";
    font-size: 10pt;
}
QWidget#Widget {
    background-color: #181818;
}
QScrollArea {
    background-color: #181818;
    border: none;
}
QWidget#scrollAreaWidgetContents_2 {
    background-color: #181818;
}
/* 修复标签页内部页面的背景色 */
QTabWidget QWidget {
    background-color: #181818;
}
/* 修复滚动条样式 */
QScrollBar:vertical {
    border: none;
    background: #181818;
    width: 12px;
    margin: 0px 0px 0px 0px;
}
QScrollBar::handle:vertical {
    background: #424242;
    min-height: 20px;
    border-radius: 6px;
}
QScrollBar::handle:vertical:hover {
    background: #616161;
}
QScrollBar::add-line:vertical {
    height: 0px;
    subcontrol-position: bottom;
    subcontrol-origin: margin;
}
QScrollBar::sub-line:vertical {
    height: 0px;
    subcontrol-position: top;
    subcontrol-origin: margin;
}
QScrollBar:horizontal {
    border: none;
    background: #181818;
    height: 12px;
    margin: 0px 0px 0px 0px;
}
QScrollBar::handle:horizontal {
    background: #424242;
    min-width: 20px;
    border-radius: 6px;
}
QScrollBar::handle:horizontal:hover {
    background: #616161;
}
QScrollBar::add-line:horizontal {
    width: 0px;
    subcontrol-position: right;
    subcontrol-origin: margin;
}
QScrollBar::sub-line:horizontal {
    width: 0px;
    subcontrol-position: left;
    subcontrol-origin: margin;
}
/* 修复角落控件背景 */
QAbstractScrollArea::corner {
    background: #181818;
    border: none;
}
QGroupBox {
    background-color: #252525;
    border: 1px solid #3a3a3a;
    border-radius: 8px;
    margin-top: 12px;
    margin-bottom: 4px;
    padding: 10px 8px 8px 8px;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0px 8px;
    background-color: #252525;
    color: #64b5f6;
    font-size: 12px;
    font-weight: bold;
}
QLabel {
    color: #b0bec5;
    padding: 1px 6px 1px 0px;
    min-height: 26px;
    max-height: 26px;
    line-height: 26px;
}
QLabel[objectName*="Section"] {
    color: #64b5f6;
    font-size: 12px;
    font-weight: bold;
    padding: 4px 0px;
    margin-bottom: 2px;
    min-height: 26px;
    max-height: 26px;
}
QLineEdit {
    background-color: #2d2d2d;
    color: #eceff1;
    border: 1px solid #424242;
    border-radius: 4px;
    padding: 2px 8px;
    padding-right: 22px;
    margin: 1px 0px;
    min-height: 26px;
}
QLineEdit:read-only {
    background-color: #1e1e1e;
    color: #90a4ae;
    border: 1px solid #3a3a3a;
}
QTextEdit[objectName$="ConclusionLineEdit"] {
    background-color: #1e1e1e;
    color: #90a4ae;
    border: 1px solid #3a3a3a;
    border-radius: 4px;
    padding: 0px 4px;
}
QLineEdit:focus {
    border: 2px solid #64b5f6;
    background-color: #1e3a5f;
}
QLineEdit#SphereDiameterLineEdit,
QLineEdit#SphereRatioLineEdit,
QLineEdit#AirShipLengthLineEdit,
QLineEdit#AirShipDLRatioLineEdit,
QLineEdit#AirShipCenterRatioLineEdit,
QLineEdit#SphereAltitudeLineEdit,
QLineEdit#SphereTargetHeightLineEdit,
QLineEdit#SphereFilmUnitWeightLineEdit,
QLineEdit#SphereCableUnitWeightLineEdit,
QLineEdit#SphereAuxiliaryFilmUnitWeightLineEdit,
QLineEdit#SphereCustomerLoadLineEdit,
QLineEdit#AirShipAltitudeLineEdit,
QLineEdit#AirShipTargetHeightLineEdit,
QLineEdit#AirShipFilmUnitWeightLineEdit,
QLineEdit#AirShipCableUnitWeightLineEdit,
QLineEdit#AirShipAuxiliaryFilmUnitWeightLineEdit,
QLineEdit#AirShipCustomerLoadLineEdit,
QLineEdit#SphereFillFractionLineEdit,
QLineEdit#AirShipFillFractionLineEdit {
    background-color: #3e2723;
    border: 2px solid #ff9800;
    color: #ffb74d;
    font-weight: 500;
}
QComboBox {
    background-color: #2d2d2d;
    color: #eceff1;
    border: 1px solid #424242;
    border-radius: 4px;
    padding: 2px 8px;
    margin: 1px 0px;
    min-height: 26px;
    max-height: 26px;
}
QComboBox:focus {
    border: 2px solid #64b5f6;
    background-color: #1e3a5f;
}
QComboBox::drop-down {
    border: none;
    width: 20px;
}
QComboBox QAbstractItemView {
    background-color: #2d2d2d;
    color: #eceff1;
    selection-background-color: #1e3a5f;
    selection-color: #64b5f6;
    border: 1px solid #424242;
}
/* 斑马纹效果 - 偶数行 */
QLabel[row="even"],
QLineEdit[row="even"],
QComboBox[row="even"],
QPushButton[row="even"] {
    background-color: #353941;
    margin: 0px;
    padding-top: 2px;
    padding-bottom: 2px;
}
/* 斑马纹效果 - 奇数行 */
QLabel[row="odd"],
QLineEdit[row="odd"],
QComboBox[row="odd"],
QPushButton[row="odd"] {
    background-color: #2a2d31;
    margin: 0px;
    padding-top: 2px;
    padding-bottom: 2px;
}
/* 强制覆盖斑马纹样式的按钮 */
QPushButton[objectName*="Query"],
QPushButton[objectName*="Apply"],
QPushButton[objectName*="Add"],
QPushButton[objectName*="Delete"],
QPushButton[objectName*="Update"],
QPushButton[objectName*="UpData"] {
    min-width: 0px;
    padding: 4px 8px;
    background-color: #1976d2;
    color: #ffffff;
    border: none;
    margin: 0px;
}
QPushButton[objectName*="Query"]:hover,
QPushButton[objectName*="Apply"]:hover,
QPushButton[objectName*="Add"]:hover,
QPushButton[objectName*="Delete"]:hover,
QPushButton[objectName*="Update"]:hover,
QPushButton[objectName*="UpData"]:hover {
    background-color: #1e88e5;
}
/* 输入框和下拉框保持原有的左右padding */
QLineEdit[row] {
    padding-left: 8px;
    padding-right: 22px;
}
QComboBox[row] {
    padding-left: 8px;
    padding-right: 8px;
}
/* 只读输入框保持原样式 */
QLineEdit[row="even"]:read-only {
    background-color: #424751;
}
QLineEdit[row="odd"]:read-only {
    background-color: #373a3f;
}
/* 聚焦状态保持统一 */
QLineEdit[row]:focus,
QComboBox[row]:focus {
    background-color: #1e3a5f;
    border: 2px solid #64b5f6;
}
QComboBox[objectName*="QueryWind"],
QComboBox[objectName*="QueryFilm"],
QComboBox[objectName*="QueryCable"],
QComboBox[objectName*="QueryTube"] {
    background-color: #3e2723;
    border: 2px solid #ff9800;
    color: #ffb74d;
}
QLineEdit[objectName*="Query"] {
}
QPushButton {
    background-color: #1976d2;
    color: #ffffff;
    border-radius: 4px;
    padding: 0px 12px;
    border: none;
    font-weight: 500;
    min-height: 26px;
    max-height: 26px;
}
QPushButton[objectName*="Query"],
QPushButton[objectName*="Apply"],
QPushButton[objectName*="Add"],
QPushButton[objectName*="Delete"],
QPushButton[objectName*="Update"],
QPushButton[objectName*="UpData"] {
    min-width: 0px;
    padding: 4px 8px;
    background-color: #1976d2;
    color: #ffffff;
    border: none;
}
QPushButton:hover {
    background-color: #1e88e5;
}
QPushButton:pressed {
    background-color: #0d47a1;
}
/* 修复标签页背景 */
QTabWidget {
    background-color: #181818;
}
QTabWidget::pane {
    border: 1px solid #3a3a3a;
    background-color: #252525;
    border-radius: 4px;
}
QTabBar {
    background-color: #181818;
}
QTabBar::tab {
    background-color: #1e1e1e;
    color: #90a4ae;
    padding: 6px 14px;
    border: 1px solid #3a3a3a;
    margin: 2px;
}
QTabBar::tab:selected {
    background-color: #252525;
    color: #64b5f6;
    font-weight: bold;
    border-bottom: 3px solid #64b5f6;
}
/* 修复表格左上角按钮 */
QTableCornerButton::section {
    background-color: #1e1e1e;
    border: 1px solid #3a3a3a;
    color: #b0bec5;
}
QToolTip {
    background-color: #fffbe6;
    color: #212529;
    border: 1px solid #c9b458;
    padding: 4px 6px;
    font-size: 10pt;
}
QTableView {
    background-color: #252525;
    alternate-background-color: #2f2f2f;
    color: #eceff1;
    gridline-color: #3a3a3a;
}
QHeaderView::section {
    background-color: #1e1e1e;
    color: #b0bec5;
    padding: 5px;
    border: 1px solid #3a3a3a;
    font-weight: 600;
}
QCheckBox {
    color: #eceff1;
}
QRadioButton {
    color: #eceff1;
}
"""

def get_theme_style():
    """根据当前设置返回应用的主题样式"""
    global current_theme, auto_theme_enabled
    
    if current_theme == 'light':
        return LIGHT_THEME
    elif current_theme == 'dark':
        return DARK_THEME
    elif current_theme == 'auto' and auto_theme_enabled:
        # 自动模式：6:00-18:00 使用日间主题，其他时间使用夜间主题
        current_hour = QTime.currentTime().hour()
        if 6 <= current_hour < 18:
            return LIGHT_THEME
        else:
            return DARK_THEME
    else:
        return DARK_THEME  # 默认使用夜间主题

def apply_theme():
    """应用主题到主窗口"""
    global MainWindow, ui
    if MainWindow:
        style = get_theme_style()
        MainWindow.setStyleSheet(style)
        
        # 设置Windows标题栏颜色
        is_dark = (style == DARK_THEME)
        diagrams.set_dark(is_dark)
        for canvas in MainWindow.findChildren(diagrams.Canvas):
            canvas.update()
        try:
            hwnd = int(MainWindow.winId())
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            set_window_attribute = windll.dwmapi.DwmSetWindowAttribute
            value = c_int(1 if is_dark else 0)
            set_window_attribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, byref(value), ctypes.sizeof(value))
            
            # 强制刷新标题栏
            windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0027) # SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED
        except Exception as e:
            pass

        # 设置表格左上角按钮文字
        if 'ui' in globals():
            table_views = [ui.WindTableView, ui.FilmTableView, ui.CableTableView, ui.TubeTableView]
            for tv in table_views:
                if tv:
                    btn = tv.findChild(QAbstractButton)
                    if btn:
                        btn.setText("序号")
                        # 确保文字颜色正确
                        if is_dark:
                            btn.setStyleSheet("color: #b0bec5; font-weight: bold; border: 1px solid #3a3a3a; background-color: #1e1e1e;")
                        else:
                            btn.setStyleSheet("")

            # 更新关于页面的文字颜色
            if hasattr(ui, 'textBrowser_About'):
                if is_dark:
                    main_color = "#eceff1"
                    footer_color = "#b0bec5"
                else:
                    main_color = "#000000"
                    footer_color = "#666666"
                ui.textBrowser_About.setHtml(ABOUT_HTML_TEMPLATE.format(main_color=main_color, footer_color=footer_color))

        # 重新应用斑马纹效果
        if 'ui' in globals():
            apply_zebra_stripes(ui)
            # 强制刷新样式
            MainWindow.style().unpolish(MainWindow)
            MainWindow.style().polish(MainWindow)
            MainWindow.update()

def set_theme_light():
    """设置为日间主题"""
    global current_theme
    current_theme = 'light'
    apply_theme()

def set_theme_dark():
    """设置为夜间主题"""
    global current_theme
    current_theme = 'dark'
    apply_theme()

def set_theme_auto():
    """设置为自动切换"""
    global current_theme
    current_theme = 'auto'
    apply_theme()

def toggle_auto_theme(enabled):
    """切换自动主题开关"""
    global auto_theme_enabled, current_theme
    auto_theme_enabled = enabled
    if enabled:
        current_theme = 'auto'
    apply_theme()

def check_auto_theme_update():
    """定时检查是否需要自动更新主题（仅在自动模式下）"""
    if current_theme == 'auto' and auto_theme_enabled:
        apply_theme()

#endregion
#region 定义日志
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(filename)s[line:%(lineno)d] %(levelname)s %(message)s',
                    filename='CalculateApp.log',
                    filemode='w')
#endregion
#region 实例化管理类
manageWind= ManageWind()#实列化风压管理类
manageWind.createWindTable("WindTable")

manageFilm= ManageFilm()#实列化膜材管理类
manageFilm.createFilmTable("FilmTable")

manageCable= ManageCable()#实列化缆绳管理类
manageCable.createCableTable("CableTable")

manageTube= ManageTube()#实列化管材管理类
manageTube.createTubeTable("TubeTable")
#endregion

#region 球体计算
def SphereDivideNumberCalculate():#球体开片评估
    try: 
        if  ui.SphereDiameterLineEdit.text()=="" or ui.SphereDiameterLineEdit.text().strip()=="":
            return  # 如果输入框为空，直接返回，不进行评估
        else: 
            pass             
        if  ui.SphereRatioLineEdit.text()=="": 
            ui.SphereRatioLineEdit.setText("1")
        else:   
           pass
        diameter=float(ui.SphereDiameterLineEdit.text())#球体直径
        if diameter<1:
            ui.SphereDivideNumberComboBox.setCurrentText('6')
        elif diameter<2 and diameter>=1:
            ui.SphereDivideNumberComboBox.setCurrentText('6')
        elif diameter<3 and diameter>=2:
            ui.SphereDivideNumberComboBox.setCurrentText('8')
        elif diameter<4 and diameter>=3:
            ui.SphereDivideNumberComboBox.setCurrentText('10')
        elif diameter<5 and diameter>=4:
            ui.SphereDivideNumberComboBox.setCurrentText('12')
        elif diameter<6 and diameter>=5:
            ui.SphereDivideNumberComboBox.setCurrentText('16')
        elif diameter<7 and diameter>=6:
            ui.SphereDivideNumberComboBox.setCurrentText('18')
        elif diameter<8 and diameter>=7:
            ui.SphereDivideNumberComboBox.setCurrentText('24')
        elif diameter<9 and diameter>=8:
            ui.SphereDivideNumberComboBox.setCurrentText('24')
        elif diameter<10 and diameter>=9:
            ui.SphereDivideNumberComboBox.setCurrentText('32')
        elif diameter<11 and diameter>=10:
            ui.SphereDivideNumberComboBox.setCurrentText('32')
        elif diameter<12 and diameter>=11:
            ui.SphereDivideNumberComboBox.setCurrentText('32')
        elif diameter<13 and diameter>=12:
            ui.SphereDivideNumberComboBox.setCurrentText('40')
        elif diameter<14 and diameter>=13:
            ui.SphereDivideNumberComboBox.setCurrentText('40')
        elif diameter<15 and diameter>=14:
            ui.SphereDivideNumberComboBox.setCurrentText('48')
        elif diameter<16 and diameter>=15:
            ui.SphereDivideNumberComboBox.setCurrentText('48')
        elif diameter<17 and diameter>=16:
            ui.SphereDivideNumberComboBox.setCurrentText('48')
        elif diameter<18 and diameter>=17:
            ui.SphereDivideNumberComboBox.setCurrentText('56')
        elif diameter<19 and diameter>=18:
            ui.SphereDivideNumberComboBox.setCurrentText('56')
        elif diameter<20 and diameter>=19:
            ui.SphereDivideNumberComboBox.setCurrentText('56')
        elif diameter<21 and diameter>=20:
            ui.SphereDivideNumberComboBox.setCurrentText('64')
        elif diameter<22 and diameter>=21:
            ui.SphereDivideNumberComboBox.setCurrentText('64')
        elif diameter<23 and diameter>=22:
            ui.SphereDivideNumberComboBox.setCurrentText('72')
        elif diameter<24 and diameter>=23:
            ui.SphereDivideNumberComboBox.setCurrentText('72')
        elif diameter<25 and diameter>=24:
             ui.SphereDivideNumberComboBox.setCurrentText('72')
        else:
            if ui.SphereDivideNumberComboBox.findText('80') < 0:
                ui.SphereDivideNumberComboBox.addItem('80')
            ui.SphereDivideNumberComboBox.setCurrentText('80')
    except   ValueError:
       logging.error("请输入正确的数值") 
#endregion
#region 飞艇计算
def AirShipDivideNumberCalculate():#飞艇开片评估
    try:
        if  ui.AirShipLengthLineEdit.text()=="" or ui.AirShipLengthLineEdit.text().strip()=="":
            return  # 如果输入框为空，直接返回，不进行评估
        else:  
            pass
        if  ui.AirShipDLRatioLineEdit.text()=="": 
            ui.AirShipDLRatioLineEdit.setText("0.25")
        else:
            pass
        airShipDiameter=float(ui.AirShipLengthLineEdit.text())*float(ui.AirShipDLRatioLineEdit.text())
        if airShipDiameter<1:
            ui.AirShipDivideNumberComboBox.setCurrentText('6')
        elif airShipDiameter<2 and airShipDiameter>=1:
            ui.AirShipDivideNumberComboBox.setCurrentText('6')
        elif airShipDiameter<3 and airShipDiameter>=2:
            ui.AirShipDivideNumberComboBox.setCurrentText('8')
        elif airShipDiameter<4 and airShipDiameter>=3:
            ui.AirShipDivideNumberComboBox.setCurrentText('10')
        elif airShipDiameter<5 and airShipDiameter>=4:
            ui.AirShipDivideNumberComboBox.setCurrentText('12')
        elif airShipDiameter<6 and airShipDiameter>=5:
            ui.AirShipDivideNumberComboBox.setCurrentText('16')
        elif airShipDiameter<7 and airShipDiameter>=6:
            ui.AirShipDivideNumberComboBox.setCurrentText('18')
        elif airShipDiameter<8 and airShipDiameter>=7:
            ui.AirShipDivideNumberComboBox.setCurrentText('24')
        elif airShipDiameter<9 and airShipDiameter>=8:
            ui.AirShipDivideNumberComboBox.setCurrentText('24')
        elif airShipDiameter<10 and airShipDiameter>=9:
            ui.AirShipDivideNumberComboBox.setCurrentText('32')
        elif airShipDiameter<11 and airShipDiameter>=10:
            ui.AirShipDivideNumberComboBox.setCurrentText('32')
        elif airShipDiameter<12 and airShipDiameter>=11:
            ui.AirShipDivideNumberComboBox.setCurrentText('32')
        elif airShipDiameter<13 and airShipDiameter>=12:
            ui.AirShipDivideNumberComboBox.setCurrentText('40')
        elif airShipDiameter<14 and airShipDiameter>=13:
            ui.AirShipDivideNumberComboBox.setCurrentText('40')
        elif airShipDiameter<15 and airShipDiameter>=14:
            ui.AirShipDivideNumberComboBox.setCurrentText('48')
        elif airShipDiameter<16 and airShipDiameter>=15:
            ui.AirShipDivideNumberComboBox.setCurrentText('48')
        elif airShipDiameter<17 and airShipDiameter>=16:
            ui.AirShipDivideNumberComboBox.setCurrentText('48')
        elif airShipDiameter<18 and airShipDiameter>=17:
            ui.AirShipDivideNumberComboBox.setCurrentText('56')
        elif airShipDiameter<19 and airShipDiameter>=18:
            ui.AirShipDivideNumberComboBox.setCurrentText('56')
        elif airShipDiameter<20 and airShipDiameter>=19:
            ui.AirShipDivideNumberComboBox.setCurrentText('56')
        elif airShipDiameter<21 and airShipDiameter>=20:
            ui.AirShipDivideNumberComboBox.setCurrentText('64')
        elif airShipDiameter<22 and airShipDiameter>=21:
            ui.AirShipDivideNumberComboBox.setCurrentText('64')
        elif airShipDiameter<23 and airShipDiameter>=22:
            ui.AirShipDivideNumberComboBox.setCurrentText('72')
        elif airShipDiameter<24 and airShipDiameter>=23:
            ui.AirShipDivideNumberComboBox.setCurrentText('72')
        elif airShipDiameter<25 and airShipDiameter>=24:
             ui.AirShipDivideNumberComboBox.setCurrentText('72')
        else:
            if ui.AirShipDivideNumberComboBox.findText('80') < 0:
                ui.AirShipDivideNumberComboBox.addItem('80')
            ui.AirShipDivideNumberComboBox.setCurrentText('80')
    except ValueError:
       logging.error("请输入正确的数值") 
#endregion
#region 风速管理
def QueryWind():#风压查询 
    try: 
        windLevel = ui.QueryWindComboBox.currentText()
        data=manageWind.selectWind('WindTable','*',windLevel)
        ui.QueryWindNameLineEdit.setText(str(data[0][2]))
        ui.QueryWindSpeedLineEdit.setText(str(data[0][3]))
        ui.QueryWindPressureLineEdit.setText(str(data[0][4]))
    except ValueError:
       logging.error("请输入正确的数值")  
def ManageInsertWind(): 
   try:
        wind=Wind(0,0,'清风',0,0)
        wind.level = int(ui.QueryWindComboBox.currentText())    
        wind.name = ui.QueryWindNameLineEdit.text()
        wind.speed = float(ui.QueryWindSpeedLineEdit.text())   
        wind.pressure=float(ui.QueryWindPressureLineEdit.text())
        reply=QMessageBox.question(MainWindow, '提示', '是否确认添加？', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if  reply==QMessageBox.Yes:
            manageWind.insertWind('WindTable',wind)
            ManageQueryWind()
   except Exception as e:
       logging.error(e)
def ManageDeleteWind():
    try:
        reply=QMessageBox.question(MainWindow, '提示', '是否确认删除？', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if  reply==QMessageBox.Yes:
            manageWind.deleteWind('WindTable',int(ui.QueryWindComboBox.currentText()))
            ManageQueryWind()
    except Exception as e:
       logging.error(e)
def ManageUpdateWind():
   try:
     wind=Wind(0,0,'清风',0,0)
     wind.level = int(ui.QueryWindComboBox.currentText())    
     wind.name = ui.QueryWindNameLineEdit.text()
     wind.speed = float(ui.QueryWindSpeedLineEdit.text())   
     wind.pressure=float(ui.QueryWindPressureLineEdit.text())
     reply=QMessageBox.question(MainWindow, '提示', '是否确认修改？', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
     if reply==QMessageBox.Yes:
        manageWind.updateWind('WindTable',wind)
        ManageQueryWind()
   except Exception as e:
       logging.error(e)
def ManageQueryWind(): 
    try:
        headers=['编号','等级','名称','速度(m/s)','压强(Kg/㎡)']
        data=manageWind.selectAllWind('WindTable',headers) 
        ui.WindTableView.setModel(data)
        ui.WindTableView.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    except Exception as e:
       logging.error(e)
def SelectionChangedWind(index: QModelIndex):
    try:
          if index.isValid():
              row=index.row()
              windModel=ui.WindTableView.model()
              columns=windModel.columnCount()
              rowData=[]
              for i in range(columns):
                  index=windModel.index(row,i)
                  data=windModel.data(index,Qt.DisplayRole)
                  rowData.append(data)            
              ui.QueryWindComboBox.setCurrentText(str(rowData[1]))
              ui.QueryWindNameLineEdit.setText(str(rowData[2]))
              ui.QueryWindSpeedLineEdit.setText(str(rowData[3]))
              ui.QueryWindPressureLineEdit.setText(str(rowData[4]))
    except Exception as e:
       logging.error(e)

#endregion 
#region 膜材管理
def QueryFilm():#膜材查询
    
    try:
        manufacture = ui.QueryFilmManufactureComboBox.currentText()
        material = ui.QueryFilmMaterialComboBox.currentText()
        thickness = ui.QueryFilmThicknessComboBox.currentText()
        data=manageFilm.selectFilm('FilmTable','*',manufacture,material,thickness)
        if len(data)>0:
            ui.QueryFilmUnitWeightLineEdit.setText(str(data[0][4]))
            ui.QueryFilmBreakingForceWarpLineEdit.setText(str(data[0][5]))
            ui.QueryFilmBreakingForceWeftLineEdit.setText(str(data[0][6]))
            ui.QueryFilmTearStrengthWarpLineEdit.setText(str(data[0][7]))
            ui.QueryFilmTearStrengthWeftLineEdit.setText(str(data[0][8]))
            ui.QueryFilmPeelStrengthWarpLineEdit.setText(str(data[0][9]))
            ui.QueryFilmPeelStrengthWeftLineEdit.setText(str(data[0][10]))
            ui.QueryFilmElongateWarpLineEdit.setText(str(data[0][11]))
            ui.QueryFilmElongateWeftLineEdit.setText(str(data[0][12]))
            ui.QueryFilmPermeabilityLineEdit.setText(str(data[0][13])) 
        else:
            ui.QueryFilmUnitWeightLineEdit.setText('NULL')
            ui.QueryFilmBreakingForceWarpLineEdit.setText('NULL')
            ui.QueryFilmBreakingForceWeftLineEdit.setText('NULL')
            ui.QueryFilmTearStrengthWarpLineEdit.setText('NULL')
            ui.QueryFilmTearStrengthWeftLineEdit.setText('NULL')
            ui.QueryFilmPeelStrengthWarpLineEdit.setText('NULL')
            ui.QueryFilmPeelStrengthWeftLineEdit.setText('NULL')
            ui.QueryFilmElongateWarpLineEdit.setText('NULL')
            ui.QueryFilmElongateWeftLineEdit.setText('NULL')
            ui.QueryFilmPermeabilityLineEdit.setText('NULL')
    except ValueError:
       logging.error("请输入正确的数值")  
def ManageInsertFilm(): 
   try:
        film=Film()
        film.manufacture = ui.QueryFilmManufactureComboBox.currentText()
        film.material = ui.QueryFilmMaterialComboBox.currentText()
        
        def get_float(text):
            if not text or text.strip() == '' or text.strip().upper() == 'NULL':
                return 0.0
            try:
                return float(text)
            except ValueError:
                return 0.0

        film.thickness = get_float(ui.QueryFilmThicknessComboBox.currentText())
        film.unitWeight = get_float(ui.QueryFilmUnitWeightLineEdit.text())
        film.breakingForceWarp = get_float(ui.QueryFilmBreakingForceWarpLineEdit.text())
        film.breakingForceWeft = get_float(ui.QueryFilmBreakingForceWeftLineEdit.text())
        film.tearStrengthWarp = get_float(ui.QueryFilmTearStrengthWarpLineEdit.text())
        film.tearStrengthWeft = get_float(ui.QueryFilmTearStrengthWeftLineEdit.text())
        film.peelStrengthWarp = get_float(ui.QueryFilmPeelStrengthWarpLineEdit.text())
        film.peelStrengthWeft = get_float(ui.QueryFilmPeelStrengthWeftLineEdit.text())
        film.elongateWarp = get_float(ui.QueryFilmElongateWarpLineEdit.text())
        film.elongateWeft = get_float(ui.QueryFilmElongateWeftLineEdit.text())
        film.permeability=get_float(ui.QueryFilmPermeabilityLineEdit.text())
        
        reply=QMessageBox.question(MainWindow, '提示', '是否确认添加？', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if  reply==QMessageBox.Yes:
            manageFilm.insertFilm('FilmTable',film)
            ManageQueryFilm()
       
   except Exception as e:
       logging.error(e)
       QMessageBox.warning(MainWindow, '错误', f'添加失败: {str(e)}')
def ManageDeleteFilm():
    try:
        reply=QMessageBox.question(MainWindow, '提示', '是否确认删除？', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if  reply==QMessageBox.Yes:
            thickness_text = ui.QueryFilmThicknessComboBox.currentText()
            thickness = 0.0
            if thickness_text and thickness_text.strip() != '' and thickness_text.strip().upper() != 'NULL':
                 try:
                    thickness = float(thickness_text)
                 except ValueError:
                    thickness = 0.0
            
            manageFilm.deleteFilm('FilmTable',ui.QueryFilmManufactureComboBox.currentText(),ui.QueryFilmMaterialComboBox.currentText(),thickness)
            ManageQueryFilm()
    except Exception as e:
       logging.error(e)
       QMessageBox.warning(MainWindow, '错误', f'删除失败: {str(e)}')
def ManageUpdateFilm():
   try:
     film=Film()
     film.manufacture = ui.QueryFilmManufactureComboBox.currentText()
     film.material = ui.QueryFilmMaterialComboBox.currentText()
     
     def get_float(text):
            if not text or text.strip() == '' or text.strip().upper() == 'NULL':
                return 0.0
            try:
                return float(text)
            except ValueError:
                return 0.0

     film.thickness = get_float(ui.QueryFilmThicknessComboBox.currentText())
     film.unitWeight = get_float(ui.QueryFilmUnitWeightLineEdit.text())
     film.breakingForceWarp = get_float(ui.QueryFilmBreakingForceWarpLineEdit.text())
     film.breakingForceWeft = get_float(ui.QueryFilmBreakingForceWeftLineEdit.text())
     film.tearStrengthWarp = get_float(ui.QueryFilmTearStrengthWarpLineEdit.text())
     film.tearStrengthWeft = get_float(ui.QueryFilmTearStrengthWeftLineEdit.text())
     film.peelStrengthWarp = get_float(ui.QueryFilmPeelStrengthWarpLineEdit.text())
     film.peelStrengthWeft = get_float(ui.QueryFilmPeelStrengthWeftLineEdit.text())
     film.elongateWarp = get_float(ui.QueryFilmElongateWarpLineEdit.text())
     film.elongateWeft = get_float(ui.QueryFilmElongateWeftLineEdit.text())
     film.permeability=get_float(ui.QueryFilmPermeabilityLineEdit.text())
     
     reply=QMessageBox.question(MainWindow, '提示', '是否确认修改？', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
     if reply==QMessageBox.Yes:
        manageFilm.updateFilm('FilmTable',film)
        ManageQueryFilm()
   except Exception as e:
       logging.error(e)
       QMessageBox.warning(MainWindow, '错误', f'修改失败: {str(e)}')
       logging.error(e)
def ManageQueryFilm(): 
    try:
        headers=['编号','产家','材质','厚度(mm)','克重(Kg/㎡)','抗拉强度-经(N/5cm)','抗拉强度-纬(N/5cm)','撕裂强度-径(N)','撕裂强度-纬(N)','剥离负荷-径(N/5cm)','剥离负荷-纬(N/5cm)','断裂伸长率-径（%)','断裂伸长率-纬（%)','透氦率（L/㎡*24h*atm）']
        data=manageFilm.selectAllFilm('FilmTable',headers) 
        ui.FilmTableView.setModel(data)
        ui.FilmTableView.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    except Exception as e:
       logging.error(e)
def SelectionChangedFilm(index: QModelIndex):
    try:
          if index.isValid():
              row=index.row()
              filmModel=ui.FilmTableView.model()
              columns=filmModel.columnCount()
              rowData=[]
              for i in range(columns):
                  index=filmModel.index(row,i)
                  data=filmModel.data(index,Qt.DisplayRole)
                  rowData.append(data)            
              ui.QueryFilmManufactureComboBox.setCurrentText(str(rowData[1]))
              ui.QueryFilmMaterialComboBox.setCurrentText(str(rowData[2]))
              ui.QueryFilmThicknessComboBox.setCurrentText(str(rowData[3]))
              ui.QueryFilmUnitWeightLineEdit.setText(str(rowData[4]))
              ui.QueryFilmBreakingForceWarpLineEdit.setText(str(rowData[5]))
              ui.QueryFilmBreakingForceWeftLineEdit.setText(str(rowData[6]))
              ui.QueryFilmTearStrengthWarpLineEdit.setText(str(rowData[7]))
              ui.QueryFilmTearStrengthWeftLineEdit.setText(str(rowData[8]))
              ui.QueryFilmPeelStrengthWarpLineEdit.setText(str(rowData[9]))
              ui.QueryFilmPeelStrengthWeftLineEdit.setText(str(rowData[10]))
              ui.QueryFilmElongateWarpLineEdit.setText(str(rowData[11]))
              ui.QueryFilmElongateWeftLineEdit.setText(str(rowData[12]))
              ui.QueryFilmPermeabilityLineEdit.setText(str(rowData[13]))
    except Exception as e:
       logging.error(e)
#endregion
#region 缆绳部分
def QueryCable():#缆绳查询
    try: 
        material = ui.QueryCableMaterialComboBox.currentText()
        diameter = ui.QueryCableDiameterComboBox.currentText()
        data=manageCable.selectCable('CableTable','*',material,diameter)
        if len(data)>0:
            ui.QueryCableUnitWeightLineEdit.setText(str(data[0][3]))
            ui.QueryCableBreakingForceLineEdit.setText(str(data[0][4]))
        else:
            ui.QueryCableUnitWeightLineEdit.setText("NULL")
            ui.QueryCableBreakingForceLineEdit.setText("NULL")

    except ValueError:
       logging.error("请输入正确的数值")  
def ManageInsertCable(): 
   try:
        cable=Cable()
        cable.material = ui.QueryCableMaterialComboBox.currentText()
        cable.diameter = float(ui.QueryCableDiameterComboBox.currentText())
        cable.unitWeight = float(ui.QueryCableUnitWeightLineEdit.text())
        cable.breakingForce = float(ui.QueryCableBreakingForceLineEdit.text())
        reply=QMessageBox.question(MainWindow, '提示', '是否确认添加？', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if  reply==QMessageBox.Yes:
            manageCable.insertCable('CableTable',cable)
            ManageQueryCable()
   except Exception as e:
       logging.error(e)
def ManageDeleteCable():
    try:
        reply=QMessageBox.question(MainWindow, '提示', '是否确认删除？', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if  reply==QMessageBox.Yes:
            manageCable.deleteCable('CableTable',ui.QueryCableMaterialComboBox.currentText(),float(ui.QueryCableDiameterComboBox.currentText()))
            ManageQueryCable()
    except Exception as e:
       logging.error(e)
def ManageUpdateCable():
   try:
     cable=Cable()
     cable.material = ui.QueryCableMaterialComboBox.currentText()
     cable.diameter = float(ui.QueryCableDiameterComboBox.currentText())
     cable.unitWeight = float(ui.QueryCableUnitWeightLineEdit.text())
     cable.breakingForce = float(ui.QueryCableBreakingForceLineEdit.text())
     reply=QMessageBox.question(MainWindow, '提示', '是否确认修改？', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
     if reply==QMessageBox.Yes:
        manageCable.updateCable('CableTable',cable)
        ManageQueryCable()
   except Exception as e:
       logging.error(e)
def ManageQueryCable(): 
    try:
        headers=['编号','缆绳材质','缆绳直径(mm)','米重(Kg/m)','破断力(kgf)']
        data=manageCable.selectAllCable('CableTable',headers) 
        ui.CableTableView.setModel(data)
        ui.CableTableView.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    except Exception as e:
       logging.error(e)
def SelectionChangedCable(index: QModelIndex):
    try:
          if index.isValid():
              row=index.row()
              cableModel=ui.CableTableView.model()
              columns=cableModel.columnCount()
              rowData=[]
              for i in range(columns):
                  index=cableModel.index(row,i)
                  data=cableModel.data(index,Qt.DisplayRole)
                  rowData.append(data)                                      
              ui.QueryCableMaterialComboBox.setCurrentText(str(rowData[1]))
              ui.QueryCableDiameterComboBox.setCurrentText(str(int(rowData[2])))
              ui.QueryCableUnitWeightLineEdit.setText(str(rowData[3]))
              ui.QueryCableBreakingForceLineEdit.setText(str(rowData[4]))
    except Exception as e:
       logging.error(e)
# endregion
#region 管材部分
def QueryTube():#管材查询
    try: 
        material = ui.QueryTubeMaterialComboBox.currentText()
        diameter = ui.QueryTubeDiameterComboBox.currentText()
        thickness = ui.QueryTubeThicknessComboBox.currentText()
        data=manageTube.selectTube('TubeTable','*',material,diameter,thickness)
        if len(data)>0:           
            ui.QueryTubeUnitWeightLineEdit.setText(str(data[0][4]))
        else:
            ui.QueryTubeUnitWeightLineEdit.setText("NULL")    
    except ValueError:
       logging.error("请输入正确的数值")  
def ManageInsertTube(): 
   try:
        tube=Tube()
        tube.material = ui.QueryTubeMaterialComboBox.currentText()
        tube.diameter = float(ui.QueryTubeDiameterComboBox.currentText())
        tube.thickness = float(ui.QueryTubeThicknessComboBox.currentText())
        tube.unitWeight = float(ui.QueryTubeUnitWeightLineEdit.text())
        reply=QMessageBox.question(MainWindow, '提示', '是否确认添加？', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if  reply==QMessageBox.Yes:
            manageTube.insertTube('TubeTable',tube)
            ManageQueryTube()
   except Exception as e:
       logging.error(e)
def ManageDeleteTube():
    try:
        reply=QMessageBox.question(MainWindow, '提示', '是否确认删除？', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if  reply==QMessageBox.Yes:
            manageTube.deleteTube('TubeTable',ui.QueryTubeMaterialComboBox.currentText(),float(ui.QueryTubeDiameterComboBox.currentText()),float(ui.QueryTubeThicknessComboBox.currentText()))
            ManageQueryTube()
    except Exception as e:
       logging.error(e)
def ManageUpdateTube():
   try:
     tube=Tube()
     tube.material = ui.QueryTubeMaterialComboBox.currentText()
     tube.diameter = float(ui.QueryTubeDiameterComboBox.currentText())
     tube.thickness = float(ui.QueryTubeThicknessComboBox.currentText())
     tube.unitWeight = float(ui.QueryTubeUnitWeightLineEdit.text())
     reply=QMessageBox.question(MainWindow, '提示', '是否确认修改？', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
     if reply==QMessageBox.Yes:
        manageTube.updateTube('TubeTable',tube)
        ManageQueryTube()
   except Exception as e:
       logging.error(e)
def ManageQueryTube(): 
    try:
        headers=['编号','管材材质','管材规格(mm)','管材壁厚','米重(Kg/m)']
        data=manageTube.selectAllTube('TubeTable',headers) 
        ui.TubeTableView.setModel(data)
        ui.TubeTableView.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    except Exception as e:
       logging.error(e)
def SelectionChangedTube(index: QModelIndex):
    try:
          if index.isValid():
              row=index.row()
              tubeModel=ui.TubeTableView.model()
              columns=tubeModel.columnCount()
              rowData=[]
              for i in range(columns):
                  index=tubeModel.index(row,i)
                  data=tubeModel.data(index,Qt.DisplayRole)
                  rowData.append(data)            
              ui.QueryTubeMaterialComboBox.setCurrentText(str(rowData[1]))
              ui.QueryTubeDiameterComboBox.setCurrentText(str(int(rowData[2])))
              ui.QueryTubeThicknessComboBox.setCurrentText(str(rowData[3]))
              ui.QueryTubeUnitWeightLineEdit.setText(str(rowData[4]))
    except Exception as e:
       logging.error(e)
#endregion
#region 页面参数选择与应用

class SimpleTableSelectDialog(QDialog):
    def __init__(self, parent=None):
        super(SimpleTableSelectDialog, self).__init__(parent)
        self.setWindowTitle("选择数据")
        self.resize(900, 600) # 增加默认尺寸
        
        layout = QVBoxLayout(self)
        
        # 添加说明标签
        label = QLabel("请双击选择一行数据，或选中后点击确定：")
        label.setStyleSheet("font-weight: bold; color: #1976d2; margin-bottom: 5px;")
        layout.addWidget(label)
        
        self.tableView = QTableView(self)
        layout.addWidget(self.tableView)
        
        # 美化表格
        self.tableView.setAlternatingRowColors(True) # 启用斑马纹
        self.tableView.setSelectionBehavior(QAbstractItemView.SelectRows) # 选中整行
        self.tableView.setSelectionMode(QAbstractItemView.SingleSelection) # 单选模式
        self.tableView.verticalHeader().setVisible(False) # 隐藏行号
        self.tableView.horizontalHeader().setStretchLastSection(True) # 最后一列拉伸
        self.tableView.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents) # 列宽自适应内容
        self.tableView.setEditTriggers(QAbstractItemView.NoEditTriggers) # 禁止编辑
        
        # 设置样式表
        self.tableView.setStyleSheet("""
            QTableView {
                background-color: #ffffff;
                alternate-background-color: #f5f5f5; /* 斑马纹颜色 */
                gridline-color: #e0e0e0;
                selection-background-color: #e3f2fd; /* 选中行背景色 */
                selection-color: #1976d2; /* 选中行文字颜色 */
                border: 1px solid #d0d0d0;
            }
            QHeaderView::section {
                background-color: #f8f9fa;
                padding: 6px;
                border: none;
                border-bottom: 2px solid #1976d2;
                font-weight: bold;
                color: #495057;
            }
            QTableView::item {
                padding: 5px;
            }
            QTableView::item:selected {
                background-color: #e3f2fd;
                color: #1976d2;
            }
        """)
        
        self.buttonBox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        layout.addWidget(self.buttonBox)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        self.selected_row = None
        self.tableView.doubleClicked.connect(self.on_double_clicked)

    def on_double_clicked(self, index: QModelIndex):
        model = self.tableView.model()
        if not index.isValid() or model is None:
            return
        row = index.row()
        columns = model.columnCount()
        row_data = []
        for i in range(columns):
            idx = model.index(row, i)
            row_data.append(model.data(idx, Qt.DisplayRole))
        self.selected_row = row_data
        self.accept()

    def get_selected_row(self):
        if self.selected_row is not None:
            return self.selected_row
        model = self.tableView.model()
        if model is None:
            return None
        selection_model = self.tableView.selectionModel()
        if selection_model is None or not selection_model.hasSelection():
            return None
        index = selection_model.currentIndex()
        if not index.isValid():
            return None
        row = index.row()
        columns = model.columnCount()
        row_data = []
        for i in range(columns):
            idx = model.index(row, i)
            row_data.append(model.data(idx, Qt.DisplayRole))
        return row_data


def _safe_get_value(row, index):
    """从行数据中安全取值，过滤 NULL。"""
    try:
        if row is None or len(row) <= index:
            return None
        value = row[index]
        if value is None:
            return None
        text = str(value)
        if text == 'NULL':
            return None
        return text
    except Exception:
        return None


def _apply_helium_permeability(row, leakage_line_edit):
    """透氦率 L/(㎡·24h·atm) → 氦气逃逸率 m³/(㎡·天)（内外氦分压差按 1 atm）。"""
    try:
        permeability = float(_safe_get_value(row, 13))
    except (TypeError, ValueError):
        return
    if permeability > 0:
        leakage_line_edit.setText("{:.4g}".format(permeability / 1000.0))


def _apply_film_strength(row, prefix):
    """膜材抗拉强度（经、纬取小值，N/5cm）。"""
    values = []
    for index in (5, 6):
        try:
            values.append(float(_safe_get_value(row, index)))
        except (TypeError, ValueError):
            pass
    if values:
        getattr(ui, f"{prefix}FilmStrengthLineEdit").setText("{:g}".format(min(values)))


def _apply_main_cable(row, prefix):
    """主系留缆：同步米重、直径、破断力。"""
    for index, name in ((3, "CableUnitWeight"), (2, "CableDiameter"), (4, "CableBreakingForce")):
        text = _safe_get_value(row, index)
        if text is not None:
            getattr(ui, f"{prefix}{name}LineEdit").setText(text)


def SphereSelectFilmFromDb():
    """气球页面：从膜材数据库选择克重。"""
    try:
        headers = ['编号','产家','材质','厚度(mm)','克重(Kg/㎡)','抗拉强度-经(N/5cm)','抗拉强度-纬(N/5cm)','撕裂强度-径(N)','撕裂强度-纬(N)','剥离负荷-径(N/5cm)','剥离负荷-纬(N/5cm)','断裂伸长率-径（%)','断裂伸长率-纬（%)','透氦率（L/㎡*24h*atm）']
        dialog = SimpleTableSelectDialog()
        model = manageFilm.selectAllFilm('FilmTable', headers)
        dialog.tableView.setModel(model)
        if dialog.exec_() == QDialog.Accepted:
            row = dialog.get_selected_row()
            text = _safe_get_value(row, 4)
            if text is not None:
                ui.SphereFilmUnitWeightLineEdit.setText(text)
            _apply_helium_permeability(row, ui.SphereHeliumLeakageRateLineEdit)
            _apply_film_strength(row, "Sphere")
    except Exception as e:
        logging.error(e)


def SphereSelectAuxFilmFromDb():
    """气球页面：从膜材数据库选择副气囊克重。"""
    try:
        headers = ['编号','产家','材质','厚度(mm)','克重(Kg/㎡)','抗拉强度-经(N/5cm)','抗拉强度-纬(N/5cm)','撕裂强度-径(N)','撕裂强度-纬(N)','剥离负荷-径(N/5cm)','剥离负荷-纬(N/5cm)','断裂伸长率-径（%)','断裂伸长率-纬（%)','透氦率（L/㎡*24h*atm）']
        dialog = SimpleTableSelectDialog()
        model = manageFilm.selectAllFilm('FilmTable', headers)
        dialog.tableView.setModel(model)
        if dialog.exec_() == QDialog.Accepted:
            row = dialog.get_selected_row()
            text = _safe_get_value(row, 4)
            if text is not None:
                ui.SphereAuxiliaryFilmUnitWeightLineEdit.setText(text)
    except Exception as e:
        logging.error(e)


def SphereSelectPocketSailFilmFromDb():
    """气球页面：从膜材数据库选择兜帆材质。"""
    try:
        headers = ['编号','产家','材质','厚度(mm)','克重(Kg/㎡)','抗拉强度-经(N/5cm)','抗拉强度-纬(N/5cm)','撕裂强度-径(N)','撕裂强度-纬(N)','剥离负荷-径(N/5cm)','剥离负荷-纬(N/5cm)','断裂伸长率-径（%)','断裂伸长率-纬（%)','透氦率（L/㎡*24h*atm）']
        dialog = SimpleTableSelectDialog()
        model = manageFilm.selectAllFilm('FilmTable', headers)
        dialog.tableView.setModel(model)
        if dialog.exec_() == QDialog.Accepted:
            row = dialog.get_selected_row()
            text = _safe_get_value(row, 4)
            if text is not None:
                ui.PocketSailMaterialLineEdit.setText(text)
    except Exception as e:
        logging.error(e)

def SphereSelectWingSailFilmFromDb():
    """气球页面：从膜材数据库选择翼帆材质。"""
    try:
        headers = ['编号','产家','材质','厚度(mm)','克重(Kg/㎡)','抗拉强度-经(N/5cm)','抗拉强度-纬(N/5cm)','撕裂强度-径(N)','撕裂强度-纬(N)','剥离负荷-径(N/5cm)','剥离负荷-纬(N/5cm)','断裂伸长率-径（%)','断裂伸长率-纬（%)','透氦率（L/㎡*24h*atm）']
        dialog = SimpleTableSelectDialog()
        model = manageFilm.selectAllFilm('FilmTable', headers)
        dialog.tableView.setModel(model)
        if dialog.exec_() == QDialog.Accepted:
            row = dialog.get_selected_row()
            text = _safe_get_value(row, 4)
            if text is not None:
                ui.WingSailMaterialLineEdit.setText(text)
    except Exception as e:
        logging.error(e)

def SphereSelectWingSailRodFromDb():
    """气球页面：从管材数据库选择碳纤维杆米重。"""
    try:
        headers = ['编号','管材材质','管材规格(mm)','管材壁厚','米重(Kg/m)']
        dialog = SimpleTableSelectDialog()
        model = manageTube.selectAllTube('TubeTable', headers)
        dialog.tableView.setModel(model)
        if dialog.exec_() == QDialog.Accepted:
            row = dialog.get_selected_row()
            text = _safe_get_value(row, 4)
            if text is not None:
                ui.WingSailRodUnitWeightLineEdit.setText(text)
    except Exception as e:
        logging.error(e)

def AirShipSelectFilmFromDb():
    """飞艇页面：从膜材数据库选择克重。"""
    try:
        headers = ['编号','产家','材质','厚度(mm)','克重(Kg/㎡)','抗拉强度-经(N/5cm)','抗拉强度-纬(N/5cm)','撕裂强度-径(N)','撕裂强度-纬(N)','剥离负荷-径(N/5cm)','剥离负荷-纬(N/5cm)','断裂伸长率-径（%)','断裂伸长率-纬（%)','透氦率（L/㎡*24h*atm）']
        dialog = SimpleTableSelectDialog()
        model = manageFilm.selectAllFilm('FilmTable', headers)
        dialog.tableView.setModel(model)
        if dialog.exec_() == QDialog.Accepted:
            row = dialog.get_selected_row()
            text = _safe_get_value(row, 4)
            if text is not None:
                ui.AirShipFilmUnitWeightLineEdit.setText(text)
            _apply_helium_permeability(row, ui.AirShipHeliumLeakageRateLineEdit)
            _apply_film_strength(row, "AirShip")
    except Exception as e:
        logging.error(e)


def AirShipSelectAuxFilmFromDb():
    """飞艇页面：从膜材数据库选择副气囊克重。"""
    try:
        headers = ['编号','产家','材质','厚度(mm)','克重(Kg/㎡)','抗拉强度-经(N/5cm)','抗拉强度-纬(N/5cm)','撕裂强度-径(N)','撕裂强度-纬(N)','剥离负荷-径(N/5cm)','剥离负荷-纬(N/5cm)','断裂伸长率-径（%)','断裂伸长率-纬（%)','透氦率（L/㎡*24h*atm）']
        dialog = SimpleTableSelectDialog()
        model = manageFilm.selectAllFilm('FilmTable', headers)
        dialog.tableView.setModel(model)
        if dialog.exec_() == QDialog.Accepted:
            row = dialog.get_selected_row()
            text = _safe_get_value(row, 4)
            if text is not None:
                ui.AirShipAuxiliaryFilmUnitWeightLineEdit.setText(text)
    except Exception as e:
        logging.error(e)


def SphereSelectWindFromDb():
    """气球页面：从风速数据库选择工作风速。"""
    try:
        headers = ['编号','等级','名称','速度(m/s)','压强(Kg/㎡)']
        dialog = SimpleTableSelectDialog()
        model = manageWind.selectAllWind('WindTable', headers)
        dialog.tableView.setModel(model)
        if dialog.exec_() == QDialog.Accepted:
            row = dialog.get_selected_row()
            text = _safe_get_value(row, 3)
            if text is not None:
                ui.SphereWindPressureLineEdit.setText(text)
    except Exception as e:
        logging.error(e)


def AirShipSelectWindFromDb():
    """飞艇页面：从风速数据库选择工作风速。"""
    try:
        headers = ['编号','等级','名称','速度(m/s)','压强(Kg/㎡)']
        dialog = SimpleTableSelectDialog()
        model = manageWind.selectAllWind('WindTable', headers)
        dialog.tableView.setModel(model)
        if dialog.exec_() == QDialog.Accepted:
            row = dialog.get_selected_row()
            text = _safe_get_value(row, 3)
            if text is not None:
                ui.AirShipWindPressureLineEdit.setText(text)
    except Exception as e:
        logging.error(e)


def SphereSelectCableFromDb():
    """气球页面：从缆绳数据库选择主系留缆。"""
    try:
        headers = ['编号','缆绳材质','缆绳直径(mm)','米重(Kg/m)','破断力(kgf)']
        dialog = SimpleTableSelectDialog()
        model = manageCable.selectAllCable('CableTable', headers)
        dialog.tableView.setModel(model)
        if dialog.exec_() == QDialog.Accepted:
            _apply_main_cable(dialog.get_selected_row(), "Sphere")
    except Exception as e:
        logging.error(e)


def AirShipSelectCableFromDb():
    """飞艇页面：从缆绳数据库选择主系留缆。"""
    try:
        headers = ['编号','缆绳材质','缆绳直径(mm)','米重(Kg/m)','破断力(kgf)']
        dialog = SimpleTableSelectDialog()
        model = manageCable.selectAllCable('CableTable', headers)
        dialog.tableView.setModel(model)
        if dialog.exec_() == QDialog.Accepted:
            _apply_main_cable(dialog.get_selected_row(), "AirShip")
    except Exception as e:
        logging.error(e)


def open_drag_dialog(prefix):
    """风阻系数选型模型：显示构成、依据曲线与影响因素，可写入或清除手动值。"""
    try:
        from drag_dialog import DragDialog
        (SphereCalculate if prefix == "Sphere" else AirShipCalculate)()
        report = drag_report(prefix)
        if report is None:
            return
        edit = getattr(ui, f"{prefix}DragCoefficientLineEdit")
        DragDialog(report, edit.setText, lambda: edit.setText(""), MainWindow).exec_()
    except Exception as e:
        logging.exception(e)


def ApplyWindToSphere():
    """管理页风速 -> 气球页面工作风速。"""
    try:
        text = _safe_get_value([ui.QueryWindSpeedLineEdit.text()], 0)
        if text is not None:
            ui.SphereWindPressureLineEdit.setText(text)
    except Exception as e:
        logging.error(e)


def ApplyWindToAirShip():
    """管理页风速 -> 飞艇页面工作风速。"""
    try:
        text = _safe_get_value([ui.QueryWindSpeedLineEdit.text()], 0)
        if text is not None:
            ui.AirShipWindPressureLineEdit.setText(text)
    except Exception as e:
        logging.error(e)


def ApplyFilmToSphere():
    """管理页膜材 -> 气球页面膜材克重。"""
    try:
        text = _safe_get_value([ui.QueryFilmUnitWeightLineEdit.text()], 0)
        if text is not None:
            ui.SphereFilmUnitWeightLineEdit.setText(text)
    except Exception as e:
        logging.error(e)


def ApplyFilmToAirShip():
    """管理页膜材 -> 飞艇页面膜材克重。"""
    try:
        text = _safe_get_value([ui.QueryFilmUnitWeightLineEdit.text()], 0)
        if text is not None:
            ui.AirShipFilmUnitWeightLineEdit.setText(text)
    except Exception as e:
        logging.error(e)


def ApplyCableToSphere():
    """管理页缆绳 -> 气球页面缆绳米重。"""
    try:
        text = _safe_get_value([ui.QueryCableUnitWeightLineEdit.text()], 0)
        if text is not None:
            ui.SphereCableUnitWeightLineEdit.setText(text)
    except Exception as e:
        logging.error(e)


def ApplyCableToAirShip():
    """管理页缆绳 -> 飞艇页面缆绳米重。"""
    try:
        text = _safe_get_value([ui.QueryCableUnitWeightLineEdit.text()], 0)
        if text is not None:
            ui.AirShipCableUnitWeightLineEdit.setText(text)
    except Exception as e:
        logging.error(e)

#endregion
#region 关于链接
def move_button_under_query(button, query_button):
    """Move a button to be under the query button"""
    if not button or not query_button:
        return
        
    # Remove from old layout
    if button.parentWidget() and button.parentWidget().layout():
        button.parentWidget().layout().removeWidget(button)
    
    # Set new parent
    button.setParent(query_button.parentWidget())
    
    # Add to new layout
    target_layout = query_button.parentWidget().layout()
    if target_layout:
        index = target_layout.indexOf(query_button)
        target_layout.insertWidget(index + 1, button)

def enhance_equipment_widgets(ui):
    """
    增强设备参数控件：
    1. 增加复选框（默认不勾选）
    2. 增加数量输入框（默认1）
    3. 增加单位标签（套）
    """
    equipment_list = [
        "NetBag", "RotateConnector", "ForceSensor", "Platform", 
        "AirFan", "SafetyValve", "EscapeValve", "PowerBoard", 
        "WindMeter", "ControlBox", "InflationPort", "ObservationWindow"
    ]
    
    def find_layout_containing_widget(layout, widget):
        if not layout: return None
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item.widget() == widget:
                return layout
            if item.layout():
                res = find_layout_containing_widget(item.layout(), widget)
                if res: return res
        return None

    for name in equipment_list:
        line_edit_name = f"Sphere{name}LineEdit"
        if not hasattr(ui, line_edit_name):
            continue
            
        line_edit = getattr(ui, line_edit_name)
        
        # Find the layout containing this line edit
        # Start searching from the GroupBox layout
        # Note: Some items might be in different group boxes if UI changed, but usually in SphereLoad
        group_box = ui.groupBox_SphereLoad
        layout = find_layout_containing_widget(group_box.layout(), line_edit)
        
        if layout and isinstance(layout, QHBoxLayout):
            # 1. Add CheckBox at the beginning
            checkbox_name = f"Sphere{name}CheckBox"
            if hasattr(ui, checkbox_name): continue # Already added

            checkbox = QCheckBox()
            checkbox.setObjectName(checkbox_name)
            checkbox.setChecked(False) # Default unchecked
            # Insert at index 0
            layout.insertWidget(0, checkbox)
            setattr(ui, checkbox_name, checkbox)
            
            # 2. Add Quantity Input and Unit at the end
            qty_line_edit_name = f"Sphere{name}QuantityLineEdit"
            qty_line_edit = QLineEdit("1")
            qty_line_edit.setObjectName(qty_line_edit_name)
            qty_line_edit.setFixedWidth(50) # Small width for quantity
            qty_line_edit.setAlignment(Qt.AlignCenter)
            
            unit_label = QLabel("套")
            
            layout.addWidget(qty_line_edit)
            layout.addWidget(unit_label)
            setattr(ui, qty_line_edit_name, qty_line_edit)
            
            # Connect signals
            checkbox.stateChanged.connect(SphereCalculateRealTime)
            qty_line_edit.textChanged.connect(SphereCalculateRealTime)
            
            # Adjust stretches
            # Checkbox(0), Label(3), WeightEdit(4), WeightUnit(0), QtyEdit(1), QtyUnit(0)
            for i in range(layout.count()):
                layout.setStretch(i, 0)
            
            layout.setStretch(1, 3) # Label
            layout.setStretch(2, 4) # Weight Edit
            layout.setStretch(4, 1) # Qty Edit

def enhance_airship_equipment_widgets(ui):
    """
    Enhance Airship equipment widgets with CheckBox and Quantity input.
    """
    equipment_list = [
        "NetBag", "RotateConnector", "ForceSensor", "Platform", 
        "AirFan", "SafetyValve", "EscapeValve", "PowerBoard", 
        "WindMeter", "ControlBox", "InflationPort", "ObservationWindow"
    ]

    def find_layout_containing_widget(layout, widget):
        if layout is None: return None
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item.widget() == widget:
                return layout
            if item.layout():
                res = find_layout_containing_widget(item.layout(), widget)
                if res: return res
        return None

    for name in equipment_list:
        line_edit_name = f"AirShip{name}LineEdit"
        if not hasattr(ui, line_edit_name):
            continue
            
        line_edit = getattr(ui, line_edit_name)
        
        # Find the layout containing this line edit
        # Start searching from the GroupBox layout
        group_box = ui.groupBox_AirShipLoad
        layout = find_layout_containing_widget(group_box.layout(), line_edit)
        
        if layout and isinstance(layout, QHBoxLayout):
            # 1. Add CheckBox at the beginning
            checkbox_name = f"AirShip{name}CheckBox"
            if hasattr(ui, checkbox_name): continue # Already added

            checkbox = QCheckBox()
            checkbox.setObjectName(checkbox_name)
            checkbox.setChecked(False) # Default unchecked
            # Insert at index 0
            layout.insertWidget(0, checkbox)
            setattr(ui, checkbox_name, checkbox)
            
            # 2. Add Quantity Input and Unit at the end
            qty_line_edit_name = f"AirShip{name}QuantityLineEdit"
            qty_line_edit = QLineEdit("1")
            qty_line_edit.setObjectName(qty_line_edit_name)
            qty_line_edit.setFixedWidth(50) # Small width for quantity
            qty_line_edit.setAlignment(Qt.AlignCenter)
            
            unit_label = QLabel("套")
            
            layout.addWidget(qty_line_edit)
            layout.addWidget(unit_label)
            setattr(ui, qty_line_edit_name, qty_line_edit)
            
            # Connect signals
            checkbox.stateChanged.connect(AirShipCalculateRealTime)
            qty_line_edit.textChanged.connect(AirShipCalculateRealTime)
            
            # Adjust stretches
            # Checkbox(0), Label(3), WeightEdit(4), WeightUnit(0), QtyEdit(1), QtyUnit(0)
            for i in range(layout.count()):
                layout.setStretch(i, 0)
            
            layout.setStretch(1, 3) # Label
            layout.setStretch(2, 4) # Weight Edit
            layout.setStretch(4, 1) # Qty Edit

def add_sail_widgets(ui):
    """在气球页面添加帆配置控件"""
    # 获取目标布局 (材料与结构参数组)
    target_group_box = ui.groupBox_SphereMaterial
    target_layout = target_group_box.layout()
    
    if not target_layout:
        logging.error("Could not find layout for groupBox_SphereMaterial")
        return

    # 1. 帆类型选择 (Radio Buttons)
    # 使用水平布局，并命名以启用斑马纹
    layout_type = QHBoxLayout()
    layout_type.setObjectName("horizontalLayout_SailType")
    ui.layout_SailType = layout_type
    
    label_type = QLabel("帆型:")
    ui.radio_NoSail = QRadioButton("无帆")
    ui.radio_PocketSail = QRadioButton("兜帆")
    ui.radio_WingSail = QRadioButton("翼帆")
    ui.radio_NoSail.setChecked(True)
    
    ui.sailButtonGroup = QButtonGroup(ui.SpherePage)
    ui.sailButtonGroup.addButton(ui.radio_NoSail, 0)
    ui.sailButtonGroup.addButton(ui.radio_PocketSail, 1)
    ui.sailButtonGroup.addButton(ui.radio_WingSail, 2)
    
    layout_type.addWidget(label_type)
    layout_type.addWidget(ui.radio_NoSail)
    layout_type.addWidget(ui.radio_PocketSail)
    layout_type.addWidget(ui.radio_WingSail)
    layout_type.addStretch()
    
    target_layout.addLayout(layout_type)
    
    # 辅助函数：创建标准单行参数布局 (Label + Edit + Unit)
    def create_param_row(label_text, line_edit, unit_text=""):
        row_layout = QHBoxLayout()
        row_layout.setObjectName("horizontalLayout_SailParam") # 统一命名前缀以启用斑马纹
        
        label = QLabel(label_text)
        row_layout.addWidget(label)
        
        row_layout.addWidget(line_edit)
        
        unit_label = QLabel(unit_text)
        row_layout.addWidget(unit_label)
            
        # 设置伸缩因子，保持与主界面一致 (4:6:1)
        row_layout.setStretch(0, 4)
        row_layout.setStretch(1, 6)
        row_layout.setStretch(2, 1)
             
        return row_layout

    # 2. 兜帆参数区域
    ui.widget_PocketSail = QWidget()
    layout_pocket = QVBoxLayout(ui.widget_PocketSail)
    layout_pocket.setContentsMargins(0, 0, 0, 0)
    layout_pocket.setSpacing(4) # 与主界面一致的间距
    
    # 兜帆面积比例
    ui.PocketSailAreaRatioLineEdit = QLineEdit("0.22")
    layout_pocket.addLayout(create_param_row("兜帆面积比例:", ui.PocketSailAreaRatioLineEdit))
    
    # 兜帆面积
    ui.PocketSailAreaLineEdit = QLineEdit()
    ui.PocketSailAreaLineEdit.setReadOnly(True)
    layout_pocket.addLayout(create_param_row("兜帆面积:", ui.PocketSailAreaLineEdit, "㎡"))
    
    # 兜帆材质
    ui.PocketSailMaterialLineEdit = QLineEdit("0.05")
    layout_pocket.addLayout(create_param_row("兜帆材质:", ui.PocketSailMaterialLineEdit, "Kg/㎡"))
    
    # 兜帆质量
    ui.PocketSailWeightLineEdit = QLineEdit()
    ui.PocketSailWeightLineEdit.setReadOnly(True)
    layout_pocket.addLayout(create_param_row("兜帆质量:", ui.PocketSailWeightLineEdit, "Kg"))
    
    # 气动系数以帆面积为参考面积
    ui.PocketSailLiftCoeffLineEdit = QLineEdit("0.3")
    ui.PocketSailLiftCoeffLineEdit.setToolTip("兜帆升力系数，典型 0.3～0.5")
    layout_pocket.addLayout(create_param_row("升力系数 CL:", ui.PocketSailLiftCoeffLineEdit))
    ui.PocketSailDragCoeffLineEdit = QLineEdit("0.1")
    ui.PocketSailDragCoeffLineEdit.setToolTip("兜帆阻力系数，典型 0.1～0.2")
    ui.PocketSailDragCoeffLineEdit.textChanged.connect(SphereCalculateRealTime)
    layout_pocket.addLayout(create_param_row("阻力系数 CD:", ui.PocketSailDragCoeffLineEdit))
    
    # 兜帆气动升力（目标高度平均风）
    ui.PocketSailLiftLineEdit = QLineEdit()
    ui.PocketSailLiftLineEdit.setReadOnly(True)
    layout_pocket.addLayout(create_param_row("兜帆气动升力:", ui.PocketSailLiftLineEdit, "kgf"))
    
    target_layout.addWidget(ui.widget_PocketSail)
    
    # 3. 翼帆参数区域
    ui.widget_WingSail = QWidget()
    layout_wing = QVBoxLayout(ui.widget_WingSail)
    layout_wing.setContentsMargins(0, 0, 0, 0)
    layout_wing.setSpacing(4)
    
    # 翼帆面积比例
    ui.WingSailAreaRatioLineEdit = QLineEdit("0.26")
    layout_wing.addLayout(create_param_row("翼帆面积比例:", ui.WingSailAreaRatioLineEdit))
    
    # 翼帆面积
    ui.WingSailAreaLineEdit = QLineEdit()
    ui.WingSailAreaLineEdit.setReadOnly(True)
    layout_wing.addLayout(create_param_row("翼帆面积:", ui.WingSailAreaLineEdit, "㎡"))
    
    # 翼帆材质
    ui.WingSailMaterialLineEdit = QLineEdit("0.05")
    layout_wing.addLayout(create_param_row("翼帆材质:", ui.WingSailMaterialLineEdit, "Kg/㎡"))
    
    # 翼帆质量
    ui.WingSailWeightLineEdit = QLineEdit()
    ui.WingSailWeightLineEdit.setReadOnly(True)
    layout_wing.addLayout(create_param_row("翼帆质量:", ui.WingSailWeightLineEdit, "Kg"))
    
    # 碳纤维杆长度
    ui.WingSailRodLengthLineEdit = QLineEdit()
    layout_wing.addLayout(create_param_row("碳纤维杆长度:", ui.WingSailRodLengthLineEdit, "m"))
    
    # 碳纤维杆米重
    ui.WingSailRodUnitWeightLineEdit = QLineEdit()
    layout_wing.addLayout(create_param_row("碳纤维杆米重:", ui.WingSailRodUnitWeightLineEdit, "Kg/m"))
    
    # 碳纤维杆质量
    ui.WingSailRodWeightLineEdit = QLineEdit()
    ui.WingSailRodWeightLineEdit.setReadOnly(True)
    layout_wing.addLayout(create_param_row("碳纤维杆质量:", ui.WingSailRodWeightLineEdit, "Kg"))
    
    ui.WingSailLiftCoeffLineEdit = QLineEdit("0.6")
    ui.WingSailLiftCoeffLineEdit.setToolTip("翼帆升力系数，典型 0.5～0.8")
    layout_wing.addLayout(create_param_row("升力系数 CL:", ui.WingSailLiftCoeffLineEdit))
    ui.WingSailDragCoeffLineEdit = QLineEdit("0.1")
    ui.WingSailDragCoeffLineEdit.setToolTip("翼帆阻力系数，典型 0.1～0.15")
    ui.WingSailDragCoeffLineEdit.textChanged.connect(SphereCalculateRealTime)
    layout_wing.addLayout(create_param_row("阻力系数 CD:", ui.WingSailDragCoeffLineEdit))
    
    # 翼帆气动升力（目标高度平均风）
    ui.WingSailLiftLineEdit = QLineEdit()
    ui.WingSailLiftLineEdit.setReadOnly(True)
    layout_wing.addLayout(create_param_row("翼帆气动升力:", ui.WingSailLiftLineEdit, "kgf"))
    
    target_layout.addWidget(ui.widget_WingSail)
    
    # 初始可见性
    ui.widget_PocketSail.setVisible(False)
    ui.widget_WingSail.setVisible(False)

    # 绑定切换事件
    def on_sail_type_changed(id, checked):
        if checked:
            ui.widget_PocketSail.setVisible(id == 1)
            ui.widget_WingSail.setVisible(id == 2)
            
            # 如果切换到翼帆且碳杆长度为空，则触发计算以填充默认值
            if id == 2 and not ui.WingSailRodLengthLineEdit.text():
                 SphereCalculateRealTime()
                 
            # 触发重算
            SphereCalculateRealTime()
            
    ui.sailButtonGroup.idToggled.connect(on_sail_type_changed)

def add_airship_tail_widgets(ui):
    """在飞艇页面创建尾翼参数控件（统一放入 widget_AirShipTail，由页面布局模块重新编排）。"""
    target_layout = ui.groupBox_AirShipMaterial.layout()
    if not target_layout:
        logging.error("Could not find layout for groupBox_AirShipMaterial")
        return

    def create_param_row(label_text, line_edit, unit_text=""):
        row_layout = QHBoxLayout()
        row_layout.setObjectName("horizontalLayout_TailParam")
        row_layout.addWidget(QLabel(label_text))
        row_layout.addWidget(line_edit)
        row_layout.addWidget(QLabel(unit_text))
        row_layout.setStretch(0, 4)
        row_layout.setStretch(1, 6)
        row_layout.setStretch(2, 1)
        return row_layout

    ui.widget_AirShipTail = QWidget()
    tail_layout = QVBoxLayout(ui.widget_AirShipTail)
    tail_layout.setContentsMargins(0, 0, 0, 0)
    tail_layout.setSpacing(4)

    ui.AirShipTailSurfaceAreaRatioLineEdit = QLineEdit("0.31")
    tail_layout.addLayout(create_param_row("尾翼总表面积比率:", ui.AirShipTailSurfaceAreaRatioLineEdit))
    ui.AirShipTailSurfaceAreaLineEdit = QLineEdit()
    ui.AirShipTailSurfaceAreaLineEdit.setReadOnly(True)
    tail_layout.addLayout(create_param_row("尾翼总表面积:", ui.AirShipTailSurfaceAreaLineEdit, "㎡"))
    ui.AirShipTailWeightLineEdit = QLineEdit()
    ui.AirShipTailWeightLineEdit.setReadOnly(True)
    tail_layout.addLayout(create_param_row("尾翼总质量（参考）:", ui.AirShipTailWeightLineEdit, "kg"))
    ui.AirShipTailDragCoeffLineEdit = QLineEdit()
    ui.AirShipTailDragCoeffLineEdit.setPlaceholderText("自动（模型）")
    ui.AirShipTailDragCoeffLineEdit.setToolTip("留空由模型按尾翼雷诺数、厚度自动计算（约 0.008～0.015，参考面积为尾翼平面面积）；手动填写则覆盖")
    tail_layout.addLayout(create_param_row("尾翼阻力系数:", ui.AirShipTailDragCoeffLineEdit))
    target_layout.addWidget(ui.widget_AirShipTail)

    for name in ("TailSurfaceAreaRatio", "TailDragCoeff"):
        getattr(ui, f"AirShip{name}LineEdit").textChanged.connect(AirShipCalculateRealTime)

def adjust_ui_layout(ui):
    """
    Adjust UI layout according to requirements
    """
    # Helper function to align labels in a groupbox
    def align_labels_in_groupbox(groupbox):
        layout = groupbox.layout()
        if not layout: return
        
        labels = []
        
        def find_row_labels(layout_item):
            if not layout_item: return
            l = layout_item.layout()
            
            # If item is a widget with a layout (e.g. container widget), use that layout
            if not l and layout_item.widget() and layout_item.widget().layout():
                l = layout_item.widget().layout()
                
            if isinstance(l, QHBoxLayout):
                if l.objectName() == "horizontalLayout_Section":
                    return
                # Check first item
                if l.count() > 0:
                    first = l.itemAt(0)
                    if first and first.widget() and isinstance(first.widget(), QLabel):
                        labels.append(first.widget())
            elif isinstance(l, QVBoxLayout):
                # Recurse
                for i in range(l.count()):
                    find_row_labels(l.itemAt(i))
        
        # Start traversal
        for i in range(layout.count()):
            find_row_labels(layout.itemAt(i))
            
        if not labels: return
        
        # Calculate max width
        max_width = 0
        for label in labels:
            width = label.fontMetrics().boundingRect(label.text()).width()
            max_width = max(max_width, width)
        
        # Add padding for stylesheet padding and safety margin
        max_width += 20
        
        # Apply fixed width
        for label in labels:
            label.setFixedWidth(max_width)
            label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

    # 1. Fixed row height for SpherePage and AirshipPage
    pages = [ui.SpherePage, ui.AirshipPage]
    for page in pages:
        group_boxes = page.findChildren(QGroupBox)
        for gb in group_boxes:
            layout = gb.layout()
            if not layout: continue
            
            # Add stretch to pack items to top (fix row spacing)
            if isinstance(layout, QVBoxLayout):
                layout.addStretch(1)

            def fix_widgets_in_layout(l):
                if not l: return
                for i in range(l.count()):
                    item = l.itemAt(i)
                    if not item: continue
                    
                    child_l = item.layout()
                    # Handle widget with layout (e.g. container widget)
                    if not child_l and item.widget() and item.widget().layout():
                        child_l = item.widget().layout()
                        
                    if isinstance(child_l, QHBoxLayout):
                        for j in range(child_l.count()):
                            w_item = child_l.itemAt(j)
                            if w_item and w_item.widget():
                                w = w_item.widget()
                                sp = w.sizePolicy()
                                sp.setVerticalPolicy(QSizePolicy.Fixed)
                                # Allow QLineEdit to expand horizontally
                                if isinstance(w, QLineEdit):
                                    sp.setHorizontalPolicy(QSizePolicy.Expanding)
                                w.setSizePolicy(sp)
                    elif isinstance(child_l, QVBoxLayout):
                        fix_widgets_in_layout(child_l)

            fix_widgets_in_layout(layout)

    # 2. Hide "Apply to" buttons
    apply_buttons = [
        'WindApplySpherePushButton', 'WindApplyAirShipPushButton',
        'FilmApplySpherePushButton', 'FilmApplyAirShipPushButton',
        'CableApplySpherePushButton', 'CableApplyAirShipPushButton'
    ]
    
    for btn_name in apply_buttons:
        if hasattr(ui, btn_name):
            btn = getattr(ui, btn_name)
            btn.setVisible(False)

    # 3. Elastic Width
    # Iterate all widgets in scroll area
    widgets = ui.scrollAreaWidgetContents_2.findChildren(QWidget)
    for w in widgets:
        if isinstance(w, (QLineEdit, QComboBox)):
            # Check if widget belongs to Query Pages (Wind, Film, Cable, Tube)
            parent = w.parent()
            is_query_page = False
            while parent:
                if parent.objectName() in ["WindPage", "FilmPage", "CablePage", "TubePage"]:
                    is_query_page = True
                    break
                parent = parent.parent()
            
            if is_query_page:
                # For query pages, allow shrinking but keep a reasonable minimum width
                w.setMinimumWidth(60)
                # Use Preferred policy so they don't aggressively expand if not needed
                sp = w.sizePolicy()
                sp.setHorizontalPolicy(QSizePolicy.Preferred)
                w.setSizePolicy(sp)
            else:
                w.setMinimumWidth(0)
                # For other pages, allow full expansion
                w.setMaximumWidth(16777215)
                sp = w.sizePolicy()
                sp.setHorizontalPolicy(QSizePolicy.Expanding)
                w.setSizePolicy(sp)

        elif isinstance(w, QPushButton):
            # Don't force expand on buttons, let them be sized by content or specific rules
            pass

    # 4. Align Labels
    # Find all GroupBoxes in the main scroll area
    all_group_boxes = ui.scrollAreaWidgetContents_2.findChildren(QGroupBox)
    for gb in all_group_boxes:
        align_labels_in_groupbox(gb)

    # 5. Optimize Query Page Buttons
    
    # Helper to find layout containing widget
    def find_layout_containing_widget(layout, widget):
        if not layout: return None
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item.widget() == widget:
                return layout
            if item.layout():
                res = find_layout_containing_widget(item.layout(), widget)
                if res: return res
        return None

    # A. Add/Delete/Update Buttons: Fixed Width, Right Aligned
    manage_button_names = [
        'WindAddPushButton', 'WindDeletedPushButton', 'WindUpdatePushButton',
        'FilmAddPushButton', 'FilmDeletePushButton', 'FilmUpDataPushButton',
        'CableAddPushButton', 'CableDeletePushButton', 'CableUpDataPushButton',
        'TubeAddPushButton', 'TubeDeletePushButton', 'TubeUpDataPushButton'
    ]
    
    # Track layouts we've already adjusted to avoid adding multiple stretches
    adjusted_layouts = set()

    for name in manage_button_names:
        if hasattr(ui, name):
            btn = getattr(ui, name)
            btn.setFixedWidth(100) # Unified width
            
            # Find parent layout
            parent = btn.parentWidget()
            if parent and parent.layout():
                target_layout = find_layout_containing_widget(parent.layout(), btn)
                if target_layout and isinstance(target_layout, QHBoxLayout):
                    if target_layout not in adjusted_layouts:
                        # Insert stretch at the beginning (index 0) to push buttons to the right
                        target_layout.insertStretch(0, 1)
                        target_layout.setSpacing(30) # Unified spacing
                        adjusted_layouts.add(target_layout)

    # 6. Optimize Query Page Input Layouts (Fix Stretches)
    # Iterate through Query Pages and fix the 4:6:1 stretch ratio to 0:1:0
    query_pages = [ui.WindPage, ui.FilmPage, ui.CablePage, ui.TubePage]
    for page in query_pages:
        # Find all QHBoxLayouts
        # We need to traverse the layout tree
        def fix_layout_stretches(layout):
            if not layout: return
            
            # Check if this is a QHBoxLayout with 3 items (Label, Input, Label)
            if isinstance(layout, QHBoxLayout) and layout.count() == 3:
                item0 = layout.itemAt(0)
                item1 = layout.itemAt(1)
                item2 = layout.itemAt(2)
                
                w0 = item0.widget()
                w1 = item1.widget()
                w2 = item2.widget()
                
                if isinstance(w0, QLabel) and isinstance(w1, (QLineEdit, QComboBox)) and isinstance(w2, QLabel):
                    # Found the pattern! Reset stretches.
                    layout.setStretch(0, 0) # Label: Auto
                    layout.setStretch(1, 1) # Input: Expand
                    layout.setStretch(2, 0) # Unit: Auto
            
            # Recurse
            for i in range(layout.count()):
                item = layout.itemAt(i)
                if item.layout():
                    fix_layout_stretches(item.layout())
        
        if page.layout():
            fix_layout_stretches(page.layout())


    # 7. Fix TableView Width Issue
    # Ensure TableViews don't force the window to be wide
    table_views = [ui.WindTableView, ui.FilmTableView, ui.CableTableView, ui.TubeTableView]
    for tv in table_views:
        if tv:
            tv.setMinimumWidth(0)
            # 设置表格最小高度为200px
            tv.setMinimumHeight(200)
            # 启用斑马纹效果
            tv.setAlternatingRowColors(True)
            
            sp = tv.sizePolicy()
            sp.setHorizontalPolicy(QSizePolicy.Expanding)
            tv.setSizePolicy(sp)
            # Ensure horizontal scrollbar appears if content is too wide, instead of expanding window
            tv.setSizeAdjustPolicy(QAbstractScrollArea.AdjustIgnored)

def AboutLink():#关于链接
    url='https://github.com/chenhangwei/'
    webbrowser.open(url)

#region 主函数
if __name__ == "__main__":

    app = QApplication(sys.argv)                        
    MainWindow = QWidget()  
    MainWindow.width = 1000
    MainWindow.height = 1500                  
    ui = ui_form.Ui_Widget()     # ui=GUI的py文件名.类名
    ui.setupUi(MainWindow)
    
    ui.label_322.setText("kgf")  # 缆绳破断力单位
    # 计算控制器绑定界面对象
    bind_calculator(ui)

    # 增强设备参数控件（复选框、数量）
    enhance_equipment_widgets(ui)
    enhance_airship_equipment_widgets(ui)
    
    # 动态添加帆配置控件
    add_sail_widgets(ui)
    
    # 动态添加飞艇尾翼参数控件
    add_airship_tail_widgets(ui)

    # 按“外形 / 场地气体浮力 / 重量 / 缆绳与风 / 校核结果”重组两个计算页面
    sphere_rows = build_page(ui, "Sphere", SphereCalculateRealTime)
    airship_rows = build_page(ui, "AirShip", AirShipCalculateRealTime)
    ui.SphereWindModeComboBox.currentIndexChanged.connect(
        lambda index: update_wind_mode_rows(ui, "Sphere", sphere_rows, index))
    ui.AirShipWindModeComboBox.currentIndexChanged.connect(
        lambda index: update_wind_mode_rows(ui, "AirShip", airship_rows, index))
    update_wind_mode_rows(ui, "Sphere", sphere_rows, ui.SphereWindModeComboBox.currentIndex())
    update_wind_mode_rows(ui, "AirShip", airship_rows, ui.AirShipWindModeComboBox.currentIndex())
    calc_controller.connect_diagrams()
    
    # 必填输入（橙色框）：去掉 ui_form 里的内联蓝色样式，由主题的橙色规则接管
    for _prefix in ("Sphere", "AirShip"):
        for _key in ("Altitude", "TargetHeight", "FilmUnitWeight", "CableUnitWeight", "AuxiliaryFilmUnitWeight",
                     "CustomerLoad", "FillFraction"):
            getattr(ui, f"{_prefix}{_key}LineEdit").setStyleSheet("")

    # 应用初始主题 (Ensure font and style are applied BEFORE calculating layout metrics)
    apply_theme()
    # Ensure style is polished so font metrics are accurate
    MainWindow.ensurePolished()
    
    # 调整UI布局（固定行高、移动按钮、弹性宽度、对齐标签）
    adjust_ui_layout(ui)
    # 输入框最小宽度，避免数字被截断（数量框为固定宽度，不受影响）
    for _page in (ui.SpherePage, ui.AirshipPage):
        for _edit in _page.findChildren(QLineEdit):
            if _edit.minimumWidth() != _edit.maximumWidth():
                _edit.setMinimumWidth(76)
    # 拉点/绳组克重输入框带有“…”按钮，需更宽
    for _prefix in ("Sphere", "AirShip"):
        for _name in ("PullPoint", "MoorRope1", "MoorRope2", "MoorRope3", "MoorMainRope",
                      "TetherRope1", "TetherRope2", "TetherRope3"):
            _edit = getattr(ui, f"{_prefix}{_name}WeightLineEdit", None)
            if _edit is not None:
                _edit.setMinimumWidth(100)
    
    # 应用斑马纹效果（交替行背景色）
    # Re-apply zebra stripes to ensure moved buttons are covered
    apply_zebra_stripes(ui)
    
    # 创建定时器，每小时检查一次是否需要自动切换主题
    theme_timer = QTimer()
    theme_timer.timeout.connect(check_auto_theme_update)
    theme_timer.start(3600000)  # 3600000ms = 1小时

    # 为输入框添加内嵌"..."按钮
    def add_select_action(line_edit, click_handler, tooltip):
        """为LineEdit添加右侧内嵌按钮"""
        # 创建工具按钮
        button = QToolButton(line_edit)
        button.setText("…")  # 使用Unicode省略号
        button.setToolTip(tooltip)
        button.setCursor(Qt.PointingHandCursor)
        button.setStyleSheet("""
            QToolButton {
                border: none;
                background: transparent;
                font-size: 14px;
                font-weight: bold;
                padding: 0px 3px;
            }
            QToolButton:hover {
                background-color: rgba(66, 165, 245, 0.1);
                border-radius: 2px;
            }
        """)
        button.clicked.connect(click_handler)
        button.setFixedSize(QSize(18, 18))
        
        # 调整输入框内边距以留出按钮空间
        line_edit.setTextMargins(0, 0, 22, 0)
        
        # 将按钮定位到输入框右侧
        def update_button_position():
            button.move(line_edit.width() - button.width() - 3, 
                       (line_edit.height() - button.height()) // 2)
        
        # 保存原有的resizeEvent
        original_resize = line_edit.resizeEvent
        def new_resize_event(event):
            if original_resize:
                original_resize(event)
            update_button_position()
        line_edit.resizeEvent = new_resize_event
        
        update_button_position()
    
    # 创建缆绳选择回调函数的工厂
    def make_cable_select_handler(target_line_edit):
        """为指定的输入框创建缆绳选择回调函数"""
        def handler():
            try:
                headers = ['编号','缆绳材质','缆绳直径(mm)','米重(Kg/m)','破断力(kgf)']
                dialog = SimpleTableSelectDialog()
                model = manageCable.selectAllCable('CableTable', headers)
                dialog.tableView.setModel(model)
                if dialog.exec_() == QDialog.Accepted:
                    row = dialog.get_selected_row()
                    text = _safe_get_value(row, 3)
                    if text is not None:
                        target_line_edit.setText(text)
            except Exception as e:
                logging.error(e)
        return handler
    
    # 气球页面内嵌按钮
    if hasattr(ui, "SphereFilmUnitWeightLineEdit"):
        add_select_action(ui.SphereFilmUnitWeightLineEdit, SphereSelectFilmFromDb, "从膜材数据库选择标准克重")
    if hasattr(ui, "SphereAuxiliaryFilmUnitWeightLineEdit"):
        add_select_action(ui.SphereAuxiliaryFilmUnitWeightLineEdit, SphereSelectAuxFilmFromDb, "从膜材数据库选择副气囊克重")
    if hasattr(ui, "SphereWindPressureLineEdit"):
        add_select_action(ui.SphereWindPressureLineEdit, SphereSelectWindFromDb, "从风速数据库选择工作风速")
    if hasattr(ui, "SphereCableUnitWeightLineEdit"):
        add_select_action(ui.SphereCableUnitWeightLineEdit, SphereSelectCableFromDb, "从缆绳数据库选择（同步米重、直径、破断力）")
    
    add_select_action(ui.SphereDragCoefficientLineEdit, lambda: open_drag_dialog("Sphere"), "风阻系数选型模型（依据与曲线）")
    add_select_action(ui.AirShipDragCoefficientLineEdit, lambda: open_drag_dialog("AirShip"), "风阻系数选型模型（依据与曲线）")

    # 气球页面新增缆绳内嵌按钮
    if hasattr(ui, "SphereMoorRope1WeightLineEdit"):
        add_select_action(ui.SphereMoorRope1WeightLineEdit, make_cable_select_handler(ui.SphereMoorRope1WeightLineEdit), "从缆绳数据库选择锚泊支绳1克重")
    if hasattr(ui, "SphereMoorRope2WeightLineEdit"):
        add_select_action(ui.SphereMoorRope2WeightLineEdit, make_cable_select_handler(ui.SphereMoorRope2WeightLineEdit), "从缆绳数据库选择锚泊支绳2克重")
    if hasattr(ui, "SphereMoorRope3WeightLineEdit"):
        add_select_action(ui.SphereMoorRope3WeightLineEdit, make_cable_select_handler(ui.SphereMoorRope3WeightLineEdit), "从缆绳数据库选择锚泊支绳3克重")
    if hasattr(ui, "SphereMoorMainRopeWeightLineEdit"):
        add_select_action(ui.SphereMoorMainRopeWeightLineEdit, make_cable_select_handler(ui.SphereMoorMainRopeWeightLineEdit), "从缆绳数据库选择锚泊主绳克重")
    if hasattr(ui, "SphereTetherRope1WeightLineEdit"):
        add_select_action(ui.SphereTetherRope1WeightLineEdit, make_cable_select_handler(ui.SphereTetherRope1WeightLineEdit), "从缆绳数据库选择系留支绳1克重")
    if hasattr(ui, "SphereTetherRope2WeightLineEdit"):
        add_select_action(ui.SphereTetherRope2WeightLineEdit, make_cable_select_handler(ui.SphereTetherRope2WeightLineEdit), "从缆绳数据库选择系留支绳2克重")
    if hasattr(ui, "SphereTetherRope3WeightLineEdit"):
        add_select_action(ui.SphereTetherRope3WeightLineEdit, make_cable_select_handler(ui.SphereTetherRope3WeightLineEdit), "从缆绳数据库选择系留支绳3克重")
    
    # 帆配置内嵌按钮
    if hasattr(ui, "PocketSailMaterialLineEdit"):
        add_select_action(ui.PocketSailMaterialLineEdit, SphereSelectPocketSailFilmFromDb, "从膜材数据库选择兜帆材质")
    if hasattr(ui, "WingSailMaterialLineEdit"):
        add_select_action(ui.WingSailMaterialLineEdit, SphereSelectWingSailFilmFromDb, "从膜材数据库选择翼帆材质")
    if hasattr(ui, "WingSailRodUnitWeightLineEdit"):
        add_select_action(ui.WingSailRodUnitWeightLineEdit, SphereSelectWingSailRodFromDb, "从管材数据库选择碳纤维杆米重")
    
    # 飞艇页面内嵌按钮
    if hasattr(ui, "AirShipFilmUnitWeightLineEdit"):
        add_select_action(ui.AirShipFilmUnitWeightLineEdit, AirShipSelectFilmFromDb, "从膜材数据库选择标准克重")
    if hasattr(ui, "AirShipAuxiliaryFilmUnitWeightLineEdit"):
        add_select_action(ui.AirShipAuxiliaryFilmUnitWeightLineEdit, AirShipSelectAuxFilmFromDb, "从膜材数据库选择副气囊克重")
    if hasattr(ui, "AirShipWindPressureLineEdit"):
        add_select_action(ui.AirShipWindPressureLineEdit, AirShipSelectWindFromDb, "从风速数据库选择工作风速")
    if hasattr(ui, "AirShipCableUnitWeightLineEdit"):
        add_select_action(ui.AirShipCableUnitWeightLineEdit, AirShipSelectCableFromDb, "从缆绳数据库选择（同步米重、直径、破断力）")
    
    # 飞艇页面新增缆绳内嵌按钮
    if hasattr(ui, "AirShipMoorRope1WeightLineEdit"):
        add_select_action(ui.AirShipMoorRope1WeightLineEdit, make_cable_select_handler(ui.AirShipMoorRope1WeightLineEdit), "从缆绳数据库选择锚泊支绳1克重")
    if hasattr(ui, "AirShipMoorRope2WeightLineEdit"):
        add_select_action(ui.AirShipMoorRope2WeightLineEdit, make_cable_select_handler(ui.AirShipMoorRope2WeightLineEdit), "从缆绳数据库选择锚泊支绳2克重")
    if hasattr(ui, "AirShipMoorRope3WeightLineEdit"):
        add_select_action(ui.AirShipMoorRope3WeightLineEdit, make_cable_select_handler(ui.AirShipMoorRope3WeightLineEdit), "从缆绳数据库选择锚泊支绳3克重")
    if hasattr(ui, "AirShipMoorMainRopeWeightLineEdit"):
        add_select_action(ui.AirShipMoorMainRopeWeightLineEdit, make_cable_select_handler(ui.AirShipMoorMainRopeWeightLineEdit), "从缆绳数据库选择锚泊主绳克重")
    if hasattr(ui, "AirShipTetherRope1WeightLineEdit"):
        add_select_action(ui.AirShipTetherRope1WeightLineEdit, make_cable_select_handler(ui.AirShipTetherRope1WeightLineEdit), "从缆绳数据库选择系留支绳1克重")
    if hasattr(ui, "AirShipTetherRope2WeightLineEdit"):
        add_select_action(ui.AirShipTetherRope2WeightLineEdit, make_cable_select_handler(ui.AirShipTetherRope2WeightLineEdit), "从缆绳数据库选择系留支绳2克重")
    if hasattr(ui, "AirShipTetherRope3WeightLineEdit"):
        add_select_action(ui.AirShipTetherRope3WeightLineEdit, make_cable_select_handler(ui.AirShipTetherRope3WeightLineEdit), "从缆绳数据库选择系留支绳3克重")

    # 隐藏原有的按钮（如果存在）
    if hasattr(ui, "SphereFilmSelectButton"):
        ui.SphereFilmSelectButton.hide()
    if hasattr(ui, "SphereWindSelectButton"):
        ui.SphereWindSelectButton.hide()
    if hasattr(ui, "SphereCableSelectButton"):
        ui.SphereCableSelectButton.hide()
    # 隐藏气球页面新增的缆绳按钮
    for btn_name in ["SphereMoorRope1SelectButton", "SphereMoorRope2SelectButton", "SphereMoorRope3SelectButton",
                     "SphereMoorMainRopeSelectButton", "SphereTetherRope1SelectButton", 
                     "SphereTetherRope2SelectButton", "SphereTetherRope3SelectButton"]:
        if hasattr(ui, btn_name):
            getattr(ui, btn_name).hide()
    if hasattr(ui, "AirShipFilmSelectButton"):
        ui.AirShipFilmSelectButton.hide()

    # 导出报告页（Word）与计算页的保存/打开数据按钮
    report_export.setup_report_page(ui)
    page_state.hooks.update(get_info=lambda: report_export.get_info(ui), set_info=lambda info: report_export.set_info(ui, info))
    for _prefix in ("Sphere", "AirShip"):
        getattr(ui, f"{_prefix}SaveDataButton").clicked.connect(lambda _=False, p=_prefix: page_state.save_page(ui, p, MainWindow))
        getattr(ui, f"{_prefix}OpenDataButton").clicked.connect(lambda _=False: page_state.open_file(ui, MainWindow))
    if hasattr(ui, "AirShipWindSelectButton"):
        ui.AirShipWindSelectButton.hide()
    if hasattr(ui, "AirShipCableSelectButton"):
        ui.AirShipCableSelectButton.hide()
    # 隐藏飞艇页面新增的缆绳按钮
    for btn_name in ["AirShipMoorRope1SelectButton", "AirShipMoorRope2SelectButton", "AirShipMoorRope3SelectButton",
                     "AirShipMoorMainRopeSelectButton", "AirShipTetherRope1SelectButton", 
                     "AirShipTetherRope2SelectButton", "AirShipTetherRope3SelectButton"]:
        if hasattr(ui, btn_name):
            getattr(ui, btn_name).hide()
    
    # 为管理页按钮设置文字
    if hasattr(ui, "WindApplySpherePushButton"):
        ui.WindApplySpherePushButton.setText("应用到气球工作风速")
        ui.WindApplySpherePushButton.setToolTip("将当前查询到的风速应用到气球页面的工作风速输入栏")
    if hasattr(ui, "WindApplyAirShipPushButton"):
        ui.WindApplyAirShipPushButton.setText("应用到飞艇工作风速")
        ui.WindApplyAirShipPushButton.setToolTip("将当前查询到的风速应用到飞艇页面的工作风速输入栏")
    if hasattr(ui, "FilmApplySpherePushButton"):
        ui.FilmApplySpherePushButton.setText("应用到气球膜材克重")
        ui.FilmApplySpherePushButton.setToolTip("将当前查询到的膜材克重应用到气球页面的膜材克重输入栏")
    if hasattr(ui, "FilmApplyAirShipPushButton"):
        ui.FilmApplyAirShipPushButton.setText("应用到飞艇膜材克重")
        ui.FilmApplyAirShipPushButton.setToolTip("将当前查询到的膜材克重应用到飞艇页面的膜材克重输入栏")
    if hasattr(ui, "CableApplySpherePushButton"):
        ui.CableApplySpherePushButton.setText("应用到气球缆绳克重")
        ui.CableApplySpherePushButton.setToolTip("将当前查询到的缆绳米重应用到气球页面的缆绳克重输入栏")
    if hasattr(ui, "CableApplyAirShipPushButton"):
        ui.CableApplyAirShipPushButton.setText("应用到飞艇缆绳克重")
        ui.CableApplyAirShipPushButton.setToolTip("将当前查询到的缆绳米重应用到飞艇页面的缆绳克重输入栏")

#region 按钮点击事件
    # ui.SpherePushButton.clicked.connect(SphereCalculate) # 球体计算 - 已移除，使用实时计算

    # ui.AirshipPushButton.clicked.connect(AirShipCalculate)# 飞艇计算 - 已移除，使用实时计算


    # ui.QueryWindPushButton.clicked.connect(QueryWind)# 风压查询
    ui.QueryWindPushButton.setVisible(False)
    ui.QueryWindComboBox.currentTextChanged.connect(QueryWind)

    # ui.QueryFilmPushButton.clicked.connect(QueryFilm)# 膜材查询
    ui.QueryFilmPushButton.setVisible(False)
    ui.QueryFilmManufactureComboBox.currentTextChanged.connect(QueryFilm)
    ui.QueryFilmMaterialComboBox.currentTextChanged.connect(QueryFilm)
    ui.QueryFilmThicknessComboBox.currentTextChanged.connect(QueryFilm)

    # ui.QueryCablePushButton.clicked.connect(QueryCable)# 缆绳查询
    ui.QueryCablePushButton.setVisible(False)
    ui.QueryCableMaterialComboBox.currentTextChanged.connect(QueryCable)
    ui.QueryCableDiameterComboBox.currentTextChanged.connect(QueryCable)

    # ui.QueryTubePushButton.clicked.connect(QueryTube)# 管材查询
    ui.QueryTubePushButton.setVisible(False)
    ui.QueryTubeMaterialComboBox.currentTextChanged.connect(QueryTube)
    ui.QueryTubeDiameterComboBox.currentTextChanged.connect(QueryTube)
    ui.QueryTubeThicknessComboBox.currentTextChanged.connect(QueryTube)

    ui.AboutCommandLinkButton.clicked.connect(AboutLink)# 关于链接
    
    # 主题切换信号绑定
    ui.radioButton_light_theme.clicked.connect(set_theme_light)
    ui.radioButton_dark_theme.clicked.connect(set_theme_dark)
    ui.radioButton_auto_theme.clicked.connect(set_theme_auto)
    ui.checkBox_auto_theme.stateChanged.connect(lambda state: toggle_auto_theme(state == 2))  # 2 = Qt.Checked
  
    ui.WindAddPushButton.clicked.connect(ManageInsertWind)# 风压管理-添加
    ui.WindDeletedPushButton.clicked.connect(ManageDeleteWind)# 风压管理-删除
    ui.WindUpdatePushButton.clicked.connect(ManageUpdateWind)# 风压管理-修改
    # ui.WindQueryPushButton.clicked.connect(ManageQueryWind)# 风压管理-更新
    ui.WindQueryPushButton.setVisible(False)
    ManageQueryWind() # Initialize table
    ui.WindTableView.clicked.connect(SelectionChangedWind)# 风压管理-表格显示

    ui.FilmAddPushButton.clicked.connect(ManageInsertFilm)# 膜材管理-添加
    ui.FilmDeletePushButton.clicked.connect(ManageDeleteFilm)# 膜材管理-删除
    ui.FilmUpDataPushButton.clicked.connect(ManageUpdateFilm)# 膜材管理-修改
    # ui.FilmQueryPushButton.clicked.connect(ManageQueryFilm)# 膜材管理-更新
    ui.FilmQueryPushButton.setVisible(False)
    ManageQueryFilm() # Initialize table
    ui.FilmTableView.clicked.connect(SelectionChangedFilm)# 膜材管理-表格显示

    ui.CableAddPushButton.clicked.connect(ManageInsertCable)# 缆绳管理-添加
    ui.CableDeletePushButton.clicked.connect(ManageDeleteCable)# 缆绳管理-删除
    ui.CableUpDataPushButton.clicked.connect(ManageUpdateCable)# 缆绳管理-修改
    # ui.CableQueryPushButton.clicked.connect(ManageQueryCable)# 缆绳管理-更新
    ui.CableQueryPushButton.setVisible(False)
    ManageQueryCable() # Initialize table
    ui.CableTableView.clicked.connect(SelectionChangedCable)# 缆绳管理-表格显示

    # 管理页 -> 计算页 应用按钮
    ui.WindApplySpherePushButton.clicked.connect(ApplyWindToSphere)
    ui.WindApplyAirShipPushButton.clicked.connect(ApplyWindToAirShip)
    ui.FilmApplySpherePushButton.clicked.connect(ApplyFilmToSphere)
    ui.FilmApplyAirShipPushButton.clicked.connect(ApplyFilmToAirShip)
    ui.CableApplySpherePushButton.clicked.connect(ApplyCableToSphere)
    ui.CableApplyAirShipPushButton.clicked.connect(ApplyCableToAirShip)
    
    # 计算页行内"从数据库选择"按钮（已隐藏，使用内嵌按钮代替）
    # ui.SphereFilmSelectButton.clicked.connect(SphereSelectFilmFromDb)
    # ui.AirShipFilmSelectButton.clicked.connect(AirShipSelectFilmFromDb)
    # ui.SphereWindSelectButton.clicked.connect(SphereSelectWindFromDb)
    # ui.AirShipWindSelectButton.clicked.connect(AirShipSelectWindFromDb)
    # ui.TubeQueryPushButton.clicked.connect(ManageQueryTube)# 管材管理-更新 
    ui.TubeQueryPushButton.setVisible(False)
    ManageQueryTube() # Initialize tablemDb)
    # ui.AirShipCableSelectButton.clicked.connect(AirShipSelectCableFromDb)

    ui.TubeAddPushButton.clicked.connect(ManageInsertTube)# 管材管理-添加
    ui.TubeDeletePushButton.clicked.connect(ManageDeleteTube)# 管材管理-删除
    ui.TubeUpDataPushButton.clicked.connect(ManageUpdateTube)# 管材管理-修改
    ui.TubeQueryPushButton.clicked.connect(ManageQueryTube)# 管材管理-更新 
    ui.TubeTableView.clicked.connect(SelectionChangedTube)# 管材管理-表格显示

    # 输入框文本改变事件 - 实时评估
    ui.SphereDiameterLineEdit.textChanged.connect(SphereDivideNumberCalculate)  # 球体直径改变时自动评估开片数
    ui.AirShipLengthLineEdit.textChanged.connect(AirShipDivideNumberCalculate)  # 飞艇长度改变时自动评估开片数
    ui.AirShipDLRatioLineEdit.textChanged.connect(AirShipDivideNumberCalculate)  # 飞艇径长比改变时自动评估开片数

    # 设置新增缆绳配件的默认值
    # 球体页面默认值
    if hasattr(ui, "SpherePullPointWeightLineEdit"):
        ui.SpherePullPointWeightLineEdit.setText("0.1")  # 拉点克重默认0.1Kg
    if hasattr(ui, "SpherePullPointLineEdit"):
        ui.SpherePullPointLineEdit.setText("16")  # 拉点数量默认16个
    # 锚泊支绳1
    if hasattr(ui, "SphereMoorRope1WeightLineEdit"):
        ui.SphereMoorRope1WeightLineEdit.setText("0.005")  # 支绳1克重默认0.005
    if hasattr(ui, "SphereMoorRope1LengthLineEdit"):
        ui.SphereMoorRope1LengthLineEdit.setText("4")  # 支绳长度默认4m
    if hasattr(ui, "SphereMoorRope1CountLineEdit"):
        ui.SphereMoorRope1CountLineEdit.setText("32")  # 支绳1数量默认32
    # 锚泊支绳2
    if hasattr(ui, "SphereMoorRope2WeightLineEdit"):
        ui.SphereMoorRope2WeightLineEdit.setText("0.01")  # 支绳2克重默认0.01
    if hasattr(ui, "SphereMoorRope2LengthLineEdit"):
        ui.SphereMoorRope2LengthLineEdit.setText("4")  # 支绳长度默认4m
    if hasattr(ui, "SphereMoorRope2CountLineEdit"):
        ui.SphereMoorRope2CountLineEdit.setText("16")  # 支绳2数量默认16
    # 锚泊支绳3
    if hasattr(ui, "SphereMoorRope3WeightLineEdit"):
        ui.SphereMoorRope3WeightLineEdit.setText("0.023")  # 支绳3克重默认0.023
    if hasattr(ui, "SphereMoorRope3LengthLineEdit"):
        ui.SphereMoorRope3LengthLineEdit.setText("4")  # 支绳长度默认4m
    if hasattr(ui, "SphereMoorRope3CountLineEdit"):
        ui.SphereMoorRope3CountLineEdit.setText("8")  # 支绳3数量默认8
    # 锚泊主绳
    if hasattr(ui, "SphereMoorMainRopeWeightLineEdit"):
        ui.SphereMoorMainRopeWeightLineEdit.setText("0.035")  # 主绳克重默认0.035
    if hasattr(ui, "SphereMoorMainRopeLengthLineEdit"):
        ui.SphereMoorMainRopeLengthLineEdit.setText("15")  # 主绳长度默认15m
    if hasattr(ui, "SphereMoorMainRopeCountLineEdit"):
        ui.SphereMoorMainRopeCountLineEdit.setText("8")  # 主绳数量默认8
    # 系留支绳1
    if hasattr(ui, "SphereTetherRope1WeightLineEdit"):
        ui.SphereTetherRope1WeightLineEdit.setText("0.005")  # 支绳1克重默认0.005
    if hasattr(ui, "SphereTetherRope1LengthLineEdit"):
        ui.SphereTetherRope1LengthLineEdit.setText("4")  # 支绳长度默认4m
    if hasattr(ui, "SphereTetherRope1CountLineEdit"):
        ui.SphereTetherRope1CountLineEdit.setText("32")  # 支绳1数量默认32
    # 系留支绳2
    if hasattr(ui, "SphereTetherRope2WeightLineEdit"):
        ui.SphereTetherRope2WeightLineEdit.setText("0.01")  # 支绳2克重默认0.01
    if hasattr(ui, "SphereTetherRope2LengthLineEdit"):
        ui.SphereTetherRope2LengthLineEdit.setText("4")  # 支绳长度默认4m
    if hasattr(ui, "SphereTetherRope2CountLineEdit"):
        ui.SphereTetherRope2CountLineEdit.setText("16")  # 支绳2数量默认16
    # 系留支绳3
    if hasattr(ui, "SphereTetherRope3WeightLineEdit"):
        ui.SphereTetherRope3WeightLineEdit.setText("0.023")  # 支绳3克重默认0.023
    if hasattr(ui, "SphereTetherRope3LengthLineEdit"):
        ui.SphereTetherRope3LengthLineEdit.setText("4")  # 支绳长度默认4m
    if hasattr(ui, "SphereTetherRope3CountLineEdit"):
        ui.SphereTetherRope3CountLineEdit.setText("8")  # 支绳3数量默认8
    
    # 飞艇页面默认值
    if hasattr(ui, "AirShipPullPointWeightLineEdit"):
        ui.AirShipPullPointWeightLineEdit.setText("0.1")  # 拉点克重默认0.1Kg
    if hasattr(ui, "AirShipPullPointLineEdit"):
        ui.AirShipPullPointLineEdit.setText("16")  # 拉点数量默认16个
    # 锚泊支绳1
    if hasattr(ui, "AirShipMoorRope1WeightLineEdit"):
        ui.AirShipMoorRope1WeightLineEdit.setText("0.005")  # 支绳1克重默认0.005
    if hasattr(ui, "AirShipMoorRope1LengthLineEdit"):
        ui.AirShipMoorRope1LengthLineEdit.setText("4")  # 支绳长度默认4m
    if hasattr(ui, "AirShipMoorRope1CountLineEdit"):
        ui.AirShipMoorRope1CountLineEdit.setText("32")  # 支绳1数量默认32
    # 锚泊支绳2
    if hasattr(ui, "AirShipMoorRope2WeightLineEdit"):
        ui.AirShipMoorRope2WeightLineEdit.setText("0.01")  # 支绳2克重默认0.01
    if hasattr(ui, "AirShipMoorRope2LengthLineEdit"):
        ui.AirShipMoorRope2LengthLineEdit.setText("4")  # 支绳长度默认4m
    if hasattr(ui, "AirShipMoorRope2CountLineEdit"):
        ui.AirShipMoorRope2CountLineEdit.setText("16")  # 支绳2数量默认16
    # 锚泊支绳3
    if hasattr(ui, "AirShipMoorRope3WeightLineEdit"):
        ui.AirShipMoorRope3WeightLineEdit.setText("0.023")  # 支绳3克重默认0.023
    if hasattr(ui, "AirShipMoorRope3LengthLineEdit"):
        ui.AirShipMoorRope3LengthLineEdit.setText("4")  # 支绳长度默认4m
    if hasattr(ui, "AirShipMoorRope3CountLineEdit"):
        ui.AirShipMoorRope3CountLineEdit.setText("8")  # 支绳3数量默认8
    # 锚泊主绳
    if hasattr(ui, "AirShipMoorMainRopeWeightLineEdit"):
        ui.AirShipMoorMainRopeWeightLineEdit.setText("0.035")  # 主绳克重默认0.035
    if hasattr(ui, "AirShipMoorMainRopeLengthLineEdit"):
        ui.AirShipMoorMainRopeLengthLineEdit.setText("15")  # 主绳长度默认15m
    if hasattr(ui, "AirShipMoorMainRopeCountLineEdit"):
        ui.AirShipMoorMainRopeCountLineEdit.setText("8")  # 主绳数量默认8
    # 系留支绳1
    if hasattr(ui, "AirShipTetherRope1WeightLineEdit"):
        ui.AirShipTetherRope1WeightLineEdit.setText("0.005")  # 支绳1克重默认0.005
    if hasattr(ui, "AirShipTetherRope1LengthLineEdit"):
        ui.AirShipTetherRope1LengthLineEdit.setText("4")  # 支绳长度默认4m
    if hasattr(ui, "AirShipTetherRope1CountLineEdit"):
        ui.AirShipTetherRope1CountLineEdit.setText("32")  # 支绳1数量默认32
    # 系留支绳2
    if hasattr(ui, "AirShipTetherRope2WeightLineEdit"):
        ui.AirShipTetherRope2WeightLineEdit.setText("0.01")  # 支绳2克重默认0.01
    if hasattr(ui, "AirShipTetherRope2LengthLineEdit"):
        ui.AirShipTetherRope2LengthLineEdit.setText("4")  # 支绳长度默认4m
    if hasattr(ui, "AirShipTetherRope2CountLineEdit"):
        ui.AirShipTetherRope2CountLineEdit.setText("16")  # 支绳2数量默认16
    # 系留支绳3
    if hasattr(ui, "AirShipTetherRope3WeightLineEdit"):
        ui.AirShipTetherRope3WeightLineEdit.setText("0.023")  # 支绳3克重默认0.023
    if hasattr(ui, "AirShipTetherRope3LengthLineEdit"):
        ui.AirShipTetherRope3LengthLineEdit.setText("4")  # 支绳长度默认4m
    if hasattr(ui, "AirShipTetherRope3CountLineEdit"):
        ui.AirShipTetherRope3CountLineEdit.setText("8")  # 支绳3数量默认8

#endregion
    
    # 实时计算事件绑定
    equipment_names = ["NetBag", "RotateConnector", "ForceSensor", "Platform", "AirFan", "SafetyValve",
                       "EscapeValve", "PowerBoard", "WindMeter", "ControlBox", "InflationPort", "ObservationWindow"]
    rope_names = ["MoorRope1", "MoorRope2", "MoorRope3", "MoorMainRope", "TetherRope1", "TetherRope2", "TetherRope3"]
    common_inputs = ["FilmUnitWeight", "AuxiliaryFilmUnitWeight", "CableDiameter", "WindPressure", "CustomerLoad",
                     "TargetHeight", "CableUnitWeight", "Altitude", "OtherWeight", "AuxiliaryAirbagRatio",
                     "HeliumLeakageRate", "StayDays", "GroundTemperature", "TempDiff", "GasTemperature",
                     "DragCoefficient", "GasPurity", "PullPointWeight", "PullPoint"]
    # 这些输入变化后副气囊比例恢复自动推荐
    aux_reset_inputs = ["GroundTemperature", "TempDiff", "FillTemperature", "GasTemperature", "TargetHeight", "Altitude",
                        "FillFraction", "FillEndTarget", "AuxMargin"]

    def connect_once(widget, signal_name, slot):
        """界面布局模块创建的控件已自行绑定重算，这里只绑定 ui_form 原有控件。"""
        if widget is not None and not widget.property("autoBound"):
            getattr(widget, signal_name).connect(slot)

    for prefix, recalc, reset_aux, manual_aux, shape_inputs in (
        ("Sphere", SphereCalculateRealTime, ResetSphereAuxRatioMode, SphereAuxRatioManualEdit, ["Diameter", "Ratio"]),
        ("AirShip", AirShipCalculateRealTime, ResetAirShipAuxRatioMode, AirShipAuxRatioManualEdit,
         ["Length", "DLRatio", "CenterRatio"]),
    ):
        rope_inputs = [f"{rope}{part}" for rope in rope_names for part in ("Weight", "Length", "Count")]
        for name in shape_inputs + common_inputs + equipment_names + rope_inputs:
            connect_once(getattr(ui, f"{prefix}{name}LineEdit", None), "textChanged", recalc)
        for name in ["PullPoint"] + rope_names:
            getattr(ui, f"checkBox_{prefix}{name}Enable").stateChanged.connect(recalc)
        for name in ("DivideNumber", "SewWidth", "GasType"):
            connect_once(getattr(ui, f"{prefix}{name}ComboBox"), "currentTextChanged", recalc)
        for name in shape_inputs[:1] + aux_reset_inputs:
            widget = getattr(ui, f"{prefix}{name}LineEdit", None)
            if widget is not None:
                widget.textChanged.connect(reset_aux)
        getattr(ui, f"{prefix}AuxiliaryAirbagRatioLineEdit").textChanged.connect(manual_aux)

    for name in ("PocketSailAreaRatio", "PocketSailMaterial", "PocketSailLiftCoeff", "WingSailAreaRatio",
                 "WingSailMaterial", "WingSailRodLength", "WingSailRodUnitWeight", "WingSailLiftCoeff"):
        getattr(ui, f"{name}LineEdit").textChanged.connect(SphereCalculateRealTime)
    
    # 再次强制设置查询页面按钮间隔（因为apply_zebra_stripes可能会重置间隔）
    def fix_query_buttons_spacing(ui):
        manage_button_names = [
            'WindAddPushButton', 'WindDeletedPushButton', 'WindUpdatePushButton',
            'FilmAddPushButton', 'FilmDeletePushButton', 'FilmUpDataPushButton',
            'CableAddPushButton', 'CableDeletePushButton', 'CableUpDataPushButton',
            'TubeAddPushButton', 'TubeDeletePushButton', 'TubeUpDataPushButton'
        ]
        
        # Helper to find layout containing widget
        def find_layout_containing_widget(layout, widget):
            if not layout: return None
            for i in range(layout.count()):
                item = layout.itemAt(i)
                if item.widget() == widget:
                    return layout
                if item.layout():
                    res = find_layout_containing_widget(item.layout(), widget)
                    if res: return res
            return None

        processed_layouts = set()
        for name in manage_button_names:
            if hasattr(ui, name):
                btn = getattr(ui, name)
                parent = btn.parentWidget()
                if parent and parent.layout():
                    target_layout = find_layout_containing_widget(parent.layout(), btn)
                    if target_layout and isinstance(target_layout, QHBoxLayout):
                        if target_layout not in processed_layouts:
                            target_layout.setSpacing(30)
                            processed_layouts.add(target_layout)
    
    fix_query_buttons_spacing(ui)

    # 自动调整窗口大小的功能已移除，以保持用户拖动的窗口尺寸
    # def on_tab_changed(index):
    #     ...
    
    # ui.tabWidget.currentChanged.connect(on_tab_changed)
    
    # 初始化时也执行一次，确保初始状态正确
    # on_tab_changed(ui.tabWidget.currentIndex())

    SphereDivideNumberCalculate()
    AirShipDivideNumberCalculate()

    MainWindow.resize(MainWindow.width, MainWindow.height)
    MainWindow.show()
    sys.exit(app.exec_())
#endregion
