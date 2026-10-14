"""Dependency-free GitHub Pages publication checks."""

import re
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
PUBLIC_URL = "https://aswin-blix.github.io/NetPulse/"


class Page(HTMLParser):
    """Collect markup attributes and text without a browser dependency."""

    VOID_TAGS = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }

    def __init__(self, source):
        super().__init__()
        self.elements = []
        self.stack = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        element = {"tag": tag, "attrs": dict(attrs), "text": ""}
        self.elements.append(element)
        if tag not in self.VOID_TAGS:
            self.stack.append(element)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]["tag"] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        if any(element["attrs"].get("aria-hidden") == "true" for element in self.stack):
            return
        for element in self.stack:
            element["text"] += data

    def tags(self, tag):
        return [element for element in self.elements if element["tag"] == tag]


class SiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = Page((SITE / "index.html").read_text(encoding="utf-8"))
        cls.ids = {
            element["attrs"]["id"]: element
            for element in cls.page.elements
            if "id" in element["attrs"]
        }

    def test_ids_and_internal_references_resolve(self):
        ids = [element["attrs"]["id"] for element in self.page.elements if "id" in element["attrs"]]
        self.assertEqual(len(ids), len(set(ids)), "Duplicate HTML IDs")
        for element in self.page.elements:
            attrs = element["attrs"]
            references = []
            href = attrs.get("href", "")
            if href.startswith("#") and len(href) > 1:
                references.append(unquote(href[1:]))
            for attribute in ("for", "aria-labelledby", "aria-describedby"):
                references.extend(attrs.get(attribute, "").split())
            for target in references:
                with self.subTest(element=element["tag"], target=target):
                    self.assertIn(target, self.ids)

    def test_local_assets_work_under_project_url(self):
        resources = []
        for element in self.page.elements:
            for attribute in ("src", "href"):
                value = element["attrs"].get(attribute, "")
                if value and not value.startswith("#"):
                    resources.append(value)
        css = (SITE / "styles.css").read_text(encoding="utf-8")
        resources.extend(re.findall(r"url\([\"']?([^\s)\"']+)", css))
        local_count = 0
        for resource in resources:
            parsed = urlsplit(resource)
            if parsed.scheme or parsed.netloc:
                continue
            with self.subTest(resource=resource):
                resolved = urlsplit(urljoin(PUBLIC_URL, resource))
                self.assertTrue(resolved.path.startswith("/NetPulse/"))
                relative = unquote(resolved.path.removeprefix("/NetPulse/"))
                target = (SITE / relative).resolve()
                self.assertTrue(target.is_relative_to(SITE.resolve()))
                self.assertTrue(target.is_file(), f"Missing local resource: {resource}")
                local_count += 1
        self.assertGreaterEqual(local_count, 4)

    def test_controls_and_images_have_accessible_names(self):
        labels = {
            element["attrs"].get("for"): element["text"].strip()
            for element in self.page.tags("label")
        }
        for element in self.page.elements:
            attrs = element["attrs"]
            with self.subTest(tag=element["tag"], id=attrs.get("id")):
                if element["tag"] in {"a", "button", "summary"}:
                    self.assertTrue(attrs.get("aria-label") or element["text"].strip())
                elif element["tag"] == "input":
                    self.assertTrue(attrs.get("aria-label") or labels.get(attrs.get("id")))
                elif element["tag"] == "img":
                    self.assertTrue(attrs.get("alt", "").strip())
                    self.assertGreater(int(attrs["width"]), 0)
                    self.assertGreater(int(attrs["height"]), 0)
        self.assertEqual(self.ids["copy-status"]["attrs"]["role"], "status")
        self.assertEqual(self.ids["demo-widget"]["attrs"]["tabindex"], "0")

    def test_page_metadata_and_landmarks(self):
        self.assertEqual(self.page.tags("html")[0]["attrs"]["lang"], "en")
        self.assertEqual(len(self.page.tags("h1")), 1)
        self.assertEqual(len(self.page.tags("main")), 1)
        self.assertIn("NetPulse", self.page.tags("title")[0]["text"])
        metadata = {
            element["attrs"].get("name", element["attrs"].get("property")): element["attrs"].get(
                "content"
            )
            for element in self.page.tags("meta")
        }
        self.assertTrue(metadata["description"])
        self.assertIn("width=device-width", metadata["viewport"])
        self.assertEqual(metadata["og:url"], PUBLIC_URL)
        canonical = [
            element["attrs"]["href"]
            for element in self.page.tags("link")
            if element["attrs"].get("rel") == "canonical"
        ]
        self.assertEqual(canonical, [PUBLIC_URL])

    def test_script_bindings_and_source_command_exist(self):
        script = (SITE / "script.js").read_text(encoding="utf-8")
        bound_ids = re.findall(r"getElementById\([\"']([^\"']+)[\"']\)", script)
        self.assertTrue(bound_ids)
        for element_id in bound_ids:
            with self.subTest(element_id=element_id):
                self.assertIn(element_id, self.ids)
        self.assertEqual(self.ids["run-command"]["text"].strip(), "python source/app.py")
        self.assertTrue((ROOT / "source" / "app.py").is_file())

    def test_publication_contains_only_static_site_assets(self):
        allowed = {
            ".html",
            ".css",
            ".js",
            ".png",
            ".jpg",
            ".jpeg",
            ".webp",
            ".svg",
            ".ico",
            ".woff",
            ".woff2",
            ".txt",
            ".xml",
        }
        for path in SITE.rglob("*"):
            with self.subTest(path=path.relative_to(SITE)):
                self.assertFalse(path.is_symlink(), "Do not publish links outside the site")
                if path.is_file() and path.name != ".nojekyll":
                    self.assertIn(path.suffix.lower(), allowed)
        workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
        self.assertRegex(workflow, r"(?m)^\s+path:\s*['\"]?site['\"]?\s*$")
        self.assertEqual(len(re.findall(r"actions/upload-pages-artifact@", workflow)), 1)
        self.assertTrue((SITE / ".nojekyll").is_file())


if __name__ == "__main__":
    unittest.main()
