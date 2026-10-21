"""Index consistency errors."""


class IndexDriftError(Exception):
    """Raised when Qdrant point count or payload diverges from PG mirror."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.reason_code = "index_drift"
        self.reason_detail = detail
