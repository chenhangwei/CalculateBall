"""计算数据文件：把一个计算页（气球/飞艇）的全部输入保存成 UTF-8 文本（内容为 JSON，默认扩展名 .txt），并可再次读回。

文件是文本，可用记事本查看；"summary" 节只供人阅读，读回时忽略，结果由程序按输入重新计算。
本模块与界面无关，页面控件的采集与回填见 page_state.py。
"""
import datetime
import json

FORMAT = "AerostatDesignData"
VERSION = 1
KINDS = ("Sphere", "AirShip")
KIND_NAMES = {"Sphere": "系留气球", "AirShip": "系留飞艇"}


class DataFileError(ValueError):
    """数据文件无法识别或内容不合法（消息可直接显示给用户）。"""


def build_payload(kind, inputs, state=None, summary=None, report_info=None, saved_at=None):
    if kind not in KINDS:
        raise DataFileError(f"未知的数据类型：{kind}")
    return {
        "format": FORMAT,
        "version": VERSION,
        "kind": kind,
        "kind_name": KIND_NAMES[kind],
        "saved_at": saved_at or datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "inputs": dict(inputs),
        "state": dict(state or {}),
        "report_info": dict(report_info or {}),
        "summary": dict(summary or {}),
    }


def dumps(payload):
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def loads(text):
    """解析并校验数据文件文本，返回 payload；不合法时抛 DataFileError。"""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise DataFileError(f"不是有效的计算数据文件（{error.msg}，第 {error.lineno} 行）") from error
    if not isinstance(payload, dict) or payload.get("format") != FORMAT:
        raise DataFileError("不是本程序保存的计算数据文件")
    version = payload.get("version")
    if not isinstance(version, int) or version > VERSION:
        raise DataFileError(f"数据文件版本 {version} 高于本程序支持的版本 {VERSION}，请升级程序后再打开")
    if payload.get("kind") not in KINDS:
        raise DataFileError(f"数据文件的类型无法识别：{payload.get('kind')!r}")
    inputs = payload.get("inputs")
    if not isinstance(inputs, dict):
        raise DataFileError("数据文件缺少输入数据")
    for key, value in inputs.items():
        if not isinstance(value, (str, bool)):
            raise DataFileError(f"输入项 {key} 的值类型不合法")
    for section in ("state", "report_info", "summary"):
        if not isinstance(payload.get(section, {}), dict):
            raise DataFileError(f"数据文件的 {section} 节格式不合法")
    return payload


def write_file(path, payload):
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(dumps(payload))


def read_file(path):
    with open(path, "rb") as handle:
        raw = handle.read()
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return loads(raw.decode(encoding))
        except UnicodeDecodeError:
            continue
    raise DataFileError("无法识别文件编码，请确认是本程序保存的数据文件")
