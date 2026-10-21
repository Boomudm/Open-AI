"""Industrial token extraction — part numbers, alarm codes, machine IDs."""

from __future__ import annotations

import re

_MACHINE_ID_RE = re.compile(r"\b[A-Z]{2,8}[-_]?\d{2,8}\b", re.IGNORECASE)
_PART_CODE_PREFIXES = frozenset({"BRG", "CAP", "FAN", "SEAL", "SKF", "ISO", "VGB"})
_SUBSTANTIVE_NUMBER_RE = re.compile(
    r"\d{2,}(?:\.\d+)?|\d+(?:°|°c|%|mm|cm|v|a|hz|kw|bar|psi|rpm|hour|hrs?|min)\b",
    re.IGNORECASE,
)
_ALARM_CODE_RE = re.compile(r"\b(?:E|ALM|ERR|F)[- ]?\d{2,5}\b", re.IGNORECASE)
# Trailing-"h" hex notation as drive/servo manuals print it: alarm codes ("26h
# Motor overheat") and register addresses ("2240h", "23E0h" — the bulk of this
# corpus). The substantive-number extractor keeps only the digits, so without
# this the code indexes as bare "26" and collides with page numbers and model
# suffixes (AZM26) — alarm lookups then hit or miss on phrasing alone.
# Width spans 1–8 hex digits to cover both 8-bit codes and 32-bit addresses.
# The leading digit is what separates codes from English words that happen to be
# all hex letters ("each", "ach", "ch").
_HEX_ALARM_CODE_RE = re.compile(r"\b\d[0-9a-f]{0,7}h\b", re.IGNORECASE)
_HWTO_EDM_RE = re.compile(r"\bHWTO\d?\b|\bEDM\b", re.IGNORECASE)
# IEC-60617/JIC device designators as printed on machine wiring diagrams: a
# short curated letter prefix + a small number (K1 relay, Q1/QF1/QM1 breaker,
# F2 fuse, X1/TB1 terminal block, S1/SW1 switch, PB1 push button, CB1/MCB2/
# MCCB1/ELB1 breakers, PS1 power supply, KM1/KA1 contactor/relay, H1/HL1 lamp,
# Y1/SV1 solenoid, B1 sensor, R3 relay, T1 transformer, U1/VSD1 drive, CN1
# connector). Deliberately a closed prefix set: an open [A-Z]\d scan over a
# whole manual floods boost_tokens with figure/page refs ("A4", "D2") that
# displace real tags under the token cap. M\d is covered by _AXIS_ID_RE
# already. Hyphenated machine ids ("SV-01") never match — a digit must follow
# the prefix directly.
_IEC_DEVICE_TAG_RE = re.compile(
    r"\b(?:CB|MCB|MCCB|ELB|ELCB|RCBO|TB|PS|PB|SW|FU|KM|KA|QF|QM|SB|SV|VSD|HL"
    r"|CN|CR|OL|XT|[BFGHKQRSTUXY])\d{1,3}\b",
    re.IGNORECASE,
)
# "Tag:Terminal" endpoint refs exactly as the vision connection tables print
# them ("X1:5", "M18:GND", "CN1:3"). The device half is emitted separately in
# extract_industrial_tokens so "X1:5 ต่อไปไหน" exact-matches the table row
# while plain "X1" still reaches the device index. The letters-then-digits
# shape before the colon keeps times ("12:30") and prose colons out.
_TERMINAL_REF_RE = re.compile(r"\b[A-Za-z]{1,6}\d{1,4}:[A-Za-z0-9+\-]{1,10}\b")
# Power/ground rail tokens as printed on drawings (+24VDC, 0V, DC24V, L1..L3
# incl. 1L1 downstream-of-breaker numbering). Rails are how technicians name
# what feeds a device, and the doc-level Net/Bus index stores them verbatim —
# matching "24VDC" lexically is what connects "แหล่งจ่ายไฟ 24VDC มาจากไหน" to
# the right net rows instead of the bare number "24".
_RAIL_VOLT_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:[+\-]?\d{1,3}\s?V(?:DC|AC)|DC\d{1,2}V|0V|[1-9]?L[123])"
    r"(?![A-Za-z0-9])",
    re.IGNORECASE,
)
# GND/PE stay case-sensitive: lowercase "pe" is an English syllable, and the
# drawings only ever print these uppercase.
_RAIL_NAME_RE = re.compile(r"\b(?:GND|PE)\b")
# All-caps hyphenated model codes with no digits ("AZD-KEP", "SPD-CTRL") —
# _MODEL_CODE_RE requires two digits so these were invisible. Case-sensitive:
# lowercase hyphenated English ("non-excitation") must not match.
_CAPS_HYPHEN_MODEL_RE = re.compile(r"\b[A-Z]{2,8}(?:-[A-Z]{2,8})+\b")
_PART_CODE_RE = re.compile(
    r"\b(?:SKF[- ]?\d{3,5}|ISO[- ]?\d+|6205|6308|PN[- ]?\d{3,6}|E-\d{2,4})\b",
    re.IGNORECASE,
)
_MODEL_CODE_RE = re.compile(
    r"\b[A-Z]{2,8}\d[A-Z0-9]*\d[A-Z0-9]*(?:-\d+)?\b",
    re.IGNORECASE,
)
_AXIS_ID_RE = re.compile(r"\bM\d{1,3}\b", re.IGNORECASE)
_SYMBOLIC_NAME_RE = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+){1,}\b")
_MACHINE_ID_LABEL_RE = re.compile(r"\b(?:MC|MX|MCH|LINE)[-_ ]?\d{2,6}\b", re.IGNORECASE)
# PLC/IO-mapping symbol paths, e.g. "RES0.BELT_CALIB_SENSOR" or
# "RES0.MODBUSRREG8_Operation_Control_3_10.r2LinkName".
_PLC_TAG_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9]*\d*(?:\.[A-Za-z_]\w*){1,}\b")
_PLC_TAG_SUFFIX_STOPLIST = frozenset(
    {
        "pdf",
        "xlsx",
        "xls",
        "csv",
        "doc",
        "docx",
        "txt",
        "md",
        "png",
        "jpg",
        "jpeg",
        "gif",
        "svg",
        "json",
        "yaml",
        "yml",
        "xml",
        "html",
        "htm",
        "zip",
        "dwg",
        "dxf",
        "step",
        "stp",
        "com",
        "net",
        "org",
        "io",
        "co",
        "th",
        "de",
        "jp",
        "cn",
        "www",
    }
)


def _is_likely_machine_identifier(raw: str) -> bool:
    match = re.match(r"([A-Z]{2,8})[-_]?\d", str(raw or "").upper())
    if not match:
        return False
    return match.group(1) not in _PART_CODE_PREFIXES


def _raw_machine_ids_in_text(text: str) -> set[str]:
    return {
        match.group(0)
        for match in _MACHINE_ID_RE.finditer(text or "")
        if _is_likely_machine_identifier(match.group(0))
    }


def _extract_substantive_numbers(text: str) -> set[str]:
    # Hex runs are consumed by _HEX_ALARM_CODE_RE, so blank them out first. The
    # digits of a hex literal are not a decimal quantity ("2240h" is 8768, not
    # 2240), and emitting them as one is actively harmful: the bare "20" carries
    # a 2.0 rank boost that hits 331 chunks (page numbers, model suffixes) while
    # only 4 document "20h", burying the real answer. Masking rather than a
    # lookahead also stops the number pattern from backtracking into a partial
    # prefix and emitting junk like "052" out of "0520h".
    masked = _HEX_ALARM_CODE_RE.sub(" ", text or "")
    return {m.lower() for m in _SUBSTANTIVE_NUMBER_RE.findall(masked)}


def _is_plausible_plc_tag(tag: str) -> bool:
    segments = tag.split(".")
    if segments[-1].lower() in _PLC_TAG_SUFFIX_STOPLIST:
        return False
    return any(re.search(r"[\d_]", seg) for seg in segments)


def extract_plc_tags(text: str) -> list[str]:
    """Return dotted PLC/IO symbol paths, filtering out filenames and domains."""
    seen: set[str] = set()
    tags: list[str] = []
    for match in _PLC_TAG_RE.finditer(text or ""):
        tag = match.group(0)
        if tag in seen or not _is_plausible_plc_tag(tag):
            continue
        seen.add(tag)
        tags.append(tag)
    return tags


def has_plc_tag(text: str) -> bool:
    return bool(extract_plc_tags(text))


def extract_symbolic_names(text: str) -> list[str]:
    """Return bare PLC/IO symbolic names such as ``SERVO_PEEL_D3``.

    These names often appear in technician questions without the ``RES0.``
    prefix, so the dotted PLC tag detector alone is not enough.
    """
    seen: set[str] = set()
    names: list[str] = []
    for match in _SYMBOLIC_NAME_RE.finditer(text or ""):
        name = match.group(0).strip()
        if name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def extract_industrial_tokens(text: str, *, limit: int = 24) -> list[str]:
    """Structured tokens for index/query boost (part numbers, alarms, machine IDs)."""
    normalized = (text or "").strip()
    if not normalized:
        return []

    terms: set[str] = set(_raw_machine_ids_in_text(normalized))
    terms.update(_extract_substantive_numbers(normalized))
    # Tag:Terminal refs carry their device half as its own token — the full ref
    # matches a connection-table row, the device half matches the device index.
    for match in _TERMINAL_REF_RE.finditer(normalized):
        device_half = match.group(0).split(":", 1)[0].strip().upper()
        if len(device_half) >= 2:
            terms.add(device_half)
    for pattern in (
        _PART_CODE_RE,
        _MODEL_CODE_RE,
        _AXIS_ID_RE,
        _ALARM_CODE_RE,
        _HEX_ALARM_CODE_RE,
        _MACHINE_ID_LABEL_RE,
        _HWTO_EDM_RE,
        _IEC_DEVICE_TAG_RE,
        _TERMINAL_REF_RE,
        _RAIL_VOLT_RE,
        _RAIL_NAME_RE,
        _CAPS_HYPHEN_MODEL_RE,
        _PLC_TAG_RE,
        _SYMBOLIC_NAME_RE,
    ):
        for match in pattern.finditer(normalized):
            token = match.group(0).strip().upper().replace(" ", "-")
            if len(token) >= 2:
                terms.add(token)
    ranked = sorted(terms, key=lambda t: (-len(t), t))
    return ranked[:limit]
