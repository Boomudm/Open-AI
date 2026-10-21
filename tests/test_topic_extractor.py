from spark.services.topic_extractor import extract_topic


def test_extract_bearing_thai() -> None:
    m = extract_topic("MC-001 ใช้ลูกปืนเบอร์อะไร")
    assert m.topic_label == "bearing"
    assert m.topic_confidence >= 0.5


def test_extract_overheat() -> None:
    m = extract_topic("เครื่องร้อนผิดปกติ")
    assert m.topic_label == "overheat"


def test_extract_unknown_short() -> None:
    m = extract_topic("hi")
    assert m.topic_label in (None, "general_en")
