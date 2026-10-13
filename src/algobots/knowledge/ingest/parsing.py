"""Markdown parsing into section-aligned EvidenceChunks (A14-1).

Doctrine (docvault, verified lane): chunks follow the document's own
element/section structure — one chunk per heading-delimited section, fences
kept intact, `#` inside code fences ignored. NEVER fixed-size splitting:
a section stays whole however long it is, and preamble text before the first
heading is its own chunk. Every chunk's ``text`` is a verbatim slice of the
source — failed parses surface errors and produce NO chunks; no placeholder
text is ever generated.

Frontmatter is a strict subset: flat ``key: value`` pairs, inline
``[a, b]`` lists, and one-level ``- item`` block lists. Anything else inside
a frontmatter block is a parse error (reported, not guessed). A page anchor
(``page:`` key) applies to the whole document and is stamped on every chunk.

Chunk ids are stamped by `build_chunks`, content-addressed off the version
content hash so identical content always maps to identical ids.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from algobots.knowledge.ingest.models import EvidenceChunk, WikiLink

FRONTMATTER_DELIM = "---"
_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\r?\n(.*?\r?\n)?---[ \t]*(?:\r?\n|\Z)", re.DOTALL)
_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.*?)(?:[ \t]+#+)?[ \t]*$")
_FENCE_RE = re.compile(r"^(```+|~~~+)")
_WIKILINK_RE = re.compile(
    r"\[\[([^\]#|]+?)(?:#([^\]|]+?))?(?:\|([^\]]+?))?\]\]"
)


class MarkdownParseError(Exception):
    """Structural parse failure. Carries a stable reason code."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message


@dataclass(frozen=True)
class Section:
    """A heading-delimited region of the document, verbatim."""

    anchor: str  # slug heading path, "" for the preamble
    heading: str | None
    heading_level: int  # 1-6, 0 for preamble
    start_line: int  # 1-based inclusive
    end_line: int  # 1-based inclusive
    text: str
    links: tuple[WikiLink, ...]


@dataclass(frozen=True)
class ParsedDocument:
    frontmatter: dict[str, object]
    page: int | None
    sections: tuple[Section, ...]

    @property
    def title(self) -> str | None:
        t = self.frontmatter.get("title")
        return t if isinstance(t, str) and t else None


def slugify(text: str) -> str:
    out: list[str] = []
    for ch in text.strip().lower():
        if ch.isalnum() and ch.isascii():
            out.append(ch)
        elif out and out[-1] != "-":
            out.append("-")
    s = "".join(out).strip("-")
    return s or "section"


# ------------------------------------------------------------ frontmatter --
def _parse_scalar(raw: str) -> object:
    v = raw.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        return [p.strip().strip("\"'") for p in inner.split(",")] if inner else []
    if v.lower() in ("true", "false"):
        return v.lower() == "true"
    try:
        return int(v)
    except ValueError:
        try:
            return float(v)
        except ValueError:
            return v


def parse_frontmatter(block: str) -> dict[str, object]:
    """Strict subset parser. Raises MarkdownParseError on anything that is
    not a flat key/value or one-level block list."""
    meta: dict[str, object] = {}
    current_list_key: str | None = None
    for lineno, raw in enumerate(block.splitlines(), start=1):
        if not raw.strip():
            continue
        if "\t" in raw:
            raise MarkdownParseError(
                "frontmatter", f"frontmatter line {lineno}: tabs are not valid indentation"
            )
        stripped = raw.strip()
        if stripped.startswith("- "):
            if current_list_key is None:
                raise MarkdownParseError(
                    "frontmatter",
                    f"frontmatter line {lineno}: list item outside a list value",
                )
            items = meta.get(current_list_key)
            if not isinstance(items, list):
                raise MarkdownParseError(
                    "frontmatter",
                    f"frontmatter line {lineno}: mixed scalar and list for "
                    f"{current_list_key!r}",
                )
            items.append(_parse_scalar(stripped[2:]))
            continue
        if ":" not in stripped:
            raise MarkdownParseError(
                "frontmatter",
                f"frontmatter line {lineno}: expected 'key: value', got {stripped!r}",
            )
        key, _, value = stripped.partition(":")
        key = key.strip()
        if not key:
            raise MarkdownParseError(
                "frontmatter", f"frontmatter line {lineno}: empty key"
            )
        v = value.strip()
        if v == "":
            current_list_key = key
            meta[key] = []
        else:
            current_list_key = None
            meta[key] = _parse_scalar(v)
    return meta


def split_frontmatter(text: str) -> tuple[dict[str, object], str, int]:
    """Return (frontmatter, body, body_start_line). Unterminated frontmatter
    is a parse error, never a guess."""
    if not text.startswith(FRONTMATTER_DELIM):
        return {}, text, 1
    m = _FRONTMATTER_RE.match(text)
    if m is None:
        raise MarkdownParseError(
            "frontmatter",
            "frontmatter opened with '---' but never closed",
        )
    meta = parse_frontmatter(m.group(1) or "")
    body = text[m.end():]
    body_start = text.count("\n", 0, m.end()) + 1
    return meta, body, body_start


# ---------------------------------------------------------------- sections --
def _iter_sections(body: str, body_start_line: int) -> list[Section]:
    lines = body.splitlines()
    sections: list[Section] = []
    stack: list[tuple[int, str]] = []  # (level, heading text)
    current: tuple[str, str | None, int, int, int] | None = None
    # current = (anchor, heading, heading_level, start_line, end_line)

    def emit(end_line: int) -> None:
        nonlocal current
        if current is None:
            return
        anchor, heading, level, start, _ = current
        text = "\n".join(lines[start - body_start_line : end_line - body_start_line + 1])
        links = tuple(
            WikiLink(
                target=target.strip(),
                section=section.strip() if section else None,
                label=label.strip() if label else None,
            )
            for target, section, label in _WIKILINK_RE.findall(text)
        )
        sections.append(
            Section(
                anchor=anchor,
                heading=heading,
                heading_level=level,
                start_line=start,
                end_line=end_line,
                text=text.rstrip("\n"),
                links=links,
            )
        )
        current = None

    fence: str | None = None
    for idx, line in enumerate(lines):
        lineno = body_start_line + idx
        m = _FENCE_RE.match(line)
        if m:
            marker = m.group(1)[:3]
            if fence is None:
                fence = marker
            elif fence == marker:
                fence = None
        if fence is None:
            hm = _HEADING_RE.match(line)
            if hm:
                level = len(hm.group(1))
                while stack and stack[-1][0] >= level:
                    stack.pop()
                stack.append((level, hm.group(2)))
                emit(lineno - 1)
                current = (
                    "/".join(slugify(h) for _, h in stack),
                    hm.group(2),
                    level,
                    lineno,
                    lineno,
                )
                continue
        if current is None:
            if line.strip() == "":
                continue  # preamble starts at the first content line
            current = ("", None, 0, lineno, lineno)
    emit(body_start_line + len(lines) - 1)
    return sections


def parse_markdown(text: str) -> ParsedDocument:
    """Parse Markdown into frontmatter + section-aligned Sections.

    Raises MarkdownParseError on structural failure (NUL bytes, broken
    frontmatter). On failure the caller must surface the error and emit NO
    chunks — never substitute placeholder text.
    """
    if "\x00" in text:
        raise MarkdownParseError("nul_bytes", "NUL bytes are not valid Markdown text")
    meta, body, body_start = split_frontmatter(text)
    sections = _iter_sections(body, body_start)
    page = meta.get("page")
    page_n = page if isinstance(page, int) and not isinstance(page, bool) else None
    return ParsedDocument(frontmatter=meta, page=page_n, sections=tuple(sections))


# ------------------------------------------------------------------ chunks --
def build_chunks(
    doc_id: str,
    version_id: str,
    content_hash: str,
    sections: tuple[Section, ...],
    page: int | None,
) -> list[EvidenceChunk]:
    """Stamp content-addressed chunk ids onto parsed sections.

    ``chunk_id = sha256(content_hash:order:anchor)`` — identical content
    always produces identical ids, so unchanged or reverted content reuses
    existing chunks and embedding work is never duplicated.
    """
    chunks: list[EvidenceChunk] = []
    for order, s in enumerate(sections):
        cid = "c-" + hashlib.sha256(
            f"{content_hash}:{order}:{s.anchor}".encode()
        ).hexdigest()[:24]
        chunks.append(
            EvidenceChunk(
                chunk_id=cid,
                doc_id=doc_id,
                version_id=version_id,
                anchor=s.anchor,
                heading=s.heading,
                heading_level=s.heading_level,
                page=page,
                start_line=s.start_line,
                end_line=s.end_line,
                text=s.text,
                links=s.links,
                order=order,
            )
        )
    return chunks
