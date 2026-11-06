"""真实 PyQt5（offscreen）下启动 CalculateApp 并驱动界面，用于回归基准、冒烟测试与截图。

用法：.venv314\\Scripts\\python.exe tests\\qt_harness.py <scenario> [输出目录]
scenario：baseline（记录全部输入输出到 JSON）、shots（保存两页截图）、smoke（检查日志无 ERROR）
"""
import json
import os
import runpy
import shutil
import sys
import tempfile

if not (len(sys.argv) > 1 and sys.argv[1] in ("shots", "dragshots", "diagrams", "report")):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PyQt5 import QtWidgets  # noqa: E402

DATABASES = ("wind.db", "Cable.db", "Film.db", "Tube.db")
HOOK = {}


def dump_fields(ui, prefixes=("Sphere", "AirShip", "Pocket", "Wing")):
    values = {}
    for name in sorted(vars(ui)):
        widget = getattr(ui, name)
        if isinstance(widget, QtWidgets.QLineEdit) and name.startswith(prefixes):
            values[name] = widget.text()
        elif isinstance(widget, QtWidgets.QComboBox) and name.startswith(prefixes):
            values[name] = widget.currentText()
    return values


def set_fields(ui, **fields):
    for name, value in fields.items():
        widget = getattr(ui, name)
        if isinstance(widget, QtWidgets.QComboBox):
            widget.setCurrentText(str(value))
        elif hasattr(widget, "setChecked") and isinstance(value, bool):
            widget.setChecked(value)
        else:
            widget.setText(str(value))


def calculate_now(g, which):
    """绕过 150 ms 防抖，立即执行计算。"""
    g["SphereCalculate" if which == "Sphere" else "AirShipCalculate"]()


def scenarios(g):
    ui = g["ui"]
    out = {}
    calculate_now(g, "Sphere")
    out["sphere_default"] = dump_fields(ui)
    set_fields(ui, SphereWindPressureLineEdit="18.3")
    calculate_now(g, "Sphere")
    out["sphere_wind18"] = dump_fields(ui)
    set_fields(ui, AirShipLengthLineEdit="32", AirShipDLRatioLineEdit="0.25", AirShipCenterRatioLineEdit="0.3",
               AirShipAltitudeLineEdit="2000", AirShipWindPressureLineEdit="18.3")
    calculate_now(g, "AirShip")
    out["airship_alt2000"] = dump_fields(ui)
    return out


def extra_scenarios(g):
    """覆盖帆、风速输入方式、强度输入与结论文本，检查无异常。"""
    ui = g["ui"]
    for prefix, which in (("Sphere", "Sphere"), ("AirShip", "AirShip")):
        set_fields(ui, **{f"{prefix}CableBreakingForceLineEdit": "25000", f"{prefix}FilmStrengthLineEdit": "4000",
                          f"{prefix}PullRatingLineEdit": "3000"})
        if prefix == "Sphere":
            ui.radio_PocketSail.setChecked(True)
            calculate_now(g, which)
            ui.radio_WingSail.setChecked(True)
        for mode in (0, 1, 2):
            getattr(ui, f"{prefix}WindModeComboBox").setCurrentIndex(mode)
            if mode == 2:
                set_fields(ui, **{f"{prefix}WindTableLineEdit": "0:8, 50:14, 100:18, 300:22",
                                  f"{prefix}SurvivalWindTableLineEdit": "0:20, 100:30, 300:38"})
            calculate_now(g, which)
            print(prefix, "mode", mode,
                  getattr(ui, f"{prefix}ConclusionLineEdit").text(), "|",
                  getattr(ui, f"{prefix}SurvConclusionLineEdit").text(), "|",
                  getattr(ui, f"{prefix}MaxWindSpeedLineEdit").text())


def fill_scenario(g):
    ui = g['ui']
    ui.SphereAuxiliaryAirbagRatioLineEdit.setText('0.2')
    out = {}
    for fill in ('', '0.9', '1', '1.5'):
        ui.SphereFillFractionLineEdit.setText(fill)
        calculate_now(g, 'Sphere')
        out[fill] = (ui.SphereFillVolumeLineEdit.text(), ui.SphereEffectiveLiftLineEdit.text(), ui.SpherePressureHeightLineEdit.text(),
                     ui.SphereConclusionLineEdit.text()[:90], ui.SphereTargetFillLineEdit.text(), ui.SphereMaxWindSpeedLineEdit.text()[:12])
    ui.SphereFillFractionLineEdit.setText('')
    print('FILL', out)


def aux_scenario(g):
    ui = g["ui"]
    for prefix in ("Sphere", "AirShip"):
        for ratio in ("0.06", "0.2", "0.4"):
            getattr(ui, f"{prefix}AuxiliaryAirbagRatioLineEdit").setText(ratio)
            from PyQt5 import QtTest
            QtTest.QTest.qWait(500)
            print("AUX", prefix, ratio, [getattr(ui, f"{prefix}{n}LineEdit").text() for n in (
                "AuxiliaryAirbagRatio", "AuxiliaryAirbagVolume", "AuxiliaryAirbagArea", "AuxiliaryAirbagWeight")])


def fill_aux_scenario(g):
    from PyQt5 import QtTest
    ui = g["ui"]
    ui.SphereAuxiliaryAirbagRatioLineEdit.setText("")
    out = []
    for fill in ("0.7", "0.9", ""):
        ui.SphereFillFractionLineEdit.setText(fill)
        QtTest.QTest.qWait(500)
        out.append((fill, ui.SphereAuxiliaryAirbagRatioLineEdit.text()))
    ui.SphereAuxMarginLineEdit.setText("0.5")
    ui.SphereFillFractionLineEdit.setText("0.7")
    QtTest.QTest.qWait(500)
    out.append(("0.7/margin0.5", ui.SphereAuxiliaryAirbagRatioLineEdit.text()))
    ui.SphereAuxiliaryAirbagRatioLineEdit.setText("0.4")
    QtTest.QTest.qWait(500)
    out.append(("manual0.4", ui.SphereAuxiliaryAirbagRatioLineEdit.text()))
    ui.SphereAuxMarginLineEdit.setText("0.05")
    QtTest.QTest.qWait(500)
    out.append(("margin back->auto", ui.SphereAuxiliaryAirbagRatioLineEdit.text()))
    ui.SphereFillFractionLineEdit.setText("")
    print("FILLAUX", out)


def run_hook(g):
    mode = HOOK["mode"]
    window = g["MainWindow"]
    window.resize(1700, 1000)
    window.show()
    QtWidgets.QApplication.processEvents()
    if mode == "baseline":
        result = scenarios(g)
        with open(HOOK["target"], "w", encoding="utf-8") as handle:
            json.dump(result, handle, ensure_ascii=False, indent=1)
        print("baseline 已写入", HOOK["target"], {k: len(v) for k, v in result.items()})
    elif mode == "shots":
        ui = g["ui"]
        scenarios(g)
        os.makedirs(HOOK["target"], exist_ok=True)
        for index, name in ((0, "sphere"), (1, "airship")):
            ui.tabWidget.setCurrentIndex(index)
            QtWidgets.QApplication.processEvents()
            path = os.path.join(HOOK["target"], f"{name}.png")
            window.grab().save(path)
            print("截图", path)
            content = ui.scrollAreaWidgetContents_2
            page = ui.SpherePage if name == "sphere" else ui.AirshipPage
            inner = page.findChild(QtWidgets.QScrollArea)
            if inner is not None:
                body_path = os.path.join(HOOK["target"], f"{name}_body.png")
                inner.widget().grab().save(body_path)
                print("截图", body_path, inner.widget().width(), inner.widget().height())
            content.resize(1900, max(content.minimumSizeHint().height(), content.sizeHint().height()))
            QtWidgets.QApplication.processEvents()
            full = os.path.join(HOOK["target"], f"{name}_full.png")
            content.grab().save(full)
            print("截图", full, content.size().width(), content.size().height())
    elif mode == "labels":
        ui = g["ui"]
        scenarios(g)
        import collections
        for page in (ui.SpherePage, ui.AirshipPage):
            seen = collections.defaultdict(list)
            for box in page.findChildren(QtWidgets.QGroupBox):
                for lab in box.findChildren(QtWidgets.QLabel):
                    pass
                for edit in box.findChildren(QtWidgets.QLineEdit):
                    if edit.isHidden() or edit.objectName() == "":
                        continue
                    seen[edit.objectName()].append(box.title())
            print("PAGE", page.objectName(), len(seen))
            for box in page.findChildren(QtWidgets.QGroupBox):
                rows = []
                def walk(layout):
                    for i in range(layout.count()):
                        it = layout.itemAt(i)
                        if it.layout() is not None:
                            sub = it.layout()
                            ws = [sub.itemAt(k).widget() for k in range(sub.count()) if sub.itemAt(k).widget() is not None]
                            labs = [w.text() for w in ws if isinstance(w, QtWidgets.QLabel)]
                            vals = [(w.text() if isinstance(w, QtWidgets.QLineEdit) else w.currentText()) for w in ws if isinstance(w, (QtWidgets.QLineEdit, QtWidgets.QComboBox))]
                            names = [w.objectName() for w in ws if isinstance(w, (QtWidgets.QLineEdit, QtWidgets.QComboBox))]
                            if labs or names:
                                rows.append(" | ".join(labs[:1]) + " = " + ",".join(vals) + " [" + ",".join(names) + "] " + (labs[1] if len(labs) > 1 else ""))
                            walk(sub)
                        elif it.widget() is not None and it.widget().layout() is not None:
                            walk(it.widget().layout())
                walk(box.layout())
                if box.parent() is page or box.parent().objectName() == "widget_PageContainer":
                    print("BOX", box.objectName(), box.title())
                    for r in rows:
                        print("   ", r)
    elif mode == "tips":
        ui = g["ui"]
        scenarios(g)
        total = 0
        for page in (ui.SpherePage, ui.AirshipPage):
            for widget in page.findChildren((QtWidgets.QLineEdit, QtWidgets.QComboBox, QtWidgets.QCheckBox,
                                             QtWidgets.QRadioButton)):
                total += 1
                if not widget.toolTip().strip():
                    print("NOTIP", page.objectName(), type(widget).__name__, widget.objectName() or widget.text())
        print("TIPS 控件总数", total)
    elif mode == "report":
        import page_state
        import report_export
        ui = g["ui"]
        scenarios(g)
        os.makedirs(HOOK["target"], exist_ok=True)
        ui.SphereNetBagCheckBox.setChecked(True)
        ui.checkBox_SphereMoorMainRopeEnable.setChecked(True)
        info = {"project": "测试项目", "number": "TB-001", "organization": "某某研究所", "author": "张三", "reviewer": "李四",
                "approver": "王五"}
        report_export.set_info(ui, info)
        for prefix in ("Sphere", "AirShip"):
            set_fields(ui, **{f"{prefix}CableBreakingForceLineEdit": "25000", f"{prefix}FilmStrengthLineEdit": "4000",
                              f"{prefix}PullRatingLineEdit": "3000", f"{prefix}PullPointLineEdit": "12"})
            calculate_now(g, prefix)
            g["calc_controller"].run_sweep(prefix, 0.6, 1.6, 9)
            path = os.path.join(HOOK["target"], f"report_{prefix}.docx")
            report_export.export_report(ui, prefix, path)
            print("REPORT", prefix, path, os.path.getsize(path))
            ctx = report_export.collect_context(ui, prefix)
            for key, png in ctx["images"].items():
                with open(os.path.join(HOOK["target"], f"fig_{prefix}_{key}.png"), "wb") as handle:
                    handle.write(png)
            print("REPORT 图", prefix, sorted(ctx["images"]), "附录分组", [(t, len(i)) for t, i in ctx["input_groups"]])
        ui.tabWidget.setCurrentWidget(ui.PrintPage)
        QtWidgets.QApplication.processEvents()
        window.grab().save(os.path.join(HOOK["target"], "export_page.png"))
    elif mode == "saveopen":
        import page_state
        ui = g["ui"]
        scenarios(g)
        for prefix in ("Sphere", "AirShip"):
            set_fields(ui, **{f"{prefix}CableBreakingForceLineEdit": "25000", f"{prefix}AltitudeLineEdit": "850"})
            getattr(ui, f"{prefix}AuxiliaryAirbagRatioLineEdit").setText("0.33")
            g["calc_controller"].set_aux_manual(prefix, True)
            calculate_now(g, prefix)
            before_inputs = page_state.collect_inputs(ui, prefix)
            before_results = dump_fields(ui)
            payload = page_state.build_payload(ui, prefix)
            path = os.path.join(tempfile.gettempdir(), f"calc_{prefix}.txt")
            import datafile
            datafile.write_file(path, payload)
            # 改乱输入后读回
            set_fields(ui, **{f"{prefix}AltitudeLineEdit": "5", f"{prefix}CableBreakingForceLineEdit": "1"})
            g["calc_controller"].set_aux_manual(prefix, False)
            loaded = datafile.read_file(path)
            page_state.apply_payload(ui, loaded)
            after_inputs = page_state.collect_inputs(ui, prefix)
            diff = {k: (before_inputs[k], after_inputs.get(k)) for k in before_inputs if before_inputs[k] != after_inputs.get(k)}
            print("SAVEOPEN", prefix, "输入项", len(before_inputs), "差异", diff,
                  "结果一致", dump_fields(ui) == before_results, "手动副气囊", g["calc_controller"].aux_manual(prefix))
        print("SAVEOPEN 文件示例", open(path, encoding="utf-8").read()[:300])
    elif mode == "dragshots":
        ui = g["ui"]
        scenarios(g)
        from calc_controller import drag_report
        from drag_dialog import DragDialog
        os.makedirs(HOOK["target"], exist_ok=True)
        for prefix in ("Sphere", "AirShip"):
            calculate_now(g, prefix)
            dialog = DragDialog(drag_report(prefix), lambda text: None, lambda: None)
            dialog.show()
            QtWidgets.QApplication.processEvents()
            path = os.path.join(HOOK["target"], f"drag_{prefix}.png")
            dialog.grab().save(path)
            print("截图", path)
    elif mode == "tail":
        ui = g["ui"]
        scenarios(g)
        names = ("FinPlanform", "FinSpan", "FinChord", "FinAreaRatio", "TailDragUsed", "CLAlphaUsed", "StabilityMargin",
                 "AeroLift", "HorizontalForce", "SpeedTarget", "SurvSpeedTarget")
        for aoa, cl, k, tail_cd in (("5", "", "", ""), ("0", "", "", ""), ("10", "", "", ""), ("5", "1.2", "0.4", "0.01"),
                                    ("5", "", "", "0.02")):
            ui.AirShipAoALineEdit.setText(aoa)
            ui.AirShipCLAlphaLineEdit.setText(cl)
            ui.AirShipInducedKLineEdit.setText(k)
            ui.AirShipTailDragCoeffLineEdit.setText(tail_cd)
            calculate_now(g, "AirShip")
            print("TAIL", (aoa, cl, k, tail_cd), [getattr(ui, f"AirShip{n}LineEdit").text() for n in names])
        for name in ("SpeedTarget", "SurvSpeedTarget", "WindPressure", "SurvivalWind", "MaxWindSpeed"):
            print("TIP", name, getattr(ui, f"AirShip{name}LineEdit").toolTip().replace("<br>", " | ")[-150:])
    elif mode == "diagrams":
        ui = g["ui"]
        scenarios(g)
        os.makedirs(HOOK["target"], exist_ok=True)
        from PyQt5 import QtTest
        for prefix in ("Sphere", "AirShip"):
            calculate_now(g, prefix)
            QtTest.QTest.qWait(300)
            ctx = g["calc_controller"]._last[prefix]
            print("BUDGET", prefix, round(sum(kg for _, kg in ctx["geometry"]["budget"]), 6), round(ctx["inp"].fixed_mass, 6))
            panel = getattr(ui, f"{prefix}Diagrams")
            panel.resize(1300, 420)
            for index, name in enumerate(("tether", "shape", "wind", "budget")):
                panel.tabs.setCurrentIndex(index)
                QtWidgets.QApplication.processEvents()
                path = os.path.join(HOOK["target"], f"diagram_{prefix}_{name}.png")
                getattr(panel, name).grab().save(path)
            if hasattr(g["calc_controller"], "run_sweep"):
                g["calc_controller"].run_sweep(prefix, 0.6, 1.6, 9)
            panel.tabs.setCurrentIndex(5)
            QtWidgets.QApplication.processEvents()
            panel.sweep.grab().save(os.path.join(HOOK["target"], f"diagram_{prefix}_sweep.png"))
            set_fields(ui, **{f"{prefix}CableBreakingForceLineEdit": "6000", f"{prefix}CustomerLoadLineEdit": "250"})
            g["calc_controller"].run_sweep(prefix, 0.6, 1.6, 9)
            panel.sweep.grab().save(os.path.join(HOOK["target"], f"diagram_{prefix}_sweep_fail.png"))
            print("截图", prefix)
    elif mode == "drag":
        ui = g["ui"]
        scenarios(g)
        for prefix in ("Sphere", "AirShip"):
            for manual in ("", "0.3", "0.6"):
                getattr(ui, f"{prefix}DragCoefficientLineEdit").setText(manual)
                calculate_now(g, prefix)
                print("DRAG", prefix, repr(manual), getattr(ui, f"{prefix}DragUsedLineEdit").text(),
                      getattr(ui, f"{prefix}DragRangeLineEdit").text(), getattr(ui, f"{prefix}HorizontalForceLineEdit").text())
            getattr(ui, f"{prefix}DragCoefficientLineEdit").setText("")
    elif mode == "metrics":
        ui = g["ui"]
        scenarios(g)
        for page in (ui.SpherePage, ui.AirshipPage):
            print("PAGE", page.objectName(), page.minimumSizeHint().width(), page.sizeHint().width())
            for box in page.findChildren(QtWidgets.QGroupBox):
                if box.parent() is page:
                    print("  ", box.objectName(), box.minimumSizeHint().width(), box.sizeHint().width())
        for page in (ui.SpherePage, ui.AirshipPage):
            lay = page.layout()
            for i in range(lay.count()):
                it = lay.itemAt(i)
                obj = it.widget() or it.layout()
                print("ITEM", page.objectName(), i, type(obj).__name__, (obj.objectName() if obj else None), it.minimumSize().width())
                sub = it.layout()
                if sub is not None:
                    for j in range(sub.count()):
                        s2 = sub.itemAt(j)
                        o2 = s2.widget() or s2.layout()
                        print("     SUB", j, type(o2).__name__, o2.objectName() if o2 else None, s2.minimumSize().width())
        for page in (ui.SpherePage, ui.AirshipPage):
            lay = page.layout()
            print("LAY", type(lay).__name__, lay.minimumSize().width(), lay.totalMinimumSize().width(), page.minimumWidth(), page.minimumSizeHint().width(), page.contentsMargins().left(), lay.spacing())
            for w in page.findChildren(QtWidgets.QWidget):
                if w.minimumWidth() > 300:
                    print("   WIDE", w.objectName(), type(w).__name__, w.minimumWidth())
        print("CONTENT", ui.scrollAreaWidgetContents_2.minimumSizeHint().width())
    elif mode == "smoke":
        scenarios(g)
        extra_scenarios(g)
        fill_scenario(g)
        aux_scenario(g)
        fill_aux_scenario(g)
        import time
        for which in ("Sphere", "AirShip"):
            start = time.perf_counter()
            for _ in range(5):
                calculate_now(g, which)
            print(which, "单次计算耗时 ms", round((time.perf_counter() - start) / 5 * 1000, 1))
        print("smoke 完成")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    mode = sys.argv[1] if len(sys.argv) > 1 else "smoke"
    target = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else os.path.join(ROOT, "tests", "baseline.json")
    HOOK.update(mode=mode, target=target)
    workdir = tempfile.mkdtemp(prefix="calcapp_qt_")
    for db in DATABASES:
        shutil.copy(os.path.join(ROOT, db), os.path.join(workdir, db))
    os.chdir(workdir)

    def fake_exec(self):
        run_hook(sys._getframe(1).f_globals)
        return 0

    QtWidgets.QApplication.exec_ = fake_exec
    try:
        runpy.run_path(os.path.join(ROOT, "CalculateApp.py"), run_name="__main__")
    except SystemExit:
        pass
    log = os.path.join(workdir, "CalculateApp.log")
    errors = []
    if os.path.exists(log):
        with open(log, encoding="utf-8", errors="replace") as handle:
            errors = [line.strip() for line in handle if " ERROR " in line]
    print("日志 ERROR:", errors or "无")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()





