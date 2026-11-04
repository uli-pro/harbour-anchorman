"""Unpacked books in the cache folder, one folder per book."""

import hashlib
import os
import re
import shutil

from . import archive

# Every book takes its space twice while unpacked, so only the books the
# reader switches between stay in the cache.
KEEP = 2

_KEY = re.compile(r"^[0-9a-f]{16}(\.part)?$")


def book_key(epub_path):
    """Name of the cache folder of the EPUB file at epub_path.

    A new version of the file (other size or modification time) gets a new
    key and is unpacked again. Hashing the content would mean reading
    gigabytes of audio each time a book is opened.
    """
    st = os.stat(epub_path)
    data = "\0".join([os.path.realpath(epub_path), str(st.st_size),
                      str(st.st_mtime_ns)])
    return hashlib.sha1(data.encode("utf-8", "surrogateescape")).hexdigest()[:16]


def open_book(epub_path, cache_dir, keep=KEEP):
    """Return the folder holding the unpacked EPUB, unpacking it if needed.

    Before unpacking, all but the keep - 1 most recently opened books are
    removed from cache_dir. Raises EpubError and OSError like
    archive.extract.
    """
    os.makedirs(cache_dir, exist_ok=True)
    root = os.path.join(cache_dir, book_key(epub_path))
    if not os.path.isdir(root):
        prune(cache_dir, keep - 1)
        archive.extract(epub_path, root)
    # The modification time of the folder records when it was last opened.
    os.utime(root)
    return root


def prune(cache_dir, keep):
    """Remove unfinished extractions and all but the keep newest books.

    Only folders named like cache keys are touched, so a wrong cache_dir
    cannot lose anything else.
    """
    books = []
    for entry in os.listdir(cache_dir):
        match = _KEY.match(entry)
        path = os.path.join(cache_dir, entry)
        if not match or os.path.islink(path) or not os.path.isdir(path):
            continue
        if match.group(1):
            shutil.rmtree(path)
        else:
            books.append((os.stat(path).st_mtime_ns, path))
    books.sort(reverse=True)
    for _, path in books[max(keep, 0):]:
        shutil.rmtree(path)
