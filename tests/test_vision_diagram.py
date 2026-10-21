"""Vision-LLM diagram extraction: tolerant parsing and graceful degradation."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

from spark.ingestion.parsers.pdf_parser import _apply_vision_extraction
from spark.ingestion.parsers.vision_diagram import (
    DiagramExtraction,
    _endpoints_in_cell,
    _expand_tags,
    _is_real_net,
    _rail_tokens,
    _split_endpoint,
    build_device_page_index,
    device_tags_from_analysis,
    extract_diagram_page,
    parse_extraction_response,
    split_doc_level_markdown,
    synthesize_document_overview,
)

_STRUCTURED_ANALYSIS = (
    "### ภาพรวมหน้านี้\n"
    "หน้านี้คือวงจรจ่ายไฟหลักของตู้ควบคุมสายพาน\n\n"
    "### การไล่วงจรทีละขั้น\n"
    "ไฟ 3 เฟสเข้าที่ CB1:L1 ผ่าน MC1 ไปยัง M18\n\n"
    "### อุปกรณ์ทั้งหมดในหน้านี้\n"
    "| Device Tag | ชนิด/หน้าที่ | Terminal ที่อ่านได้ |\n"
    "|---|---|---|\n"
    "| M18 | มอเตอร์สายพาน | U1, V1, W1 |\n\n"
    "### ตารางการเชื่อมต่อ\n"
    "| จาก (Tag:Terminal) | ไป (Tag:Terminal) | Net/Wire No. | หมายเหตุ |\n"
    "|---|---|---|---|\n"
    "| MC1:2 | M18:U1 | W101 | อ่านไม่ชัด |\n"
)


def test_parse_extraction_response_structured_markdown() -> None:
    result = parse_extraction_response(_STRUCTURED_ANALYSIS)
    assert result.parsed_ok
    assert "M18" in result.analysis
    assert "### การไล่วงจรทีละขั้น" in result.analysis


def test_parse_extraction_response_strips_code_fence() -> None:
    result = parse_extraction_response(f"```markdown\n{_STRUCTURED_ANALYSIS}\n```")
    assert result.parsed_ok
    assert not result.analysis.startswith("```")
    assert "### ภาพรวมหน้านี้" in result.analysis


def test_parse_extraction_response_strips_think_block() -> None:
    result = parse_extraction_response(
        f"<think>let me trace the wires…</think>\n{_STRUCTURED_ANALYSIS}"
    )
    assert result.parsed_ok
    assert "let me trace" not in result.analysis


def test_parse_extraction_response_freeform_prose_degrades() -> None:
    text = "This page shows a wiring diagram of a belt conveyor control cabinet."
    result = parse_extraction_response(text)
    assert not result.parsed_ok
    assert result.analysis == text


def test_parse_extraction_response_single_heading_still_degrades() -> None:
    # One heading alone can appear in prose by accident — require the skeleton.
    result = parse_extraction_response("### ภาพรวมหน้านี้\nวงจรจ่ายไฟ")
    assert not result.parsed_ok


def test_parse_extraction_response_empty_text() -> None:
    result = parse_extraction_response("")
    assert not result.parsed_ok
    assert result.analysis == ""


def test_diagram_extraction_to_page_content_includes_header_and_analysis() -> None:
    extraction = DiagramExtraction(analysis=_STRUCTURED_ANALYSIS, parsed_ok=True)
    content = extraction.to_page_content(page_number=3, drawing_no="EE-07")
    assert "หน้า 3" in content
    assert "Diagram page 3" in content
    assert "EE-07" in content
    assert "### ตารางการเชื่อมต่อ" in content
    assert "verify against the original page image" not in content


def test_diagram_extraction_low_confidence_flag_appended_when_not_parsed() -> None:
    extraction = DiagramExtraction(analysis="raw text", parsed_ok=False)
    content = extraction.to_page_content(page_number=1)
    assert "verify against the original page image" in content
    assert "raw text" in content


async def test_extract_diagram_page_degrades_gracefully_when_model_unavailable() -> None:
    with (
        patch("spark.core.llm_client.get_chat_llm", side_effect=RuntimeError("model not pulled")),
        # Must be stubbed, or the fake image fails to encode and the call
        # short-circuits before it ever reaches the model — passing for the
        # wrong reason.
        patch(
            "spark.ingestion.parsers.vision_diagram._image_to_data_url",
            return_value="data:image/png;base64,x",
        ),
    ):
        result = await extract_diagram_page(image=object(), llm_profile="vision_extract")
    assert not result.parsed_ok
    assert result.analysis == ""


async def test_extract_diagram_page_never_raises_when_image_cannot_be_encoded() -> None:
    """A broken image is a dead backend's equivalent: log and degrade, never raise."""
    with patch(
        "spark.ingestion.parsers.vision_diagram._image_to_data_url",
        side_effect=OSError("cannot identify image"),
    ):
        result = await extract_diagram_page(image=object(), llm_profile="vision_extract")
    assert not result.parsed_ok
    assert result.analysis == ""


async def test_extract_diagram_page_encodes_image_once_for_whole_ladder() -> None:
    """The PNG+base64 of a 200-DPI sheet costs ~180ms and is identical on every
    rung. Encoding per-rung re-did it up to 4x per page — pure waste on exactly
    the path that is already degraded (primary out of quota)."""
    encodes: list[object] = []

    def _fake_encode(image):
        encodes.append(image)
        return "data:image/png;base64,x"

    def _fake_get_chat_llm(profile: str):
        if profile != "vision_extract_llama":
            raise RuntimeError("Error code: 401 - {'error': 'This model reached daily limit.'}")
        return _streaming_llm(_STRUCTURED_ANALYSIS)

    with (
        patch("spark.core.llm_client.get_chat_llm", side_effect=_fake_get_chat_llm),
        patch(
            "spark.ingestion.parsers.vision_diagram._image_to_data_url",
            side_effect=_fake_encode,
        ),
    ):
        result = await extract_diagram_page(
            image=object(),
            llm_profile="vision_extract",
            fallback_profiles=("vision_extract_gpt", "vision_extract_llama"),
        )
    assert result.parsed_ok
    assert len(encodes) == 1, f"image encoded {len(encodes)}x while walking a 3-rung ladder"


def _streaming_llm(text: str, captured: dict | None = None):
    """Fake LLM whose astream() yields the answer in chunks (the real call
    streams to keep Cloudflare from 524-ing the multi-minute generation)."""
    llm = AsyncMock()

    def _astream(messages, **_kw):
        if captured is not None:
            captured["messages"] = messages

        async def _gen():
            mid = max(1, len(text) // 2)
            yield type("Chunk", (), {"content": text[:mid]})()
            yield type("Chunk", (), {"content": text[mid:]})()

        return _gen()

    llm.astream = _astream
    return llm


async def test_extract_diagram_page_parses_successful_response() -> None:
    mock_llm = _streaming_llm(_STRUCTURED_ANALYSIS)
    with (
        patch("spark.core.llm_client.get_chat_llm", return_value=mock_llm),
        patch("spark.ingestion.parsers.vision_diagram._image_to_data_url", return_value="data:image/png;base64,x"),
    ):
        result = await extract_diagram_page(image=object(), llm_profile="vision_extract")
    assert result.parsed_ok
    assert "M18" in result.analysis


async def test_extract_diagram_page_falls_back_when_primary_is_out_of_quota() -> None:
    """KKU returns 401 "This model reached daily limit." for every page at once, so
    a single-model config blanks a whole binder. The ladder must move on."""
    used: list[str] = []

    def _fake_get_chat_llm(profile: str):
        used.append(profile)
        if profile == "vision_extract":
            raise RuntimeError("Error code: 401 - {'error': 'This model reached daily limit.'}")
        return _streaming_llm(_STRUCTURED_ANALYSIS)

    with (
        patch("spark.core.llm_client.get_chat_llm", side_effect=_fake_get_chat_llm),
        patch(
            "spark.ingestion.parsers.vision_diagram._image_to_data_url",
            return_value="data:image/png;base64,x",
        ),
    ):
        result = await extract_diagram_page(
            image=object(),
            llm_profile="vision_extract",
            fallback_profiles=("vision_extract_gpt", "vision_extract_local"),
        )
    assert result.parsed_ok
    assert "M18" in result.analysis
    assert used == ["vision_extract", "vision_extract_gpt"]  # stopped at first success


async def test_extract_diagram_page_falls_back_on_empty_answer() -> None:
    """An HTTP 200 with an empty body is just as fatal as an error — keep walking."""
    used: list[str] = []

    def _fake_get_chat_llm(profile: str):
        used.append(profile)
        return _streaming_llm("" if profile == "vision_extract" else _STRUCTURED_ANALYSIS)

    with (
        patch("spark.core.llm_client.get_chat_llm", side_effect=_fake_get_chat_llm),
        patch(
            "spark.ingestion.parsers.vision_diagram._image_to_data_url",
            return_value="data:image/png;base64,x",
        ),
    ):
        result = await extract_diagram_page(
            image=object(),
            llm_profile="vision_extract",
            fallback_profiles=("vision_extract_llama",),
        )
    assert result.parsed_ok
    assert used == ["vision_extract", "vision_extract_llama"]


async def test_extract_diagram_page_empty_when_whole_ladder_fails() -> None:
    with (
        patch("spark.core.llm_client.get_chat_llm", side_effect=RuntimeError("all down")),
        patch(
            "spark.ingestion.parsers.vision_diagram._image_to_data_url",
            return_value="data:image/png;base64,x",
        ),
    ):
        result = await extract_diagram_page(
            image=object(),
            llm_profile="vision_extract",
            fallback_profiles=("a", "b"),
        )
    assert not result.parsed_ok
    assert result.analysis == ""


async def test_apply_vision_extraction_retains_title_block_text() -> None:
    """Vision analysis replaces page text at index time — the title-block text
    (project/customer/revision, real extractable text on an otherwise vector-only
    page) must survive alongside it, not be silently dropped."""
    title_block = (
        "Thaimectech.CO.,LTD www.thaimectech.com\n"
        "Customer Confirm By: CP(center).co.,ltd\n"
        "Title: Shrimp Trim Diagram\nJob No: EE-07"
    )
    pages = [(1, title_block, "text")]

    with (
        patch(
            "spark.ingestion.parse.pdf_vector_density.vector_drawing_pages",
            return_value={1},
        ),
        patch(
            "spark.ingestion.parsers.pdf_parser.rasterize_pdf_page",
            return_value=object(),
        ),
        patch(
            "spark.ingestion.parsers.pdf_parser.extract_diagram_page",
            new=AsyncMock(
                return_value=DiagramExtraction(
                    analysis=_STRUCTURED_ANALYSIS, parsed_ok=True
                )
            ),
        ),
    ):
        updated_pages, needs_review, extractions = await _apply_vision_extraction(
            Path("wiring_diagram.pdf"), pages, {}
        )

    assert needs_review == set()
    assert extractions[1].parsed_ok
    page_num, text, source = updated_pages[0]
    assert page_num == 1
    assert source == "vision"
    assert "### การไล่วงจรทีละขั้น" in text
    assert "Shrimp Trim Diagram" in text
    assert "CP(center).co.,ltd" in text


async def test_apply_vision_extraction_fails_when_every_page_returns_nothing() -> None:
    """Total vision wipeout (backend down / out of quota) must fail the ingest, not
    quietly index a drawing as empty title blocks. Real incident: the KKU daily
    limit hit mid-run, every page came back empty, and the job still reported
    'completed' while swapping the useless generation over a good one."""
    from spark.ingestion.parsers.base import ParserError

    pages = [(p, "Title: EE-07", "text") for p in (1, 2, 3)]

    async def _all_fail(image, *, llm_profile="vision_extract", fallback_profiles=(), timeout_seconds=600.0):
        return DiagramExtraction(analysis="", parsed_ok=False)

    with (
        patch(
            "spark.ingestion.parse.pdf_vector_density.vector_drawing_pages",
            return_value={1, 2, 3},
        ),
        patch("spark.ingestion.parsers.pdf_parser.rasterize_pdf_page", return_value=object()),
        patch("spark.ingestion.parsers.pdf_parser.extract_diagram_page", new=_all_fail),
    ):
        try:
            await _apply_vision_extraction(Path("wiring_diagram.pdf"), pages, {})
        except ParserError as exc:
            assert exc.reason_code == "vision_backend_unavailable"
        else:
            raise AssertionError("expected ParserError when all vision pages return nothing")


async def test_apply_vision_extraction_tolerates_one_failed_page() -> None:
    """One bad page still degrades gracefully — only a *total* wipeout is fatal."""
    pages = [(p, "Title: EE-07", "text") for p in (1, 2)]

    async def _one_fails(image, *, llm_profile="vision_extract", fallback_profiles=(), timeout_seconds=600.0):
        page = getattr(image, "page", 1)
        if page == 1:
            return DiagramExtraction(analysis="", parsed_ok=False)
        return DiagramExtraction(analysis=_STRUCTURED_ANALYSIS, parsed_ok=True)

    class _Img:
        def __init__(self, page):
            self.page = page

    with (
        patch(
            "spark.ingestion.parse.pdf_vector_density.vector_drawing_pages",
            return_value={1, 2},
        ),
        patch(
            "spark.ingestion.parsers.pdf_parser.rasterize_pdf_page",
            side_effect=lambda _p, page_num, dpi=200: _Img(page_num),
        ),
        patch("spark.ingestion.parsers.pdf_parser.extract_diagram_page", new=_one_fails),
    ):
        updated, needs_review, extractions = await _apply_vision_extraction(
            Path("wiring_diagram.pdf"), pages, {}
        )
    assert needs_review == {1}
    assert extractions[2].parsed_ok


async def test_pdf_parser_drops_phantom_tables_on_vision_pages() -> None:
    """pdfplumber reads a schematic's border/coordinate grid as 'tables'
    ("| F | E | D | C | B |") — observed 80 of them on one real 14-sheet
    wiring binder. Pages that went through vision extraction must not emit
    table chunks."""
    from spark.ingestion.parsers.pdf_parser import PDFParser
    from spark.ingestion.parse.layout.types import LayoutBlock, LayoutPage
    from spark.ingestion.parse.table_object import TableObject

    layout_page = LayoutPage(
        page_number=1,
        blocks=[
            LayoutBlock(
                block_id="page-1",
                page_number=1,
                block_type="text",
                text="Title: EE-07 wiring",
                extraction_source="text",
            )
        ],
        extraction_source="text",
    )

    class _FakeLayoutParser:
        name = "fake"

        def parse(self, _path):
            return 1, [layout_page], []

    phantom = TableObject(
        markdown="| F | E | D |\n| --- | --- | --- |", headers=[], rows=[], page=1
    )

    config = {
        "document_type": "drawing",
        "vision": {"enabled": True},
        "_doc_id": "11111111-1111-1111-1111-111111111111",
    }

    with (
        patch(
            "spark.ingestion.parsers.pdf_parser.get_layout_parser",
            return_value=_FakeLayoutParser(),
        ),
        patch(
            "spark.ingestion.parse.pdf_vector_density.vector_drawing_pages",
            return_value={1},
        ),
        patch(
            "spark.ingestion.parsers.pdf_parser.rasterize_pdf_page",
            return_value=object(),
        ),
        patch(
            "spark.ingestion.parsers.pdf_parser.extract_diagram_page",
            new=AsyncMock(
                return_value=DiagramExtraction(analysis=_STRUCTURED_ANALYSIS, parsed_ok=True)
            ),
        ),
        patch(
            "spark.ingestion.parsers.pdf_parser._extract_table_objects",
            return_value=[phantom],
        ),
    ):
        records = [
            rec async for rec in PDFParser().parse(Path("wiring_diagram.pdf"), config)
        ]

    assert records, "vision page text chunks must still be indexed"
    assert all(r.payload.get("chunk_level") != "table" for r in records), (
        "phantom grid tables from a vector-drawing page must be dropped"
    )


async def test_apply_vision_extraction_bounds_concurrency() -> None:
    """A 14-sheet wiring binder flags most/all pages as vector-drawing — the
    vision-LLM fan-out must not fire every page's call at once (GPU sidecar /
    provider rate-limit risk)."""
    pages = [(p, "", "text") for p in range(1, 15)]
    concurrent = 0
    max_seen = 0

    async def _fake_extract(image, *, llm_profile="vision_extract", fallback_profiles=(), timeout_seconds=480.0):
        nonlocal concurrent, max_seen
        concurrent += 1
        max_seen = max(max_seen, concurrent)
        await asyncio.sleep(0.01)
        concurrent -= 1
        return DiagramExtraction(analysis="ok", parsed_ok=True)

    with (
        patch(
            "spark.ingestion.parse.pdf_vector_density.vector_drawing_pages",
            return_value=set(range(1, 15)),
        ),
        patch(
            "spark.ingestion.parsers.pdf_parser.rasterize_pdf_page",
            return_value=object(),
        ),
        patch(
            "spark.ingestion.parsers.pdf_parser.extract_diagram_page",
            new=_fake_extract,
        ),
    ):
        await _apply_vision_extraction(
            Path("wiring_diagram.pdf"), pages, {"max_concurrency": 3}
        )

    assert max_seen <= 3


# --- Document-level synthesis (cross-page device index + system overview) ---

_PAGE5_ANALYSIS = (
    "### ภาพรวมหน้านี้\n"
    "วงจรควบคุมมอเตอร์ตัด\n\n"
    "### อุปกรณ์ทั้งหมดในหน้านี้\n"
    "| Device Tag | ชนิด/หน้าที่ | Terminal ที่อ่านได้ |\n"
    "|---|---|---|\n"
    "| M18 | มอเตอร์ตัด | U, V, W |\n"
    "| MC1 | Magnetic Contactor | A1, A2 |\n\n"
    "### การจ่ายไฟและกราวด์\n"
    "AC 380V ผ่าน MC1 ไป M18\n"
)


def test_device_tags_from_analysis_parses_table_rows() -> None:
    tags = device_tags_from_analysis(_PAGE5_ANALYSIS)
    assert tags == ["M18", "MC1"]


def test_device_tags_from_analysis_skips_header_and_thai_rows() -> None:
    analysis = (
        "### อุปกรณ์ทั้งหมดในหน้านี้\n"
        "| Device Tag | ชนิด/หน้าที่ | Terminal ที่อ่านได้ |\n"
        "|---|---|---|\n"
        "| อ่านไม่ชัด | มอเตอร์ | - |\n"
        "| M9 | มอเตอร์ | 1, 2 |\n"
    )
    assert device_tags_from_analysis(analysis) == ["M9"]


def test_build_device_page_index_merges_pages() -> None:
    index_md = build_device_page_index({3: _STRUCTURED_ANALYSIS, 5: _PAGE5_ANALYSIS})
    assert "| M18 | 3, 5 |" in index_md
    assert "| MC1 | 5 |" in index_md
    assert "Device Index" in index_md
    # Adjacency from page 3's connection table (MC1:2 → M18:U1), stored compactly
    # as each device's neighbour rather than the raw row text.
    assert "**M18**:" in index_md
    assert "MC1:2 [W101]" in index_md
    assert "**MC1**:" in index_md
    assert "M18:U1 [W101]" in index_md
    assert "ผลกระทบเมื่ออุปกรณ์เสีย" in index_md


def test_build_device_page_index_empty_when_no_tables() -> None:
    assert build_device_page_index({1: "no tables here"}) == ""


def test_build_device_page_index_tolerates_h2_headings() -> None:
    """The VLM is inconsistent about heading depth — some pages come back with
    ## instead of the ### the skeleton asks for. Matching only ### silently
    dropped whole pages (real regression: page 8 with M17–M21). The index must
    parse either level."""
    h2_analysis = _STRUCTURED_ANALYSIS.replace("### ", "## ")
    index_md = build_device_page_index({8: h2_analysis})
    assert "| M18 | 8 |" in index_md
    assert "MC1:2 [W101]" in index_md


# --- Endpoint / tag parsing helpers ---------------------------------------


def test_split_endpoint_handles_colon_and_spaced_dash() -> None:
    assert _split_endpoint("M18:GND") == ("M18", "GND")
    assert _split_endpoint("ORIENTAL AZD-KEP - GND") == ("ORIENTAL AZD-KEP", "GND")
    # internal dash of a device name (no surrounding spaces) is not a separator
    assert _split_endpoint("AZXD-SEP 1") == ("AZXD-SEP 1", "")


def test_expand_tags_splits_grouped_devices() -> None:
    assert _expand_tags("M5/M6") == ["M5", "M6"]
    # a bare numeric suffix inherits the alpha prefix of the previous member
    assert _expand_tags("AZXD-SEP 1/2") == ["AZXD-SEP 1", "AZXD-SEP 2"]
    assert _expand_tags("M18") == ["M18"]


def test_endpoints_in_cell_multi_device_shorthand() -> None:
    # several devices sharing a rail, listed in one cell
    eps = _endpoints_in_cell("M17:GND, M18:GND, M19:GND")
    assert eps == [("M17", "GND"), ("M18", "GND"), ("M19", "GND")]
    # a bare token after a Tag:Terminal is an extra terminal, not a new device
    assert _endpoints_in_cell("M5:1L1, 1N, PE") == [
        ("M5", "1L1"),
        ("M5", "1N"),
        ("M5", "PE"),
    ]


def test_is_real_net_rejects_thai_gloss() -> None:
    assert _is_real_net("DCC2_24V")
    assert _is_real_net("J1")
    assert _is_real_net("+24VDC")
    # the VLM fills the net column with a Thai description when it can't read it
    assert not _is_real_net("สายสัญญาณที่ไม่เห็นชัด")
    assert not _is_real_net("-")
    assert not _is_real_net("")


def test_rail_tokens_detects_power_and_ground() -> None:
    assert _rail_tokens("+24VDC / GND") == ["+24VDC", "GND"]
    assert "DCC2_24V" in _rail_tokens("DCC2_24V")
    assert _rail_tokens("M18") == []


_SHARED_BUS_ANALYSIS = (
    "## ภาพรวมหน้านี้\n"
    "ห้ามอเตอร์ Cut Back Slide ใช้บัส DC ร่วมกัน\n\n"
    "## อุปกรณ์ทั้งหมดในหน้านี้\n"
    "| Device Tag | ชนิด/หน้าที่ | Terminal ที่อ่านได้ |\n"
    "|---|---|---|\n"
    "| M17 | มอเตอร์ | GND |\n"
    "| M18 | มอเตอร์ | GND |\n"
    "| M19 | มอเตอร์ | GND |\n"
    "| ORIENTAL AZD-KEP | ไดรฟ์ | GND |\n\n"
    "## ตารางการเชื่อมต่อ\n"
    "| จาก (Tag:Terminal) | ไป (Tag:Terminal) | Net/Wire No. | หมายเหตุ |\n"
    "|---|---|---|---|\n"
    "| +24VDC / GND | ORIENTAL AZD-KEP:GND; M17:GND, M18:GND, M19:GND | สายไม่ชัด | บัสร่วม |\n"
)


def test_build_device_page_index_bus_row_stays_compact_and_lists_members() -> None:
    """A bus row names many devices at once. Expanding it pairwise is both wrong
    (a shared rail is not a wire between every pair) and quadratic — it produced
    an 87k-char index that silently truncated at embed time (bge-m3: 8192 tok).
    Membership must come from the net index, and the index must stay small."""
    bus = ", ".join(f"M{i}:GND" for i in range(1, 25))
    analysis = (
        "## อุปกรณ์ทั้งหมดในหน้านี้\n"
        "| Device Tag | ชนิด | Terminal |\n|---|---|---|\n"
        + "\n".join(f"| M{i} | มอเตอร์ | GND |" for i in range(1, 25))
        + "\n\n## ตารางการเชื่อมต่อ\n"
        "| จาก | ไป | Net/Wire No. | หมายเหตุ |\n|---|---|---|---|\n"
        f"| +24VDC / GND | {bus} | สายไม่ชัด | บัสร่วม |\n"
    )
    index_md = build_device_page_index({p: analysis for p in range(1, 15)})
    assert len(index_md) < 20000, f"index blew up to {len(index_md)} chars"
    # a device that only ever sits on a shared rail still gets a findable line
    lines = index_md.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith("- **M18**"))
    block = "\n".join(lines[start : start + 2])
    assert "อยู่บนบัส/เน็ตร่วม" in block
    assert "M17" in block


def test_split_doc_level_markdown_bounds_pieces() -> None:
    """Doc-level artifacts are emitted as atomic page-0 chunks (the chunker never
    splits them), so they must be pre-split to stay inside the embedder."""
    text = "## 🔎 ดัชนีอุปกรณ์ทั้งเอกสาร (Device Index)\n\n" + "\n".join(
        f"| M{i} | 1, 2, 3 | มอเตอร์สายพานตัวที่ {i} |" for i in range(400)
    )
    pieces = split_doc_level_markdown(text, max_chars=3000)
    assert len(pieces) > 1
    assert all(len(p) <= 3200 for p in pieces)
    # every piece keeps the heading so it is self-describing when retrieved alone
    assert all("Device Index" in p for p in pieces)
    # nothing is dropped
    assert sum(p.count("| M") for p in pieces) == 400


def test_build_device_page_index_shared_bus_impact() -> None:
    """The payoff case: 'if M18 fails, what else is affected?' The shared +24VDC/
    GND rail must surface every device on it, even though the printed wire label
    was unreadable (net column is a Thai gloss)."""
    index_md = build_device_page_index({8: _SHARED_BUS_ANALYSIS})
    # a Net / Shared-Bus section exists and groups the rail members
    assert "Net / Shared-Bus Index" in index_md
    # M18's adjacency block carries a shared-bus note naming its rail mates
    lines = index_md.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith("- **M18**"))
    m18_block = "\n".join(lines[start : start + 2])
    assert "อยู่บนบัส/เน็ตร่วม" in m18_block
    assert "M17" in m18_block and "M19" in m18_block
    # the unreadable Thai net label must not become a net key
    assert "สายไม่ชัด" not in index_md


async def test_synthesize_document_overview_returns_model_text() -> None:
    overview = "### ภาพรวมระบบทั้งหมด\nระบบสายพาน (หน้า 3, 5)"
    captured: dict = {}
    mock_llm = _streaming_llm(overview, captured)
    with patch("spark.core.llm_client.get_chat_llm", return_value=mock_llm):
        result = await synthesize_document_overview(
            {3: _STRUCTURED_ANALYSIS, 5: _PAGE5_ANALYSIS}
        )
    assert "ภาพรวมระบบทั้งหมด" in result
    prompt_sent = captured["messages"][0].content
    assert "หน้า 3" in prompt_sent
    assert "หน้า 5" in prompt_sent


async def test_synthesize_document_overview_degrades_to_empty_on_failure() -> None:
    with patch("spark.core.llm_client.get_chat_llm", side_effect=RuntimeError("gateway down")):
        result = await synthesize_document_overview(
            {3: _STRUCTURED_ANALYSIS, 5: _PAGE5_ANALYSIS}
        )
    assert result == ""


async def test_synthesize_document_overview_skips_single_page() -> None:
    # A one-sheet drawing has nothing cross-page to synthesize — no LLM call.
    with patch("spark.core.llm_client.get_chat_llm") as mock_get:
        result = await synthesize_document_overview({1: _STRUCTURED_ANALYSIS})
    assert result == ""
    mock_get.assert_not_called()


async def test_pdf_parser_emits_document_level_chunks() -> None:
    """A multi-sheet binder must yield page-0 device-index and system-overview
    chunks on top of the per-page analyses."""
    from spark.ingestion.parse.layout.types import LayoutBlock, LayoutPage
    from spark.ingestion.parsers.pdf_parser import PDFParser

    layout_pages = [
        LayoutPage(
            page_number=p,
            blocks=[
                LayoutBlock(
                    block_id=f"page-{p}",
                    page_number=p,
                    block_type="text",
                    text=f"Title: EE-07 sheet {p}",
                    extraction_source="text",
                )
            ],
            extraction_source="text",
        )
        for p in (1, 2)
    ]

    class _FakeLayoutParser:
        name = "fake"

        def parse(self, _path):
            return 2, layout_pages, []

    analyses = {1: _STRUCTURED_ANALYSIS, 2: _PAGE5_ANALYSIS}

    async def _fake_extract(image, *, llm_profile="vision_extract", fallback_profiles=(), timeout_seconds=480.0):
        page = getattr(image, "page", 1)
        return DiagramExtraction(analysis=analyses[page], parsed_ok=True)

    class _FakeImage:
        def __init__(self, page):
            self.page = page

    config = {
        "document_type": "drawing",
        "vision": {"enabled": True},
        "_doc_id": "11111111-1111-1111-1111-111111111111",
    }

    with (
        patch(
            "spark.ingestion.parsers.pdf_parser.get_layout_parser",
            return_value=_FakeLayoutParser(),
        ),
        patch(
            "spark.ingestion.parse.pdf_vector_density.vector_drawing_pages",
            return_value={1, 2},
        ),
        patch(
            "spark.ingestion.parsers.pdf_parser.rasterize_pdf_page",
            side_effect=lambda _path, page_num, dpi=200: _FakeImage(page_num),
        ),
        patch(
            "spark.ingestion.parsers.pdf_parser.extract_diagram_page",
            new=_fake_extract,
        ),
        patch(
            "spark.ingestion.parsers.pdf_parser._extract_table_objects",
            return_value=[],
        ),
        patch(
            "spark.ingestion.parsers.vision_diagram.synthesize_document_overview",
            new=AsyncMock(return_value="### ภาพรวมระบบทั้งหมด\nระบบตัวอย่าง (หน้า 1)"),
        ),
    ):
        records = [
            rec async for rec in PDFParser().parse(Path("wiring_diagram.pdf"), config)
        ]

    doc_level = [r for r in records if r.payload.get("page") == 0]
    section_paths = {r.payload.get("section_path") for r in doc_level}
    assert any("Device Index" in s for s in section_paths)
    assert any("System Overview" in s for s in section_paths)
    index_chunk = next(r for r in doc_level if "Device Index" in r.payload["section_path"])
    assert "M18" in index_chunk.payload["page_content"]
    for record in doc_level:
        assert record.payload["parent_chunk_id"] == ""
        assert record.payload["parent_content"] == record.payload["page_content"]
