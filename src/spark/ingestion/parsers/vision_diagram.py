"""Vision-LLM structured extraction for pages classified as vector drawings.

Ceiling, stated honestly: this cannot resolve full wire-to-terminal
connectivity from a schematic — that's a spatial/graph relationship, not
something a language model reliably reconstructs from a single rasterized
image. What it can do is produce a detailed, circuit-by-circuit narrative
(device tags, readable terminals, net names, cross references) plus
connection tables, with the citation always resolving back to the original
page (via the normal ``page`` payload field, same as every other parser) so
a human can confirm the details that actually matter for safety-relevant
wiring.
"""

from __future__ import annotations

import asyncio
import base64
import re
from collections.abc import Sequence
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from spark.core.logging import get_logger

log = get_logger(__name__)

DEFAULT_VISION_PROFILE = "vision_extract"
DEFAULT_DPI = 200
# Per-call budget once the request is in flight (queue wait behind the
# concurrency semaphore does not consume it). The gateway's qwen3-vl:4b took
# ~30-55s per 200-DPI page for the old short-JSON prompt; the detailed
# reverse-engineering prompt below generates several thousand tokens per page
# (measured ~88s on a real wiring-binder page), so the budget must cover a
# multi-minute generation, not just vision encode.
DEFAULT_TIMEOUT_SECONDS = 600.0

# Section headings the model is told to emit. parse_extraction_response()
# counts these to decide parsed_ok — keep the two lists in sync.
_SECTION_HEADINGS = (
    "ภาพรวมหน้านี้",
    "การไล่วงจรทีละขั้น",
    "อุปกรณ์ทั้งหมดในหน้านี้",
    "ตารางการเชื่อมต่อ",
    "การจ่ายไฟและกราวด์",
    "ผลกระทบเมื่ออุปกรณ์เสีย",
    "Block Diagram",
    "ความเสี่ยงและจุดที่อาจผิดพลาดของแบบ",
    "ข้อมูลที่ยังยืนยันไม่ได้",
)

_EXTRACTION_PROMPT = (
    "คุณคือ Senior Electrical Design Engineer ที่มีประสบการณ์สูงด้านระบบไฟฟ้าเครื่องจักรอุตสาหกรรม "
    "การออกแบบตู้คอนโทรล PLC, Servo, Robot และมาตรฐาน IEC 60204\n"
    "ภาพที่แนบคือ \"หนึ่งหน้า\" จากชุด Wiring Diagram หลายหน้า "
    "ให้อ่านหน้านี้อย่างละเอียดที่สุด เสมือนกำลัง Reverse Engineer ระบบทั้งหมด\n"
    "\n"
    "ข้อกำหนด:\n"
    "1. ห้ามสรุปภาพรวมเพียงอย่างเดียว ต้องไล่วงจรทีละวงจร ทีละขั้น\n"
    "2. ไล่สายไฟทุกเส้นตั้งแต่ต้นทางจนถึงปลายทาง ห้ามข้ามสายไฟหรืออุปกรณ์ใด ๆ แม้แต่ตัวเดียว\n"
    "3. ระบุอุปกรณ์ทุกตัวที่พบ พร้อม Device Tag, Terminal ทุกจุดที่อ่านได้, "
    "Net Name/Wire Number ทุกเส้น และ Cross Reference ทุกตำแหน่ง "
    "โดยคัดลอกตามที่พิมพ์ในแบบทุกตัวอักษร\n"
    "4. อธิบายหน้าที่ของอุปกรณ์แต่ละตัว และอธิบายว่าวงจรในหน้านี้เชื่อมต่อกันอย่างไร\n"
    "5. แยกวิเคราะห์ส่วนที่ปรากฏในหน้านี้: Main Power / AC Distribution / DC Distribution / "
    "Battery / Power Supply / Noise Filter / Ground / Neutral / Protective Earth (PE) / Robot Controller\n"
    "6. ข้อความที่อ่านไม่ออกให้เขียนว่า \"อ่านไม่ชัด\" ห้ามเดาหรือแต่ง label ที่อ่านไม่ได้ขึ้นเองเด็ดขาด\n"
    "7. แยกให้ชัดเจนระหว่างสิ่งที่เห็นจากแบบ กับข้อสันนิษฐานทางวิศวกรรม — "
    "ข้อสันนิษฐานให้กำกับท้ายข้อความว่า \"(สันนิษฐาน)\"\n"
    "8. อธิบายเป็นภาษาไทย แต่คง Device Tag / Terminal / Net Name ตามตัวอักษรเดิมในแบบ\n"
    "9. วิเคราะห์อย่างละเอียดที่สุด ไม่จำกัดความยาว\n"
    "10. คัดลอกรหัส/เลขรุ่น/ป้ายกำกับทุกตัวทีละตัวอักษรตามที่พิมพ์จริง ห้ามแปลง ห้ามเดา "
    "ระวังสับสนตัวอักษรที่หน้าตาคล้ายกัน: เลข 0 กับตัว O, เลข 1 กับตัว I และ l, "
    "เลข 2 กับตัว Z, เลข 5 กับตัว S, เลข 8 กับตัว B — ถ้าไม่แน่ใจให้เขียน \"(อ่านไม่ชัด)\" กำกับ\n"
    "11. ระบุว่าอุปกรณ์แต่ละตัวรับไฟจากบัส/รางไฟใด (เช่น +24VDC / -24VDC / 0V / GND / PE / L1 / L2 / L3) "
    "และในตารางการเชื่อมต่อ ถ้าเป็นบัส/รางร่วม (เช่น +24VDC, GND, PE) ให้ลงทุกอุปกรณ์ที่ต่ออยู่บนบัสเส้นเดียวกัน "
    "อย่าลงเพียงตัวเดียว เพราะบัสเหล่านี้ใช้ตอบว่า \"ถ้าอุปกรณ์หนึ่งเสีย ตัวใดกระทบด้วย\"\n"
    "\n"
    "12. ตารางการเชื่อมต่อต้องลงทุกสายที่เห็นว่าลากถึงกัน แม้ Terminal จะไม่มีป้ายกำกับ "
    "ให้ใส่แค่ Tag หรือเขียน \"ไม่ระบุ\" ในส่วน Terminal — "
    "ห้ามข้ามสายเพียงเพราะอ่าน Terminal ไม่ออก เพราะเส้นที่ข้ามไปคือคำตอบที่หายไป "
    "เช่น ไดรฟ์ที่ขับมอเตอร์ต้องมีแถว \"ไดรฟ์ → มอเตอร์\" เสมอ\n"
    "13. ช่อง Device Tag ให้ใส่ทั้งชื่อที่พิมพ์บนกล่องและรุ่น/พาร์ทที่พิมพ์กำกับไว้ "
    "เช่น \"AC Servo Drive 1 (AZXD-SEP)\" ไม่ใช่แยกรุ่นไปไว้ช่องคำอธิบาย "
    "เพื่อให้ค้นด้วยชื่อใดก็เจอ\n"
    "14. สำคัญมาก: เขียน \"ตารางอุปกรณ์\" และ \"ตารางการเชื่อมต่อ\" ให้ครบก่อนเสมอ "
    "ห้ามใช้พื้นที่หมดไปกับการบรรยายจนตารางขาดหาย ถ้าหลายวงจรเหมือนกันทุกประการ "
    "ให้บรรยายวงจรแรกโดยละเอียด วงจรที่เหมือนกันระบุสั้น ๆ ว่า \"โครงสร้างเหมือน (วงจรแรก) "
    "ต่างที่ Tag/Terminal ...\" ห้ามคัดลอกย่อหน้าเดิมซ้ำทุกวงจร\n"
    "\n"
    "ตอบเป็น Markdown ตามโครงสร้างนี้เท่านั้น เรียงลำดับหัวข้อตามนี้ (ใช้หัวข้อระดับ ### ทุกหัวข้อ "
    "หัวข้อใดไม่มีข้อมูลในหน้านี้ให้ระบุว่า \"ไม่ปรากฏในหน้านี้\" ห้ามเปลี่ยนชื่อหัวข้อ):\n"
    "\n"
    "### ภาพรวมหน้านี้\n"
    "(2-5 ประโยค: หน้านี้คือวงจรอะไร ทำหน้าที่อะไรในระบบ)\n"
    "\n"
    "### อุปกรณ์ทั้งหมดในหน้านี้\n"
    "(ลงทุกอุปกรณ์ที่พบในหน้านี้ ทุกแถว)\n"
    "| Device Tag | ชนิด/หน้าที่ | Terminal ที่อ่านได้ |\n"
    "|---|---|---|\n"
    "\n"
    "### ตารางการเชื่อมต่อ\n"
    "(ใช้รูปแบบ \"Tag:Terminal\" ในช่องจาก/ไป เช่น M18:GND, ORIENTAL AZD-KEP:GND; "
    "บัส/รางร่วมให้ลงทุกอุปกรณ์ที่ต่ออยู่ อย่าลงเพียงตัวเดียว)\n"
    "| จาก (Tag:Terminal) | ไป (Tag:Terminal) | Net/Wire No. | หมายเหตุ |\n"
    "|---|---|---|---|\n"
    "\n"
    "### การจ่ายไฟและกราวด์\n"
    "(Main Power / AC / DC / Power Supply / Battery / Noise Filter / Ground / Neutral / PE / "
    "Robot Controller เท่าที่ปรากฏในหน้านี้ — ระบุด้วยว่าแต่ละอุปกรณ์รับไฟจากบัส/รางใด)\n"
    "\n"
    "### ผลกระทบเมื่ออุปกรณ์เสีย\n"
    "(สำหรับแต่ละวงจร/อุปกรณ์หลักในหน้านี้: ถ้าอุปกรณ์นี้หรือสายของมันเสีย "
    "สาย/อุปกรณ์ใดในหน้านี้จะกระทบตามไปด้วย และตัวใดที่แยกอิสระไม่กระทบ — "
    "อ้างอิงจากบัส/รางร่วมและการต่อสายที่เห็นจริง)\n"
    "\n"
    "### การไล่วงจรทีละขั้น\n"
    "(ไล่ทีละวงจร: ไฟเข้าจากไหน ผ่านอุปกรณ์ใด ที่ Terminal ใด ออกไปที่ใด — "
    "บรรยายเส้นทางการไหลของไฟทีละขั้นจนสุดปลายทางของทุกวงจรในหน้านี้ "
    "วงจรที่เหมือนกันไม่ต้องเขียนซ้ำ ให้อ้างถึงวงจรแรก)\n"
    "\n"
    "### Block Diagram (ASCII)\n"
    "(การไหลของพลังงานในหน้านี้ เป็น ASCII diagram)\n"
    "\n"
    "### ความเสี่ยงและจุดที่อาจผิดพลาดของแบบ\n"
    "\n"
    "### ข้อมูลที่ยังยืนยันไม่ได้\n"
    "(สิ่งที่ต้องเปิดแบบหน้าอื่นหรือ Cross Reference ใดเพื่อยืนยัน)"
)

_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_CODE_FENCE_RE = re.compile(r"\A```[a-zA-Z]*\s*\n(.*)\n```\s*\Z", re.DOTALL)


async def _astream_text(llm: Any, messages: list[Any], timeout_seconds: float) -> str:
    """Invoke the LLM in streaming mode and accumulate the full text.

    Streaming is load-bearing, not an optimization: the kcalsion gateway sits
    behind Cloudflare, which kills any request with no response bytes for
    ~100s (HTTP 524). The detailed reverse-engineering prompt generates for
    well over 100s per page, so a non-streaming ainvoke() 524s on almost
    every page (observed: 16×524 vs 1×200 on a real 14-sheet binder run).
    With streaming, first tokens flow as soon as generation starts and the
    connection stays alive for the whole multi-minute answer.
    """

    async def _collect() -> str:
        parts: list[str] = []
        async for chunk in llm.astream(messages):
            content = getattr(chunk, "content", "")
            if isinstance(content, str):
                parts.append(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        parts.append(str(block.get("text") or ""))
        return "".join(parts)

    return await asyncio.wait_for(_collect(), timeout=timeout_seconds)

# --- Document-level synthesis (cross-page questions: "ถ้า M18 พังกระทบอะไร",
# "ไล่สายทั้งระบบ") -------------------------------------------------------------
# Two artifacts are indexed on top of the per-page analyses:
#   1. A deterministic device/connection index parsed from each page's device
#      and connection tables (no LLM — exact tags, never hallucinated).
#   2. An LLM-synthesized whole-document overview built from the per-page
#      overview/power sections (compact input, so it fits the small VLM's
#      context even for a 14-sheet binder).

_DEVICE_TABLE_HEADING = "อุปกรณ์ทั้งหมดในหน้านี้"
_CONNECTION_TABLE_HEADING = "ตารางการเชื่อมต่อ"
_SYNTHESIS_SECTION_HEADINGS = ("ภาพรวมหน้านี้", "การจ่ายไฟและกราวด์")
# Tolerate any heading level (## / ### / ####). The VLM is inconsistent about
# heading depth across pages — some pages come back with ## for the main
# sections instead of the ### the skeleton asks for. Matching only ### silently
# dropped every such page from the device/connection index (observed: page 8 of
# a real binder, with M17–M21, contributed nothing). Parse tolerantly instead
# of fighting the model.
_MD_SECTION_RE = re.compile(r"^#{2,4}\s+(.+?)\s*$", re.MULTILINE)
# A plausible device tag: starts alphanumeric, short, Latin script only (tags
# are printed in Latin script on the drawing). Rejects Thai prose, table
# headers, and notes so they never pollute the index.
_DEVICE_TAG_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9 _./+:#()-]{0,39}\Z")
# One device with dozens of edges (PE, 24VDC rails) would otherwise produce an
# unreadable kilometer-long line in the adjacency list.
_MAX_EDGES_PER_DEVICE = 40

_SYNTHESIS_PROMPT_HEADER = (
    "คุณคือ Senior Electrical Design Engineer ที่มีประสบการณ์สูงด้านระบบไฟฟ้าเครื่องจักรอุตสาหกรรม "
    "ตู้คอนโทรล PLC, Servo, Robot และมาตรฐาน IEC 60204\n"
    "ด้านล่างคือบทวิเคราะห์รายหน้าของ Wiring Diagram ชุดเดียวกันทั้งเล่ม "
    "ให้สังเคราะห์เป็นภาพรวมระดับทั้งระบบ\n"
    "\n"
    "ข้อกำหนด:\n"
    "1. ใช้เฉพาะข้อมูลจากบทวิเคราะห์ด้านล่าง ห้ามแต่งอุปกรณ์หรือการเชื่อมต่อที่ไม่ปรากฏ\n"
    "2. อ้างอิงเลขหน้ากำกับทุกครั้งที่กล่าวถึงวงจรหรืออุปกรณ์ เช่น (หน้า 3)\n"
    "3. ข้อสันนิษฐานทางวิศวกรรมให้กำกับ \"(สันนิษฐาน)\"\n"
    "4. อธิบายเป็นภาษาไทย คง Device Tag / Net Name ตามตัวอักษรเดิม\n"
    "\n"
    "ตอบเป็น Markdown ตามโครงสร้างนี้เท่านั้น:\n"
    "\n"
    "### ภาพรวมระบบทั้งหมด\n"
    "(ระบบนี้คืออะไร ประกอบด้วยส่วนใดบ้าง)\n"
    "\n"
    "### การไหลของพลังงานตั้งแต่จ่ายไฟเข้าจนถึงโหลด\n"
    "(ไล่ตั้งแต่ Main Power → Distribution → Control → โหลด/มอเตอร์ พร้อมเลขหน้า)\n"
    "\n"
    "### ความสัมพันธ์ระหว่างวงจรแต่ละหน้า\n"
    "(หน้าไหนป้อนไฟ/สัญญาณให้หน้าไหน อุปกรณ์ใดปรากฏหลายหน้า)\n"
    "\n"
    "### Block Diagram รวมทั้งระบบ (ASCII)\n"
    "\n"
    "### ความเสี่ยงและข้อสังเกตระดับระบบ\n"
    "\n"
    "บทวิเคราะห์รายหน้า:\n"
)

# Per-page and total input budgets for the synthesis prompt (chars). The
# gateway model's usable context is modest and client num_ctx is not honored
# over the OpenAI-compat API — keep the whole prompt well under it so the
# overview generation never truncates the later pages' input.
_SYNTHESIS_PER_PAGE_CHARS = 1200
_SYNTHESIS_TOTAL_CHARS = 14000


def _analysis_sections(analysis: str) -> dict[str, str]:
    """Split a per-page markdown analysis into {heading: body}."""
    sections: dict[str, str] = {}
    matches = list(_MD_SECTION_RE.finditer(analysis or ""))
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(analysis)
        heading = match.group(1).strip()
        sections[heading] = analysis[match.end() : end].strip()
    return sections


def _section_body(analysis: str, heading_substr: str) -> str:
    for heading, body in _analysis_sections(analysis).items():
        if heading_substr in heading:
            return body
    return ""


def _table_data_rows(body: str) -> list[list[str]]:
    """Parse markdown table body into data rows (skips header + separator)."""
    rows: list[list[str]] = []
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if not any(cells):
            continue
        if all(set(c) <= {"-", ":", " "} for c in cells):
            continue
        rows.append(cells)
    return rows[1:] if len(rows) > 1 else []


def _clean_tag(cell: str) -> str:
    tag = cell.strip("*` ")
    return tag if _DEVICE_TAG_RE.match(tag) else ""


# Separator between a device tag and its terminal inside a connection-table
# endpoint cell. The model writes either "M18:GND" or "M18 - GND"; device names
# themselves contain internal dashes with no surrounding spaces (AZD-KEP,
# AZXD-SEP 1), so a spaced " - " (or a colon) is what actually delimits the
# terminal.
_ENDPOINT_SEP_RE = re.compile(r"\s*:\s*|\s+[-–—]\s+")


def _split_endpoint(cell: str) -> tuple[str, str]:
    """Split a connection endpoint cell into (device, terminal).

    "M18 - GND" -> ("M18", "GND"); "ORIENTAL A2D-KEP - GND" ->
    ("ORIENTAL A2D-KEP", "GND"); "SPD_CTRL_7:16" -> ("SPD_CTRL_7", "16").
    Splits on the LAST separator so multi-word device names survive.
    """
    raw = cell.strip("*` ")
    seps = list(_ENDPOINT_SEP_RE.finditer(raw))
    if not seps:
        return raw, ""
    last = seps[-1]
    return raw[: last.start()].strip(), raw[last.end() :].strip()


def _expand_tags(device_cell: str) -> list[str]:
    """Expand a grouped device cell into individual tags.

    "M5/M6" -> ["M5", "M6"]; "AZXD-SEP 1/2" -> ["AZXD-SEP 1", "AZXD-SEP 2"]
    (numeric-only suffixes inherit the alpha prefix of the preceding member).
    A single tag returns just itself. Only members that validate as plausible
    tags are kept, so a stray "/" never invents garbage.
    """
    cell = device_cell.strip("*` ")
    if "/" not in cell:
        tag = _clean_tag(cell)
        return [tag] if tag else []
    out: list[str] = []
    prefix = ""
    for part in cell.split("/"):
        part = part.strip()
        if not part:
            continue
        if part[0].isdigit() and prefix:
            # bare numeric suffix like the "2" in "AZXD-SEP 1/2"
            candidate = f"{prefix}{part}"
        else:
            candidate = part
            m = re.match(r"(.*?)(\d+)\s*$", part)
            prefix = m.group(1) if m else ""
        tag = _clean_tag(candidate)
        if tag and tag not in out:
            out.append(tag)
    return out


def device_tags_from_analysis(analysis: str) -> list[str]:
    """Parse device tags from the page's device table (first column).

    Deterministic and conservative: only rows under the known heading, only
    plausible Latin-script tags. Returns tags in page order, de-duplicated.
    """
    body = _section_body(analysis, _DEVICE_TABLE_HEADING)
    tags: list[str] = []
    seen: set[str] = set()
    for cells in _table_data_rows(body):
        if not cells:
            continue
        tag = _clean_tag(cells[0])
        if not tag or tag in seen:
            continue
        seen.add(tag)
        tags.append(tag)
    return tags


_MAX_ENDPOINTS_PER_NET = 30
# The doc-level index is emitted as atomic page-0 chunks, so it is never split
# by the chunker — every one of these caps exists to keep it inside what the
# embedder can actually encode (bge-m3: 8192 tokens). Without them a 14-sheet
# binder produced an 87k-char index that silently truncated at embed time.
_MAX_MATES_PER_NET = 12
_MAX_NETS_PER_DEVICE = 8
_THAI_CHAR_RE = re.compile(r"[฀-๿]")
# Power / ground rail tokens. These are the shared buses that make "if X fails,
# what else is affected?" answerable — and, crucially, they are recoverable even
# when the small VLM fails to read the printed wire label, because they show up
# as endpoints ("+24VDC / GND") or as the net cell. Matched verbatim from the
# drawing, case-insensitively, on token boundaries.
_RAIL_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?:[+\-]?\d{1,3}\s?V(?:DC|AC)?"          # +24VDC, 24V, -24VDC, 0V
    r"|GND|PE|DC\d{1,2}V|DCC\d[_.]?\d*V?"      # GND, PE, DC24V, DCC2_24V, DCC2_0V
    r"|1?L[123]|24VDC|0V)"                      # L1..L3, 1L1..1L3
    r"(?![A-Za-z0-9])",
    re.IGNORECASE,
)


def _is_real_net(net: str) -> bool:
    """A real net/wire label is a short mostly-Latin token, not a Thai gloss.

    The VLM sometimes fills the Net column with a description ("สายสัญญาณที่ไม่
    เห็นชัด") when it can't read the printed label — reject anything containing
    Thai characters, empty/placeholder values, or absurdly long strings.
    """
    n = net.strip().strip("\"'` ")
    if not n or _THAI_CHAR_RE.search(n) or len(n) > 24:
        return False
    low = n.lower()
    return low not in ("-", "n/a", "na", "none", "null")


def _rail_tokens(*cells: str) -> list[str]:
    """Rail/bus tokens (+24VDC, GND, PE, DCC2_24V, …) found in any given cell."""
    out: list[str] = []
    for cell in cells:
        for m in _RAIL_TOKEN_RE.finditer(cell or ""):
            tok = m.group(0).strip().upper().replace(" ", "")
            if tok and tok not in out:
                out.append(tok)
    return out


def _endpoints_in_cell(cell: str) -> list[tuple[str, str]]:
    """Split a connection cell into (device, terminal) endpoints.

    Handles the shared-bus shorthand the VLM emits, where one cell names several
    devices: "M17:GND, M18:GND, M19:GND" → three endpoints. A comma-part that
    carries its own Tag:Terminal separator starts a new device; a bare part with
    no separator is treated as an extra terminal of the current device
    ("M5:1L1, 1N, PE" → M5 with terminals 1L1/1N/PE, not three devices).
    """
    out: list[tuple[str, str]] = []
    for seg in re.split(r"[;\n]", cell or ""):
        cur_dev: str | None = None
        for part in seg.split(","):
            part = part.strip().strip("*` ")
            if not part:
                continue
            if ":" in part or re.search(r"\s[-–—]\s", part):
                dev_cell, term = _split_endpoint(part)
                tags = _expand_tags(dev_cell)
                for d in tags:
                    out.append((d, term))
                cur_dev = tags[-1] if tags else cur_dev
            elif cur_dev is not None:
                out.append((cur_dev, part))  # extra terminal of the current device
            else:
                for d in _expand_tags(part):
                    out.append((d, ""))
                    cur_dev = d
    return out


def build_device_page_index(page_analyses: dict[int, str]) -> str:
    """Cross-page connectivity index ('' if empty).

    Three artifacts, all deterministic (no LLM — exact tags, never hallucinated):
      1. Device → pages + kind.
      2. Per-device adjacency (every edge touching it) with a shared-bus note,
         so "ถ้า M18 พังกระทบอะไร" resolves to both the directly wired nodes and
         the devices sharing the same power/ground rail.
      3. Net / shared-bus index: every net that ties ≥2 devices together, with
         all the (device:terminal) endpoints on it.
    """
    tag_pages: dict[str, list[int]] = {}
    tag_kind: dict[str, str] = {}
    adjacency: dict[str, list[str]] = {}
    # net name -> {device_tag: {terminal, ...}} and the pages it spans
    net_endpoints: dict[str, dict[str, set[str]]] = {}
    net_pages: dict[str, set[int]] = {}
    # device -> set of net names it sits on (for the shared-bus note)
    device_nets: dict[str, set[str]] = {}

    for page_num in sorted(page_analyses):
        analysis = page_analyses[page_num]
        for cells in _table_data_rows(_section_body(analysis, _DEVICE_TABLE_HEADING)):
            tag = _clean_tag(cells[0]) if cells else ""
            if not tag:
                continue
            pages = tag_pages.setdefault(tag, [])
            if page_num not in pages:
                pages.append(page_num)
            if len(cells) > 1 and cells[1] and tag not in tag_kind:
                tag_kind[tag] = cells[1]
        for cells in _table_data_rows(_section_body(analysis, _CONNECTION_TABLE_HEADING)):
            if len(cells) < 2:
                continue
            frm, to = cells[0].strip(), cells[1].strip()
            net = cells[2].strip() if len(cells) > 2 else ""
            if not frm or not to:
                continue
            net_clean = net.strip().strip("\"'` ")
            net_suffix = f" [{net_clean}]" if _is_real_net(net) else ""
            # Devices touched by this row (a rail token like +24VDC/GND is a net,
            # not a device — kept out of the node set, folded into nets below).
            row_devices: dict[str, set[str]] = {}
            for dev, term in _endpoints_in_cell(frm) + _endpoints_in_cell(to):
                if _rail_tokens(dev):
                    continue
                row_devices.setdefault(dev, set())
                if term:
                    row_devices[dev].add(term)
            # Direct adjacency only for genuine point-to-point rows. A bus row
            # names many devices at once; expanding it pairwise is both wrong
            # (a shared rail is not a wire between every pair) and quadratic —
            # it blew the doc-level index up to 87k chars, past what the embedder
            # can take. Bus membership is carried by the net index instead.
            if len(row_devices) == 2:
                (dev_a, terms_a), (dev_b, terms_b) = row_devices.items()
                for src, dst, dst_terms in ((dev_a, dev_b, terms_b), (dev_b, dev_a, terms_a)):
                    term_str = ",".join(sorted(dst_terms))
                    entry = (
                        f"{dst}{':' + term_str if term_str else ''}"
                        f"{net_suffix} (หน้า {page_num})"
                    )
                    bucket = adjacency.setdefault(src, [])
                    if entry not in bucket:
                        bucket.append(entry)
            # Nets established by this row: the readable net-column label plus any
            # rail/bus token in the net or endpoint cells. Every device in the row
            # is a member — this is what makes shared-bus impact answerable even
            # when the printed wire label was unreadable.
            row_nets: list[str] = []
            if _is_real_net(net):
                row_nets.append(net_clean)
            row_nets += _rail_tokens(net, frm, to)
            for netname in dict.fromkeys(row_nets):
                for dev, terms in row_devices.items():
                    net_endpoints.setdefault(netname, {}).setdefault(dev, set())
                    net_endpoints[netname][dev] |= terms
                    device_nets.setdefault(dev, set()).add(netname)
                net_pages.setdefault(netname, set()).add(page_num)

    if not tag_pages and not adjacency and not device_nets:
        return ""

    lines = [
        "## 🔎 ดัชนีอุปกรณ์ทั้งเอกสาร (Device Index)",
        "",
        "สร้างอัตโนมัติจากการอ่านแบบทุกหน้า ใช้ตอบว่าอุปกรณ์แต่ละตัวอยู่หน้าใด "
        "ต่อกับอุปกรณ์ใด อยู่บนบัส/เน็ตร่วมกับตัวใด และถ้าอุปกรณ์ตัวหนึ่งเสีย "
        "วงจร/สายเส้นใดได้รับผลกระทบ (ตรวจสอบกับแบบต้นฉบับหน้าที่อ้างถึงก่อนใช้งานจริง)",
        "",
        "### อุปกรณ์ → หน้าที่พบ",
        "| Device Tag | ปรากฏในหน้า | ชนิด/หน้าที่ |",
        "|---|---|---|",
    ]
    for tag in sorted(tag_pages, key=str.lower):
        pages_str = ", ".join(str(p) for p in tag_pages[tag])
        lines.append(f"| {tag} | {pages_str} | {tag_kind.get(tag, '')} |")

    # Every device with either a direct edge or bus membership gets a line — a
    # device that only ever appears on a shared rail (common: motors hanging off
    # a 24VDC bus) still needs its "which bus am I on" note to be findable.
    connected = set(adjacency) | set(device_nets)
    if connected:
        lines += ["", "### การเชื่อมต่อของแต่ละอุปกรณ์ (ผลกระทบเมื่ออุปกรณ์เสีย)"]
        for tag in sorted(connected, key=str.lower):
            edges = adjacency.get(tag, [])
            shown = edges[:_MAX_EDGES_PER_DEVICE]
            suffix = (
                f" …และอีก {len(edges) - len(shown)} จุด" if len(edges) > len(shown) else ""
            )
            line = f"- **{tag}**: " + (
                "; ".join(shown) + suffix
                if shown
                else "(ไม่มีสายต่อจุด-ต่อ-จุดที่ระบุชัดในแบบ — ต่อผ่านบัส/เน็ตร่วมด้านล่าง)"
            )
            # Shared-bus note: which other devices sit on the same net(s). Mates
            # are capped — a 24VDC rail can carry dozens of devices, and the full
            # membership already lives in the net index below.
            shared: list[str] = []
            for net in sorted(device_nets.get(tag, ())):
                mates = sorted(t for t in net_endpoints.get(net, {}) if t != tag)
                if not mates:
                    continue
                head = mates[:_MAX_MATES_PER_NET]
                more = f" …และอีก {len(mates) - len(head)}" if len(mates) > len(head) else ""
                shared.append(f"{net} (ร่วมกับ {', '.join(head)}{more})")
            if shared:
                line += "  \n  ↳ อยู่บนบัส/เน็ตร่วม: " + "; ".join(shared[:_MAX_NETS_PER_DEVICE])
            lines.append(line)

    shared_nets = {n: eps for n, eps in net_endpoints.items() if len(eps) >= 2}
    if shared_nets:
        lines += [
            "",
            "### ดัชนีเน็ต/บัสร่วม (Net / Shared-Bus Index)",
            "เน็ต/บัสที่เชื่อมอุปกรณ์ตั้งแต่ 2 ตัวขึ้นไป — ถ้าบัสนี้ลัด/ขาด "
            "อุปกรณ์ทุกตัวที่อยู่บนบัสเดียวกันจะได้รับผลกระทบ",
            "| Net/Wire | อุปกรณ์บนเน็ตนี้ (Tag:Terminal) | หน้า |",
            "|---|---|---|",
        ]
        for net in sorted(shared_nets, key=str.lower):
            eps = shared_nets[net]
            parts = []
            for tag in sorted(eps, key=str.lower)[:_MAX_ENDPOINTS_PER_NET]:
                terms = ", ".join(sorted(eps[tag]))
                parts.append(f"{tag}:{terms}" if terms else tag)
            pages_str = ", ".join(str(p) for p in sorted(net_pages.get(net, ())))
            lines.append(f"| {net} | {'; '.join(parts)} | {pages_str} |")

    return "\n".join(lines)


def split_doc_level_markdown(text: str, *, max_chars: int = 3000) -> list[str]:
    """Split a doc-level markdown artifact into embeddable pieces.

    The device index and system overview are emitted as *atomic* page-0 chunks
    (the chunker never splits them), so a long one silently truncates at embed
    time — bge-m3 tops out at 8192 tokens, and a real 14-sheet binder produced
    an 87k-char index. Split on line boundaries and repeat the top-level heading
    on each piece so each stays self-describing and independently retrievable.
    """
    lines = (text or "").split("\n")
    if not lines:
        return []
    title = lines[0] if lines[0].startswith("#") else ""
    parts: list[str] = []
    buf: list[str] = []
    size = 0
    for line in lines:
        add = len(line) + 1
        if buf and size + add > max_chars:
            parts.append("\n".join(buf))
            buf, size = [], 0
            if title:
                buf.append(title)
                buf.append("")
                size += len(title) + 2
        buf.append(line)
        size += add
    if buf:
        parts.append("\n".join(buf))
    return [p for p in parts if p.strip()] or [text]


async def synthesize_document_overview(
    page_analyses: dict[int, str],
    *,
    llm_profile: str = DEFAULT_VISION_PROFILE,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> str:
    """LLM-synthesized whole-document overview from per-page analyses.

    Text-only call on the same profile (the VLM answers text prompts too).
    Never raises — returns '' when the model is unavailable or the input is
    too thin, and the caller simply skips the overview chunk.
    """
    from langchain_core.messages import HumanMessage

    from spark.core.llm_client import get_chat_llm

    if len(page_analyses) < 2:
        return ""

    blocks: list[str] = []
    total = 0
    for page_num in sorted(page_analyses):
        sections = _analysis_sections(page_analyses[page_num])
        parts = [
            f"{heading}: {sections[heading]}"
            for heading in _SYNTHESIS_SECTION_HEADINGS
            if sections.get(heading)
        ]
        if not parts:
            continue
        block = f"หน้า {page_num}:\n" + "\n".join(parts)
        block = block[:_SYNTHESIS_PER_PAGE_CHARS]
        if total + len(block) > _SYNTHESIS_TOTAL_CHARS:
            break
        blocks.append(block)
        total += len(block)
    if len(blocks) < 2:
        return ""

    prompt = _SYNTHESIS_PROMPT_HEADER + "\n\n".join(blocks)
    try:
        llm = get_chat_llm(llm_profile)
        text = await _astream_text(llm, [HumanMessage(content=prompt)], timeout_seconds)
    except Exception as exc:  # noqa: BLE001 — synthesis is best-effort, never fail the ingest
        log.warning("vision_overview_synthesis_failed", profile=llm_profile, error=str(exc)[:300])
        return ""

    stripped = _THINK_BLOCK_RE.sub("", text).strip()
    fence = _CODE_FENCE_RE.match(stripped)
    if fence:
        stripped = fence.group(1).strip()
    return stripped


class VisionExtractionUnavailableError(RuntimeError):
    """Raised only when the page can't be rasterized at all (not a model-response problem)."""


@dataclass(frozen=True)
class DiagramExtraction:
    analysis: str
    parsed_ok: bool = True

    def to_page_content(self, *, page_number: int, drawing_no: str | None = None) -> str:
        header = f"## 📐 Wiring Diagram — หน้า {page_number} (Diagram page {page_number})"
        if drawing_no:
            header += f" · แบบเลขที่ {drawing_no}"
        parts = [header]
        if self.analysis:
            parts.append(self.analysis)
        if not self.parsed_ok:
            parts.append(
                "> ⚠️ คำอธิบายนี้สร้างจากระบบอ่านแบบอัตโนมัติและไม่ผ่านการตรวจโครงสร้าง — "
                "โปรดตรวจสอบกับแบบต้นฉบับหน้านี้ก่อนใช้งานจริง "
                "(automated diagram description — verify against the original page image "
                "before relying on it)"
            )
        return "\n\n".join(parts)


def rasterize_pdf_page(pdf_path: Path, page_number: int, *, dpi: int = DEFAULT_DPI) -> Any:
    """Render one 1-based PDF page to a PIL image.

    Reuses the same pdf2image/poppler path as ``image_ocr_parser.py``'s
    per-page OCR rendering — no new rasterization dependency.
    """
    try:
        from pdf2image import convert_from_path
    except ImportError as exc:
        raise VisionExtractionUnavailableError(f"pdf2image is not installed: {exc}") from exc
    try:
        images = convert_from_path(
            str(pdf_path), dpi=dpi, first_page=page_number, last_page=page_number
        )
    except Exception as exc:
        raise VisionExtractionUnavailableError(
            f"cannot render page {page_number} for vision extraction "
            f"(verify poppler is installed): {exc}"
        ) from exc
    if not images:
        raise VisionExtractionUnavailableError(f"no image rendered for page {page_number}")
    return images[0]


def _image_to_data_url(image: Any) -> str:
    buf = BytesIO()
    image.convert("RGB").save(buf, format="PNG")
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def parse_extraction_response(text: str) -> DiagramExtraction:
    """Tolerant markdown parsing — degrade to needs_review, never drop the page.

    ``parsed_ok`` means the model followed the section skeleton (≥2 of the
    required headings present). Anything else — freeform prose, an empty
    response, a refusal — is still indexed verbatim but flagged so a human
    knows to check the original page image.
    """
    stripped = _THINK_BLOCK_RE.sub("", text or "").strip()
    fence = _CODE_FENCE_RE.match(stripped)
    if fence:
        stripped = fence.group(1).strip()
    heading_hits = sum(1 for heading in _SECTION_HEADINGS if heading in stripped)
    return DiagramExtraction(analysis=stripped, parsed_ok=bool(stripped) and heading_hits >= 2)


async def extract_diagram_page(
    image: Any,
    *,
    llm_profile: str = DEFAULT_VISION_PROFILE,
    fallback_profiles: Sequence[str] = (),
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> DiagramExtraction:
    """Call the vision LLM for a rasterized page, walking a fallback ladder.

    The primary backend is a shared, quota'd gateway: KKU returns
    ``401 {'error': 'This model reached daily limit.'}`` once the day's budget is
    gone, and it does so for *every* page at once. Without a fallback the whole
    binder extracts as nothing (a real incident — a 14-sheet drawing was indexed
    as bare title blocks). So on any failure — or any empty answer — try the next
    profile; the ladder ends at a model on a different provider, which cannot be
    taken out by the same quota.

    Never raises: if every rung fails, return an empty extraction and let the
    caller decide (``_apply_vision_extraction`` fails the ingest when *all* pages
    come back empty, rather than committing an empty drawing).
    """
    from langchain_core.messages import HumanMessage

    from spark.core.llm_client import get_chat_llm

    # Encode once for the whole ladder, off the event loop. The PNG+base64 of a
    # 200-DPI sheet measures ~180ms and the data URL is identical for every rung,
    # so encoding inside the loop re-did the same work on each fallback (~10s of
    # pure waste across a 14-sheet binder once the primary hits its daily quota).
    # It is also CPU-bound: running it inline stalled the other pages already
    # streaming under the max_concurrency fan-out.
    try:
        data_url = await asyncio.to_thread(_image_to_data_url, image)
    except Exception as exc:  # noqa: BLE001 — same contract as a dead backend: never raise
        log.warning(
            "vision_diagram_encode_failed",
            error=str(exc)[:300] or type(exc).__name__,
        )
        return DiagramExtraction(analysis="", parsed_ok=False)

    message = HumanMessage(
        content=[
            {"type": "text", "text": _EXTRACTION_PROMPT},
            {"type": "image_url", "image_url": {"url": data_url}},
        ]
    )

    for profile in (llm_profile, *fallback_profiles):
        try:
            llm = get_chat_llm(profile)
            text = await _astream_text(llm, [message], timeout_seconds)
        except Exception as exc:  # noqa: BLE001 — a dead backend must not crash ingestion
            log.warning(
                "vision_diagram_extract_failed",
                profile=profile,
                error=str(exc)[:300] or type(exc).__name__,
            )
            continue
        extraction = parse_extraction_response(text)
        if extraction.analysis:
            if profile != llm_profile:
                log.warning(
                    "vision_diagram_extract_used_fallback",
                    primary=llm_profile,
                    used=profile,
                )
            return extraction
        log.warning("vision_diagram_extract_empty", profile=profile)
    return DiagramExtraction(analysis="", parsed_ok=False)
