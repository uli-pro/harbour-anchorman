import json
import os

from anchorman import bridge

from .helpers import TempDirTestCase, make_epub, mini_entries, write_files

SMIL = """<?xml version="1.0"?>
<smil xmlns="http://www.w3.org/ns/SMIL" version="3.0"><body>
  <par><text src="a.xhtml#s1"/><audio src="a.mp3" clipBegin="0s" clipEnd="1s"/></par>
  <par><text src="b.xhtml#s2"/><audio src="a.mp3" clipBegin="1s" clipEnd="2s"/></par>
  <par><text src="a.xhtml#s3"/><audio src="a.mp3" clipBegin="2s" clipEnd="3s"/></par>
  <par><text src="a.xhtml#s1"/><audio src="a.mp3" clipBegin="3s" clipEnd="4s"/></par>
  <par><text src="a.xhtml#s4"/><audio src="a.mp3" clipBegin="5s" clipEnd="4s"/></par>
</body></smil>"""


class BridgeTest(TempDirTestCase):

    def setUp(self):
        super().setUp()
        self.cache_dir = os.path.join(self.tmp, "cache")
        self.epub = os.path.join(self.tmp, "happy-prince.epub")
        make_epub(self.epub, mini_entries())

    def test_list_books(self):
        self.assertEqual(bridge.list_books([self.tmp]),
                         [{"path": self.epub, "name": "happy-prince"}])

    def test_open_book(self):
        book = bridge.open_book(self.epub, self.cache_dir)
        json.dumps(book)  # QML gets only plain values
        self.assertEqual(os.path.dirname(book["root"]), self.cache_dir)
        self.assertEqual(book["key"], "urn:uuid:4f1c2a9e-6b0d-4d5e-9a57-3c8e2f7b1d60")
        self.assertEqual(book["title"], "The Happy Prince")
        self.assertEqual(book["authors"], ["Wilde, Oscar"])
        self.assertEqual(book["language"], "en")
        self.assertEqual(book["duration"], 39000)
        self.assertEqual(book["activeClass"], "-epub-media-overlay-active")
        self.assertEqual(book["spine"], [
            {"path": "OEBPS/title.xhtml", "overlay": None, "linear": True},
            {"path": "OEBPS/chapter.xhtml",
             "overlay": "OEBPS/MediaOverlays/chapter.smil", "linear": True}])
        self.assertEqual(book["toc"], [
            {"title": "Title Page", "path": "OEBPS/title.xhtml", "fragment": "",
             "level": 0, "spine": 0},
            {"title": "The Happy Prince.", "path": "OEBPS/chapter.xhtml",
             "fragment": "chap01", "level": 0, "spine": 1}])

    def test_toc_entry_outside_spine(self):
        entries = [(name, data.replace(b'href="title.xhtml"', b'href="extra.xhtml"'))
                   if name == "OEBPS/nav.xhtml" else (name, data)
                   for name, data in mini_entries()]
        make_epub(self.epub, entries)
        toc = bridge.open_book(self.epub, self.cache_dir)["toc"]
        self.assertEqual((toc[0]["path"], toc[0]["spine"]), ("OEBPS/extra.xhtml", -1))

    def test_key_falls_back_to_file_name(self):
        entries = [(name, data.replace(b"<dc:identifier", b"<dc:source")
                    .replace(b"</dc:identifier>", b"</dc:source>"))
                   if name == "OEBPS/content.opf" else (name, data)
                   for name, data in mini_entries()]
        make_epub(self.epub, entries)
        self.assertEqual(bridge.open_book(self.epub, self.cache_dir)["key"],
                         "happy-prince.epub")

    def test_huge_identifier_gives_short_key(self):
        entries = [(name, data.replace(b"urn:uuid:4f1c2a9e-6b0d-4d5e-9a57-3c8e2f7b1d60",
                                       b"x" * 100000))
                   if name == "OEBPS/content.opf" else (name, data)
                   for name, data in mini_entries()]
        make_epub(self.epub, entries)
        key = bridge.open_book(self.epub, self.cache_dir)["key"]
        self.assertTrue(key.startswith("sha1:"))
        self.assertEqual(len(key), 45)

    def test_broken_book(self):
        with open(self.epub, "wb") as f:
            f.write(b"not a zip")
        result = bridge.open_book(self.epub, self.cache_dir)
        self.assertEqual(result["error"], "not_zip")

    def test_missing_file(self):
        result = bridge.open_book(os.path.join(self.tmp, "missing.epub"), self.cache_dir)
        self.assertEqual(result["error"], "io")

    def test_chapter_lengths(self):
        root = bridge.open_book(self.epub, self.cache_dir)["root"]
        paths = ["OEBPS/title.xhtml", "OEBPS/chapter.xhtml", "OEBPS/title.xhtml",
                 "OEBPS/missing.xhtml"]
        self.assertEqual(bridge.chapter_lengths(root, paths), [31, 233, 31, 0])

    def test_read_chapter(self):
        book = bridge.open_book(self.epub, self.cache_dir)
        chapter = book["spine"][1]
        self.assertEqual(
            bridge.read_chapter(book["root"], chapter["path"], chapter["overlay"]),
            {"ids": ["chapter-s0", "chapter-s1", "chapter-s2"], "skipped": 0})

    def test_read_chapter_keeps_ids_of_this_chapter_once(self):
        write_files(self.tmp, {"book/a.smil": SMIL})
        root = os.path.join(self.tmp, "book")
        self.assertEqual(bridge.read_chapter(root, "a.xhtml", "a.smil"),
                         {"ids": ["s1", "s3"], "skipped": 1})

    def test_read_chapter_errors(self):
        write_files(self.tmp, {"book/bad.smil": "<smil"})
        root = os.path.join(self.tmp, "book")
        self.assertEqual(bridge.read_chapter(root, "a.xhtml", "bad.smil")["error"],
                         "bad_xml")
        self.assertEqual(bridge.read_chapter(root, "a.xhtml", "missing.smil")["error"],
                         "bad_overlay")

    def test_positions(self):
        path = os.path.join(self.tmp, "positions.json")
        self.assertIsNone(bridge.load_position(path, "book"))
        position = {"spine": 1, "id": "chapter-s1", "fraction": 0.5}
        self.assertIs(bridge.save_position(path, "book", position), True)
        self.assertEqual(bridge.load_position(path, "book"), position)

    def test_last_book(self):
        path = os.path.join(self.tmp, "positions.json")
        self.assertIsNone(bridge.load_last_book(path))
        self.assertIs(bridge.save_last_book(path, self.epub), True)
        self.assertEqual(bridge.load_last_book(path), self.epub)
        open(os.path.join(self.tmp, "file"), "w").close()
        broken = os.path.join(self.tmp, "file", "positions.json")
        self.assertEqual(bridge.save_last_book(broken, self.epub)["error"], "io")

    def test_save_position_creates_folder(self):
        path = os.path.join(self.tmp, "new", "positions.json")
        position = {"spine": 0, "id": "", "fraction": 0}
        self.assertIs(bridge.save_position(path, "book", position), True)

    def test_save_position_io_error(self):
        open(os.path.join(self.tmp, "file"), "w").close()
        path = os.path.join(self.tmp, "file", "positions.json")
        result = bridge.save_position(path, "book", {"spine": 0, "id": "", "fraction": 0})
        self.assertEqual(result["error"], "io")
