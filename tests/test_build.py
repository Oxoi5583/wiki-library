"""Run with: python -m unittest discover -s tests -v"""
from html.parser import HTMLParser
import json
import re
from pathlib import Path
import tempfile
import unittest
from urllib.parse import unquote, urlsplit

import yaml

from build import build, tag_path, ROOT, MANIFEST


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if values.get("id"):
            self.ids.add(values["id"])
        for attr in ("href", "src"):
            if values.get(attr):
                self.links.append(values[attr])


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="wiki-library-test-")
        self.root = Path(self.temporary.name)
        self.source = self.root / "data"
        self.source.mkdir()
        self.output = self.root / "site"

    def tearDown(self):
        self.temporary.cleanup()

    def entry(self, identifier="test-work", **changes):
        values = {"id": identifier, "title": "測試中文譯名", "original_title": "Original Title", "media": "novel",
                  "categories": ["science-fiction-novel"], "tags": ["哲學", "心理學"], "summary": "測試簡介",
                  "features": "敘事形式測試",
                  "added": "2026-10-02", "creators": [{"name": "作者", "role": "作者"}],
                  "editions": [{"title": "測試譯本", "language": "繁體中文", "translators": ["測試譯者"]}]}
        values.update(changes)
        path = self.source / identifier / "index.md"
        path.parent.mkdir(exist_ok=True)
        path.write_text("---\n" + yaml.safe_dump(values, allow_unicode=True, sort_keys=False) + "---\n\n## 個人筆記\n\n測試內文。", encoding="utf-8")
        return path

    def test_empty_library_still_has_all_shelves(self):
        self.assertEqual(build(self.source, self.output), 0)
        self.assertTrue((self.output / "media/game/index.html").is_file())
        self.assertIn("此分類尚無館藏", (self.output / "index.html").read_text(encoding="utf-8"))

    def test_titles_translators_aliases_and_notes_are_searchable(self):
        self.entry(aliases=["地區譯名"])
        build(self.source, self.output)
        home = (self.output / "index.html").read_text(encoding="utf-8")
        import re
        payload = json.loads(re.search(r'<script id="catalog-data" type="application/json">(.*?)</script>', home, re.S).group(1))
        for term in ("測試中文譯名", "Original Title", "地區譯名", "測試譯者", "測試內文", "敘事形式測試"):
            self.assertIn(term, payload[0]["search"])
        detail = (self.output / "works/test-work/index.html").read_text(encoding="utf-8")
        self.assertIn("原文標題", detail)
        self.assertIn("測試譯者", detail)
        self.assertIn("作品特色", detail)

    def test_legacy_personal_interest_is_not_presented_as_work_features(self):
        self.entry(features="", interest="我想讀這個")
        build(self.source, self.output)
        for filename in ("index.html", "works/test-work/index.html"):
            html = (self.output / filename).read_text(encoding="utf-8")
            self.assertNotIn("我想讀這個", html)
            self.assertNotIn("為甚麼收藏它", html)

    def test_catalogue_uses_rows_and_professional_classifications(self):
        self.entry()
        build(self.source, self.output)
        html = (self.output / "index.html").read_text(encoding="utf-8")
        self.assertIn('class="work-row"', html)
        self.assertIn("科幻小說", html)
        self.assertIn("歷史小說", html)
        self.assertIn("哲學", html)
        self.assertNotIn('class="work-card"', html)
        self.assertNotIn("為每一份好奇", html)
        self.assertNotIn('class="library-hero"', html)

    def test_markdown_links_assets_and_fragments_are_portable(self):
        first = self.entry("first")
        self.entry("second")
        assets = first.parent / "assets"
        assets.mkdir()
        (assets / "圖示.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"/>', encoding="utf-8")
        with first.open("a", encoding="utf-8") as file:
            file.write('\n[下一篇](../second/index.md?from=first#個人筆記)\n\n![圖示](assets/圖示.svg)\n\n`[literal](missing.md)`\n')
        build(self.source, self.output)
        detail = (self.output / "works/first/index.html").read_text(encoding="utf-8")
        self.assertIn('../second/index.html?from=first#個人筆記', detail)
        self.assertIn('assets/%E5%9C%96%E7%A4%BA.svg', detail)
        self.assertTrue((self.output / "works/first/assets/圖示.svg").is_file())
        self.assertIn('[literal](missing.md)', detail)

    def test_invalid_metadata_does_not_change_existing_output(self):
        self.entry()
        build(self.source, self.output)
        before = (self.output / "index.html").read_bytes()
        self.entry(added="2026-02-30")
        with self.assertRaisesRegex(ValueError, "added"):
            build(self.source, self.output)
        self.assertEqual((self.output / "index.html").read_bytes(), before)

    def test_multiple_entry_errors_are_reported_together(self):
        self.entry("bad-date", added="2026-02-30")
        self.entry("bad-media", media="typo")
        with self.assertRaises(ValueError) as context:
            build(self.source, self.output)
        message = str(context.exception)
        self.assertIn("共 2 件", message)
        self.assertIn("bad-date", message)
        self.assertIn("added", message)
        self.assertIn("bad-media", message)
        self.assertIn("未知媒體", message)
        self.assertFalse(self.output.exists())

    def test_unquoted_colon_in_plain_scalar_is_repaired(self):
        path = self.entry()
        text = path.read_text(encoding="utf-8")
        text = text.replace("summary: 測試簡介", "summary: 測試: 含冒號的簡介")
        text = text.replace("features: 敘事形式測試", "features: 敘事形式: 含冒號的特色")
        path.write_text(text, encoding="utf-8")
        self.assertEqual(build(self.source, self.output), 1)
        detail = (self.output / "works/test-work/index.html").read_text(encoding="utf-8")
        self.assertIn("測試: 含冒號的簡介", detail)
        self.assertIn("敘事形式: 含冒號的特色", detail)

    def test_nested_source_label_with_unquoted_colon_is_repaired(self):
        path = self.entry()
        text = path.read_text(encoding="utf-8")
        text = text.replace(
            "editions:",
            "sources:\n  - label: Metal Skin Panic: MADOX-01\n    url: https://example.com/source\neditions:",
            1,
        )
        path.write_text(text, encoding="utf-8")
        self.assertEqual(build(self.source, self.output), 1)
        detail = (self.output / "works/test-work/index.html").read_text(encoding="utf-8")
        self.assertIn("Metal Skin Panic: MADOX-01", detail)

    def test_missing_link_fails_before_writing(self):
        path = self.entry()
        with path.open("a", encoding="utf-8") as file:
            file.write('\n[不存在](../missing/index.md)\n')
        with self.assertRaisesRegex(ValueError, "本機連結"):
            build(self.source, self.output)
        self.assertFalse(self.output.exists())

    def test_unknown_media_duplicate_ids_and_missing_original_title(self):
        path = self.entry(media="typo")
        with self.assertRaisesRegex(ValueError, "未知媒體"):
            build(self.source, self.output)
        self.entry(original_title="")
        with self.assertRaisesRegex(ValueError, "original_title"):
            build(self.source, self.output)
        self.entry()
        other = self.source / "another"
        other.mkdir()
        (other / "index.md").write_bytes(path.read_bytes())
        with self.assertRaisesRegex(ValueError, "重複 id"):
            build(self.source, self.output)

    def test_unmanaged_output_files_are_preserved(self):
        self.entry()
        self.output.mkdir()
        sentinel = self.output / "keep.txt"
        sentinel.write_text("keep", encoding="utf-8")
        build(self.source, self.output)
        build(self.source, self.output)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")
        new_output = self.root / "collision"
        new_output.mkdir()
        (new_output / "index.html").write_text("owner's page", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "拒絕覆寫"):
            build(self.source, new_output)
        self.assertEqual((new_output / "index.html").read_text(encoding="utf-8"), "owner's page")

    def test_stale_files_require_explicit_prune(self):
        path = self.entry()
        build(self.source, self.output)
        path.rename(path.with_suffix(".archived"))
        build(self.source, self.output)
        self.assertTrue((self.output / "works/test-work/index.html").exists())
        build(self.source, self.output, prune=True)
        self.assertFalse((self.output / "works/test-work/index.html").exists())
        self.assertNotIn("works/test-work/index.html", json.loads((self.output / MANIFEST).read_text(encoding="utf-8")))

    def test_source_output_overlap_and_unsafe_manifest_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "互相包含"):
            build(self.source, self.source / "site")
        self.output.mkdir()
        (self.output / MANIFEST).write_text('["../outside.txt"]', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "無效的生成檔案路徑"):
            build(self.source, self.output)

    def test_sample_library_has_no_broken_local_links_or_fragments(self):
        self.assertGreater(build(ROOT / "data", self.output), 0)
        parsed = {}
        for path in self.output.rglob("*.html"):
            parser = Links()
            parser.feed(path.read_text(encoding="utf-8"))
            parsed[path.resolve()] = parser
        for path, parser in parsed.items():
            for value in parser.links:
                url = urlsplit(value)
                if url.scheme or url.netloc:
                    continue
                target = (path.parent / unquote(url.path)).resolve() if url.path else path
                self.assertTrue(target.is_file(), f"{path}: {value}")
                if url.fragment and target in parsed:
                    self.assertIn(unquote(url.fragment), parsed[target].ids, f"{path}: {value}")

    def series(self, **changes):
        definition = {"title": "範例系列", "original_title": "Example Cycle", "aliases": ["系列別名"],
                      "orders": [{"id": "release", "title": "發行順序",
                                  "items": [{"work": "first"}, {"title": "第二部", "original_title": "Volume II"}, {"work": "third"}]},
                                 {"id": "chronology", "title": "故事時間順序", "items": [{"work": "third"}, {"work": "first"}]},
                                 {"id": "members", "title": "成員名單", "ordered": False,
                                  "items": [{"work": "first"}, {"work": "third"}]}]}
        definition.update(changes)
        path = self.source / "series.yml"
        path.write_text(yaml.safe_dump({"example-cycle": definition}, allow_unicode=True, sort_keys=False), encoding="utf-8")
        return path

    def test_series_orders_preserve_gaps_and_distinct_neighbours(self):
        self.entry("first", title="第一部")
        self.entry("third", title="第三部")
        self.series(sources=[{"label": "順序來源", "url": "https://example.com/order"}])
        self.assertEqual(build(self.source, self.output), 2)
        detail = (self.output / "works/first/index.html").read_text(encoding="utf-8")
        release = re.search(r'<section class="series-order" id="series-example-cycle--order-release">(.*?)</section>', detail, re.S).group(1)
        next_link = re.search(r'<nav class="series-neighbours".*?</nav>', release, re.S).group(0)
        self.assertIn("第二部", next_link)
        self.assertIn("尚未收錄", next_link)
        self.assertNotIn("third/index.html", next_link)  # Do not skip the missing middle work.
        chronology = re.search(r'<section class="series-order" id="series-example-cycle--order-chronology">(.*?)</section>', detail, re.S).group(1)
        self.assertIn("前一部", chronology)
        self.assertIn("../third/index.html", chronology)
        unordered = re.search(r'<section class="series-order" id="series-example-cycle--order-members">(.*?)</section>', detail, re.S).group(1)
        self.assertNotIn("series-neighbours", unordered)
        self.assertIn("不表示先後順序", unordered)
        self.assertEqual(detail.count('aria-current="true"'), 3)
        listing = (self.output / "series/example-cycle/index.html").read_text(encoding="utf-8")
        self.assertIn("../../works/first/index.html", listing)
        self.assertIn('href="https://example.com/order"', listing)
        home = (self.output / "index.html").read_text(encoding="utf-8")
        payload = json.loads(re.search(r'<script id="catalog-data" type="application/json">(.*?)</script>', home, re.S).group(1))
        self.assertEqual(payload[0]["series"], ["example-cycle"])
        self.assertIn("系列別名", payload[0]["search"])
        self.assertIn("Example Cycle", payload[0]["search"])
        self.assertIn('name="series"', home)

    def test_series_invalid_references_fail_before_changing_output(self):
        self.entry("first")
        self.entry("third")
        path = self.series()
        build(self.source, self.output)
        before = (self.output / "index.html").read_bytes()
        valid = yaml.safe_load(path.read_text(encoding="utf-8"))
        invalid_orders = [
            [{"id": "release", "title": "順序", "items": [{"work": "missing"}]}],
            [{"id": "release", "title": "順序", "items": [{"work": "first"}, {"work": "first"}]}],
            [{"id": "release", "title": "順序", "items": [{"work": "first", "title": "重複標題"}]}],
            [{"id": "release", "title": "順序", "items": [{"title": "缺原文名"}]}],
            [{"id": "release", "title": "順序", "ordered": "false", "items": [{"work": "first"}]}],
            [{"id": "release", "title": "順序", "items": []}],
            [{"id": "same", "title": "順序", "items": [{"work": "first"}]},
             {"id": "same", "title": "順序", "items": [{"work": "third"}]}],
        ]
        for orders in invalid_orders:
            with self.subTest(orders=orders):
                self.series(orders=orders)
                with self.assertRaises(ValueError):
                    build(self.source, self.output)
                self.assertEqual((self.output / "index.html").read_bytes(), before)
        path.write_text(yaml.safe_dump(valid, allow_unicode=True), encoding="utf-8")
        first = self.source / "first/index.md"
        first.rename(first.with_suffix(".archived"))
        with self.assertRaisesRegex(ValueError, "找不到館藏"):
            build(self.source, self.output)

    def test_multiple_series_and_cross_media_membership(self):
        self.entry("first")
        self.entry("third", media="game", categories=["adventure-game"])
        path = self.series()
        definitions = yaml.safe_load(path.read_text(encoding="utf-8"))
        definitions["other-cycle"] = {"title": "另一系列", "original_title": "Other Cycle",
                                      "orders": [{"id": "members", "title": "系列成員", "ordered": False, "items": [{"work": "first"}]}]}
        path.write_text(yaml.safe_dump(definitions, allow_unicode=True), encoding="utf-8")
        build(self.source, self.output)
        detail = (self.output / "works/first/index.html").read_text(encoding="utf-8")
        self.assertIn("範例系列", detail)
        self.assertIn("另一系列", detail)
        identifiers = re.findall(r'\bid="([^"]+)"', detail)
        self.assertEqual(len(identifiers), len(set(identifiers)))
        self.assertTrue((self.output / "series/other-cycle/index.html").is_file())
        for page in self.output.rglob("*.html"):
            parser = Links()
            parser.feed(page.read_text(encoding="utf-8"))
            for value in parser.links:
                url = urlsplit(value)
                if not url.scheme and not url.netloc and url.path:
                    self.assertTrue((page.parent / unquote(url.path)).resolve().is_file(), f"{page}: {value}")


if __name__ == "__main__":
    unittest.main()
