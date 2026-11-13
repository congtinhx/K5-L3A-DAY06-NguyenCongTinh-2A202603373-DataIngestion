"""Doc PDF, chuan hoa van ban, gan metadata truy nguon."""
import re
import unicodedata
from pathlib import Path

from pypdf import PdfReader

from .models import DocumentPage

HEADER_RE = re.compile(r"^(\d{1,3}\s*\|.*|.{0,45}\|\s*\d{1,3})$")
NUMERIC_LINE_RE = re.compile(r"^[\d\s.,%()\u2013\-+/]+$")
NOTES_RE = re.compile(r"\nNotes\n\s*1\.\s")


def build_vocabulary(texts: list[str]) -> set[str]:
    """Tap tu trong tai lieu, dung de quyet dinh cach noi tu bi ngat dong."""
    vocab: set[str] = set()
    for t in texts:
        vocab.update(w.lower() for w in re.findall(r"\w+", unicodedata.normalize("NFKC", t)))
    return vocab


def normalize_text(text: str, vocab: set[str] | None = None) -> str:
    """Chuan hoa Unicode (NFKC), khoang trang, noi tu bi ngat dong; giu ranh gioi dong."""
    vocab = vocab or set()
    text = unicodedata.normalize("NFKC", text).replace("\r", "")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    text = re.sub(r"[ \t]+", " ", text)

    def join(m: re.Match) -> str:
        left, right = m.group(1), m.group(2)
        return left + right if (left + right).lower() in vocab else f"{left}-{right}"

    text = re.sub(r"(\w+) ?-\s*\n\s*(\w+)", join, text)
    text = text.replace("(Box continues next page)", "")
    lines = [line.strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


def strip_layout_noise(text: str) -> tuple[str, int | None]:
    """Bo header/footer va dong chi co so; tra ve (text, so trang in tren giay)."""
    lines = text.split("\n")
    printed_page = None
    if lines:
        m = re.search(r"\d{1,3}", lines[0])
        if m and (HEADER_RE.match(lines[0]) or lines[0].isdigit()):
            printed_page = int(m.group())
    kept = [ln for ln in lines if not HEADER_RE.match(ln) and not NUMERIC_LINE_RE.match(ln)]
    return "\n".join(kept), printed_page


def cut_notes(text: str) -> tuple[str, bool]:
    """Cat phan Notes/References cuoi chuong."""
    m = NOTES_RE.search("\n" + text)
    if not m:
        return text, False
    return text[: max(m.start() - 1, 0)].rstrip(), True


def section_for(page: int, sections: list[tuple[int, int, str]]) -> str | None:
    for start, end, name in sections:
        if start <= page <= end:
            return name
    return None


def load_pdf(path: Path, document_id: str, source: str,
             sections: list[tuple[int, int, str]] | None = None,
             skip_pages: list[int] | None = None,
             errors: list[str] | None = None) -> list[DocumentPage]:
    """Doc tung trang, giu so trang PDF va nguon; ghi trang rong/loi vao errors."""
    errors = errors if errors is not None else []
    sections = sections or []
    skip_pages = set(skip_pages or [])
    if not path.exists():
        raise FileNotFoundError(f"Khong tim thay file PDF: {path}")

    reader = PdfReader(str(path))
    raws: dict[int, str] = {}
    for index, pdf_page in enumerate(reader.pages, start=1):
        if index in skip_pages:
            errors.append(f"{document_id} p{index}: SKIPPED (khai bao trong config, khong phai noi dung)")
            continue
        try:
            raws[index] = pdf_page.extract_text() or ""
        except Exception as exc:
            errors.append(f"{document_id} p{index}: EXTRACT_ERROR {exc!r}")

    vocab = build_vocabulary(list(raws.values()))
    pages: list[DocumentPage] = []
    for index, raw in raws.items():
        if not raw.strip():
            errors.append(f"{document_id} p{index}: EMPTY (khong co text, can OCR neu la scan)")
            continue
        bad_chars = sum(1 for ch in raw if ch == "\x00" or (ord(ch) < 32 and ch not in "\n\t\r"))
        if bad_chars:
            errors.append(f"{document_id} p{index}: CONTROL_CHARS_REMOVED {bad_chars} ky tu rac (vd NUL 0x00)")        
        text = normalize_text(raw, vocab)
        text, printed_page = strip_layout_noise(text)
        text, notes_removed = cut_notes(text)
        if notes_removed:
            errors.append(f"{document_id} p{index}: NOTES_REMOVED (da cat phan Notes/References)")
        pages.append(DocumentPage(
            document_id=document_id,
            source=source,
            page=index,
            text=text,
            metadata={
                "printed_page": printed_page,
                "section": section_for(index, sections),
                "raw_chars": len(raw),
                "chars": len(text),
                "notes_removed": notes_removed,
            },
        ))
    return pages