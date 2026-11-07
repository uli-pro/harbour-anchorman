"""Shared helpers for the tests."""

import os
import shutil
import tempfile
import unittest
import zipfile

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
MINI_DIR = os.path.join(DATA_DIR, "mini")


def mini_entries():
    """The files of the mini readaloud as (name, bytes), mimetype first."""
    entries = []
    for dirpath, dirnames, filenames in os.walk(MINI_DIR):
        dirnames.sort()
        for name in sorted(filenames):
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, MINI_DIR).replace(os.sep, "/")
            with open(path, "rb") as f:
                entries.append((rel, f.read()))
    entries.sort(key=lambda entry: entry[0] != "mimetype")
    return entries


def make_epub(path, entries):
    """Write entries, (name or ZipInfo, bytes) pairs, as a ZIP to path.

    The mimetype entry is stored uncompressed, as the EPUB standard demands.
    """
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries:
            if name == "mimetype":
                archive.writestr(name, data, compress_type=zipfile.ZIP_STORED)
            else:
                archive.writestr(name, data)


def write_files(root, files):
    """Create files below root from a {relative path: str or bytes} dict."""
    for name, content in files.items():
        path = os.path.join(root, *name.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if isinstance(content, str):
            content = content.encode("utf-8")
        with open(path, "wb") as f:
            f.write(content)


class TempDirTestCase(unittest.TestCase):
    """Gives every test an empty directory self.tmp."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bookfish-test-")
        self.addCleanup(shutil.rmtree, self.tmp)
