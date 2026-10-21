"""Parser plugin registry."""

from __future__ import annotations

from spark.ingestion.parsers.base import ParserPlugin
from spark.ingestion.parsers.excel_parser import ExcelParser
from spark.ingestion.parsers.image_ocr_parser import ImageOCRParser
from spark.ingestion.parsers.json_parser import JSONParser
from spark.ingestion.parsers.pdf_parser import PDFParser
from spark.ingestion.parsers.text_parser import TextParser
from spark.ingestion.parsers.word_parser import WordParser

PARSER_REGISTRY: dict[str, type[ParserPlugin]] = {
    "pdf": PDFParser,
    "excel": ExcelParser,
    "word": WordParser,
    "json": JSONParser,
    "text": TextParser,
    "image_ocr": ImageOCRParser,
}


def get_parser(name: str) -> ParserPlugin:
    if name not in PARSER_REGISTRY:
        raise ValueError(f"Unknown parser: {name}. Available: {list(PARSER_REGISTRY)}")
    return PARSER_REGISTRY[name]()
