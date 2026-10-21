"""OCR preprocess unit tests (no tesseract required)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from spark.ingestion.parsers.image_ocr_parser import _preprocess_image


def test_preprocess_contrast_only() -> None:
    try:
        from PIL import Image
    except ImportError:
        return
    img = Image.new("RGB", (40, 40), color=(128, 128, 128))
    out = _preprocess_image(img, {"contrast": 1.5})
    assert out is not None


def test_preprocess_deskew_skipped_without_opencv() -> None:
    try:
        from PIL import Image
    except ImportError:
        return
    img = Image.new("RGB", (40, 40), color=(255, 255, 255))
    with patch.dict("sys.modules", {"cv2": None}):
        out = _preprocess_image(img, {"deskew": True})
    assert out is not None


def test_preprocess_noop_when_empty_config() -> None:
    sentinel = MagicMock()
    assert _preprocess_image(sentinel, None) is sentinel
