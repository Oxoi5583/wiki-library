#!/usr/bin/env python3
"""Build a portable, Markdown-first personal library. Python 3.10+."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
import hashlib
from html import escape
from html.parser import HTMLParser
import json
import os
from pathlib import Path, PurePosixPath
import re
from string import Template
import sys
from urllib.parse import quote, unquote, urlsplit, urlunsplit

try:
    import markdown
    import yaml
except ImportError:
    sys.exit("缺少依賴，請先執行 python -m pip install -r requirements.txt")

ROOT = Path(__file__).resolve().parent
MANIFEST = ".wiki-library-manifest.json"
STATUSES = {"curious": "先收藏", "next": "想找時間", "in-progress": "正在探索",
            "finished": "已探索", "paused": "暫時擱著"}
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
LOGO = ('<svg viewBox="0 0 48 48" fill="none"><path d="M7 10c6-2 11 0 17 4 6-4 11-6 17-4v26'
        'c-6-2-11 0-17 4-6-4-11-6-17-4Z"/><path d="M24 14v26M13 19l6 2m-6 6 6 2m10-8 6-2m-6 10 6-2"/></svg>')


class UniqueLoader(yaml.SafeLoader):
    """Reject duplicate keys rather than silently replacing metadata."""


def unique_mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if not isinstance(key, str) or key in result:
            raise ValueError(f"YAML 欄位名稱必須是唯一字串：{key!r}")
        result[key] = loader.construct_object(value_node)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


PLAIN_MAPPING_VALUE = re.compile(r"^(\s*(?:-\s+)?[A-Za-z_][A-Za-z0-9_-]*:\s+)(.+)$")


def repair_unquoted_colon_scalars(text: str):
    """Quote plain mapping values containing ASCII ': ' for one parse retry."""
    repaired, changed = [], []
    for line_number, line in enumerate(text.splitlines(), 1):
        match = PLAIN_MAPPING_VALUE.match(line)
        if not match:
            repaired.append(line)
            continue
        value = match.group(2)
        stripped = value.lstrip()
        if (": " not in value or not stripped
                or stripped[0] in "\"'[{>|&*!%@"
                or " #" in value):
            repaired.append(line)
            continue
        repaired.append(match.group(1) + json.dumps(value, ensure_ascii=False))
        changed.append(line_number)
    return "\n".join(repaired), changed


def read_yaml(text: str, path: Path) -> dict:
    try:
        value = yaml.load(text, Loader=UniqueLoader)
    except yaml.YAMLError as exc:
        repaired, changed = repair_unquoted_colon_scalars(text)
        if not changed:
            raise ValueError(f"{path}: YAML 格式錯誤：{exc}") from exc
        try:
            value = yaml.load(repaired, Loader=UniqueLoader)
        except (yaml.YAMLError, ValueError) as repaired_exc:
            raise ValueError(f"{path}: YAML 格式錯誤：{repaired_exc}") from repaired_exc
        lines = ", ".join(str(line) for line in changed)
        print(
            f"警告：{path}: 已自動容錯處理未加引號且包含 ': ' 的 YAML 文字（第 {lines} 行）；"
            "建議仍在來源檔補上引號。",
            file=sys.stderr,
        )
    except ValueError as exc:
        raise ValueError(f"{path}: YAML 格式錯誤：{exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path}: YAML 必須是欄位對照表")
    return value


def text_field(meta, key, path, required=False):
    value = meta.get(key, "")
    if not isinstance(value, str) or (required and not value.strip()):
        raise ValueError(f"{path}: {key} 必須是{'非空' if required else ''}字串")
    meta[key] = value.strip()
    return meta[key]


def list_field(meta, key, path):
    value = meta.get(key, [])
    if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value):
        raise ValueError(f"{path}: {key} 必須是字串清單，可用 [] 留空")
    meta[key] = list(dict.fromkeys(x.strip() for x in value))
    return meta[key]


def url_field(meta, key, path):
    value = text_field(meta, key, path)
    if value:
        parsed = urlsplit(value)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError(f"{path}: {key} 必須是完整 HTTP(S) 網址")
    return value


def year_field(meta, key, path):
    value = meta.get(key, "")
    if value == "":
        meta[key] = ""
    elif isinstance(value, bool) or not re.fullmatch(r"[0-9]{1,4}", str(value)) or not 1 <= int(value) <= 9999:
        raise ValueError(f"{path}: {key} 必須是有效年份，未知請留空字串")
    else:
        meta[key] = int(value)


def records(meta, key, path):
    value = meta.setdefault(key, [])
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"{path}: {key} 必須是欄位對照表的清單，可用 [] 留空")
    return value


def load_config(path):
    config = read_yaml(path.read_text(encoding="utf-8-sig"), path)
    for key in ("title", "subtitle", "description"):
        text_field(config, key, path, required=True)
    for key in ("media", "categories"):
        values = config.get(key)
        if not isinstance(values, dict) or not values:
            raise ValueError(f"{path}: {key} 需要至少一個分類")
        for slug, label in values.items():
            if not SLUG.fullmatch(slug) or not isinstance(label, str) or not label.strip():
                raise ValueError(f"{path}: {key} 的鍵須為小寫英文短名，值須為非空名稱")
    return config


def load_entry(path, config):
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"{path}: 缺少開頭的 YAML metadata（---）")
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        raise ValueError(f"{path}: metadata 缺少結束的 ---")
    meta = read_yaml("\n".join(lines[1:end]), path)
    for key in ("id", "title", "original_title", "media", "summary"):
        text_field(meta, key, path, required=True)
    if not SLUG.fullmatch(meta["id"]):
        raise ValueError(f"{path}: id 須為小寫英文／數字短名，以連字號分隔")
    if meta["media"] not in config["media"]:
        raise ValueError(f"{path}: 未知媒體 {meta['media']}，請先在 library.yml 定義")
    for key in ("original_language", "features", "cover"):
        text_field(meta, key, path)
    for key in ("categories", "tags", "aliases", "related"):
        list_field(meta, key, path)
    if not meta["categories"] or any(c not in config["categories"] for c in meta["categories"]):
        raise ValueError(f"{path}: categories 需要至少一個 library.yml 已定義的主題")
    status = meta.setdefault("status", "curious")
    if not isinstance(status, str) or status not in STATUSES:
        raise ValueError(f"{path}: status 請使用 {', '.join(STATUSES)}")
    for key in ("example",):
        if not isinstance(meta.setdefault(key, False), bool):
            raise ValueError(f"{path}: {key} 必須是 true 或 false")
    added = str(meta.get("added", ""))
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", added):
            raise ValueError()
        meta["added"] = date.fromisoformat(added).isoformat()
    except ValueError as exc:
        raise ValueError(f"{path}: added 必須是有效的 YYYY-MM-DD 日期") from exc
    year_field(meta, "year", path)
    for person in records(meta, "creators", path):
        text_field(person, "name", path, required=True)
        text_field(person, "role", path, required=True)
    for edition in records(meta, "editions", path):
        text_field(edition, "title", path, required=True)
        for key in ("language", "format", "publisher", "isbn", "notes"):
            text_field(edition, key, path)
        list_field(edition, "translators", path)
        year_field(edition, "year", path)
        url_field(edition, "url", path)
    for source in records(meta, "sources", path):
        text_field(source, "label", path, required=True)
        if not url_field(source, "url", path):
            raise ValueError(f"{path}: sources 的 url 不能留空")
    cover = meta["cover"]
    if cover:
        rel = PurePosixPath(cover)
        if (rel.is_absolute() or ".." in rel.parts or "\\" in cover or ":" in cover
                or len(rel.parts) < 2 or rel.parts[0] != "assets"):
            raise ValueError(f"{path}: cover 請使用同層 assets/ 內的相對路徑")
        target = path.parent.joinpath(*rel.parts)
        if not target.is_file() or target.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg", ".avif"):
            raise ValueError(f"{path}: 找不到 cover 圖片：{cover}")
    return {"meta": meta, "path": path.resolve(), "output": Path("works") / meta["id"] / "index.html",
            "body": "\n".join(lines[end + 1:])}


def relative_url(target, page):
    return quote(Path(os.path.relpath(target, page.parent)).as_posix(), safe="/.-_")


def load_series(source, by_id):
    """A series owns its ordered lists; work membership and neighbours are derived."""
    path = source / "series.yml"
    definitions = read_yaml(path.read_text(encoding="utf-8-sig"), path) if path.exists() else {}
    for identifier, series in definitions.items():
        if not SLUG.fullmatch(identifier) or not isinstance(series, dict):
            raise ValueError(f"{path}: 系列鍵須為小寫英文短名，值須為欄位對照表")
        for field in ("title", "original_title"):
            text_field(series, field, path, required=True)
        text_field(series, "description", path)
        list_field(series, "aliases", path)
        for record in records(series, "sources", path):
            text_field(record, "label", path, required=True)
            if not url_field(record, "url", path):
                raise ValueError(f"{path}: 系列 sources 的 url 不能留空")
        orders = records(series, "orders", path)
        if not orders:
            raise ValueError(f"{path}: 系列 {identifier} 需要至少一份 orders 清單")
        order_ids, members = set(), set()
        for order in orders:
            order_id = text_field(order, "id", path, required=True)
            if not SLUG.fullmatch(order_id) or order_id in order_ids:
                raise ValueError(f"{path}: 系列 {identifier} 的順序 id 無效或重複：{order_id}")
            order_ids.add(order_id)
            text_field(order, "title", path, required=True)
            text_field(order, "notes", path)
            if not isinstance(order.setdefault("ordered", True), bool):
                raise ValueError(f"{path}: ordered 必須是 true 或 false")
            items = records(order, "items", path)
            if not items:
                raise ValueError(f"{path}: 系列 {identifier} 的 {order_id} 需要至少一個項目")
            seen = set()
            for item in items:
                text_field(item, "label", path)
                text_field(item, "notes", path)
                if "work" in item:
                    work_id = text_field(item, "work", path, required=True)
                    if work_id not in by_id:
                        raise ValueError(f"{path}: 系列 {identifier} 找不到館藏：{work_id}；未收錄作品請填 title 與 original_title")
                    if "title" in item or "original_title" in item:
                        raise ValueError(f"{path}: 已收錄系列項目只填 work，不重複填 title 或 original_title")
                    identity = ("work", work_id)
                    members.add(work_id)
                    item["title"] = by_id[work_id]["meta"]["title"]
                    item["original_title"] = by_id[work_id]["meta"]["original_title"]
                else:
                    for field in ("title", "original_title"):
                        text_field(item, field, path, required=True)
                    item["work"] = ""
                    identity = ("title", item["title"], item["original_title"])
                if identity in seen:
                    raise ValueError(f"{path}: 系列 {identifier} 的 {order_id} 有重複項目：{item['title']}")
                seen.add(identity)
        series["members"] = members
    return definitions


def tag_path(tag):
    slug = tag if SLUG.fullmatch(tag) else "tag-" + hashlib.sha256(tag.encode("utf-8")).hexdigest()[:16]
    return Path("tags") / slug / "index.html"


class LinkRewriter(HTMLParser):
    """Resolve local Markdown links and local assets after Markdown rendering."""
    def __init__(self, entry, pages, assets):
        super().__init__(convert_charrefs=False)
        self.entry, self.pages, self.assets, self.parts = entry, pages, assets, []

    def start(self, tag, attrs, closed=False):
        result = []
        for key, value in attrs:
            if key in ("href", "src") and value:
                url = urlsplit(value)
                if not url.scheme and not url.netloc and url.path:
                    target = (self.entry["path"].parent / unquote(url.path)).resolve()
                    mapping = self.pages if url.path.lower().endswith(".md") else self.assets
                    if target in mapping:
                        value = urlunsplit(("", "", relative_url(mapping[target], self.entry["output"]), url.query, url.fragment))
                    elif url.path.lower().endswith(".md") or key == "src" or url.path.startswith("assets/"):
                        raise ValueError(f"{self.entry['path']}: 找不到或未收錄的本機連結：{value}")
            result.append(key if value is None else f'{key}="{escape(value, quote=True)}"')
        self.parts.append("<" + tag + (" " + " ".join(result) if result else "") + (" />" if closed else ">"))

    def handle_starttag(self, tag, attrs): self.start(tag, attrs)
    def handle_startendtag(self, tag, attrs): self.start(tag, attrs, True)
    def handle_endtag(self, tag): self.parts.append(f"</{tag}>")
    def handle_data(self, data): self.parts.append(data)
    def handle_entityref(self, name): self.parts.append(f"&{name};")
    def handle_charref(self, name): self.parts.append(f"&#{name};")
    def handle_comment(self, data): self.parts.append(f"<!--{data}-->")
    def handle_decl(self, decl): self.parts.append(f"<!{decl}>")


def build(source: Path, output: Path, config_path: Path = ROOT / "library.yml", prune=False) -> int:
    source, output = source.expanduser().resolve(), output.expanduser().resolve()
    if not source.is_dir():
        raise ValueError(f"找不到資料目錄：{source}")
    if source == output or source in output.parents or output in source.parents:
        raise ValueError("資料和輸出目錄不能相同，也不能互相包含")
    if output == ROOT or output in ROOT.parents:
        raise ValueError("輸出目錄不能覆寫專案根目錄或其上層")
    for protected in (ROOT / "web", ROOT / "templates", ROOT / "data", ROOT / "tests"):
        if output == protected or protected in output.parents:
            raise ValueError(f"輸出目錄不能寫入專案原始檔：{protected}")
    config = load_config(config_path)
    files = sorted(source.rglob("*"))
    if any(p.is_symlink() for p in files):
        raise ValueError("data 內不支援符號連結，請使用實際檔案")
    entries = [load_entry(p, config) for p in files
               if p.is_file() and p.suffix.lower() == ".md" and not any(x.startswith(".") for x in p.relative_to(source).parts)]
    entries.sort(key=lambda e: (-date.fromisoformat(e["meta"]["added"]).toordinal(), e["meta"]["id"]))
    by_id = {}
    directories = set()
    for entry in entries:
        identifier = entry["meta"]["id"]
        if identifier in by_id:
            raise ValueError(f"{entry['path']}: 重複 id：{identifier}")
        if entry["path"].parent in directories:
            raise ValueError(f"{entry['path']}: 每個館藏資料夾只可放一份 Markdown，筆記請寫在同一檔案")
        directories.add(entry["path"].parent)
        by_id[identifier] = entry
    series = load_series(source, by_id)
    memberships = {identifier: [key for key, definition in series.items() if identifier in definition["members"]]
                   for identifier in by_id}
    pages = {e["path"]: e["output"] for e in entries}
    assets = {}
    for entry in entries:
        for file in files:
            if file.is_file() and file.suffix.lower() != ".md" and entry["path"].parent / "assets" in file.parents:
                assets[file.resolve()] = entry["output"].parent / file.relative_to(entry["path"].parent)
        for identifier in entry["meta"]["related"]:
            if identifier == entry["meta"]["id"] or identifier not in by_id:
                raise ValueError(f"{entry['path']}: related 找不到其他館藏：{identifier}")
        converter = markdown.Markdown(extensions=["extra", "toc", "sane_lists"], extension_configs={"toc": {"permalink": False}})
        rendered = converter.convert(entry["body"])
        if converter.toc:
            rendered = rendered.replace(converter.toc, "")
        entry["toc"] = converter.toc if converter.toc_tokens else ""
        entry["rendered"] = rendered
    # Link resolution happens after every asset and Markdown file has been indexed.
    for entry in entries:
        rewrite = LinkRewriter(entry, pages, assets)
        rewrite.feed(entry["rendered"])
        rewrite.close()
        entry["rendered"] = "".join(rewrite.parts)

    template = Template((ROOT / "web/page.html").read_text(encoding="utf-8-sig"))
    stylesheet = (ROOT / "web/style.css").read_text(encoding="utf-8-sig")
    static = {name: (ROOT / "web" / name).read_bytes() for name in ("site.js", "favicon.svg")}
    versions = {name: hashlib.sha256(content).hexdigest()[:12] for name, content in static.items()}
    media_counts = Counter(e["meta"]["media"] for e in entries)
    category_counts = Counter(c for e in entries for c in e["meta"]["categories"])
    tag_counts = Counter(t for e in entries for t in e["meta"]["tags"])
    generated, names = {}, set()

    def add(path, content):
        if path.as_posix().casefold() in names:
            raise ValueError(f"輸出路徑衝突：{path}")
        names.add(path.as_posix().casefold())
        generated[path] = content.encode("utf-8") if isinstance(content, str) else content

    def link(target, page, label, css=""):
        return f'<a class="{css}" href="{relative_url(target, page)}">{escape(str(label))}</a>'

    def sidebar(page, active):
        html = '<details class="shelf-nav" open><summary>館藏索引 <span aria-hidden="true">＋</span></summary><div class="shelf-nav-body"><p class="nav-caption">THE COLLECTION</p>'
        html += link(Path("catalog/index.html"), page, "全部館藏", "shelf-all" + (" current" if active in ("catalog", "home") else ""))
        html += '<p class="nav-label">媒體類型</p><nav aria-label="媒體分類">'
        for i, (key, label) in enumerate(config["media"].items(), 1):
            current = " current" if active == f"media:{key}" else ""
            html += f'<a class="shelf-link{current}" href="{relative_url(Path("media") / key / "index.html", page)}"><span class="shelf-number">{i:02}</span><span>{escape(label)}</span><span class="shelf-count">{media_counts[key]:02}</span></a>'
        html += '</nav><p class="nav-label">作品分類</p><nav class="category-nav" aria-label="作品分類">'
        for key, label in config["categories"].items():
            if category_counts[key]:
                html += link(Path("categories") / key / "index.html", page, label, "current" if active == f"category:{key}" else "")
        empty_categories = {key: label for key, label in config["categories"].items() if not category_counts[key]}
        html += '</nav>'
        if empty_categories:
            opened = ' open' if active.removeprefix('category:') in empty_categories else ''
            html += f'<details class="more-categories"{opened}><summary>其他作品分類</summary><nav class="category-nav" aria-label="其他作品分類">'
            html += "".join(link(Path("categories") / key / "index.html", page, label, "current" if active == f"category:{key}" else "") for key, label in empty_categories.items())
            html += '</nav></details>'
        html += '</div></details>'
        return html

    def page(path, title, description, content, active=""):
        add(path, template.substitute(title=escape(title), description=escape(description, quote=True),
            site_title=escape(config["title"]), site_subtitle=escape(config["subtitle"]), stylesheet=stylesheet,
            home=relative_url(Path("index.html"), path), catalog=relative_url(Path("catalog/index.html"), path),
            tags=relative_url(Path("tags/index.html"), path), series=relative_url(Path("series/index.html"), path), logo=LOGO,
            favicon=relative_url(Path("_static/favicon.svg"), path) + "?v=" + versions["favicon.svg"],
            script=relative_url(Path("_static/site.js"), path) + "?v=" + versions["site.js"],
            home_active="active" if active == "home" else "", catalog_active="active" if active == "catalog" else "",
            tags_active="active" if active == "tags" else "", series_active="active" if active.startswith("series") else "",
            sidebar=sidebar(path, active), content=content))

    def tags_html(tags, path):
        return '<div class="tags">' + "".join(link(tag_path(t), path, t, "tag") for t in tags) + '</div>'

    def plate(entry, path, large=False):
        m = entry["meta"]
        if m["cover"]:
            return f'<div class="bookplate has-cover"><img src="{relative_url(entry["output"].parent / m["cover"], path)}" alt="{escape(m["title"], quote=True)}的封面" loading="lazy"></div>'
        serial = hashlib.sha256(m["id"].encode()).hexdigest()[:4].upper()
        motif = '<svg viewBox="0 0 200 110" fill="none" aria-hidden="true"><circle cx="100" cy="55" r="39"/><ellipse cx="100" cy="55" rx="78" ry="22" transform="rotate(-25 100 55)"/><path d="M100 6v98M52 55h96"/><circle cx="160" cy="26" r="5" class="plate-star"/></svg>'
        if m["media"] in ("academic", "nonfiction"):
            motif = '<svg viewBox="0 0 200 110" fill="none" aria-hidden="true"><path d="M49 91V38l51-25 51 25v53M62 86V44l38-19 38 19v42M49 91h102M72 86V53m19 33V45m19 41V45m19 41V53"/><circle cx="100" cy="13" r="5" class="plate-star"/></svg>'
        elif m["media"] in ("film", "animation", "comic"):
            motif = '<svg viewBox="0 0 200 110" fill="none" aria-hidden="true"><path d="M49 91V51a51 51 0 0 1 102 0v40M65 91V51a35 35 0 0 1 70 0v40M49 91h102M65 74h70M100 17v74"/><circle cx="112" cy="44" r="18"/><path d="m149 20 5 5m-5 0 5-5"/></svg>'
        return (f'<div class="bookplate plate-{m["media"]}{" plate-large" if large else ""}"><div class="plate-top"><span>{escape(config["media"][m["media"]])}</span><span>WL / {serial}</span></div>'
                + motif + f'<div class="plate-bottom"><span>{escape(m["original_title"] or m["title"])}</span><span>{m["year"] or "UNDATED"}</span></div></div>')

    def row(entry, path):
        m = entry["meta"]
        creators = "".join(f'<p><span class="creator-role">{escape(c["role"])}</span>{escape(c["name"])}</p>' for c in m["creators"]) or '<p class="muted">創作者待補</p>'
        categories = "".join(link(Path("categories") / c / "index.html", path, config["categories"][c], "row-category") for c in m["categories"])
        languages = "、".join(dict.fromkeys(v["language"] for v in m["editions"] if v["language"]))
        translators = "、".join(dict.fromkeys(t for v in m["editions"] for t in v["translators"]))
        features = f'<p class="row-features"><span class="inline-label">特色</span>{escape(m["features"])}</p>' if m["features"] else ''
        versions = (f'<a class="version-link" href="{relative_url(entry["output"], path)}#editions">{len(m["editions"])} 個版本 ↗</a>'
                    if m["editions"] else '<span class="muted">版本待補</span>')
        series_links = '<p class="row-series">' + " · ".join(link(Path("series") / key / "index.html", path, series[key]["title"]) for key in memberships[m["id"]]) + '</p>' if memberships[m["id"]] else ''
        return (f'<article class="work-row" data-id="{m["id"]}" aria-labelledby="row-{m["id"]}">'
                f'<div class="row-title"><h3 id="row-{m["id"]}">{link(entry["output"], path, m["title"])}</h3>'
                f'<p class="row-original"><span class="sr-only">原文標題：</span>{escape(m["original_title"])}</p>'
                f'<p class="row-year">{m["year"] or "年份待補"}' + (' <span class="example-badge">範例</span>' if m["example"] else '') + '</p>' + series_links + '</div>'
                '<div class="row-classification">' + link(Path("media") / m["media"] / "index.html", path, config["media"][m["media"]], "row-media") + categories + '</div>'
                '<div class="row-creators"><span class="mobile-label">作者／主創</span>' + creators + '</div>'
                f'<div class="row-description"><p class="row-summary"><span class="mobile-label">簡介</span>{escape(m["summary"])}</p>' + features + tags_html(m["tags"], path) + '</div>'
                f'<div class="row-versions">{versions}<p class="edition-language">{escape(languages)}</p>'
                + (f'<p class="row-translators">譯者：{escape(translators)}</p>' if translators else '')
                + f'<span class="status status-{m["status"]}">{STATUSES[m["status"]]}</span></div></article>')

    def work_list(items, path):
        return ('<div class="work-list-header" aria-hidden="true"><span>作品／原文標題</span><span>媒體／作品分類</span><span>作者／主創</span><span>內容簡介／作品特色</span><span>版本／狀態</span></div>'
                + '<div class="work-list">' + "".join(row(e, path) for e in items) + '</div>')

    def options(values):
        return "".join(f'<option value="{escape(key, quote=True)}">{escape(label)}</option>' for key, label in values.items())

    def catalogue(items, path, title="館藏目錄", scoped=False, heading="h2"):
        item_media = {k: v for k, v in config["media"].items() if any(e["meta"]["media"] == k for e in items)}
        item_categories = {k: v for k, v in config["categories"].items() if any(k in e["meta"]["categories"] for e in items)}
        item_tags = {t: t for t in sorted({t for e in items for t in e["meta"]["tags"]})}
        item_series = {key: definition["title"] for key, definition in series.items()
                       if any(e["meta"]["id"] in definition["members"] for e in items)}
        payload = []
        for entry in items:
            m = entry["meta"]
            searchable = " ".join([m["title"], m["original_title"], m["summary"], m["features"], m["original_language"],
                *m["aliases"], *m["tags"], config["media"][m["media"]], *(config["categories"][c] for c in m["categories"]),
                *(c["name"] + " " + c["role"] for c in m["creators"]),
                *(" ".join([v["title"], v["language"], v["publisher"], v["isbn"], v["notes"], *v["translators"]]) for v in m["editions"]),
                *(" ".join([series[key]["title"], series[key]["original_title"], *series[key]["aliases"]]) for key in memberships[m["id"]]), entry["body"]])
            payload.append({"id": m["id"], "title": m["title"], "media": m["media"], "categories": m["categories"],
                            "tags": m["tags"], "series": memberships[m["id"]], "status": m["status"], "year": m["year"], "added": m["added"], "search": searchable})
        data = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
        html = f'<section class="catalogue" aria-labelledby="catalog-title"><div class="section-heading"><{heading} id="catalog-title">{escape(title)}</{heading}><p><span id="result-count" aria-live="polite">{len(items)}</span> 件館藏</p></div>'
        html += ('<form class="catalog-tools" role="search"><label class="search-box"><span class="search-icon" aria-hidden="true">⌕</span><span class="sr-only">搜尋館藏</span>'
                 f'<input type="search" name="q" placeholder="搜尋{"此分類的" if scoped else "作品、"}作者、分類、標籤、譯者…" autocomplete="off"><kbd aria-hidden="true">/</kbd></label>'
                 '<div class="filter-row"><label><span class="sr-only">媒體</span><select name="media"><option value="">全部媒體</option>' + options(item_media) + '</select></label>'
                 '<label><span class="sr-only">作品分類</span><select name="category"><option value="">全部作品分類</option>' + options(item_categories) + '</select></label>'
                 '<label><span class="sr-only">系列</span><select name="series"><option value="">全部系列</option>' + options(item_series) + '</select></label>'
                 '<label><span class="sr-only">標籤</span><select name="tag"><option value="">全部標籤</option>' + options(item_tags) + '</select></label>'
                 '<label><span class="sr-only">探索狀態</span><select name="status"><option value="">全部狀態</option>' + options(STATUSES) + '</select></label>'
                 '<label class="sort-control"><span class="sr-only">排序</span><select name="sort"><option value="added">最近收錄</option><option value="oldest">最早收錄</option><option value="title">作品名稱</option><option value="year">作品年份</option></select></label>'
                 '<button class="reset-button" type="reset">清除篩選</button></div><button class="sr-only" type="submit">搜尋</button></form>'
                 '<noscript><p class="notice">即時搜尋需要 JavaScript；仍可從媒體、作品分類與標籤頁瀏覽館藏。</p></noscript>')
        html += work_list(items, path)
        html += f'<div class="empty-state" id="empty-state"{" hidden" if items else ""}><h3>{"此分類尚無館藏" if not items else "沒有符合條件的作品"}</h3><p>{"新增作品後會列於此處。" if not items else "試試其他關鍵字，或清除部分篩選條件。"}</p></div>'
        return html + f'<script id="catalog-data" type="application/json">{data}</script></section>'

    example_count = sum(e["meta"]["example"] for e in entries)
    home = Path("index.html")
    intro = ''
    if example_count:
        intro = f'<p class="example-note">含 {example_count} 件範例館藏，可自行替換；狀態及個人筆記為格式示範。</p>'
    page(home, "館藏目錄", config["description"], catalogue(entries, home, heading="h1") + intro, "home")
    path = Path("catalog/index.html")
    page(path, "全部館藏", "搜尋作品、作者、譯本、分類與筆記。", catalogue(entries, path, "全部館藏", heading="h1"), "catalog")
    for kind, definitions, folder, field in (("media", config["media"], "media", "media"), ("category", config["categories"], "categories", "categories")):
        for key, label in definitions.items():
            items = [e for e in entries if (e["meta"][field] == key if field == "media" else key in e["meta"][field])]
            path = Path(folder) / key / "index.html"
            page(path, label, f"{label}相關館藏", catalogue(items, path, label, True, heading="h1"), f"{kind}:{key}")
    path = Path("tags/index.html")
    tag_cloud = '<div class="tag-index">' + "".join(f'<a href="{relative_url(tag_path(t), path)}"><span># {escape(t)}</span><strong>{count:02}</strong></a>' for t, count in sorted(tag_counts.items())) + '</div>'
    if not tag_counts:
        tag_cloud = '<p class="notice">館藏加入 tags 後，標籤會列於此處。</p>'
    page(path, "標籤索引", "以學科、題材及專業領域索引作品。", '<header class="page-heading"><h1>標籤索引</h1><p>依學科、題材與專業領域查找跨媒體作品。</p></header>' + tag_cloud, "tags")
    for tag in sorted(tag_counts):
        path = tag_path(tag)
        items = [e for e in entries if tag in e["meta"]["tags"]]
        page(path, f"標籤：{tag}", f"標籤 {tag} 的館藏", catalogue(items, path, f"標籤：{tag}", True, heading="h1"), "tags")

    def series_item(item, path):
        title = link(by_id[item["work"]]["output"], path, item["title"]) if item["work"] else '<span>' + escape(item["title"]) + '</span>'
        label = '<span class="series-part">' + escape(item["label"]) + '</span>' if item["label"] else ''
        original = '<span class="series-original">' + escape(item["original_title"]) + '</span>'
        pending = '<span class="muted">尚未收錄</span>' if not item["work"] else ''
        return label + '<span class="series-item-title">' + title + original + '</span>' + pending

    def series_orders(key, definition, path, current=""):
        html = ''
        for order in definition["orders"]:
            html += '<section class="series-order" id="series-' + key + '--order-' + order["id"] + '"><h3>' + escape(order["title"]) + '</h3>'
            if order["notes"]:
                html += '<p class="muted">' + escape(order["notes"]) + '</p>'
            if not order["ordered"]:
                html += '<p class="muted">此清單只列系列成員，不表示先後順序。</p>'
            tag = "ol" if order["ordered"] else "ul"
            html += f'<{tag} class="series-sequence">'
            for item in order["items"]:
                is_current = bool(current) and item["work"] == current
                html += '<li' + (' class="series-current" aria-current="true"' if is_current else '') + '>' + series_item(item, path)
                if is_current:
                    html += '<span class="series-current-label">本作品</span>'
                if item["notes"]:
                    html += '<p class="series-item-notes">' + escape(item["notes"]) + '</p>'
                html += '</li>'
            html += f'</{tag}>'
            if current and order["ordered"]:
                position = next((i for i, item in enumerate(order["items"]) if item["work"] == current), None)
                if position is not None:
                    neighbours = []
                    for offset, label in ((-1, "前一部"), (1, "後一部")):
                        neighbour = position + offset
                        if 0 <= neighbour < len(order["items"]):
                            neighbours.append('<div><span class="nav-label">' + label + '</span>' + series_item(order["items"][neighbour], path) + '</div>')
                    if neighbours:
                        html += '<nav class="series-neighbours" aria-label="' + escape(order["title"], quote=True) + '的前後作品">' + ''.join(neighbours) + '</nav>'
            html += '</section>'
        return html

    path = Path("series/index.html")
    series_index = '<header class="page-heading"><h1>系列索引</h1><p>依系列查看作品，以及出版、故事時間或閱讀順序。</p></header><div class="series-index">'
    for key, definition in series.items():
        series_index += '<article><h2>' + link(Path("series") / key / "index.html", path, definition["title"]) + '</h2><p class="series-original">' + escape(definition["original_title"]) + '</p><p>' + escape(definition["description"]) + '</p><p class="muted">' + str(len(definition["members"])) + ' 件已收錄 · ' + str(len(definition["orders"])) + ' 份清單</p></article>'
    if not series:
        series_index += '<p class="notice">尚未建立系列。可在 data/series.yml 整理系列成員與先後順序。</p>'
    page(path, "系列索引", "系列成員與不同閱讀順序", series_index + '</div>', "series")
    for key, definition in series.items():
        path = Path("series") / key / "index.html"
        content = '<header class="page-heading"><h1>' + escape(definition["title"]) + '</h1><p class="series-original">' + escape(definition["original_title"]) + '</p><p>' + escape(definition["description"]) + '</p></header>'
        if definition["aliases"]:
            content += '<p class="muted">別名：' + escape('、'.join(definition["aliases"])) + '</p>'
        content += series_orders(key, definition, path)
        if definition["sources"]:
            content += '<section class="sources-section"><h2>順序資料來源</h2><ul>' + ''.join(f'<li><a href="{escape(record["url"], quote=True)}">{escape(record["label"])}</a></li>' for record in definition["sources"]) + '</ul></section>'
        page(path, definition["title"], definition["description"], content, "series:" + key)

    for entry in entries:
        m, path = entry["meta"], entry["output"]
        breadcrumb = '<nav class="breadcrumbs" aria-label="館藏路徑">' + link(home, path, "館藏目錄") + '<span>/</span>' + link(Path("media") / m["media"] / "index.html", path, config["media"][m["media"]]) + '<span>/</span><span>館藏資料</span></nav>'
        heading = f'<header class="work-heading"><p class="eyebrow">COLLECTION / {escape(m["id"].upper())}</p><h1>{escape(m["title"])}</h1><p class="work-original"><span class="original-label">原文標題</span>{escape(m["original_title"])}</p></header>'
        facts = '<dl class="work-facts">'
        for label, value in (("媒體", config["media"][m["media"]]), ("原作年份", m["year"] or "待補"), ("原作語言", m["original_language"] or "待補"), ("探索狀態", STATUSES[m["status"]]), ("收錄日期", m["added"])):
            facts += f'<div><dt>{label}</dt><dd>{escape(str(value))}</dd></div>'
        if m["aliases"]:
            facts += f'<div><dt>其他譯名／別名</dt><dd>{escape("、".join(m["aliases"]))}</dd></div>'
        for creator in m["creators"]:
            facts += f'<div><dt>{escape(creator["role"])}</dt><dd>{escape(creator["name"])}</dd></div>'
        facts += '</dl>'
        info = '<aside class="work-info">' + plate(entry, path, True) + '<p class="plate-caption">' + ('館藏封面' if m["cover"] else '自製藏書票 · 非原作封面') + '</p>' + facts
        info += '<p class="nav-label">作品分類</p><div class="tags">' + "".join(link(Path("categories") / c / "index.html", path, config["categories"][c], "tag") for c in m["categories"]) + '</div><p class="nav-label">學科／題材標籤</p>' + tags_html(m["tags"], path) + '</aside>'
        article = '<div class="work-reading"><section class="summary-section"><p class="eyebrow">ABOUT THE WORK</p><h2>內容簡介</h2><p>' + escape(m["summary"]) + '</p></section>'
        if m["features"]:
            article += '<section class="features-section"><h2>作品特色</h2><p>' + escape(m["features"]) + '</p></section>'
        if m["example"]:
            article += '<p class="notice">這是範例館藏；狀態及個人筆記為格式示範。</p>'
        if memberships[m["id"]]:
            article += '<section class="work-series"><h2>所屬系列與先後關係</h2>'
            for key in memberships[m["id"]]:
                definition = series[key]
                article += '<details class="series-details" open><summary>' + escape(definition["title"]) + '</summary><p>' + link(Path("series") / key / "index.html", path, "完整系列與順序來源 ↗") + '</p>' + series_orders(key, definition, path, m["id"]) + '</details>'
            article += '</section>'
        article += '<section class="editions-section" id="editions"><div class="section-heading"><h2>譯本與發行版本</h2><span>' + str(len(m["editions"])) + ' 個版本</span></div>'
        for edition in m["editions"]:
            title = escape(edition["title"])
            if edition["url"]:
                title = f'<a href="{escape(edition["url"], quote=True)}">{title} ↗</a>'
            details = " · ".join(str(v) for v in (edition["language"], edition["format"], edition["publisher"], edition["year"]) if v)
            article += '<article class="edition"><h3>' + title + '</h3><p class="edition-meta">' + escape(details) + '</p>'
            if edition["translators"]:
                article += '<p><span class="muted">譯者</span> ' + escape("、".join(edition["translators"])) + '</p>'
            if edition["isbn"]:
                article += '<p class="isbn">ISBN ' + escape(edition["isbn"]) + '</p>'
            if edition["notes"]:
                article += '<p>' + escape(edition["notes"]) + '</p>'
            article += '</article>'
        if not m["editions"]:
            article += '<p class="notice">版本資訊尚未整理，之後可以補上譯者、出版社、字幕或平台版本。</p>'
        article += '</section>'
        if entry["toc"]:
            article += '<details class="reading-toc"><summary>筆記目錄</summary>' + entry["toc"] + '</details>'
        if entry["rendered"].strip():
            article += '<article class="prose" aria-label="館藏筆記">' + entry["rendered"] + '</article>'
        if m["sources"]:
            article += '<section class="sources-section"><h2>資料來源</h2><ul>' + "".join(f'<li><a href="{escape(s["url"], quote=True)}">{escape(s["label"])} ↗</a></li>' for s in m["sources"]) + '</ul></section>'
        article += '</div>'
        related = [by_id[k] for k in m["related"]]
        others = [e for e in entries if e != entry and e not in related]
        def score(other):
            return len(set(m["tags"]) & set(other["meta"]["tags"])) * 3 + len(set(m["categories"]) & set(other["meta"]["categories"]))
        others.sort(key=score, reverse=True)
        related += [e for e in others if score(e) > 0]
        content = breadcrumb + heading + '<div class="work-layout">' + info + article + '</div>'
        if related:
            content += '<section class="related-shelf"><div class="section-heading"><h2>相關作品</h2><p>共同分類或標籤</p></div>' + work_list(related[:3], path) + '</section>'
        page(path, m["title"], m["summary"], content, f"media:{m['media']}")
    for name, content in static.items():
        add(Path("_static") / name, content)
    for original, destination in assets.items():
        add(destination, original.read_bytes())
    add(Path(".nojekyll"), "")

    def destination(name):
        rel = PurePosixPath(name)
        if not name or rel.is_absolute() or ".." in rel.parts or "\\" in name or ":" in name or name == MANIFEST:
            raise ValueError(f"無效的生成檔案路徑：{name}")
        target = output.joinpath(*rel.parts)
        if target == output or output not in target.resolve().parents:
            raise ValueError(f"生成檔案超出輸出目錄：{name}")
        if any(p.is_symlink() for p in (target, *target.parents) if p == output or output in p.parents):
            raise ValueError(f"輸出路徑包含符號連結：{name}")
        return target

    manifest = output / MANIFEST
    if manifest.is_symlink():
        raise ValueError("生成記錄不能是符號連結")
    previous = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else []
    if not isinstance(previous, list) or any(not isinstance(p, str) for p in previous):
        raise ValueError(f"生成記錄格式錯誤：{manifest}")
    previous_set = set(previous)
    current = {p.as_posix() for p in generated}
    managed_casefold = {name.casefold() for name in previous_set}
    for name in previous_set | current:
        target = destination(name)
        if target.exists() and (not target.is_file() or name.casefold() not in managed_casefold):
            raise ValueError(f"拒絕覆寫非本腳本管理的檔案：{target}")
        if any(parent.exists() and not parent.is_dir() for parent in target.parents):
            raise ValueError(f"輸出路徑的父層不是目錄：{target}")
    # Validate every entry, link and destination before changing the output.
    output.mkdir(parents=True, exist_ok=True)
    for rel, content in generated.items():
        target = destination(rel.as_posix())
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    if prune:
        for name in previous_set - current:
            destination(name).unlink(missing_ok=True)
    managed = current if prune else previous_set | current
    manifest.write_text(json.dumps(sorted(managed), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(entries)


def main():
    parser = argparse.ArgumentParser(description="把 Markdown 館藏生成為靜態興趣圖書館")
    parser.add_argument("--source", type=Path, default=ROOT / "data", help="資料目錄，預設為腳本旁的 data/")
    parser.add_argument("--output", type=Path, default=ROOT / "site", help="生成目錄，預設為腳本旁的 site/")
    parser.add_argument("--config", type=Path, default=ROOT / "library.yml", help="網站與分類設定")
    parser.add_argument("--prune", action="store_true", help="刪除不再使用的受管理生成檔案；預設保留")
    args = parser.parse_args()
    try:
        count = build(args.source, args.output, args.config, args.prune)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"生成失敗：{exc}", file=sys.stderr)
        return 1
    print(f"已生成 {count} 件館藏：{args.output.expanduser().resolve() / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
