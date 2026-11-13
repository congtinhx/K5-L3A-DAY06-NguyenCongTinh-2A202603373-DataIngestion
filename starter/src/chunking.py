"""Hai cach chia chunk: kich thuoc co dinh (A) va theo cau/heading (B, C)."""
import re

from .models import Chunk, DocumentPage

HEADING_RE = re.compile(r"^(Box|Figure|Table)\s+[A-Z]?\d|^(Key messages|Introduction|Spotlight)$")
SENTENCE_END_RE = re.compile(
    r"(?<=[.!?\u201d\"])\s+(?=[A-Z\u201c\"(\u2022])|(?<=[.!?]\d)\s+(?=[A-Z\u201c\"(\u2022])|\s(?=\u2022)")


def _make_chunk(prefix: str, page: DocumentPage, idx: int, start: int, end: int,
                flat: str, strategy: str) -> Chunk:
    return Chunk(
        chunk_id=f"{prefix}:{page.document_id}:p{page.page:03d}:c{idx:03d}",
        document_id=page.document_id,
        source=page.source,
        page=page.page,
        text=flat[start:end],
        metadata={
            **{k: page.metadata.get(k) for k in ("section", "printed_page")},
            "char_start": start,
            "char_end": end,
            "strategy": strategy,
        },
    )


def _trim(flat: str, start: int, end: int) -> tuple[int, int]:
    while start < end and flat[start].isspace():
        start += 1
    while end > start and flat[end - 1].isspace():
        end -= 1
    return start, end


def fixed_size(page: DocumentPage, size: int, overlap: int, prefix: str = "A") -> list[Chunk]:
    """Cat cua so size ky tu, chong lan overlap ky tu."""
    if size <= 0 or not 0 <= overlap < size:
        raise ValueError("Can 0 <= overlap < size")
    flat = page.text.replace("\n", " ")
    chunks, step, idx = [], size - overlap, 0
    for start in range(0, len(flat), step):
        s, e = _trim(flat, start, min(start + size, len(flat)))
        if e > s:
            chunks.append(_make_chunk(prefix, page, idx, s, e, flat, "fixed_size"))
            idx += 1
        if start + size >= len(flat):
            break
    return chunks


def _units(text: str) -> list[tuple[int, int, bool]]:
    """Tach trang thanh cau/bullet/heading: (start, end, is_heading)."""
    flat = text.replace("\n", " ")
    hard_starts, pos = set(), 0
    for line in text.split("\n"):
        if HEADING_RE.match(line):
            hard_starts.add(pos)
        pos += len(line) + 1
    cuts = {0, len(flat)} | hard_starts
    cuts |= {m.end() for m in SENTENCE_END_RE.finditer(flat)}
    ordered = sorted(cuts)
    return [(a, b, a in hard_starts) for a, b in zip(ordered, ordered[1:]) if b > a]


def _merge_small(spans: list[tuple[int, int]], min_size: int, max_size: int) -> list[tuple[int, int]]:
    """Gop chunk qua ngan vao chunk ke tiep (hoac chunk truoc)."""
    spans = list(spans)
    i = 0
    while i < len(spans):
        s, e = spans[i]
        if e - s < min_size and len(spans) > 1:
            if i + 1 < len(spans) and spans[i + 1][1] - s <= max_size:
                spans[i + 1] = (s, spans[i + 1][1])
                del spans[i]
                continue
            if i > 0 and e - spans[i - 1][0] <= max_size:
                spans[i - 1] = (spans[i - 1][0], e)
                del spans[i]
                continue
        i += 1
    return spans


def by_paragraph(page: DocumentPage, max_size: int, prefix: str = "B",
                 min_size: int = 200) -> list[Chunk]:
    """Gom cac cau lien tiep thanh chunk <= max_size; heading luon mo chunk moi."""
    flat = page.text.replace("\n", " ")
    spans: list[tuple[int, int]] = []
    cur_s = cur_e = None
    for s, e, is_heading in _units(page.text):
        if cur_s is not None and (is_heading or e - cur_s > max_size):
            spans.append((cur_s, cur_e))
            cur_s = cur_e = None
        if e - s > max_size:
            while e - s > max_size:
                cut = flat.rfind(" ", s, s + max_size)
                cut = cut if cut > s else s + max_size
                spans.append((s, cut))
                s = cut
        if cur_s is None:
            cur_s = s
        cur_e = e
    if cur_s is not None:
        spans.append((cur_s, cur_e))
    spans = _merge_small(spans, min_size, max_size)

    chunks = []
    for s, e in spans:
        s, e = _trim(flat, s, e)
        if e > s:
            chunks.append(_make_chunk(prefix, page, len(chunks), s, e, flat, "by_paragraph"))
    return chunks