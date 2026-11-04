import os

import zipfile

from anchorman.library import BookFile, card_folders, is_readaloud, list_books

from .helpers import TempDirTestCase, write_files


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


class CardFoldersTest(TempDirTestCase):

    def test_folders_only_sorted(self):
        write_files(self.tmp, {"b-card/x": "", "a-card/x": "", "file": ""})
        self.assertEqual(card_folders(self.tmp), [os.path.join(self.tmp, "a-card"),
                                                  os.path.join(self.tmp, "b-card")])

    def test_missing(self):
        self.assertEqual(card_folders(os.path.join(self.tmp, "missing")), [])
