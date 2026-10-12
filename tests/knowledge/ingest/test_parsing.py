"""AC3 — Markdown parsing into semantic EvidenceChunks (A14-1).

Doctrine: section-aligned chunking per the document's own heading structure
(never fixed-size), code fences kept intact (a `#` inside a fence is code,
not a heading), wiki-links captured per chunk, page/section anchors
preserved, and every chunk's text is a verbatim slice of the source.
"""

from __future__ import annotations

import pytest

from algobots.knowledge.ingest import (
    WikiLink,
    build_chunks,
    parse_markdown,
)
from algobots.knowledge.ingest.parsing import MarkdownParseError, parse_frontmatter
from conftest import FIXTURES, register


def _parse_fixture(name: str):
    return parse_markdown((FIXTURES / name).read_text(encoding="utf-8"))


# ------------------------------------------------------------- frontmatter --
def test_frontmatter_subset_types():
    meta = parse_frontmatter(
        'title: T\npage: 3\nratio: 0.5\nflag: true\nquoted: "a, b"\n'
        "tags: [alpha, beta]\nauthors:\n  - Ada\n  - Grace\n"
    )
    assert meta["title"] == "T"
    assert meta["page"] == 3
    assert meta["ratio"] == 0.5
    assert meta["flag"] is True
    assert meta["quoted"] == "a, b"
    assert meta["tags"] == ["alpha", "beta"]
    assert meta["authors"] == ["Ada", "Grace"]


def test_frontmatter_rejects_junk_line():
    with pytest.raises(MarkdownParseError) as ei:
        parse_frontmatter("title: T\nthis line has no colon\n")
    assert ei.value.reason == "frontmatter"
    assert "no colon" in ei.value.message


def test_frontmatter_rejects_tabs():
    with pytest.raises(MarkdownParseError):
        parse_frontmatter("tags:\n\t- tab item\n")


def test_frontmatter_rejects_orphan_list_item():
    with pytest.raises(MarkdownParseError):
        parse_frontmatter("- stray item\ntitle: T\n")


# ---------------------------------------------------------------- sections --
def test_section_aligned_chunks_simple_note():
    parsed = _parse_fixture("notes/simple-note.md")
    anchors = [s.anchor for s in parsed.sections]
    assert anchors == ["", "methods", "methods/bootstrapping", "results"]
    assert parsed.page == 3
    assert [s.heading_level for s in parsed.sections] == [0, 1, 2, 1]


def test_chunks_follow_heading_tree_not_fixed_size():
    """A one-word section stays a one-word chunk; a long section stays whole —
    no fixed-size splitting, ever."""
    text = "# Short\n\nx\n\n# Long\n\n" + ("paragraph\n\n" * 50)
    parsed = parse_markdown(text)
    assert len(parsed.sections) == 2
    assert parsed.sections[0].text == "# Short\n\nx"  # tiny section stays tiny
    assert "paragraph\n\nparagraph" in parsed.sections[1].text
    assert len(parsed.sections[1].text) > 400  # would be split by any sizer


def test_duplicate_headings_keep_distinct_anchors_via_path():
    parsed = _parse_fixture("notes/nested-note.md")
    anchors = [s.anchor for s in parsed.sections]
    assert anchors.count("guide/methods") == 2  # duplicate name, same path...
    # ...but distinct ORDER keeps chunk ids distinct (content-hash:order:anchor)
    chunks = build_chunks("d1", "v1", "hash-x", parsed.sections, parsed.page)
    assert len({c.chunk_id for c in chunks}) == len(chunks)


def test_hash_inside_code_fence_is_not_a_heading():
    parsed = _parse_fixture("notes/nested-note.md")
    appendix = next(s for s in parsed.sections if s.anchor == "appendix")
    assert "this hash is code" in appendix.text
    assert "# this hash is code, not a heading" in appendix.text
    assert "```python" in appendix.text  # fence kept verbatim, intact
    assert not any(s.heading == "this hash is code, not a heading" for s in parsed.sections)


def test_wiki_links_captured_with_section_and_alias():
    parsed = _parse_fixture("notes/simple-note.md")
    preamble = parsed.sections[0]
    assert preamble.links == (
        WikiLink(target="Other Note", section=None, label="other"),
    )
    results = parsed.sections[-1]
    assert results.links[0].target == "Methods"
    assert results.links[0].section == "Bootstrapping"
    assert results.links[0].label is None


def test_chunk_text_is_verbatim_slice_of_source():
    raw = (FIXTURES / "notes/nested-note.md").read_text(encoding="utf-8")
    lines = raw.splitlines()
    parsed = parse_markdown(raw)
    for s in parsed.sections:
        rebuilt = "\n".join(lines[s.start_line - 1 : s.end_line])
        assert s.text == rebuilt.rstrip("\n")  # verbatim, only trailing blanks trimmed


def test_line_anchors_are_one_based_and_contiguous():
    raw = (FIXTURES / "notes/simple-note.md").read_text(encoding="utf-8")
    parsed = parse_markdown(raw)
    covered = set()
    for s in parsed.sections:
        assert s.start_line >= 1 and s.end_line >= s.start_line
        covered.update(range(s.start_line, s.end_line + 1))
    # every non-blank line after the frontmatter block is claimed by a chunk
    for i, line in enumerate(raw.splitlines(), start=1):
        if line.strip() and not line.strip() == "---" and i > 5:
            assert i in covered, f"line {i} unclaimed: {line!r}"


def test_page_anchor_from_frontmatter_stamp_on_every_chunk():
    parsed = _parse_fixture("notes/simple-note.md")
    chunks = build_chunks("d1", "v1", "hash-y", parsed.sections, parsed.page)
    assert {c.page for c in chunks} == {3}


def test_nul_bytes_rejected():
    with pytest.raises(MarkdownParseError) as ei:
        parse_markdown("# Title\n\x00\n")
    assert ei.value.reason == "nul_bytes"


# --------------------------------------------------------- ingest level E2E --
def test_fixture_note_ingests_to_expected_chunks(make_vault, store, ingest):
    root, _ = make_vault("notes/simple-note.md")
    source = register(ingest, store, root)
    report = ingest.run(source)
    assert report.errors == []
    doc = store.documents(source.source_id)[0]
    version = store.get_version(doc.current_version_id)
    assert version.chunk_count == 4
    chunks = store.chunks_for(version.version_id)
    assert [c.anchor for c in chunks] == ["", "methods", "methods/bootstrapping", "results"]
    assert all(c.doc_id == doc.doc_id and c.version_id == version.version_id for c in chunks)
    assert [c.order for c in chunks] == [0, 1, 2, 3]


def test_failed_parse_surfaces_error_and_generates_no_chunks(make_vault, store, ingest):
    root, _ = make_vault("malformed/bad-frontmatter.md")
    source = register(ingest, store, root)
    report = ingest.run(source)
    assert report.errors, "parse failure must be surfaced"
    assert all("no colon" in e or "frontmatter" in e for e in report.errors)
    assert report.chunks_new == []  # never placeholder text
    doc = store.documents(source.source_id)[0]
    assert store.get_version(doc.current_version_id).chunk_count == 0
