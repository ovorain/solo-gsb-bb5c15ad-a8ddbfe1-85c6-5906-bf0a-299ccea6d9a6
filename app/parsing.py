"""文本归一化与输入解析（对白稿 / SRT 字幕）。"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_TAG_RE = re.compile(r"<[^>]+>")          # <i> <font ...> 等 HTML 标签
_ASS_RE = re.compile(r"\{[^}]*\}")        # {\an8} 等 ASS 覆盖标签
_TIME_RE = re.compile(
    r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})"
    r"\s*-->\s*"
    r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})"
)
_BLANK_BLOCK_RE = re.compile(r"\n[ \t]*\n")


def normalize(text: str) -> str:
    """归一化用于匹配的文本：NFKC 归一后去掉空白与标点，英文字母转小写。

    去除 Unicode 类别为 P*（标点）、Z*（分隔符/空白）、C*（控制符）的字符，
    其余字符（含中文、字母、数字）保留。
    """
    text = unicodedata.normalize("NFKC", text)
    chars = []
    for ch in text:
        if unicodedata.category(ch)[0] in ("P", "Z", "C"):
            continue
        chars.append(ch.lower())
    return "".join(chars)


@dataclass
class ScriptItem:
    line_no: int          # 原始行号（从 1 开始，含空行）
    text: str             # 原文（已去首尾空白）
    norm: str             # 归一化文本


@dataclass
class SrtItem:
    index: int            # 字幕序号（按解析顺序重新编号）
    start: str            # 开始时间码 HH:MM:SS,mmm
    end: str              # 结束时间码 HH:MM:SS,mmm
    text: str             # 原文（可能多行）
    norm: str             # 归一化文本


def parse_script(text: str) -> list[ScriptItem]:
    """逐行对白稿：每个非空行为一条。"""
    items: list[ScriptItem] = []
    for lineno, raw in enumerate(text.splitlines(), 1):
        t = raw.strip()
        if not t:
            continue
        items.append(ScriptItem(line_no=lineno, text=t, norm=normalize(t)))
    return items


def _clean_srt_text(raw: str) -> str:
    t = _TAG_RE.sub("", raw)
    t = _ASS_RE.sub("", t)
    return t


def _fmt_time(h: str, m: str, s: str, ms: str) -> str:
    return f"{int(h):02d}:{m}:{s},{ms.ljust(3, '0')[:3]}"


def parse_srt(text: str) -> list[SrtItem]:
    """解析 SRT：按空行分块，定位时间码行，保留时间码与（可能多行的）文本。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    items: list[SrtItem] = []
    for block in _BLANK_BLOCK_RE.split(text.strip()):
        lines = block.split("\n")
        time_at = None
        match = None
        for k, line in enumerate(lines):
            match = _TIME_RE.search(line)
            if match:
                time_at = k
                break
        if time_at is None or match is None:
            continue
        g = match.groups()
        start = _fmt_time(g[0], g[1], g[2], g[3])
        end = _fmt_time(g[4], g[5], g[6], g[7])
        raw_text = "\n".join(lines[time_at + 1:]).strip()
        items.append(
            SrtItem(
                index=len(items) + 1,
                start=start,
                end=end,
                text=raw_text,
                norm=normalize(_clean_srt_text(raw_text)),
            )
        )
    return items
