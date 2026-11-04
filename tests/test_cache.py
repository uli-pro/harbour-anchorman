import os
import time
from unittest import mock

from anchorman import cache
from anchorman.errors import EpubError
from anchorman.package import read_package

from .helpers import TempDirTestCase, make_epub, mini_entries


class OpenBookTest(TempDirTestCase):

    def setUp(self):
        super().setUp()
        self.cache_dir = os.path.join(self.tmp, "cache")

    def epub(self, name):
        path = os.path.join(self.tmp, name)
        make_epub(path, mini_entries())
        return path

    def open(self, epub, keep=cache.KEEP):
        return cache.open_book(epub, self.cache_dir, read_package, keep)[0]

    def books(self):
        return sorted(os.listdir(self.cache_dir))

    def age(self, root, seconds):
        """Make root look as if it was last opened seconds ago."""
        then = time.time() - seconds
        os.utime(root, (then, then))

    def test_first_open_unpacks(self):
        root = self.open(self.epub("a.epub"))
        self.assertEqual(os.path.dirname(root), self.cache_dir)
        self.assertTrue(os.path.isfile(os.path.join(root, "OEBPS", "content.opf")))

    def test_second_open_is_a_hit(self):
        epub = self.epub("a.epub")
        root = self.open(epub)
        marker = os.path.join(root, "marker")
        open(marker, "w").close()
        self.age(root, 100)
        self.assertEqual(self.open(epub), root)
        self.assertTrue(os.path.exists(marker))
        self.assertGreater(os.stat(root).st_mtime, time.time() - 50)

    def test_changed_file_gets_new_key(self):
        epub = self.epub("a.epub")
        key = cache.book_key(epub)
        os.utime(epub, (1000, 1000))
        self.assertNotEqual(cache.book_key(epub), key)

    def test_keeps_the_two_most_recent_books(self):
        epub_a = self.epub("a.epub")
        a = self.open(epub_a)
        self.age(a, 300)
        b = self.open(self.epub("b.epub"))
        self.age(b, 200)
        self.open(epub_a)  # a is newest now
        c = self.open(self.epub("c.epub"))
        self.assertEqual(self.books(), sorted(os.path.basename(p) for p in (a, c)))

    def test_keep_one(self):
        self.open(self.epub("a.epub"), keep=1)
        b = self.open(self.epub("b.epub"), keep=1)
        self.assertEqual(self.books(), [os.path.basename(b)])

    def test_removes_unfinished_extractions(self):
        os.makedirs(os.path.join(self.cache_dir, "0123456789abcdef.part"))
        root = self.open(self.epub("a.epub"))
        self.assertEqual(self.books(), [os.path.basename(root)])

    def test_leaves_foreign_entries_alone(self):
        os.makedirs(os.path.join(self.cache_dir, "other"))
        os.makedirs(os.path.join(self.cache_dir, "0123456789ABCDEF"))
        self.open(self.epub("a.epub"), keep=1)
        self.open(self.epub("b.epub"), keep=1)
        self.assertIn("other", self.books())
        self.assertIn("0123456789ABCDEF", self.books())

    def test_broken_book_leaves_nothing(self):
        epub = os.path.join(self.tmp, "broken.epub")
        with open(epub, "wb") as f:
            f.write(b"not a zip")
        with self.assertRaises(EpubError) as cm:
            self.open(epub)
        self.assertEqual(cm.exception.code, "not_zip")
        self.assertEqual(self.books(), [])

    def test_broken_book_keeps_cached_books(self):
        a = self.open(self.epub("a.epub"))
        b = self.open(self.epub("b.epub"))
        epub = os.path.join(self.tmp, "broken.epub")
        with open(epub, "wb") as f:
            f.write(b"not a zip")
        with self.assertRaises(EpubError):
            self.open(epub)
        self.assertEqual(self.books(), sorted(os.path.basename(p) for p in (a, b)))

    def test_unreadable_book_keeps_cached_books(self):
        a = self.open(self.epub("a.epub"))
        b = self.open(self.epub("b.epub"))
        epub = os.path.join(self.tmp, "c.epub")
        make_epub(epub, [(name, b"<broken" if name == "OEBPS/content.opf" else data)
                         for name, data in mini_entries()])
        with self.assertRaises(EpubError) as cm:
            self.open(epub)
        self.assertEqual(cm.exception.code, "bad_xml")
        self.assertEqual(self.books(), sorted(os.path.basename(p) for p in (a, b)))

    def test_returns_what_read_returns(self):
        epub = self.epub("a.epub")
        root, result = cache.open_book(epub, self.cache_dir, len)
        self.assertEqual(result, len(root))
        self.assertEqual(cache.open_book(epub, self.cache_dir, len), (root, len(root)))

    def test_makes_room_when_space_is_short(self):
        a = self.open(self.epub("a.epub"))
        self.age(a, 300)
        b = self.open(self.epub("b.epub"))
        real_extract = cache.archive.extract
        calls = []

        def extract(epub_path, dest_dir):
            calls.append(sorted(os.listdir(self.cache_dir)))
            if len(calls) == 1:
                raise EpubError("no_space")
            real_extract(epub_path, dest_dir)

        with mock.patch.object(cache.archive, "extract", extract):
            c = self.open(self.epub("c.epub"))
        names = [os.path.basename(p) for p in (a, b, c)]
        self.assertEqual(calls, [sorted(names[:2]), [names[1]]])
        self.assertEqual(self.books(), sorted(names[1:]))

    def test_missing_file(self):
        with self.assertRaises(OSError):
            self.open(os.path.join(self.tmp, "missing.epub"))
