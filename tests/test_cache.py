import os
import time
from unittest import mock

from anchorman import cache
from anchorman.errors import EpubError

from .helpers import TempDirTestCase, make_epub, mini_entries


class OpenBookTest(TempDirTestCase):

    def setUp(self):
        super().setUp()
        self.cache_dir = os.path.join(self.tmp, "cache")

    def epub(self, name):
        path = os.path.join(self.tmp, name)
        make_epub(path, mini_entries())
        return path

    def books(self):
        return sorted(os.listdir(self.cache_dir))

    def age(self, root, seconds):
        """Make root look as if it was last opened seconds ago."""
        then = time.time() - seconds
        os.utime(root, (then, then))

    def test_first_open_unpacks(self):
        root = cache.open_book(self.epub("a.epub"), self.cache_dir)
        self.assertEqual(os.path.dirname(root), self.cache_dir)
        self.assertTrue(os.path.isfile(os.path.join(root, "OEBPS", "content.opf")))

    def test_second_open_is_a_hit(self):
        epub = self.epub("a.epub")
        root = cache.open_book(epub, self.cache_dir)
        marker = os.path.join(root, "marker")
        open(marker, "w").close()
        self.age(root, 100)
        self.assertEqual(cache.open_book(epub, self.cache_dir), root)
        self.assertTrue(os.path.exists(marker))
        self.assertGreater(os.stat(root).st_mtime, time.time() - 50)

    def test_changed_file_gets_new_key(self):
        epub = self.epub("a.epub")
        key = cache.book_key(epub)
        os.utime(epub, (1000, 1000))
        self.assertNotEqual(cache.book_key(epub), key)

    def test_keeps_the_two_most_recent_books(self):
        epub_a = self.epub("a.epub")
        a = cache.open_book(epub_a, self.cache_dir)
        self.age(a, 300)
        b = cache.open_book(self.epub("b.epub"), self.cache_dir)
        self.age(b, 200)
        cache.open_book(epub_a, self.cache_dir)  # a is newest now
        c = cache.open_book(self.epub("c.epub"), self.cache_dir)
        self.assertEqual(self.books(), sorted(os.path.basename(p) for p in (a, c)))

    def test_keep_one(self):
        cache.open_book(self.epub("a.epub"), self.cache_dir, keep=1)
        b = cache.open_book(self.epub("b.epub"), self.cache_dir, keep=1)
        self.assertEqual(self.books(), [os.path.basename(b)])

    def test_removes_unfinished_extractions(self):
        os.makedirs(os.path.join(self.cache_dir, "0123456789abcdef.part"))
        root = cache.open_book(self.epub("a.epub"), self.cache_dir)
        self.assertEqual(self.books(), [os.path.basename(root)])

    def test_leaves_foreign_entries_alone(self):
        os.makedirs(os.path.join(self.cache_dir, "other"))
        os.makedirs(os.path.join(self.cache_dir, "0123456789ABCDEF"))
        cache.open_book(self.epub("a.epub"), self.cache_dir, keep=1)
        cache.open_book(self.epub("b.epub"), self.cache_dir, keep=1)
        self.assertIn("other", self.books())
        self.assertIn("0123456789ABCDEF", self.books())

    def test_broken_book_leaves_nothing(self):
        epub = os.path.join(self.tmp, "broken.epub")
        with open(epub, "wb") as f:
            f.write(b"not a zip")
        with self.assertRaises(EpubError) as cm:
            cache.open_book(epub, self.cache_dir)
        self.assertEqual(cm.exception.code, "not_zip")
        self.assertEqual(self.books(), [])

    def test_broken_book_keeps_cached_books(self):
        a = cache.open_book(self.epub("a.epub"), self.cache_dir)
        b = cache.open_book(self.epub("b.epub"), self.cache_dir)
        epub = os.path.join(self.tmp, "broken.epub")
        with open(epub, "wb") as f:
            f.write(b"not a zip")
        with self.assertRaises(EpubError):
            cache.open_book(epub, self.cache_dir)
        self.assertEqual(self.books(), sorted(os.path.basename(p) for p in (a, b)))

    def test_makes_room_when_space_is_short(self):
        a = cache.open_book(self.epub("a.epub"), self.cache_dir)
        self.age(a, 300)
        b = cache.open_book(self.epub("b.epub"), self.cache_dir)
        real_extract = cache.archive.extract
        calls = []

        def extract(epub_path, dest_dir):
            calls.append(sorted(os.listdir(self.cache_dir)))
            if len(calls) == 1:
                raise EpubError("no_space")
            real_extract(epub_path, dest_dir)

        with mock.patch.object(cache.archive, "extract", extract):
            c = cache.open_book(self.epub("c.epub"), self.cache_dir)
        names = [os.path.basename(p) for p in (a, b, c)]
        self.assertEqual(calls, [sorted(names[:2]), [names[1]]])
        self.assertEqual(self.books(), sorted(names[1:]))

    def test_missing_file(self):
        with self.assertRaises(OSError):
            cache.open_book(os.path.join(self.tmp, "missing.epub"), self.cache_dir)
