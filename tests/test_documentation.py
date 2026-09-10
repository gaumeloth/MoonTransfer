from __future__ import annotations

import re
import unittest
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from tools.package_release import RELEASE_DOCUMENT_NAMES


ROOT = Path(__file__).resolve().parents[1]
SINGLE_LANGUAGE = {"THIRD_PARTY_NOTICES.md", "android/recipes/README.md"}


class HTMLReferences(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.ids: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for key, value in attrs:
            if value is None:
                continue
            if key in {"src", "href"}:
                self.links.append(value)
            if key == "id":
                self.ids.add(value)


def prose(text: str) -> str:
    # These checks cover the inline links, ATX headings and HTML used in our docs,
    # not arbitrary Markdown. Fenced command examples are deliberately excluded.
    result = []
    fence = ""
    for line in text.splitlines():
        match = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if match:
            marker = match.group(1)
            if not fence:
                fence = marker
            elif marker[0] == fence[0] and len(marker) >= len(fence):
                fence = ""
            continue
        if not fence:
            result.append(line)
    return "\n".join(result)


def references(text: str) -> tuple[list[str], set[str]]:
    text = prose(text)
    html = HTMLReferences()
    html.feed(text)
    links = re.findall(r"!?\[[^\]]*\]\(([^\s()]+)\)", text)
    anchors = set(html.ids)
    counts: Counter[str] = Counter()
    for title in re.findall(r"^#{1,6}\s+(.+?)\s*#*\s*$", text, re.MULTILINE):
        slug = re.sub(r"[^\w\- ]", "", title.lower()).replace(" ", "-")
        number = counts[slug]
        counts[slug] += 1
        anchors.add(f"{slug}-{number}" if number else slug)
    return links + html.links, anchors


def local_reference(document: Path, link: str) -> tuple[Path, str] | None:
    url = urlsplit(link)
    if url.scheme or url.netloc:
        return None
    target = document.parent / unquote(url.path) if url.path else document
    return target.resolve(), unquote(url.fragment)


class DocumentationTests(unittest.TestCase):
    def test_reference_extraction(self) -> None:
        links, anchors = references(
            '# Guide\n## Compatibilità\n## Repeat\n## Repeat\n'
            '[local](guide.md#repeat)\n![logo](logo.png)\n'
            '<img src="image.png">\n<a id="manual"></a>\n'
            '```md\n[example](missing.md)\n## Not a heading\n```\n'
        )
        self.assertEqual(links, ["guide.md#repeat", "logo.png", "image.png"])
        self.assertEqual(anchors, {"guide", "compatibilità", "repeat", "repeat-1", "manual"})

    def test_local_reference_resolution(self) -> None:
        document = ROOT / "docs/BUILD.md"
        self.assertEqual(
            local_reference(document, "../README.it.md#compatibilit%C3%A0-del-trasporto"),
            (ROOT / "README.it.md", "compatibilità-del-trasporto"),
        )
        self.assertIsNone(local_reference(document, "https://example.com/guide"))

    def test_documentation_links_and_release_contents(self) -> None:
        documents = sorted(
            set(ROOT.glob("*.md"))
            | set((ROOT / "docs").rglob("*.md"))
            | set((ROOT / "android").glob("*.md"))
            | set((ROOT / "android/recipes").rglob("*.md"))
        )
        packaged = {ROOT / name for name in RELEASE_DOCUMENT_NAMES}
        for document in documents:
            with self.subTest(document=document.relative_to(ROOT)):
                self.assertIn(document, packaged, "Guide missing from release allowlist")
                text = document.read_text(encoding="utf-8")
                links, _ = references(text)
                for link in links:
                    with self.subTest(link=link):
                        local = local_reference(document, link)
                        if local is None:
                            continue
                        target, fragment = local
                        self.assertTrue(target.is_relative_to(ROOT), "Link escapes checkout")
                        self.assertTrue(target.is_file(), "Broken local link")
                        self.assertIn(target, packaged, "Link missing from extracted release")
                        if fragment:
                            _, anchors = references(target.read_text(encoding="utf-8"))
                            self.assertIn(fragment, anchors, "Broken heading anchor")
                name = document.relative_to(ROOT).as_posix()
                if name not in SINGLE_LANGUAGE:
                    counterpart = (
                        document.with_name(document.name.replace(".it.md", ".md"))
                        if document.name.endswith(".it.md")
                        else document.with_suffix(".it.md")
                    )
                    self.assertTrue(counterpart.is_file(), "Missing translation counterpart")
                    translated_targets = {
                        result[0]
                        for link in links
                        if (result := local_reference(document, link)) is not None
                    }
                    self.assertIn(counterpart, translated_targets, "Missing language switch")

    def test_release_allowlist_is_explicit_and_complete(self) -> None:
        self.assertEqual(len(RELEASE_DOCUMENT_NAMES), len(set(RELEASE_DOCUMENT_NAMES)))
        for name in RELEASE_DOCUMENT_NAMES:
            with self.subTest(name=name):
                path = ROOT / name
                self.assertTrue(path.is_file())
                self.assertTrue(path.resolve().is_relative_to(ROOT))
                self.assertNotIn(path.suffix, {".p12", ".jks", ".xcf", ".py"})


if __name__ == "__main__":
    unittest.main()
