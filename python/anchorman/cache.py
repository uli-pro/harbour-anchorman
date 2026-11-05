"""Unpacked books in the cache folder, one folder per book."""

import hashlib
import os
import re
import shutil

from . import archive
from .errors import EpubError

# Every book takes its space twice while unpacked, so only the books the
# reader switches between stay in the cache: those listed to read on.
KEEP = 3

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


def open_book(epub_path, cache_dir, read, keep=KEEP):
    """Unpack the EPUB if needed and return (root, read(root)).

    read parses the unpacked book and raises EpubError if it is unusable.
    Afterwards only the keep most recently opened books stay in cache_dir.
    Older books are removed only once the new one is unpacked and read, so
    a broken file never costs a good book; a new book that read rejects is
    removed again. Only when space is short are older books removed first,
    even if the new book then still does not fit. Raises EpubError and
    OSError like archive.extract.
    """
    os.makedirs(cache_dir, exist_ok=True)
    root = os.path.join(cache_dir, book_key(epub_path))
    if os.path.isdir(root):
        # The modification time of the folder records when it was last opened.
        os.utime(root)
        return root, read(root)
    try:
        archive.extract(epub_path, root)
    except EpubError as e:
        if e.code != "no_space":
            raise
        prune(cache_dir, keep - 1)
        archive.extract(epub_path, root)
    try:
        result = read(root)
    except BaseException:
        shutil.rmtree(root, ignore_errors=True)
        raise
    os.utime(root)
    prune(cache_dir, keep)
    return root, result


def prune(cache_dir, keep):
    """Remove unfinished extractions and all but the keep newest books.

    Only folders named like cache keys are touched, so a wrong cache_dir
    cannot lose anything else. Folders that cannot be removed are left for
    the next time; the book just opened must not fail because of them.
    """
    books = []
    for entry in os.listdir(cache_dir):
        match = _KEY.match(entry)
        path = os.path.join(cache_dir, entry)
        if not match or os.path.islink(path) or not os.path.isdir(path):
            continue
        if match.group(1):
            shutil.rmtree(path, ignore_errors=True)
        else:
            books.append((os.stat(path).st_mtime_ns, path))
    books.sort(reverse=True)
    for _, path in books[max(keep, 0):]:
        shutil.rmtree(path, ignore_errors=True)
