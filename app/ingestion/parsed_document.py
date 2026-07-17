from dataclasses import dataclass, field


@dataclass
class ParsedDocument:
    """Normalized text/tables from a PDF parse or image OCR pass."""

    text: str
    tables: list[list[list[str]]] = field(default_factory=list)
    page_count: int = 0
    char_count: int = 0
