"""Word 研究报告生成器：把一次设计计算的输入与结果整理成结构化的 .docx 报告（封面、摘要、目录、正文、附录）。

与界面无关（只依赖 python-docx）；图片由调用方以 PNG 字节传入，缺省则跳过相应图。
ctx 约定见 report_export.collect_context。力的单位统一为 kgf（括号内给出 kN），质量 kg，压强 Pa。
"""
import datetime
import io
import math

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from aerostat_physics import KGF_PER_KN, kn_to_kg
from aerostat_wind import WIND_MODES, beaufort_level, beaufort_text

CN_BODY, CN_HEAD, LATIN = "宋体", "黑体", "Times New Roman"
GREEN, RED, ORANGE, GREY = RGBColor(0x2E, 0x7D, 0x32), RGBColor(0xC6, 0x28, 0x28), RGBColor(0xEF, 0x6C, 0x00), RGBColor(0x55, 0x55, 0x55)
TEXT_WIDTH_CM = 16.0
VERDICT_COLORS = {"合格": GREEN, "不合格": RED, "未校核": ORANGE, "提示": ORANGE}
KIND_NAME = {"Sphere": "系留气球", "AirShip": "系留飞艇"}


# ---------------------------------------------------------------- 格式化
def n(value, digits=2, empty="—"):
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return empty
    return f"{value:.{digits}f}"


def kgf(force_kn):
    return None if force_kn is None else force_kn * KGF_PER_KN


def force_text(force_kn, digits=1):
    """kgf 为主，括号内给出 kN。"""
    if force_kn is None:
        return "—"
    return f"{force_kn * KGF_PER_KN:.{digits}f} kgf（{force_kn:.2f} kN）"


def verdict_of(value, required):
    if value is None:
        return "未校核"
    return "合格" if value >= required else "不合格"


# ---------------------------------------------------------------- 底层样式
def _set_run_font(run, cn=CN_BODY, size=None, bold=None, color=None, italic=None, latin=LATIN):
    run.font.name = latin
    run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), cn)
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.font.bold = bold
    if italic is not None:
        run.font.italic = italic
    if color is not None:
        run.font.color.rgb = color


def _style_font(style, cn, size, bold=False, color=RGBColor(0, 0, 0)):
    style.font.name = LATIN
    style.font.size = Pt(size)
    style.font.bold = bold
    style.font.color.rgb = color
    fonts = style.element.get_or_add_rPr().rFonts
    for attribute in list(fonts.attrib):
        if "Theme" in attribute or "theme" in attribute:
            del fonts.attrib[attribute]
    fonts.set(qn("w:eastAsia"), cn)
    fonts.set(qn("w:ascii"), LATIN)
    fonts.set(qn("w:hAnsi"), LATIN)


def _shade(cell, fill):
    properties = cell._element.get_or_add_tcPr()
    shading = OxmlElement("w:shd")
    shading.set(qn("w:val"), "clear")
    shading.set(qn("w:color"), "auto")
    shading.set(qn("w:fill"), fill)
    properties.insert_element_before(shading, "w:noWrap", "w:tcMar", "w:textDirection", "w:tcFitText", "w:vAlign",
                                     "w:hideMark")


def _borders(element, **edges):
    """edges: top/bottom/left/right/insideH/insideV = (线型, 粗细 1/8 pt, 颜色)，None 表示无线。element 为 tblPr 或 tcPr。"""
    is_table = element.tag.endswith("tblPr")
    borders = OxmlElement("w:tblBorders" if is_table else "w:tcBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        if edge not in edges:
            continue
        spec = edges[edge]
        node = OxmlElement(f"w:{edge}")
        if spec is None:
            node.set(qn("w:val"), "nil")
        else:
            node.set(qn("w:val"), spec[0])
            node.set(qn("w:sz"), str(spec[1]))
            node.set(qn("w:space"), "0")
            node.set(qn("w:color"), spec[2])
        borders.append(node)
    if is_table:
        element.insert_element_before(borders, "w:shd", "w:tblLayout", "w:tblCellMar", "w:tblLook", "w:tblCaption",
                                      "w:tblDescription")
    else:
        element.insert_element_before(borders, "w:shd", "w:noWrap", "w:tcMar", "w:textDirection", "w:tcFitText",
                                      "w:vAlign", "w:hideMark")


def _add_field(paragraph, instruction, placeholder="", size=None, cn=CN_BODY):
    def part(kind):
        run = paragraph.add_run()
        _set_run_font(run, cn, size)
        node = OxmlElement("w:fldChar")
        node.set(qn("w:fldCharType"), kind)
        run._element.append(node)
        return run

    part("begin")
    run = paragraph.add_run()
    _set_run_font(run, cn, size)
    code = OxmlElement("w:instrText")
    code.set(qn("xml:space"), "preserve")
    code.text = f" {instruction} "
    run._element.append(code)
    part("separate")
    shown = paragraph.add_run(placeholder)
    _set_run_font(shown, cn, size)
    part("end")


def _keep_with_next(paragraph, flag=True):
    paragraph.paragraph_format.keep_with_next = flag


# ---------------------------------------------------------------- 报告构建器
class Report:
    def __init__(self, ctx):
        self.ctx = ctx
        self.kind = ctx["kind"]
        self.is_sphere = self.kind == "Sphere"
        self.name = KIND_NAME[self.kind]
        self.inp, self.res, self.geo = ctx["inp"], ctx["res"], ctx["geometry"]
        self.gas, self.work, self.surv, self.maxw = self.res["gas"], self.res["work"], self.res["survival"], self.res["max_wind"]
        self.req, self.cable = self.inp.requirements, self.inp.cable
        self.info = ctx.get("info") or {}
        self.options = ctx.get("options") or {}
        self.images = ctx.get("images") or {}
        self.ui = ctx.get("ui") or {}
        self.drag = ctx.get("drag")
        self.date = ctx.get("date") or datetime.date.today()
        self.figure_no = self.table_no = self.equation_no = 0
        self.doc = Document()
        self._setup()

    # ---- 取界面值
    def u(self, key, default=""):
        for suffix in ("LineEdit", "ComboBox"):
            value = self.ui.get(f"{'Sphere' if self.is_sphere else 'AirShip'}{key}{suffix}")
            if value is not None and str(value).strip() != "":
                return str(value).strip()
        return default

    def uf(self, key):
        try:
            return float(self.u(key))
        except ValueError:
            return None

    @property
    def title(self):
        if self.info.get("title"):
            return self.info["title"]
        shape = self.geo["shape"]
        size = f"{2 * shape['b']:.1f} m " if self.is_sphere else f"{shape['a1'] + shape['a2']:.1f} m "
        return f"{size}{self.name}设计计算报告"

    # ---- 文档初始化
    def _setup(self):
        doc = self.doc
        section = doc.sections[0]
        section.page_width, section.page_height = Cm(21.0), Cm(29.7)
        section.left_margin = section.right_margin = Cm(2.5)
        section.top_margin, section.bottom_margin = Cm(2.5), Cm(2.3)
        section.header_distance, section.footer_distance = Cm(1.3), Cm(1.1)
        section.different_first_page_header_footer = True
        _style_font(doc.styles["Normal"], CN_BODY, 12)
        normal = doc.styles["Normal"].paragraph_format
        normal.line_spacing = 1.35
        normal.space_after = Pt(0)
        for name, size, before, after in (("Heading 1", 16, 18, 10), ("Heading 2", 14, 12, 6), ("Heading 3", 12, 8, 4)):
            style = doc.styles[name]
            _style_font(style, CN_HEAD, size, bold=True)
            style.paragraph_format.space_before, style.paragraph_format.space_after = Pt(before), Pt(after)
            style.paragraph_format.keep_with_next = True
        properties = doc.core_properties
        properties.title, properties.author = self.title, self.info.get("author") or "系留浮空器设计计算软件"
        properties.subject = f"{self.name}设计计算与校核"
        settings = doc.settings.element
        update = OxmlElement("w:updateFields")
        update.set(qn("w:val"), "true")
        settings.append(update)
        header = section.header.paragraphs[0]
        header.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _set_run_font(header.add_run(self.title), CN_BODY, 9, color=GREY)
        _borders_paragraph(header)
        footer = section.footer.paragraphs[0]
        footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _set_run_font(footer.add_run("第 "), CN_BODY, 9, color=GREY)
        _add_field(footer, "PAGE", "1", 9)
        _set_run_font(footer.add_run(" 页  共 "), CN_BODY, 9, color=GREY)
        _add_field(footer, "NUMPAGES", "1", 9)
        _set_run_font(footer.add_run(" 页"), CN_BODY, 9, color=GREY)

    # ---- 文字块
    def heading(self, level, text):
        paragraph = self.doc.add_heading(level=level)
        _set_run_font(paragraph.add_run(text), CN_HEAD, {1: 16, 2: 14, 3: 12}[level], bold=True)
        return paragraph

    def para(self, text, indent=True, bold=False, size=12, align=None, color=None, space_after=4):
        paragraph = self.doc.add_paragraph()
        if indent:
            paragraph.paragraph_format.first_line_indent = Pt(2 * size)
        paragraph.paragraph_format.space_after = Pt(space_after)
        if align:
            paragraph.alignment = align
        _set_run_font(paragraph.add_run(text), CN_BODY, size, bold=bold, color=color)
        return paragraph

    def bullets(self, items, size=12, numbered=False):
        for index, text in enumerate(items, 1):
            paragraph = self.doc.add_paragraph()
            paragraph.paragraph_format.left_indent = Cm(0.9)
            paragraph.paragraph_format.first_line_indent = Cm(-0.6)
            paragraph.paragraph_format.space_after = Pt(2)
            _set_run_font(paragraph.add_run(f"{index}）" if numbered else "·  "), CN_BODY, size)
            _set_run_font(paragraph.add_run(text), CN_BODY, size)

    def note(self, text):
        return self.para(text, indent=False, size=10, color=GREY, space_after=6)

    def equation(self, text, description=""):
        self.equation_no += 1
        paragraph = self.doc.add_paragraph()
        paragraph.paragraph_format.space_before = Pt(3)
        paragraph.paragraph_format.space_after = Pt(3)
        stops = paragraph.paragraph_format.tab_stops
        stops.add_tab_stop(Cm(TEXT_WIDTH_CM / 2), WD_TAB_ALIGNMENT.CENTER)
        stops.add_tab_stop(Cm(TEXT_WIDTH_CM), WD_TAB_ALIGNMENT.RIGHT)
        _set_run_font(paragraph.add_run("\t" + text), CN_BODY, 11, italic=False)
        _set_run_font(paragraph.add_run(f"\t（{self.equation_no}）"), CN_BODY, 11)
        if description:
            self.note(description)

    def page_break(self):
        self.doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    # ---- 表
    def caption(self, kind, text):
        if kind == "表":
            self.table_no += 1
            number = self.table_no
        else:
            self.figure_no += 1
            number = self.figure_no
        paragraph = self.doc.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.paragraph_format.space_before = Pt(6 if kind == "表" else 2)
        paragraph.paragraph_format.space_after = Pt(4 if kind == "表" else 10)
        _set_run_font(paragraph.add_run(f"{kind} {number}  {text}"), CN_HEAD, 10.5)
        return paragraph

    def table(self, caption, headers, rows, widths=None, align=None, size=10):
        """三线表。rows 的元素是各列文本的序列；单个字符串表示一个跨列的分组标题行；caption 为 None 时不编号。"""
        if caption:
            _keep_with_next(self.caption("表", caption))
        columns = len(headers)
        widths = widths or [TEXT_WIDTH_CM / columns] * columns
        align = align or (["l"] + ["c"] * (columns - 1))
        table = self.doc.add_table(rows=1, cols=columns)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.autofit = False
        _borders(table._tbl.tblPr, top=("single", 12, "000000"), bottom=("single", 12, "000000"), left=None, right=None,
                 insideH=("single", 2, "BFBFBF"), insideV=None)
        head = table.rows[0]
        self._row_flags(head, header=True)
        for index, text in enumerate(headers):
            self._cell(head.cells[index], text, widths[index], "c", size, bold=True, fill="EDF2F8", bottom=True)
        for row in rows:
            cells = table.add_row()
            self._row_flags(cells)
            if isinstance(row, str):
                merged = cells.cells[0].merge(cells.cells[-1])
                self._cell(merged, row, sum(widths), "l", size, bold=True, fill="F5F5F5")
                continue
            for index, text in enumerate(row):
                text = "" if text is None else str(text)
                color = VERDICT_COLORS.get(text)
                self._cell(cells.cells[index], text, widths[index], align[index], size, bold=color is not None, color=color)
        if len(rows) <= 14:   # 短表不跨页
            for row in table.rows[:-1]:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        _keep_with_next(paragraph)
        spacer = self.doc.add_paragraph()
        spacer.paragraph_format.space_after = Pt(2)
        spacer.paragraph_format.line_spacing = 0.6
        return table

    @staticmethod
    def _row_flags(row, header=False):
        properties = row._tr.get_or_add_trPr()
        split = OxmlElement("w:cantSplit")
        properties.append(split)
        if header:
            repeat = OxmlElement("w:tblHeader")
            properties.append(repeat)

    @staticmethod
    def _cell(cell, text, width_cm, align, size, bold=False, color=None, fill=None, bottom=False):
        cell.width = Cm(width_cm)
        if bottom:
            _borders(cell._element.get_or_add_tcPr(), bottom=("single", 8, "000000"))
        if fill:
            _shade(cell, fill)
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        paragraph = cell.paragraphs[0]
        paragraph.alignment = {"l": WD_ALIGN_PARAGRAPH.LEFT, "c": WD_ALIGN_PARAGRAPH.CENTER, "r": WD_ALIGN_PARAGRAPH.RIGHT}[align]
        paragraph.paragraph_format.line_spacing = 1.1
        paragraph.paragraph_format.space_before = paragraph.paragraph_format.space_after = Pt(2)
        _set_run_font(paragraph.add_run(text), CN_BODY, size, bold=bold, color=color)

    def kv_table(self, caption, items, widths=(5.8, 6.6, 3.6)):
        """参数表：items 为 (名称, 数值, 单位) 或分组标题字符串。"""
        return self.table(caption, ["参数", "数值", "单位"], [item if isinstance(item, str) else tuple(item) for item in items],
                          list(widths), ["l", "c", "c"])

    def figure(self, key, caption, width_cm=15.5):
        png = self.images.get(key)
        if not png:
            return False
        paragraph = self.doc.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.paragraph_format.space_before = Pt(6)
        paragraph.paragraph_format.space_after = Pt(0)
        _keep_with_next(paragraph)
        paragraph.add_run().add_picture(io.BytesIO(png), width=Cm(width_cm))
        self.caption("图", caption)
        return True

    # ================================================================ 封面与前置部分
    def build(self):
        self.cover()
        self.abstract()
        self.contents()
        self.chapter_overview()
        self.chapter_inputs()
        self.chapter_methods()
        self.chapter_results()
        self.chapter_conclusion()
        if self.options.get("appendix", True):
            self.appendices()
        return self.doc

    def cover(self):
        doc = self.doc
        for _ in range(4):
            doc.add_paragraph()
        paragraph = doc.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _set_run_font(paragraph.add_run(self.title), CN_HEAD, 26, bold=True)
        paragraph.paragraph_format.space_after = Pt(14)
        paragraph = doc.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _set_run_font(paragraph.add_run("工程设计计算与校核报告"), CN_HEAD, 16, color=GREY)
        for _ in range(5):
            doc.add_paragraph()
        info = self.info
        rows = [("项目名称", info.get("project") or self.title), ("报告编号", info.get("number") or "—"),
                ("版本", info.get("version") or "V1.0"), ("编制单位", info.get("organization") or "—"),
                ("编制", info.get("author") or "—"), ("审核", info.get("reviewer") or "—"),
                ("批准", info.get("approver") or "—"), ("编制日期", self.date.strftime("%Y年%m月%d日"))]
        table = doc.add_table(rows=len(rows), cols=2)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.autofit = False
        _borders(table._tbl.tblPr, top=None, bottom=("single", 6, "000000"), left=None, right=None,
                 insideH=("single", 4, "999999"), insideV=None)
        for index, (label, value) in enumerate(rows):
            self._cell(table.rows[index].cells[0], label + "：", 4.0, "r", 13, bold=True)
            self._cell(table.rows[index].cells[1], value, 8.5, "l", 13)
            for cell in table.rows[index].cells:
                cell.paragraphs[0].paragraph_format.space_before = Pt(6)
                cell.paragraphs[0].paragraph_format.space_after = Pt(6)
        for _ in range(2):
            doc.add_paragraph()
        self.table(None, ["版本", "日期", "编制", "说明"],
                   [(info.get("version") or "V1.0", self.date.strftime("%Y-%m-%d"), info.get("author") or "—",
                     "依据软件计算结果自动生成")], [2.4, 3.4, 3.4, 6.8], size=10.5)
        self.note("本报告的全部数值由系留浮空器设计计算软件按所列输入与模型计算得出；输入条件变化时应重新计算并重新生成报告。")
        self.page_break()

    # ---- 摘要
    def key_indicators(self):
        work, surv, req = self.work, self.surv, self.req
        mean = work["mean"]
        rows = [
            ("囊体总容积", f"{n(self.geo['volume'])} m³", "—", "—"),
            ("毛浮力（设计取值）", f"{n(self.gas['lift_governing_kg'], 1)} kgf", "—", "—"),
            ("系统总重（不含缆绳）", f"{n(self.res['mass_total_kg'], 1)} kg", "—", "—"),
            ("静净浮力（未计缆绳）", f"{n(self.res['static_net_kg'], 1)} kgf", "> 0", "合格" if self.res["static_net_kg"] > 0 else "不合格"),
            ("工作风下净浮力（扣缆绳）", f"{n(kn_to_kg(mean['net_buoyancy']), 1)} kgf" if mean["flyable"] else "缆绳拖地", "> 0",
             "合格" if mean["flyable"] else "不合格"),
            ("缆绳安全系数 · 工作风", n(work["cable_sf"]), f"≥ {req.cable_sf:g}", verdict_of(work["cable_sf"], req.cable_sf)),
            ("缆绳安全系数 · 生存风", n(surv["cable_sf"]), f"≥ {req.survival_sf:g}", verdict_of(surv["cable_sf"], req.survival_sf)),
            ("膜材安全系数 · 工作风", n(work["film"]["sf"]), f"≥ {req.film_sf:g}", verdict_of(work["film"]["sf"], req.film_sf)),
            ("锚点悬链角 · 工作风", f"{n(mean['angle_deg'], 1)}°" if mean["flyable"] else "拖地",
             f"≥ {req.min_angle_deg:g}°" if req.min_angle_deg > 0 else "不拖地", "合格" if self._angle_ok() else "不合格"),
            ("最大允许风速（离地 10 m）", f"{n(self.maxw['speed_10'], 1)} m/s（{beaufort_level(self.maxw['speed_10'])} 级）"
             if self.maxw["scale"] > 0 else "无（静风即不合格）", f"≥ {work['wind']['speed_10']:.1f} m/s",
             "合格" if self.maxw["scale"] >= 1.0 else "不合格"),
        ]
        return rows

    def _angle_ok(self):
        mean = self.work["mean"]
        return mean["flyable"] and mean["angle_deg"] >= self.req.min_angle_deg

    def overall(self):
        """(是否全部合格, 结论句)。"""
        gas_ok = not self.gas["alarms"]
        ok = gas_ok and self.work["ok"] and self.surv["ok"] and self.maxw["scale"] > 0
        if ok:
            return True, "合格"
        reasons = list(self.gas["alarms"]) + list(self.work["failures"])
        if not self.surv["ok"]:
            reasons += [f"生存风：{text}" for text in self.surv["failures"]]
        if self.maxw["scale"] <= 0 and not reasons:
            reasons.append("静风下即不满足校核")
        return False, "不合格：" + "；".join(reasons)

    def abstract(self):
        self.heading(1, "摘  要")
        inp, work, surv, mean = self.inp, self.work, self.surv, self.work["mean"]
        shape = self.geo["shape"]
        if self.is_sphere:
            body = f"{self.name}（直径 {2 * shape['b']:.2f} m、高 {2 * shape['a']:.2f} m）"
        else:
            body = f"{self.name}（长 {shape['a1'] + shape['a2']:.2f} m、最大直径 {2 * shape['b']:.2f} m）"
        self.para(f"本报告对{body}进行了设计计算与校核。设计条件：场地海拔 {inp.altitude:.0f} m，目标高度（离地）{inp.target_height:.0f} m，"
                  f"场地环境温度 {inp.field_temp_c:.1f} ℃，昼夜温差 {inp.temp_diff_c:.1f} ℃；工作风离地 10 m 风速 "
                  f"{work['wind']['speed_10']:.1f} m/s（{beaufort_text(work['wind']['speed_10'])}），生存风离地 10 m 风速 "
                  f"{surv['wind']['speed_10']:.1f} m/s（{beaufort_text(surv['wind']['speed_10'])}）；填充气体为{inp.gas_type}（纯度 {inp.purity:g}%）。")
        net_text = (f"工作风下缆绳可悬空，缆绳悬空长度 {mean['cable_length']:.0f} m、向下风漂移 {mean['drift']:.0f} m、锚点悬链角 "
                    f"{mean['angle_deg']:.1f}°，缆绳阵风峰值拉力 {force_text(work['peak_tension'])}。") if mean["flyable"] else \
            "工作风下缆绳无法悬空（拖地），净浮力不足。"
        self.para(f"主要结果：囊体总容积 {self.geo['volume']:.1f} m³，目标高度毛浮力 {self.gas['lift_governing_kg']:.1f} kgf，系统总重 "
                  f"{self.res['mass_total_kg']:.1f} kg，静净浮力 {self.res['static_net_kg']:.1f} kgf。{net_text}"
                  f"缆绳安全系数 工作风 {n(work['cable_sf'])}（要求 ≥ {self.req.cable_sf:g}）、生存风 {n(surv['cable_sf'])}"
                  f"（要求 ≥ {self.req.survival_sf:g}）；膜材安全系数 {n(work['film']['sf'])}（要求 ≥ {self.req.film_sf:g}）。"
                  + (f"满足全部校核的最大允许风速为离地 10 m {self.maxw['speed_10']:.1f} m/s（{beaufort_level(self.maxw['speed_10'])} 级）。"
                     if self.maxw["scale"] > 0 else "静风下即不满足校核，没有允许风速。"))
        ok, text = self.overall()
        self.para(f"综合结论：{text}。", bold=True, color=GREEN if ok else RED)
        self.table("主要设计指标一览", ["指标", "计算值", "要求", "判定"], self.key_indicators(), [5.6, 4.6, 3.4, 2.4])
        paragraph = self.para("关键词：", indent=False, bold=True, size=12)
        _set_run_font(paragraph.add_run("系留浮空器；浮力；缆绳平衡；风载荷；强度校核；安全系数"), CN_BODY, 12)
        self.page_break()

    def contents(self):
        paragraph = self.doc.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.paragraph_format.space_after = Pt(12)
        _set_run_font(paragraph.add_run("目  录"), CN_HEAD, 16, bold=True)
        toc = self.doc.add_paragraph()
        _add_field(toc, 'TOC \\o "1-2" \\h \\z \\u', "（目录将在 Word 打开时自动生成；如未显示，请右键此处选择“更新域”）", 11)
        self.page_break()

    # ================================================================ 1 概述
    def chapter_overview(self):
        self.heading(1, "1  概述")
        self.heading(2, "1.1  编制目的")
        self.para(f"本报告针对所设计的{self.name}，在给定的场地、气象、材料与系留条件下，完成浮力与重量平衡、风载荷、"
                  "系留缆绳平衡及强度校核，并给出最大允许风速与设计结论，为方案评审、加工制造与现场运行提供依据。")
        self.heading(2, "1.2  设计对象")
        shape = self.geo["shape"]
        if self.is_sphere:
            self.para(f"设计对象为球形（回转椭球）系留气球：赤道直径 {2 * shape['b']:.2f} m，高径比 "
                      f"{shape['a'] / shape['b']:.2f}（竖向高 {2 * shape['a']:.2f} m），采用 {shape['divide']} 片开片缝制；"
                      "囊体内设副气囊（隔层）以补偿氦气的温度与气压变化，并维持运行超压。")
        else:
            self.para(f"设计对象为系留飞艇：全长 {shape['a1'] + shape['a2']:.2f} m，最大直径 {2 * shape['b']:.2f} m，艇身为前后两段椭球拼接的回转体，"
                      f"最大截面距鼻端 {shape['a1']:.2f} m；尾部设 {int(shape['fin_count'])} 片充气尾翼；囊体内设副气囊以补偿氦气的温度与气压变化，"
                      "并维持运行超压。")
        self.heading(2, "1.3  计算流程")
        self.bullets(["大气与浮力：由场地海拔、气温给出空气密度，计算氦气浮力与充盈度、压力高度、副气囊；",
                      "重量平衡：浮力减去膜材、副气囊、设备、绳组与负载，得到静净浮力；",
                      "风场：按地貌给出风速剖面、阵风系数与动压，区分工作风与生存风；",
                      "本体气动力：风阻系数选型（球体/回转体经验模型），计算本体风阻与攻角升力；",
                      "缆绳平衡：沿缆长分段积分，计入缆绳自重与横流风阻，求缆绳形状、拉力、锚点夹角与漂移；",
                      "强度校核：缆绳、膜材、拉点安全系数与运行超压；",
                      "最大允许风速：对工作风整体缩放并二分搜索，直至任一校核不满足。"], numbered=True)
        self.heading(2, "1.4  依据与参考资料")
        self.bullets(["GB 50009-2012《建筑结构荷载规范》（风压高度变化系数、阵风系数、地面粗糙度分类）；",
                      "GB/T 28591-2012《风力等级》（蒲福风级及风速范围）；",
                      "NASA Glenn Research Center, Earth Atmosphere Model（对流层标准大气近似）；",
                      "Hoerner S.F., Fluid-Dynamic Drag, 1965（圆球与回转体阻力）；",
                      "Schlichting H., Boundary Layer Theory（平板摩擦与粗糙度修正）；",
                      "Morrison F.A., Data Correlation for Drag Coefficient for Sphere, Michigan Technological University, 2013；",
                      "Khoury G.A.(ed.), Airship Technology, 2nd ed., Cambridge University Press, 2012；",
                      "Munk M.M., The Aerodynamic Forces on Airship Hulls, NACA Report No.184, 1924（回转体力矩）。"], numbered=True, size=11)
        self.heading(2, "1.5  单位与符号")
        self.para("力以 kgf 表示（1 kgf = 9.80665 N），括号内给出对应的 kN；质量 kg，长度 m，压强 Pa，温度 ℃，风速 m/s。"
                  "风力等级按离地 10 m 平均风速定义（蒲福风级）。符号见附录 C。")

    # ================================================================ 2 设计输入
    def chapter_inputs(self):
        inp, cable, req = self.inp, self.cable, self.req
        self.heading(1, "2  设计输入与设计条件")
        self.heading(2, "2.1  场地与环境条件")
        work_wind, surv_wind = inp.work_wind, inp.survival_wind or inp.work_wind
        mode = WIND_MODES[work_wind.mode] if 0 <= work_wind.mode < len(WIND_MODES) else str(work_wind.mode)
        wind_items = [("风速输入方式", mode, "—")]
        if work_wind.mode == 2:
            wind_items += [("工作风廓线（高度:风速）", self.u("WindTable") or "—", "m : m/s"),
                           ("生存风廓线（高度:风速）", self.u("SurvivalWindTable") or "（同工作风）", "m : m/s")]
        else:
            where = "离地 10 m" if work_wind.mode == 0 else "目标高度"
            wind_items += [(f"工作风速（{where}）", n(work_wind.speed_ref, 1), "m/s"),
                           (f"生存风速（{where}）", n(surv_wind.speed_ref, 1), "m/s")]
        wind_items += [("地面粗糙度", inp.terrain, "—"),
                       ("阵风系数", "自动（GB 50009，随高度变化）" if inp.gust_override is None else f"{inp.gust_override:g}（定值）", "—"),
                       ("自由大气湍流强度", n(inp.free_turbulence, 3), "—")]
        self.kv_table("场地、气象与风条件", [
            "场地与气温",
            ("场地海拔", n(inp.altitude, 0), "m"), ("目标高度（离地）", n(inp.target_height, 0), "m"),
            ("场地环境温度（实测）", n(inp.field_temp_c, 1), "℃"), ("昼夜温差", n(inp.temp_diff_c, 1), "℃"),
            ("滞空天数", n(inp.stay_days, 0), "天"), "风条件"] + wind_items)
        self.heading(2, "2.2  外形与几何参数")
        self.geometry_table()
        self.heading(2, "2.3  材料与重量清单")
        self.mass_table()
        self.heading(2, "2.4  气体与充装参数")
        self.kv_table("气体、充装与副气囊输入", [
            ("填充气体", inp.gas_type, "—"), ("气体纯度", n(inp.purity, 1), "%"), ("气体过热度（日照）", n(inp.superheat_k, 1), "K"),
            ("副气囊比例（占总容积）", n(inp.aux_ratio, 3), "—"),
            ("气体充盈度（输入）", n(inp.fill_fraction, 3) if inp.fill_fraction is not None else "自动（刚好充满）", "—"),
            ("滞空末期充盈度目标", n(inp.fill_end_target, 3) if inp.fill_end_target is not None else "未指定", "—"),
            ("充气时气温", n(inp.fill_temp_c, 1) if inp.fill_temp_c is not None else "自动（夜间最低温）", "℃"),
            ("氦气透氦率（逃逸率）", n(inp.leakage_rate, 4), "m³/(m²·天)"), ("纯度衰减", n(inp.purity_decay_per_day, 2), "%/天"),
            ("升降速度", n(inp.climb_speed, 2), "m/s")])
        self.heading(2, "2.5  系留缆绳")
        effective = cable.breaking_force_kn * cable.strength_factor
        self.kv_table("系留缆绳参数", [
            ("缆绳直径", n(cable.diameter_m * 1000, 1), "mm"), ("缆绳米重", n(cable.unit_weight_kg_m, 4), "kg/m"),
            ("缆绳风阻系数（横流）", n(cable.drag_coeff, 2), "—"),
            ("新缆最小破断力", force_text(cable.breaking_force_kn) if cable.breaking_force_kn > 0 else "未输入", "—"),
            ("强度折减系数（接头/老化）", n(cable.strength_factor, 2), "—"),
            ("有效强度", force_text(effective) if cable.breaking_force_kn > 0 else "—", "—")], widths=(5.8, 7.2, 3.0))
        self.heading(2, "2.6  校核准则")
        overpressure = ("自动（= k × 工作阵风动压）" if inp.overpressure_kpa is None else f"{inp.overpressure_kpa * 1000:.0f}")
        self.kv_table("校核准则与强度参数", [
            "要求值",
            ("缆绳安全系数 · 工作风", f"≥ {req.cable_sf:g}", "—"), ("缆绳/膜材/拉点安全系数 · 生存风", f"≥ {req.survival_sf:g}", "—"),
            ("膜材、拉点安全系数 · 工作风", f"≥ {req.film_sf:g}", "—"),
            ("锚点最小离地角", f"≥ {req.min_angle_deg:g}（0 表示仅要求缆绳不拖地）", "°"),
            ("运行超压要求", f"≥ {req.overpressure_k:g} × 阵风动压", "—"),
            "膜材与拉点",
            ("膜材抗拉强度（经纬向较小者）", n(inp.film_strength_n5cm, 0) if inp.film_strength_n5cm > 0 else "未输入", "N/5cm"),
            ("接缝效率", n(inp.seam_efficiency, 2), "—"), ("运行超压（内部恒定压强）", overpressure, "Pa"),
            ("拉点数量", f"{inp.pull_points}" if inp.pull_points > 0 else "未设", "个"),
            ("吊带半角", n(inp.bridle_half_angle_deg, 0), "°"), ("载荷不均系数", n(inp.load_nonuniformity, 2), "—"),
            ("拉点额定拉力", force_text(inp.pull_point_rating_kn) if inp.pull_point_rating_kn > 0 else "未输入", "—")],
            widths=(6.4, 6.6, 3.0))

    def geometry_table(self):
        shape, geo = self.geo["shape"], self.geo
        if self.is_sphere:
            items = ["外形", ("赤道直径 D", n(2 * shape["b"]), "m"), ("高径比", n(shape["a"] / shape["b"], 3), "—"),
                     ("竖向总高", n(2 * shape["a"]), "m"), ("开片数量", f"{shape['divide']}", "片"),
                     ("缝宽", self.u("SewWidth") or "—", "mm")]
            sail = self._sail_text()
            if sail:
                items.append(("帆配置", sail, "—"))
        else:
            length = shape["a1"] + shape["a2"]
            items = ["艇身", ("全长 L", n(length), "m"), ("最大直径 D", n(2 * shape["b"]), "m"),
                     ("长径比 L/D", n(length / (2 * shape["b"]), 2), "—"), ("最大截面距鼻端 a₁", n(shape["a1"]), "m"),
                     ("最大截面距尾端 a₂", n(shape["a2"]), "m"), ("开片数量", self.u("DivideNumber") or "—", "片"),
                     ("缝宽", self.u("SewWidth") or "—", "mm"),
                     "尾翼与攻角",
                     ("尾翼片数", f"{int(shape['fin_count'])}", "片"), ("单片翼展", n(shape["span"]), "m"),
                     ("单片平均弦长", n(shape["chord"]), "m"), ("尾翼总平面面积", n(shape["planform"]), "m²"),
                     ("尾翼相对厚度 t/c", n(shape["thickness"], 2), "—"), ("配平攻角", self.u("AoA") or "—", "°")]
        items += ["计算所得", ("囊体总容积 V", n(geo["volume"]), "m³"), ("表面积 S", n(geo["surface"]), "m²"),
                  ("迎风投影面积 A", n(geo["windward"]), "m²"), ("缝制面积", n(geo["sew"]), "m²")]
        self.kv_table("外形与几何参数", items)

    def _sail_text(self):
        for key, label in (("radio_PocketSail", "兜帆"), ("radio_WingSail", "翼帆")):
            if self.ui.get(key) is True:
                return label
        return ""

    def mass_table(self):
        total = self.res["mass_total_kg"]
        items = [(name, mass) for name, mass in self.geo["budget"] if mass > 1e-9]
        items.append(("副气囊膜材", self.gas["aux_mass"]))
        rows = [(name, n(mass), n(100 * mass / total, 1) if total > 0 else "—") for name, mass in items]
        rows.append(("合计（不含缆绳）", n(total), "100.0"))
        film_unit = self.u("FilmUnitWeight")
        self.table("重量清单", ["项目", "质量 / kg", "占比 / %"], rows, [8.0, 4.0, 4.0])
        details = []
        if film_unit:
            details.append(f"囊体膜材克重 {film_unit} kg/m²，副气囊膜材克重 {self.inp.aux_unit_weight:g} kg/m²")
        if not self.is_sphere:
            details.append("尾翼自重与尾翼浮力按相互抵消处理，均不计入")
        if details:
            self.note("说明：" + "；".join(details) + "。设备、绳组与拉点的明细见附录 A。")

    # ================================================================ 3 计算方法
    def chapter_methods(self):
        self.heading(1, "3  计算方法与模型")
        self.heading(2, "3.1  大气与浮力")
        self.para("以场地实测气温为基准，按对流层递减率 0.00649 ℃/m 推算任意海拔的环境温度；气压取标准大气，空气密度按理想气体状态方程计算。"
                  "气体的毛浮力为同体积空气与气体混合物的重量差。")
        self.equation("ρ_air = P(h) / (R·T)，R = 287 J/(kg·K)", "P(h) 为海拔 h 处的标准大气压，T 为环境热力学温度。")
        self.equation("L = V·(ρ_air − ρ_mix)，ρ_mix = p·ρ_gas + (1 − p)·ρ_air",
                      "V 为气体体积，p 为气体纯度（体积分数），杂质按同温空气计。毛浮力按质量当量（kg）给出，乘以 g 即为力。")
        self.equation("L = m_保留 · (1/m − 1)，m = p·μ + (1 − p)，μ = M_气体 / M_空气",
                      "囊体内的气体与环境同温同压时，浮力只与气体质量 m_保留 有关；目标高度氦气膨胀超过容积的部分被排出，m_保留 = min(充装质量, 目标高度最热时的容积上限质量)。")
        self.heading(2, "3.2  气体膨胀、充盈度与副气囊")
        self.para("囊体总容积不变，氦气质量不变。上升和升温时氦气膨胀，挤出副气囊内的空气；下降和降温时氦气收缩，由风机向副气囊补气。"
                  "设计取目标高度白天最热（含日照过热）时氦气体积不超过囊体总容积，副气囊容积须能容纳夜间最冷、滞空末期的最大空气量。")
        self.equation("Φ = V₂ / V₁ = (P_场地 / P_高空) · (T_气体,高空 / T_充装)")
        self.equation("充盈度 × Φ ≤ 1；副气囊比例 ≥ 1 − 充盈度",
                      "压力高度为氦气恰好充满囊体的离地高度，超过后开始排气，浮力不再增加。")
        self.heading(2, "3.3  风场与动压")
        self.para("采用 GB 50009-2012 的风压高度变化系数与阵风系数。风速剖面形状由地貌决定，梯度风高度以上取常数；动压中的空气密度按场地气温递减修正，"
                  "取夜间最低气温（密度最大，偏保守）。")
        self.equation("V(z) = V₁₀ · √μz(z)，μz(z) = c · (z / 10)^e")
        self.equation("β(z) = 1 + 2·g·I(z)，I(z) = I₁₀ · (z / 10)^(−α)，g = 2.5")
        self.equation("q(z) = ½ · ρ(z) · V(z)²",
                      "梯度风高度以上湍流强度在一倍梯度高度内平滑过渡到自由大气值。阵风动压 = β · q，用于缆绳峰值拉力与超压校核。")
        self.heading(2, "3.4  本体气动力与风阻系数")
        if self.is_sphere:
            self.para("球体风阻系数以大型系留气球的工程基准 CD = 0.47（Hoerner 亚临界圆球值）为底，叠加拉点、吊带、接缝等附件阻力增量与欠压变形增量；"
                      "不计光滑圆球在阻力危机雷诺数附近的降阻（该降阻对粗糙度、湍流和变形极敏感，不可靠）。")
        else:
            self.para("艇身零攻角阻力按 Hoerner 回转体公式计算：摩擦阻力取全湍流平板摩擦系数并按表面等效粗糙度修正，"
                      "压差阻力由长径比形状因子给出，再叠加附件与欠压变形增量；尾翼阻力与攻角诱导阻力另行计入，攻角升力由艇身与尾翼模型给出。")
        self.equation("D = q · Σ(C_D · S)；L_a = q · Σ(C_L · S)", "D 为本体风阻，L_a 为气动升力（飞艇配平攻角产生）。")
        self.heading(2, "3.5  系留缆绳平衡")
        self.para("自浮空器连接点向下沿缆长分段积分，每段计入缆绳自重与横流风阻，直至到达地面；φ 为缆绳局部与地面的夹角。"
                  "若积分过程中垂向拉力降为零，说明浮力不足以托起缆绳，缆绳拖地。")
        self.equation("dTₓ/ds = q(z)·C_dc·d·sin³φ")
        self.equation("dT_z/ds = −w − q(z)·C_dc·d·sin²φ·cosφ", "Tₓ、T_z 为缆绳水平、垂向拉力，w 为缆绳单位长度重量，C_dc 为缆绳横流风阻系数，d 为缆径。")
        self.para("生存风下缆长保持工作风平衡时的长度不变，浮空器被风压低到缆长刚好够到的高度，此后的风压、阵风与拉力均按该高度计算。")
        self.heading(2, "3.6  强度校核")
        self.equation("n_c = η_c · F_b / T_peak", "缆绳安全系数：F_b 为新缆破断力，η_c 为强度折减，T_peak 为阵风下缆绳最大拉力（取顶端与锚点较大者）。")
        self.equation("Δp ≥ k · β · q", "运行超压须不小于超压系数 k 乘阵风动压，否则迎风面凹陷。")
        self.equation("N = Δp · R / 2（球）；N_φ = Δp·R₂/2，N_θ = N_φ·(2 − R₂/R₁)（回转椭球）",
                      "薄膜理论：R₁、R₂ 为子午向与平行圆向曲率半径；回转椭球取各点较大的拉力合力。")
        self.equation("n_f = σ_b · η_s / N", "膜材安全系数：σ_b 为膜材抗拉强度（折算到每米宽），η_s 为接缝效率。")
        self.equation("P = T_peak · K / (n · cosθ)；n_p = P_rated / P", "拉点单点载荷：K 为载荷不均系数，n 为拉点数，θ 为吊带半角。")
        self.heading(2, "3.7  最大允许风速")
        self.para("保持风速剖面形状不变，对工作风整体缩放，二分搜索满足全部工作风校核（缆绳不拖地、锚点夹角、缆绳/膜材/拉点安全系数、运行超压）的最大风速，"
                  "同时给出离地 10 m 与目标高度两个对应值。")

    # ================================================================ 4 结果
    def chapter_results(self):
        self.heading(1, "4  计算结果与分析")
        self.result_geometry()
        self.result_gas()
        self.result_balance()
        self.result_wind()
        self.result_drag()
        self.result_tether()
        self.result_checks()
        self.result_max_wind()
        number = 9
        if self.options.get("sensitivity", True) and self.ctx.get("sensitivity"):
            self.result_sensitivity(number)
            number += 1
        if self.images.get("sweep"):
            self.result_sweep(number)

    def result_geometry(self):
        self.heading(2, "4.1  外形与几何")
        shape = self.geo["shape"]
        gas = self.gas
        self.para(f"{self.name}囊体总容积 {self.geo['volume']:.2f} m³，表面积 {self.geo['surface']:.2f} m²，迎风投影面积 {self.geo['windward']:.2f} m²。"
                  f"副气囊比例 {self.inp.aux_ratio:.3f}，副气囊容积 {gas['aux_volume']:.2f} m³、隔层高 {gas['aux_height']:.2f} m、"
                  f"膜面积 {gas['aux_area']:.2f} m²、质量 {gas['aux_mass']:.2f} kg，主气囊（氦气）容积 {self.geo['volume'] - gas['aux_volume']:.2f} m³。")
        if not self.figure("shape", "外形与副气囊示意"):
            self.note("（外形示意图未生成）")
        if not self.is_sphere:
            tail = [("尾翼总平面面积", self.u("FinPlanform"), "m²"), ("尾翼总面积 / V^(2/3)", self.u("FinAreaRatio"), "—"),
                    ("尾翼几何体积（估算，不计入浮力）", self.u("FinVolumeGeo"), "m³"), ("采用的尾翼阻力系数", self.u("TailDragUsed"), "—"),
                    ("采用的升力线斜率 CLα", self.u("CLAlphaUsed"), "/rad"), ("尾翼/Munk 力矩比", self.u("StabilityMargin"), "—"),
                    ("工作风气动升力", self.u("AeroLift"), "kgf")]
            tail = [(a, b or "—", c) for a, b, c in tail]
            self.kv_table("尾翼与气动稳定性", tail)

    def result_gas(self):
        gas, inp = self.gas, self.inp
        self.heading(2, "4.2  气体状态、充盈度与浮力")
        self.kv_table("气体状态与浮力", [
            "充盈度与压力高度",
            ("实际初始充盈度", n(gas["fill_fraction"], 3), "—"), ("初始充气体积", n(gas["initial_gas_volume"]), "m³"),
            ("气体膨胀比 Φ（场地→目标高度最热）", n(gas["expansion_ratio"], 3), "—"),
            ("目标高度氦气充盈度（白天最热）", n(gas["fill_target_raw"], 3), "—"), ("建议充盈度", n(gas["fill_recommended"], 3), "—"),
            ("滞空末期充盈度（地面）", n(gas["fill_end"], 3), "—"), ("滞空末期目标高度充盈度", n(gas["fill_target_end_raw"], 3), "—"),
            ("压力高度（离地）", n(gas["pressure_height"], 0), "m"), ("目标高度白天最高气温", n(gas["t_target_hot_c"], 1), "℃"),
            "逃逸与副气囊空气量",
            ("滞空期间氦气逸出体积", n(gas["leak_volume"], 3), "m³"), ("末期气体纯度", n(gas["purity_end"], 1), "%"),
            ("夜间副气囊最大空气量", n(gas["aux_air_cold"]), "m³"), ("目标高度副气囊空气量", n(gas["aux_air_target"]), "m³"),
            ("升降换气量", n(gas["aux_exchange"]), "m³"), ("换气流量", n(gas["aux_flow_m3_min"]), "m³/min"),
            "浮力",
            ("场地总浮升力（地面，满容积）", n(gas["field_total_lift_kg"], 1), "kgf"), ("海拔损耗", n(gas["altitude_loss_kg"], 1), "kgf"),
            ("目标高度毛浮力 · 初期", n(gas["lift_start_kg"], 1), "kgf"), ("目标高度毛浮力 · 滞空末期", n(gas["lift_end_kg"], 1), "kgf"),
            ("设计取值（" + ("滞空末期" if inp.stay_days > 0 else "初期") + "）", n(gas["lift_governing_kg"], 1), "kgf")])
        self.para("氦气浮力只取决于氦气质量（质量守恒），目标高度的气压和气温只通过“超容排气”影响浮力。因此毛浮力由场地满充浮力出发，"
                  "依次扣除未充满的容积、修正充装温度、扣除高温膨胀排出的氦气，滞空时再扣除逸出与纯度衰减，逐项见下表。"
                  "尾翼自重与尾翼浮力按相互抵消处理，均不计入。")
        notes = {"fill": f"初始充盈度 {gas['fill_fraction']:.3f}，未充氦气的容积没有浮力",
                 "fill_temp": "充装时气温与场地环境温度之差改变充入的氦气质量",
                 "vent": f"目标高度白天最热时氦气体积为总容积的 {gas['fill_target_raw']:.3f} 倍（>1 时多余部分排出）",
                 "leak": f"滞空 {inp.stay_days:g} 天，逸出 {gas['leak_volume']:.3f} m³", "purity": f"纯度 {inp.purity:g}% → {gas['purity_end']:.1f}%"}
        level = gas["field_total_lift_kg"]
        rows = [("场地总浮升力（满容积）", "—", n(level, 1), "总容积全充氦气，场地海拔、场地气温")]
        for key, label, delta in gas["lift_steps"]:
            level += delta
            rows.append((label, f"{delta:+.1f}", n(level, 1), notes.get(key, "")))
        rows.append(("毛浮力（设计取值）", "—", n(gas["lift_governing_kg"], 1), "滞空末期" if inp.stay_days > 0 else "初期"))
        self.table("毛浮力构成（逐项修正，kgf）", ["项目", "变化量", "累计", "说明"], rows, [4.2, 2.0, 2.2, 7.6], ["l", "c", "c", "l"], size=9.5)
        self.volume_states_block()
        text = (f"目标高度白天最热时氦气体积为总容积的 {gas['fill_target_raw']:.3f} 倍"
                + ("，未超出囊体容积。" if gas["fill_target_raw"] <= 1.0 + 1e-9 else "，超出囊体容积，设计不可行。")
                + (f" 滞空 {inp.stay_days:g} 天，氦气逸出 {gas['leak_volume']:.3f} m³，毛浮力由 {gas['lift_start_kg']:.1f} kgf 降至 "
                   f"{gas['lift_end_kg']:.1f} kgf，设计以滞空末期为准。" if inp.stay_days > 0 else ""))
        self.para(text)
        for item in list(gas["alarms"]) + list(gas["warnings"]):
            self.para("注意：" + item, indent=False, size=11, color=ORANGE)

    def volume_states_block(self):
        gas = self.gas
        self.para("囊体总容积不变。海拔升高（气压降低）、气温升高使氦气体积膨胀，充盈度随之升高，副气囊内的空气被挤出，空气体积 = 总容积 − 氦气体积；"
                  "下降、降温和逸出时则相反，由风机向副气囊补气。氦气质量不变时浮力不变，只有氦气膨胀到充满囊体、被迫排出时才损失浮力。"
                  "下表为各工况的体积分配，副气囊须能容纳其中最大的空气量。")
        capacity = gas["aux_volume"]
        rows = [(s["label"], n(s["helium"]), n(s["air"]), n(s["fill"], 3),
                 f"{100 * s['air'] / capacity:.0f}%" if capacity > 0 else "—", "合格" if s["fits"] else "不合格")
                for s in gas["volume_states"]]
        self.table(f"氦气与副气囊体积随工况变化（总容积 {self.geo['volume']:.1f} m³，副气囊容积 {capacity:.1f} m³）",
                   ["工况", "氦气体积 m³", "副气囊空气 m³", "氦气充盈度", "空气 / 副气囊容积", "副气囊能否容纳"], rows,
                   [4.6, 2.2, 2.4, 2.0, 2.6, 2.2], size=9.5)
        self.figure("volume", "氦气与副气囊体积随工况的变化")

    def result_balance(self):
        self.heading(2, "4.3  浮力与重量平衡")
        mean = self.work["mean"]
        self.para(f"目标高度毛浮力 {self.gas['lift_governing_kg']:.1f} kgf，扣除系统总重 {self.res['mass_total_kg']:.1f} kg 后，静净浮力 "
                  f"{self.res['static_net_kg']:.1f} kgf（占毛浮力 {100 * self.res['static_net_kg'] / self.gas['lift_governing_kg']:.1f}%）"
                  if self.gas["lift_governing_kg"] > 0 else "目标高度毛浮力为零。")
        if mean["flyable"]:
            self.para(f"工作风下缆绳自重 {kn_to_kg(mean['cable_weight']):.1f} kg、气动升力 {n(kgf(self.work['aero_lift']), 1)} kgf，"
                      f"锚点处净浮力 {kn_to_kg(mean['net_buoyancy']):.1f} kgf。")
        if not self.figure("budget", "浮力与重量平衡（瀑布图）"):
            self.note("（浮力与重量图未生成）")

    def result_wind(self):
        self.heading(2, "4.4  风环境")
        w, s = self.work["wind"], self.surv["wind"]
        self.table("工作风与生存风条件", ["项目", "工作风", "生存风"], [
            ("离地 10 m 平均风速 / m·s⁻¹", n(w["speed_10"], 1), n(s["speed_10"], 1)),
            ("蒲福风级（按 10 m 风速）", beaufort_text(w["speed_10"]), beaufort_text(s["speed_10"])),
            ("浮空器所在高度 / m", n(self.work["height"], 0), n(self.surv["height"], 0) + ("（被压低）" if self.surv["blown_down"] else "")),
            ("该高度平均风速 / m·s⁻¹", n(w["speed_target"], 1), n(s["speed_target"], 1)),
            ("该高度动压 q / Pa", n(w["pressure_target_kpa"] * 1000, 1), n(s["pressure_target_kpa"] * 1000, 1)),
            ("阵风系数 β", n(w["gust_target"], 2), n(s["gust_target"], 2)),
            ("阵风动压 β·q / Pa", n(w["pressure_target_kpa"] * w["gust_target"] * 1000, 1), n(s["pressure_target_kpa"] * s["gust_target"] * 1000, 1))],
            [6.0, 5.0, 5.0], ["l", "c", "c"])
        if self.surv["blown_down"]:
            self.para(f"生存风下缆长固定，浮空器被压低至 {self.surv['height']:.0f} m（目标高度 {self.inp.target_height:.0f} m）。")
        if not self.figure("wind", "风速廓线与风级"):
            self.note("（风廓线图未生成）")

    def result_drag(self):
        self.heading(2, "4.5  本体气动力")
        drag = self.drag
        if drag:
            result = drag["result"]
            used = drag["used"]
            rows = [(component.name, n(component.value, 3), component.basis) for component in result.components]
            rows.append(("合计（模型）", n(result.cd, 3), f"合理范围 {result.low:.3f} ～ {result.high:.3f}"))
            self.table("风阻系数构成", ["分项", "系数", "依据"], rows, [3.6, 2.0, 10.4], ["l", "c", "l"], size=9)
            how = "手动输入" if drag.get("manual") is not None else "自动选型"
            self.para(f"计算采用的本体风阻系数 CD = {used:.3f}（{how}），雷诺数 Re = {result.reynolds:.2e}，流态：{result.regime}。"
                      f"设计风速 {drag['speed']:.1f} m/s、空气密度 {drag['density']:.3f} kg/m³、气温 {drag['temp']:.1f} ℃。")
            for item in result.notes:
                self.para("注意：" + item, indent=False, size=11, color=ORANGE)
        work = self.work
        rows = [("总阻力面积 ΣCD·S", f"{self.inp.drag_area:.3f} m²"), ("工作风本体风阻", force_text(work["body_drag"])),
                ("工作风气动升力", force_text(work["aero_lift"]))]
        self.kv_table("本体气动力（工作风）", [(a, b, "—") for a, b in rows], widths=(6.4, 6.6, 3.0))

    def result_tether(self):
        self.heading(2, "4.6  系留状态与缆绳受力")
        w, s = self.work, self.surv
        wm, sm = w["mean"], s["mean"]

        def col(case, key, factor=1.0, digits=1, only_flyable=True):
            mean = case["mean"]
            if only_flyable and not mean["flyable"]:
                return "拖地"
            value = mean[key]
            return n(value * factor, digits)

        rows = [
            ("缆绳状态", "悬空" if wm["flyable"] else "拖地", "悬空" if sm["flyable"] else "拖地（仅提示）"),
            ("浮空器高度 / m", n(w["height"], 0), n(s["height"], 0)),
            ("缆绳悬空长度 / m", col(w, "cable_length", digits=1), col(s, "cable_length", digits=1)),
            ("向下风水平漂移 / m", col(w, "drift"), col(s, "drift")),
            ("锚点悬链角 / °", col(w, "angle_deg"), col(s, "angle_deg")),
            ("缆绳顶端夹角 / °", n(wm["top_angle_deg"], 1), n(sm["top_angle_deg"], 1)),
            ("本体风阻 / kgf", n(kgf(w["body_drag"]), 1), n(kgf(s["body_drag"]), 1)),
            ("缆绳风阻（水平分量）/ kgf", col(w, "cable_drag_h", KGF_PER_KN), col(s, "cable_drag_h", KGF_PER_KN)),
            ("总水平力 / kgf", col(w, "horizontal", KGF_PER_KN), col(s, "horizontal", KGF_PER_KN)),
            ("缆绳自重 / kg", n(kn_to_kg(wm["cable_weight"]), 1) if wm["flyable"] else "拖地",
             n(kn_to_kg(sm["cable_weight"]), 1) if sm["flyable"] else "拖地"),
            ("缆绳顶端拉力（平均风）/ kgf", n(kgf(wm["tension"]), 1), n(kgf(sm["tension"]), 1)),
            ("锚点拉力（平均风）/ kgf", col(w, "anchor_tension", KGF_PER_KN), col(s, "anchor_tension", KGF_PER_KN)),
            ("阵风峰值拉力 / kgf", n(kgf(w["peak_tension"]), 1), n(kgf(s["peak_tension"]), 1)),
            ("锚点处净浮力 / kgf", n(kn_to_kg(wm["net_buoyancy"]), 1) if wm["flyable"] else "拖地",
             n(kn_to_kg(sm["net_buoyancy"]), 1) if sm["flyable"] else "拖地")]
        self.table("系留状态与缆绳受力", ["项目", "工作风", "生存风"], rows, [6.4, 4.8, 4.8], ["l", "c", "c"])
        if not self.figure("tether", "系留姿态与受力（侧视，工作风/生存风）"):
            self.note("（受力与姿态图未生成）")
        for text in w["warnings"]:
            self.para("注意（工作风）：" + text, indent=False, size=11, color=ORANGE)
        for text in s["warnings"]:
            self.para("注意（生存风）：" + text, indent=False, size=11, color=ORANGE)

    def result_checks(self):
        self.heading(2, "4.7  强度校核")
        w, s, req, inp = self.work, self.surv, self.req, self.inp
        rows = ["工作风"]
        rows += self._check_rows(w, req.cable_sf, req.film_sf, True)
        rows.append("生存风")
        rows += self._check_rows(s, req.survival_sf, req.survival_sf, False)
        self.table("强度与稳定性校核汇总", ["校核项", "计算值", "要求值", "判定"], rows, [5.8, 4.4, 3.6, 2.2], ["l", "c", "c", "c"])
        film = w["film"]
        if film["stress"] is not None:
            self.para(f"膜材：运行超压 {film['operating_kpa'] * 1000:.0f} Pa 下膜应力 {film['stress'] * 50:.1f} N/5cm"
                      + (f"，折减后的膜材有效强度 {film['strength'] * 50:.1f} N/5cm。" if film["strength"] is not None else "；未输入膜材强度，未校核安全系数。"))
        ok, text = self.overall()
        self.para(f"校核结论：{text}。", bold=True, color=GREEN if ok else RED)

    def _check_rows(self, case, sf_cable, sf_film, working):
        mean, film, pull, req, cable = case["mean"], case["film"], case["pull"], self.req, self.cable
        rows = []
        if working:
            rows.append(("缆绳不拖地", "悬空" if mean["flyable"] else "拖地", "悬空", "合格" if mean["flyable"] else "不合格"))
            if req.min_angle_deg > 0:
                rows.append(("锚点离地角", f"{n(mean['angle_deg'], 1)}°" if mean["flyable"] else "—", f"≥ {req.min_angle_deg:g}°",
                             "合格" if self._angle_ok() else "不合格"))
        else:
            rows.append(("缆绳不拖地（仅提示）", "悬空" if mean["flyable"] else "拖地", "—", "合格" if mean["flyable"] else "提示"))
        rows.append(("阵风峰值缆绳拉力", force_text(case["peak_tension"]), f"有效强度 {force_text(cable.breaking_force_kn * cable.strength_factor, 0)}"
                     if cable.breaking_force_kn > 0 else "—", "—"))
        rows.append(("缆绳安全系数", n(case["cable_sf"]), f"≥ {sf_cable:g}", verdict_of(case["cable_sf"], sf_cable)))
        if film["operating_kpa"] is not None:
            rows.append(("运行超压", f"{film['operating_kpa'] * 1000:.0f} Pa", f"≥ {film['required_kpa'] * 1000:.0f} Pa",
                         "合格" if film["operating_kpa"] + 1e-12 >= film["required_kpa"] else ("不合格" if working else "提示")))
        rows.append(("膜材安全系数", n(film["sf"]), f"≥ {sf_film:g}", verdict_of(film["sf"], sf_film)))
        rows.append(("拉点单点载荷", force_text(pull["load"]) if pull["load"] is not None else "未设拉点", "—", "—"))
        rows.append(("拉点安全系数", n(pull["sf"]), f"≥ {sf_film:g}", verdict_of(pull["sf"], sf_film) if pull["load"] is not None else "未校核"))
        return rows

    def result_max_wind(self):
        self.heading(2, "4.8  最大允许风速")
        mw = self.maxw
        if self.gas["alarms"]:
            self.para("存在充盈度或副气囊报警，最大允许风速无效，请先解决报警。")
            return
        if mw["scale"] <= 0:
            self.para("静风下即不满足工作风校核（浮力不足或超压不足），没有允许风速。", color=RED)
            return
        prefix = "不低于 " if mw["unbounded"] else ""
        self.para(f"满足工作风全部校核的最大允许风速：离地 10 m 处 {prefix}{mw['speed_10']:.1f} m/s（{beaufort_text(mw['speed_10'])}），"
                  f"目标高度处 {prefix}{mw['speed_target']:.1f} m/s。当前工作风离地 10 m 风速为 {self.work['wind']['speed_10']:.1f} m/s，"
                  f"风速裕度 {100 * (mw['scale'] - 1):.0f}%。" + ("" if mw["scale"] >= 1.0 else "最大允许风速低于设定工作风，工作风校核不通过。"))

    def result_sensitivity(self, number):
        rows = self.ctx["sensitivity"]
        self.heading(2, f"4.{number}  风速敏感性分析")
        self.para("保持风速剖面形状不变，将工作风按离地 10 m 风速逐点缩放，计算缆绳拉力、安全系数、净浮力、漂移与锚点角的变化，用于判断设计对风速的敏感程度与裕度。")
        self.figure("sensitivity", "风速敏感性分析曲线", 16.0)
        picks = rows if len(rows) <= 9 else [rows[round(i * (len(rows) - 1) / 8)] for i in range(9)]
        table_rows = []
        for r in picks:
            table_rows.append((n(r["speed_10"], 1), str(beaufort_level(r["speed_10"])), n(kgf(r["tension"]), 0), n(kgf(r["peak_tension"]), 0),
                               n(r["cable_sf"]), n(r["net_buoyancy"], 0), n(r["drift"], 0), "合格" if r["ok"] else "不合格"))
        self.table("风速敏感性数据", ["10 m 风速 m/s", "风级", "顶端拉力 kgf", "峰值拉力 kgf", "缆绳安全系数", "锚点净浮力 kgf", "漂移 m", "判定"],
                   table_rows, [2.0, 1.2, 2.1, 2.1, 2.1, 2.4, 1.6, 2.5], size=9)
        failing = next((r for r in rows if not r["ok"]), None)
        if failing is not None and failing["speed_10"] > 0:
            self.para(f"在计算范围内，离地 10 m 风速达到 {failing['speed_10']:.1f} m/s 附近时校核开始不通过。")

    def result_sweep(self, number):
        self.heading(2, f"4.{number}  设计选型曲线")
        self.para(f"依次改变{'直径' if self.is_sphere else '长度'}并完整计算，得到不同尺寸下的合格情况、最大允许风速、缆绳安全系数与浮力。")
        self.figure("sweep", "设计尺寸选型曲线", 16.0)

    # ================================================================ 5 结论
    def chapter_conclusion(self):
        self.heading(1, "5  结论与建议")
        self.heading(2, "5.1  结论")
        ok, text = self.overall()
        mean = self.work["mean"]
        items = [f"总体结论：{text}。",
                 f"浮力：目标高度毛浮力 {self.gas['lift_governing_kg']:.1f} kgf，系统总重 {self.res['mass_total_kg']:.1f} kg，静净浮力 {self.res['static_net_kg']:.1f} kgf"
                 + ("（浮力富余）" if self.res["static_net_kg"] > 0 else "（超重）") + "。"]
        if mean["flyable"]:
            items.append(f"工作风下缆绳悬空，锚点悬链角 {mean['angle_deg']:.1f}°，漂移 {mean['drift']:.0f} m，阵风峰值拉力 {force_text(self.work['peak_tension'])}。")
        else:
            items.append("工作风下缆绳拖地，设计不成立。")
        margins = [("缆绳·工作", self.work["cable_sf"], self.req.cable_sf), ("缆绳·生存", self.surv["cable_sf"], self.req.survival_sf),
                   ("膜材·工作", self.work["film"]["sf"], self.req.film_sf), ("膜材·生存", self.surv["film"]["sf"], self.req.survival_sf)]
        checked = [(label, value / required) for label, value, required in margins if value is not None]
        if checked:
            label, ratio = min(checked, key=lambda item: item[1])
            items.append(f"强度裕度：最薄弱环节为“{label}”，安全系数为要求值的 {ratio:.2f} 倍。")
        if self.maxw["scale"] > 0:
            items.append(f"最大允许风速：离地 10 m {self.maxw['speed_10']:.1f} m/s（{beaufort_level(self.maxw['speed_10'])} 级），"
                         f"为设定工作风的 {self.maxw['scale']:.2f} 倍。")
        self.bullets(items, numbered=True)
        self.heading(2, "5.2  风险提示")
        notes = list(self.gas["alarms"]) + list(self.gas["warnings"]) + list(self.work["warnings"]) + [f"生存风：{t}" for t in self.surv["warnings"]]
        if self.inp.film_strength_n5cm <= 0:
            notes.append("未输入膜材抗拉强度，膜材与拉点的强度未校核。")
        if self.cable.breaking_force_kn <= 0:
            notes.append("未输入缆绳破断力，缆绳安全系数未校核。")
        self.bullets(notes or ["计算过程中没有产生风险提示。"])
        self.heading(2, "5.3  建议")
        self.bullets(self.suggestions(ok))

    def suggestions(self, ok):
        advice = []
        failures = list(self.work["failures"]) + [f"生存风：{t}" for t in self.surv["failures"]] + list(self.gas["alarms"])
        keyed = [("超重", "减轻重量（客户负载、附件设备、膜材克重）或增大囊体容积；也可降低目标高度。"),
                 ("拖地", "增加静净浮力：增大囊体容积、减轻重量、提高氦气纯度，或降低目标高度与工作风速要求。"),
                 ("缆绳安全系数", "选用更高破断力的缆绳，或减小缆绳直径以降低横流风阻；必要时降低工作/生存风速要求。"),
                 ("膜材安全系数", "选用更高强度的膜材、提高接缝效率，或在满足超压要求的前提下降低运行超压。"),
                 ("拉点安全系数", "增加拉点数量、提高单点额定拉力、减小吊带半角或降低载荷不均系数。"),
                 ("超压", "提高内部恒定压强（副气囊风机能力），或降低风速要求。"),
                 ("锚点夹角", "增加净浮力或降低风阻（减小迎风面积、优化外形），以抬高缆绳底部离地角。"),
                 ("充盈度", "降低充盈度、增大副气囊比例，或降低目标高度、减小昼夜温差与日照过热。")]
        for key, text in keyed:
            if any(key in item for item in failures):
                advice.append(text)
        if self.maxw["scale"] > 0 and self.maxw["scale"] < 1.0:
            advice.append("最大允许风速低于设定工作风速：应降低工作风速要求，或按上述措施提高浮力与缆绳强度。")
        if ok:
            advice.append("设计满足全部校核。建议按最大允许风速制定运行风速红线，并对缆绳、膜材做定期检查与强度复核。")
            if self.maxw["scale"] > 0 and self.maxw["scale"] < 1.15:
                advice.append("风速裕度较小，建议留出更大安全余量或采用更保守的工作风输入。")
        advice.append("本报告基于工程简化模型与所列输入；风阻系数、阵风与湍流参数宜用风洞/现场试验或站点实测数据校准后再用于最终定型。")
        return advice

    # ================================================================ 附录
    def appendices(self):
        self.page_break()
        self.heading(1, "附录 A  输入与结果参数清单")
        self.para("下列数据取自计算界面（含输入与实时结果），按界面分组列出。", indent=False)
        groups = self.ctx.get("input_groups") or []
        for title, items in groups:
            rows = []
            for name, value, unit in items:
                if name == "###SUBTITLE###":
                    rows.append(value)
                else:
                    rows.append((name, value if value != "" else "—", unit))
            if rows:
                self.heading(3, title)
                self.kv_table(f"{title}", rows, widths=(6.4, 6.0, 3.6))
        self.heading(1, "附录 B  假设与适用范围")
        self.bullets(["风速剖面、阵风系数按 GB 50009-2012 的地貌参数；梯度风高度以上的自由大气湍流强度为工程假设，需用站点实测数据校准。",
                      "升力取白天最高气温（含日照过热），风压取夜间最低气温（空气密度最大），二者组合偏保守；气体升力不计过热增益。",
                      "球体风阻系数不计阻力危机降阻；飞艇艇身按全湍流计算，不计层流段减阻。附件、欠压变形增量为工程假设值，风洞或试验数据始终优先。",
                      "缆绳按准静态分段平衡求解，不计缆绳振动、涡激与浮空器的动态响应；阵风按峰值动压（阵风系数 × 平均动压）等效。",
                      "膜应力采用薄膜理论，不计接缝、拉点处的应力集中，由接缝效率与载荷不均系数近似；氦气只考虑逸出与排出，不考虑补气。",
                      "生存风工况假定缆长不变，浮空器被风压低至缆长刚好够到的高度。",
                      "所有结果均为设计计算值，不能替代系留系统的试验验证、检验与相关法规要求。"], size=11)
        self.heading(1, "附录 C  符号说明")
        self.table("主要符号", ["符号", "含义", "单位"], [
            ("V", "囊体总容积 / 气体体积", "m³"), ("S", "表面积 / 参考面积", "m²"), ("ρ", "空气密度", "kg/m³"),
            ("L", "毛浮力（质量当量）", "kgf"), ("Φ", "气体膨胀比", "—"), ("p", "气体纯度", "—"),
            ("V₁₀", "离地 10 m 平均风速", "m/s"), ("V(z)", "高度 z 处平均风速", "m/s"), ("μz", "风压高度变化系数", "—"),
            ("β", "阵风系数", "—"), ("q", "动压 ½ρV²", "Pa"), ("C_D", "本体风阻系数", "—"),
            ("C_dc", "缆绳横流风阻系数", "—"), ("T", "缆绳拉力", "kgf"), ("n_c / n_f / n_p", "缆绳 / 膜材 / 拉点安全系数", "—"),
            ("Δp", "运行超压（囊内外压差）", "Pa"), ("N", "膜应力合力（每米宽）", "N/m"), ("k", "超压系数", "—")],
            [3.0, 10.0, 3.0], ["c", "l", "c"])


def _borders_paragraph(paragraph):
    properties = paragraph._p.get_or_add_pPr()
    border = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    for key, value in (("val", "single"), ("sz", "6"), ("space", "1"), ("color", "999999")):
        bottom.set(qn(f"w:{key}"), value)
    border.append(bottom)
    properties.insert_element_before(
        border, "w:shd", "w:tabs", "w:suppressAutoHyphens", "w:kinsoku", "w:wordWrap", "w:overflowPunct",
        "w:topLinePunct", "w:autoSpaceDE", "w:autoSpaceDN", "w:bidi", "w:adjustRightInd", "w:snapToGrid", "w:spacing",
        "w:ind", "w:contextualSpacing", "w:mirrorIndents", "w:suppressOverlap", "w:jc", "w:textDirection",
        "w:textAlignment", "w:textboxTightWrap", "w:outlineLvl", "w:divId", "w:cnfStyle", "w:rPr", "w:sectPr",
        "w:pPrChange")


def generate(path, ctx):
    """生成 Word 报告并保存到 path，返回 path。"""
    report = Report(ctx)
    report.build().save(path)
    return path
