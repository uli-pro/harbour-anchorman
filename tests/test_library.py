import json
import os
import struct
import unittest
from unittest import mock

from bookfish import library
from bookfish.errors import EpubError
from bookfish.library import (BookFile, book_info, broken_info, card_folders, extract_cover,
                               list_books, load_cached, normal_identifier,
                               prune_covers, scan, without_replaced)

from .helpers import TempDirTestCase, make_epub, write_files


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
        extra="", overlay=False):
    return """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" xmlns:dc="http://purl.org/dc/elements/1.1/"
         version="3.0" unique-identifier="uid">
  <metadata><dc:identifier id="uid">{}</dc:identifier><dc:title>{}</dc:title>{}{}</metadata>
  <manifest><item id="c" href="c.xhtml" media-type="application/xhtml+xml"{}/>
    <item id="s" href="c.smil" media-type="application/smil+xml"/>
    <item id="img" href="cover.png" media-type="image/png" properties="cover-image"/></manifest>
  <spine><itemref idref="c"/></spine>
</package>""".format(identifier, title, creator, extra,
                     ' media-overlay="s"' if overlay else "")


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
                                   '<meta name="calibre:series_index" content="3"/>', overlay=True),
                   audio=True)
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

    def test_drm_listed_as_broken(self):
        path = os.path.join(self.tmp, "drm.epub")
        make_epub(path, [("META-INF/container.xml", CONTAINER), ("OPS/p.opf", opf()),
                         ("META-INF/encryption.xml",
                          '<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container" '
                          'xmlns:enc="http://www.w3.org/2001/04/xmlenc#"><enc:EncryptedData>'
                          '<enc:EncryptionMethod Algorithm="aes"/></enc:EncryptedData></encryption>')])
        info = book_info(path)
        self.assertEqual((info["title"], info["broken"]), ("A Book", True))

    def test_smil_without_overlay_is_no_readaloud(self):
        path = os.path.join(self.tmp, "b.epub")
        write_book(path, audio=True)
        self.assertFalse(book_info(path)["audio"])

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
        entries, changed = scan([self.books], self.cache)
        self.assertEqual([e["info"]["title"] for e in entries], ["A Book", "B"])
        self.assertTrue(changed)
        self.assertEqual(scan([self.books], self.cache), (entries, False))
        write_book(b, package=opf(title="B2"))
        os.utime(b, ns=(1, 1))
        os.remove(a)
        with mock.patch("bookfish.library.book_info", wraps=library.book_info) as read:
            entries, changed = scan([self.books], self.cache)
        self.assertEqual([e["info"]["title"] for e in entries], ["B2"])
        self.assertTrue(changed)
        self.assertEqual(read.call_count, 1)
        self.assertEqual(load_cached(self.cache), entries)

    def test_other_and_missing_folders_stay_cached(self):
        other = os.path.join(self.tmp, "card")
        os.makedirs(other)
        write_book(os.path.join(other, "c.epub"))
        self.book("a.epub")
        scan([self.books, other], self.cache)
        scan([self.books], self.cache)  # one folder chosen
        os.rename(other, other + "-out")  # card taken out
        entries, changed = scan([self.books, other], self.cache)
        self.assertEqual(len(entries), 1)
        self.assertFalse(changed)
        self.assertEqual(len(load_cached(self.cache)), 2)

    def test_read_again_after_a_passing_error(self):
        path = self.book("a.epub")
        with mock.patch("bookfish.library.book_info", side_effect=OSError("card gone")):
            entry = scan([self.books], self.cache)[0][0]
        self.assertTrue(entry["info"]["broken"])
        entry = scan([self.books], self.cache)[0][0]
        self.assertFalse(entry["info"]["broken"])
        with mock.patch("bookfish.library.book_info", side_effect=EpubError("bad_xml")):
            os.utime(path, ns=(2, 2))
            scan([self.books], self.cache)
        self.assertTrue(scan([self.books], self.cache)[0][0]["info"]["broken"])

    def test_fifo_and_folder_are_not_opened(self):
        os.mkfifo(os.path.join(self.books, "pipe.epub"))  # would hang if opened
        os.mkdir(os.path.join(self.books, "folder.epub"))
        self.assertEqual(scan([self.books], self.cache)[0], [])
        with self.assertRaises(EpubError):
            book_info(os.path.join(self.books, "pipe.epub"))

    def test_broken_book_listed_by_file_name(self):
        write_files(self.books, {"Broken Book.epub": b"no zip"})
        info = scan([self.books], self.cache)[0][0]["info"]
        self.assertEqual((info["title"], info["broken"]), ("Broken Book", True))

    def test_damaged_cache_is_ignored(self):
        self.book("a.epub")
        for content in ("{", "[]", '{"version": 4, "books": [{"path": 5}]}',
                        '{"version": 99, "books": []}', "[" * 100000 + "]" * 100000):
            write_files(os.path.dirname(self.cache), {"library.json": content})
            self.assertEqual(load_cached(self.cache), [])
            self.assertEqual(len(scan([self.books], self.cache)[0]), 1)

    def test_entry_with_wrong_types_is_dropped(self):
        self.book("a.epub")
        entry = scan([self.books], self.cache)[0][0]
        for field, value in (("authors", [1]), ("index", float("nan")), ("index", True)):
            bad = dict(entry, info=dict(entry["info"], **{field: value}))
            write_files(os.path.dirname(self.cache), {"library.json": json.dumps(
                {"version": 4, "books": [bad]})})
            self.assertEqual(load_cached(self.cache), [], field)


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

    def test_huge_png_refused(self):
        path = os.path.join(self.tmp, "b.epub")
        header = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        write_book(path, cover=header + struct.pack(">II", 20000, 100) + b"rest")
        self.assertFalse(extract_cover(path, "OPS/cover.png", os.path.join(self.tmp, "c.png")))
        write_book(path, cover=header + struct.pack(">II", 1000, 1500) + b"rest")
        self.assertTrue(extract_cover(path, "OPS/cover.png", os.path.join(self.tmp, "c.png")))

    def test_oversized_cover(self):
        path = os.path.join(self.tmp, "b.epub")
        write_book(path, cover=b"x" * (5 * 1024 * 1024 + 1))
        self.assertFalse(extract_cover(path, "OPS/cover.png", os.path.join(self.tmp, "c.png")))
