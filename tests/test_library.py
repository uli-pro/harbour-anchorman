import json
import os
import unittest
import zipfile
from unittest import mock

from anchorman import library
from anchorman.errors import EpubError
from anchorman.library import (BookFile, book_info, broken_info, card_folders, extract_cover,
                               is_readaloud, list_books, load_cached, normal_identifier,
                               prune_covers, scan, without_replaced)

from .helpers import TempDirTestCase, make_epub, write_files


def make_zip(path, names):
    with zipfile.ZipFile(path, "w") as archive:
        for name in names:
            archive.writestr(name, "x")


class ListBooksTest(TempDirTestCase):

    def path(self, name):
        return os.path.join(self.tmp, *name.split("/"))

    def test_finds_epubs_in_subfolders_sorted_by_name(self):
        write_files(self.tmp, {
            "b/zebra.epub": "", "apple.EPUB": "", "a/Mango.epub": "",
            "notes.txt": "", "book.epub.part": ""})
        self.assertEqual(list_books([self.tmp]), [
            BookFile(self.path("apple.EPUB"), "apple"),
            BookFile(self.path("a/Mango.epub"), "Mango"),
            BookFile(self.path("b/zebra.epub"), "zebra")])

    def test_hidden_files_and_folders_left_out(self):
        write_files(self.tmp, {".hidden.epub": "", ".trash/old.epub": "",
                               "book.epub": ""})
        self.assertEqual([b.name for b in list_books([self.tmp])], ["book"])

    def test_links_to_folders_not_followed(self):
        write_files(self.tmp, {"books/book.epub": ""})
        os.symlink(self.tmp, self.path("books/loop"))
        self.assertEqual([b.path for b in list_books([self.path("books")])],
                         [self.path("books/book.epub")])

    def test_several_folders(self):
        write_files(self.tmp, {"one/b.epub": "", "two/a.epub": ""})
        self.assertEqual(
            [b.name for b in list_books([self.path("one"), self.path("two")])],
            ["a", "b"])

    def test_missing_folder(self):
        self.assertEqual(list_books([self.path("missing")]), [])

    def test_accept(self):
        write_files(self.tmp, {"a.epub": "", "b.epub": ""})
        books = list_books([self.tmp], lambda path: path.endswith("b.epub"))
        self.assertEqual([b.name for b in books], ["b"])

    def test_link_to_a_listed_book_lists_it_once(self):
        write_files(self.tmp, {"a.epub": ""})
        os.symlink(self.path("a.epub"), self.path("b.epub"))
        self.assertEqual(len(list_books([self.tmp])), 1)

    def test_names_not_valid_utf8_left_out(self):
        write_files(self.tmp, {"good.epub": ""})
        open(os.path.join(self.tmp.encode(), b"bad\xff.epub"), "w").close()
        self.assertEqual([b.name for b in list_books([self.tmp])], ["good"])

    def test_same_folder_twice_lists_books_once(self):
        write_files(self.tmp, {"a.epub": ""})
        self.assertEqual(len(list_books([self.tmp, self.tmp])), 1)


class IsReadaloudTest(TempDirTestCase):

    def path(self, name):
        return os.path.join(self.tmp, name)

    def test_with_smil(self):
        make_zip(self.path("a.epub"), ["mimetype", "OEBPS/MediaOverlays/c.smil"])
        self.assertTrue(is_readaloud(self.path("a.epub")))

    def test_upper_case(self):
        make_zip(self.path("a.epub"), ["OPS/C.SMIL"])
        self.assertTrue(is_readaloud(self.path("a.epub")))

    def test_without_smil(self):
        make_zip(self.path("a.epub"), ["mimetype", "OEBPS/c.xhtml", "OEBPS/smil.txt"])
        self.assertFalse(is_readaloud(self.path("a.epub")))

    def test_unreadable(self):
        write_files(self.tmp, {"text.epub": "not a zip", "empty.epub": ""})
        self.assertFalse(is_readaloud(self.path("text.epub")))
        self.assertFalse(is_readaloud(self.path("empty.epub")))
        self.assertFalse(is_readaloud(self.path("missing.epub")))
        os.mkdir(self.path("folder.epub"))
        self.assertFalse(is_readaloud(self.path("folder.epub")))

    def test_fifo_is_not_opened(self):
        os.mkfifo(self.path("pipe.epub"))
        self.assertFalse(is_readaloud(self.path("pipe.epub")))  # would hang if opened


class CardFoldersTest(TempDirTestCase):

    def test_folders_only_sorted(self):
        write_files(self.tmp, {"b-card/x": "", "a-card/x": "", "file": ""})
        self.assertEqual(card_folders(self.tmp), [os.path.join(self.tmp, "a-card"),
                                                  os.path.join(self.tmp, "b-card")])

    def test_missing(self):
        self.assertEqual(card_folders(os.path.join(self.tmp, "missing")), [])


CONTAINER = """<?xml version="1.0"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
  <rootfiles><rootfile full-path="OPS/p.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>"""


def opf(identifier="id-1", title="A Book", creator="<dc:creator>Ann Author</dc:creator>",
        extra=""):
    return """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" xmlns:dc="http://purl.org/dc/elements/1.1/"
         version="3.0" unique-identifier="uid">
  <metadata><dc:identifier id="uid">{}</dc:identifier><dc:title>{}</dc:title>{}{}</metadata>
  <manifest><item id="c" href="c.xhtml" media-type="application/xhtml+xml"/>
    <item id="img" href="cover.png" media-type="image/png" properties="cover-image"/></manifest>
  <spine><itemref idref="c"/></spine>
</package>""".format(identifier, title, creator, extra)


def write_book(path, package=None, audio=False, cover=b"PNG"):
    entries = [("mimetype", b"application/epub+zip"), ("META-INF/container.xml", CONTAINER),
               ("OPS/p.opf", package or opf()), ("OPS/c.xhtml", "<html/>")]
    if cover is not None:
        entries.append(("OPS/cover.png", cover))
    if audio:
        entries.append(("OPS/c.smil", "<smil/>"))
    make_epub(path, entries)


class BookInfoTest(TempDirTestCase):

    def test_read_from_the_zip(self):
        path = os.path.join(self.tmp, "b.epub")
        write_book(path, opf(extra='<meta name="calibre:series" content="S"/>'
                                   '<meta name="calibre:series_index" content="3"/>'), audio=True)
        self.assertEqual(book_info(path), {
            "identifier": "id-1", "title": "A Book", "authors": ["Ann Author"], "sort": "Ann Author",
            "series": "S", "index": 3.0, "cover": "OPS/cover.png", "audio": True, "broken": False})

    def test_unusable_books_raise(self):
        cases = {
            "notzip.epub": b"no zip",
            "nocontainer.epub": [("mimetype", b"application/epub+zip")],
            "dtd.epub": [("META-INF/container.xml", CONTAINER),
                         ("OPS/p.opf", '<!DOCTYPE p [<!ENTITY a "x">]><p/>')],
        }
        for name, content in cases.items():
            path = os.path.join(self.tmp, name)
            if isinstance(content, bytes):
                write_files(self.tmp, {name: content})
            else:
                make_epub(path, content)
            with self.assertRaises(Exception, msg=name):
                book_info(path)

    def test_oversized_package_document(self):
        path = os.path.join(self.tmp, "big.epub")
        write_book(path, opf(extra="<!--" + "x" * (10 * 1024 * 1024) + "-->"))
        with self.assertRaises(EpubError) as cm:
            book_info(path)
        self.assertEqual(cm.exception.code, "too_large")


class ScanTest(TempDirTestCase):

    def setUp(self):
        super().setUp()
        self.books = os.path.join(self.tmp, "books")
        self.cache = os.path.join(self.tmp, "cache", "library.json")
        os.makedirs(self.books)

    def book(self, name, **kwargs):
        path = os.path.join(self.books, name)
        write_book(path, **kwargs)
        return path

    def test_reads_only_new_and_changed_books(self):
        a = self.book("a.epub")
        b = self.book("b.epub", package=opf(title="B"))
        self.assertEqual([e["info"]["title"] for e in scan([self.books], self.cache)], ["A Book", "B"])
        write_book(b, package=opf(title="B2"))
        os.utime(b, ns=(1, 1))
        os.remove(a)
        with mock.patch("anchorman.library.book_info", wraps=library.book_info) as read:
            entries = scan([self.books], self.cache)
        self.assertEqual([e["info"]["title"] for e in entries], ["B2"])
        self.assertEqual(read.call_count, 1)
        self.assertEqual(load_cached(self.cache), entries)

    def test_broken_book_listed_by_file_name(self):
        write_files(self.books, {"Broken Book.epub": b"no zip"})
        info = scan([self.books], self.cache)[0]["info"]
        self.assertEqual((info["title"], info["broken"]), ("Broken Book", True))

    def test_damaged_cache_is_ignored(self):
        self.book("a.epub")
        for content in ("{", "[]", '{"version": 1, "books": [{"path": 5}]}',
                        '{"version": 99, "books": []}'):
            write_files(os.path.dirname(self.cache), {"library.json": content})
            self.assertEqual(load_cached(self.cache), [])
            self.assertEqual(len(scan([self.books], self.cache)), 1)

    def test_entry_with_wrong_types_is_dropped(self):
        self.book("a.epub")
        entry = scan([self.books], self.cache)[0]
        entry["info"]["authors"] = [1]
        write_files(os.path.dirname(self.cache), {"library.json": json.dumps(
            {"version": 1, "books": [entry]})})
        self.assertEqual(load_cached(self.cache), [])


class ReplacedTest(unittest.TestCase):

    def entry(self, identifier, title, audio):
        info = dict(broken_info("x"), identifier=identifier, title=title, audio=audio, broken=False)
        return {"path": title + str(audio), "stamp": [0, 0], "info": info}

    def test_readaloud_replaces_its_epub(self):
        epub = self.entry("urn:uuid:ABC", "Patriot Games", False)
        readaloud = self.entry("uuid:abc", "Patriot Games", True)
        other_title = self.entry("urn:uuid:abc", "Red Rabbit", False)
        other_id = self.entry("urn:uuid:xyz", "Patriot Games", False)
        no_id = self.entry("", "Patriot Games", False)
        self.assertEqual(without_replaced([epub, readaloud, other_title, other_id, no_id]),
                         [readaloud, other_title, other_id, no_id])

    def test_normal_identifier(self):
        for identifier in ("urn:uuid:abc", "uuid:ABC", " abc ", "url:abc"):
            self.assertEqual(normal_identifier(identifier), "abc")
        self.assertEqual(normal_identifier("urn:asin:B006"), "b006")


class CoverTest(TempDirTestCase):

    def test_extract_and_prune(self):
        path = os.path.join(self.tmp, "b.epub")
        write_book(path)
        covers = os.path.join(self.tmp, "covers")
        os.makedirs(covers)
        target = os.path.join(covers, "0123456789abcdef.png")
        self.assertTrue(extract_cover(path, "OPS/cover.png", target))
        with open(target, "rb") as f:
            self.assertEqual(f.read(), b"PNG")
        self.assertFalse(extract_cover(path, "OPS/missing.png", target + "x"))
        write_files(covers, {"fedcba9876543210.jpg": "", "other.txt": ""})
        prune_covers(covers, {"0123456789abcdef"})
        self.assertEqual(sorted(os.listdir(covers)), ["0123456789abcdef.png", "other.txt"])

    def test_oversized_cover(self):
        path = os.path.join(self.tmp, "b.epub")
        write_book(path, cover=b"x" * (5 * 1024 * 1024 + 1))
        self.assertFalse(extract_cover(path, "OPS/cover.png", os.path.join(self.tmp, "c.png")))
