import os
import stat
import struct
import warnings
import zipfile

from anchorman.archive import extract
from anchorman.errors import EpubError

from .helpers import TempDirTestCase, make_epub, mini_entries

MIMETYPE = ("mimetype", b"application/epub+zip")


class ExtractTest(TempDirTestCase):

    def setUp(self):
        super().setUp()
        self.dest = os.path.join(self.tmp, "book")

    def epub(self, entries):
        path = os.path.join(self.tmp, "book.epub")
        make_epub(path, entries)
        return path

    def assertFails(self, code, epub, **limits):
        with self.assertRaises(EpubError) as cm:
            extract(epub, self.dest, **limits)
        self.assertEqual(cm.exception.code, code)
        self.assertFalse(os.path.lexists(self.dest))
        self.assertFalse(os.path.lexists(self.dest + ".part"))

    def test_mini(self):
        entries = mini_entries()
        extract(self.epub(entries), self.dest)
        for name, data in entries:
            with open(os.path.join(self.dest, *name.split("/")), "rb") as f:
                self.assertEqual(f.read(), data, name)
        self.assertFalse(os.path.lexists(self.dest + ".part"))

    def test_parent_reference(self):
        self.assertFails("unsafe_path", self.epub([MIMETYPE, ("../evil", b"x")]))
        self.assertFalse(os.path.lexists(os.path.join(self.tmp, "evil")))

    def test_unsafe_names(self):
        for name in ("/tmp/evil", "..\\evil", "C:evil", "a/../../evil",
                     "OEBPS/../../evil", ".."):
            with self.subTest(name=name):
                self.assertFails("unsafe_path", self.epub([MIMETYPE, (name, b"x")]))

    def test_dot_segments(self):
        extract(self.epub([MIMETYPE, ("./OEBPS//a.txt", b"x")]), self.dest)
        self.assertTrue(os.path.isfile(os.path.join(self.dest, "OEBPS", "a.txt")))

    def test_symlink_skipped(self):
        link = zipfile.ZipInfo("link")
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        extract(self.epub([MIMETYPE, (link, b"/etc/passwd")]), self.dest)
        self.assertFalse(os.path.lexists(os.path.join(self.dest, "link")))

    def test_duplicate_name(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # zipfile warns about duplicates
            epub = self.epub([MIMETYPE, ("a.txt", b"1"), ("a.txt", b"2")])
        self.assertFails("unsafe_path", epub)

    def test_file_and_directory_clash(self):
        self.assertFails("unsafe_path",
                         self.epub([MIMETYPE, ("a", b"1"), ("a/b", b"2")]))

    def test_too_many_files(self):
        self.assertFails("too_many_files", self.epub(mini_entries()),
                         max_entries=3)

    def test_zip_bomb(self):
        # 10 MB of zeros compress to about 10 KB.
        epub = self.epub([MIMETYPE, ("zeros", b"\0" * 10000000)])
        self.assertLess(os.path.getsize(epub), 100000)
        self.assertFails("too_large", epub, headroom=1000000)

    def test_zip_bomb_with_false_size(self):
        # zipfile never reads more than the declared size; the bomb then
        # fails its checksum.
        epub = self.epub([MIMETYPE, ("zeros", b"\0" * 10000000)])
        _patch_sizes(epub, "zeros", 1000)
        self.assertFails("not_zip", epub, headroom=1000000)

    def test_no_space(self):
        self.assertFails("no_space", self.epub(mini_entries()),
                         min_free_space=10 ** 18)

    def test_not_zip(self):
        path = os.path.join(self.tmp, "book.epub")
        with open(path, "wb") as f:
            f.write(b"This is not a ZIP file.")
        self.assertFails("not_zip", path)

    def test_missing_mimetype(self):
        self.assertFails("not_epub", self.epub([("a.txt", b"x")]))

    def test_wrong_mimetype(self):
        self.assertFails("not_epub",
                         self.epub([("mimetype", b"application/zip"), ("a", b"x")]))

    def test_bad_checksum(self):
        path = os.path.join(self.tmp, "book.epub")
        with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as archive:
            archive.writestr(*MIMETYPE)
            archive.writestr("a.txt", b"hello world")
        with open(path, "r+b") as f:
            data = f.read()
            f.seek(data.index(b"hello world"))
            f.write(b"J")
        self.assertFails("not_zip", path)

    def test_destination_exists(self):
        os.mkdir(self.dest)
        with self.assertRaises(ValueError):
            extract(self.epub(mini_entries()), self.dest)

    def test_leftover_part_replaced(self):
        os.makedirs(os.path.join(self.dest + ".part", "junk"))
        extract(self.epub(mini_entries()), self.dest)
        self.assertFalse(os.path.lexists(os.path.join(self.dest, "junk")))
        self.assertFalse(os.path.lexists(self.dest + ".part"))


def _patch_sizes(path, name, size):
    """Overwrite the uncompressed size of entry name in both ZIP headers."""
    with open(path, "r+b") as f:
        data = bytearray(f.read())
        encoded = name.encode()
        local = data.index(b"PK\x03\x04")
        while data[local + 30:local + 30 + len(encoded)] != encoded:
            local = data.index(b"PK\x03\x04", local + 4)
        struct.pack_into("<I", data, local + 22, size)
        central = data.index(b"PK\x01\x02")
        while data[central + 46:central + 46 + len(encoded)] != encoded:
            central = data.index(b"PK\x01\x02", central + 4)
        struct.pack_into("<I", data, central + 24, size)
        f.seek(0)
        f.write(data)
