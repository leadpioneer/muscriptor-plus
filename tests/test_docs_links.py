"""Documentation links must resolve.

Docs are read on GitHub, where a renamed heading or a moved file silently
breaks every link to it. This test walks the repository's Markdown files and
checks, for each relative link:

* the target file exists (``installation.md``, ``../LICENSE``, …);
* the ``#fragment``, if any, matches a heading of the target document using
  GitHub's anchor rules (lowercase, punctuation stripped, spaces → hyphens).

External ``http(s)`` links are not fetched — CI must not depend on the
network — they are simply skipped.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SKIP_DIRS = {
    ".git",
    ".venv",
    "node_modules",
    "web_dist",
    "__pycache__",
    ".pytest_cache",
}

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
CODE_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)


def _markdown_files() -> list[Path]:
    files = []
    for path in sorted(REPO_ROOT.rglob("*.md")):
        parts = set(path.relative_to(REPO_ROOT).parts)
        if parts & SKIP_DIRS:
            continue
        files.append(path)
    return files


def _slugify(heading: str) -> str:
    """GitHub's heading anchor: lowercase, drop punctuation, spaces → hyphens."""
    slug = re.sub(r"[^\w\s-]", "", heading.strip().lower(), flags=re.UNICODE)
    return slug.replace(" ", "-")


_heading_cache: dict[Path, set[str]] = {}


def _anchors(path: Path) -> set[str]:
    if path not in _heading_cache:
        text = path.read_text(encoding="utf-8")
        anchors = set()
        for _hashes, title in HEADING_RE.findall(text):
            # GitHub appends -1, -2, … to duplicate headings; the first
            # occurrence keeps the plain anchor, which is what links use.
            anchors.add(_slugify(title))
        _heading_cache[path] = anchors
    return _heading_cache[path]


def _links(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    text = CODE_BLOCK_RE.sub("", text)
    text = INLINE_CODE_RE.sub("", text)
    return [target.strip() for target in LINK_RE.findall(text)]


@pytest.mark.parametrize(
    "doc", _markdown_files(), ids=lambda p: str(p.relative_to(REPO_ROOT))
)
def test_documentation_links_resolve(doc: Path):
    problems: list[str] = []
    for target in _links(doc):
        if not target or target.startswith(("http://", "https://", "mailto:")):
            continue
        file_part, _, fragment = target.partition("#")
        if not file_part:
            target_doc = doc
        else:
            if file_part.startswith("/"):
                problems.append(f"{target}: root-absolute links don't work on GitHub")
                continue
            target_doc = (doc.parent / file_part).resolve()
            if not target_doc.exists():
                problems.append(f"{target}: file not found")
                continue
        if fragment and target_doc.suffix == ".md":
            if fragment not in _anchors(target_doc):
                problems.append(
                    f"{target}: no heading #{fragment} in {target_doc.name}"
                )
    assert not problems, "\n".join(problems)
