import io
import os
import sys
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from test_model import sphere_inputs  # noqa: E402
from aerostat_model import analyze, sensitivity_speeds, wind_sweep  # noqa: E402
from aerostat_drag import sphere_design  # noqa: E402

try:
    import docx
    import report_docx
except ImportError:  # python-docx 未安装时跳过报告测试
    docx = None


class SensitivityTests(unittest.TestCase):
    def setUp(self):
        self.inp = sphere_inputs(overpressure_kpa=0.8, film_strength_n5cm=4000.0)
        self.res = analyze(self.inp)

    def test_speeds_cover_work_and_max_wind(self):
        speeds = sensitivity_speeds(self.res)
        self.assertEqual(speeds[0], 0.0)
        self.assertGreater(speeds[-1], self.res["work"]["wind"]["speed_10"])
        self.assertGreaterEqual(speeds[-1], self.res["max_wind"]["speed_10"])
        self.assertEqual(speeds, sorted(speeds))

    def test_sweep_reproduces_the_base_case_and_is_monotonic(self):
        work_v10 = self.res["work"]["wind"]["speed_10"]
        rows = wind_sweep(self.inp, self.res, [work_v10])
        self.assertAlmostEqual(rows[0]["tension"], self.res["work"]["mean"]["tension"], delta=2e-3 * rows[0]["tension"])
        self.assertAlmostEqual(rows[0]["peak_tension"], self.res["work"]["peak_tension"], delta=2e-3 * rows[0]["peak_tension"])
        rows = wind_sweep(self.inp, self.res, [2.0, 6.0, 10.0])
        flying = [r for r in rows if r["flyable"]]
        self.assertGreaterEqual(len(flying), 2)
        self.assertEqual([r["peak_tension"] for r in flying], sorted(r["peak_tension"] for r in flying))

    def test_ok_flag_matches_max_wind(self):
        limit = self.res["max_wind"]["speed_10"]
        below, above = wind_sweep(self.inp, self.res, [0.9 * limit, 1.2 * limit])
        self.assertTrue(below["ok"])
        self.assertFalse(above["ok"])


def make_ctx(kind="Sphere", **overrides):
    inp = sphere_inputs(**overrides)
    if kind == "AirShip":
        inp.shape = "airship"
    res = analyze(inp)
    sphere_shape = {"kind": "sphere", "a": 5.0, "b": 5.0, "divide": 32}
    airship_shape = {"kind": "airship", "a1": 9.6, "a2": 22.4, "b": 4.0, "fin_count": 4, "span": 2.0, "chord": 3.0,
                     "planform": 24.0, "thickness": 0.15}
    geometry = {"volume": inp.volume, "surface": inp.surface_area, "windward": 78.5, "sew": 40.0, "film_mass": 30.0,
                "budget": [("球体膜材", 30.0), ("帆", 0.0), ("附件设备", 12.0), ("客户负载", 18.0)],
                "shape": sphere_shape if kind == "Sphere" else airship_shape}
    drag = sphere_design(10.0, 8.0, 1.2, 15.0)
    ctx = {"kind": kind, "inp": inp, "res": res, "geometry": geometry,
           "drag": {"result": drag, "used": drag.cd, "manual": None, "speed": 8.0, "density": 1.2, "temp": 15.0},
           "info": {"project": "测试项目", "number": "T-001", "author": "张三"},
           "ui": {"SphereFilmUnitWeightLineEdit": "0.2", "SphereSewWidthComboBox": "40"},
           "sensitivity": wind_sweep(inp, res, sensitivity_speeds(res)),
           "input_groups": [("① 外形与材料", [("###SUBTITLE###", "外形", ""), ("气球直径", "10", "m")])],
           "options": {"appendix": True, "sensitivity": True}}
    return ctx


@unittest.skipIf(docx is None, "需要 python-docx")
class ReportDocxTests(unittest.TestCase):
    def build(self, ctx):
        stream = io.BytesIO()
        report_docx.generate(stream, ctx)
        stream.seek(0)
        return docx.Document(stream), stream.getvalue()

    def texts(self, document):
        parts = [p.text for p in document.paragraphs]
        for table in document.tables:
            for row in table.rows:
                parts.extend(cell.text for cell in row.cells)
        return "\n".join(parts)

    def test_sphere_report_has_all_chapters_and_data(self):
        document, raw = self.build(make_ctx("Sphere"))
        headings = [p.text for p in document.paragraphs if p.style.name.startswith("Heading")]
        for expected in ("摘  要", "1  概述", "2  设计输入与设计条件", "3  计算方法与模型", "4  计算结果与分析", "5  结论与建议",
                         "附录 A  输入与结果参数清单"):
            self.assertIn(expected, headings)
        text = self.texts(document)
        self.assertIn("测试项目", text)
        self.assertIn("缆绳安全系数", text)
        self.assertIn("风速敏感性", text)
        self.assertTrue(zipfile.is_zipfile(io.BytesIO(raw)))

    def test_airship_report_includes_tail_section(self):
        document, _ = self.build(make_ctx("AirShip"))
        text = self.texts(document)
        self.assertIn("尾翼", text)
        self.assertIn("系留飞艇", text)

    def test_failing_design_reports_failure_and_advice(self):
        ctx = make_ctx("Sphere", fixed_mass=2000.0)
        document, _ = self.build(ctx)
        text = self.texts(document)
        self.assertIn("不合格", text)
        self.assertIn("减轻重量", text)

    def test_options_can_drop_appendix_and_sensitivity(self):
        ctx = make_ctx("Sphere")
        ctx["options"] = {"appendix": False, "sensitivity": False}
        document, _ = self.build(ctx)
        text = self.texts(document)
        headings = [p.text for p in document.paragraphs if p.style.name.startswith("Heading")]
        self.assertNotIn("附录 A  输入与结果参数清单", headings)
        self.assertNotIn("风速敏感性数据", text)

    def test_images_are_embedded(self):
        from base64 import b64decode
        png = b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")
        ctx = make_ctx("Sphere")
        ctx["images"] = {"shape": png, "wind": png}
        document, _ = self.build(ctx)
        self.assertEqual(len(document.inline_shapes), 2)


if __name__ == "__main__":
    unittest.main()
