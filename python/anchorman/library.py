"""Finding the books in the library folders."""

import collections
import os
import zipfile

BookFile = collections.namedtuple("BookFile", "path name")
BookFile.__doc__ = "An EPUB file; name is the file name without extension."


def list_books(folders, accept=None):
    """Return the EPUB files below folders, sorted by name.

    Hidden files and folders are left out. Symbolic links to folders are not
    followed, so a link cannot make the walk endless. Missing folders are
    ignored. accept, if given, decides about each file by its path.
    """
    books = []
    seen = set()
    for folder in folders:
        for dirpath, dirnames, filenames in os.walk(folder):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for filename in filenames:
                stem, ext = os.path.splitext(filename)
                if ext.lower() != ".epub" or filename.startswith("."):
                    continue
                path = os.path.join(dirpath, filename)
                if path in seen or (accept and not accept(path)):
                    continue
                seen.add(path)
                books.append(BookFile(path, stem))
    books.sort(key=lambda book: (book.name.casefold(), book.path))
    return books


def is_readaloud(path):
    """True if the EPUB at path contains SMIL files, i.e. Media Overlays.

    Only the ZIP directory is read: 657 books on a memory card take about
    two seconds. A file that cannot be read is no readaloud.
    """
    try:
        with zipfile.ZipFile(path) as archive:
            return any(name.lower().endswith(".smil") for name in archive.namelist())
    except (OSError, EOFError, ValueError, zipfile.BadZipFile, zipfile.LargeZipFile):
        return False


def card_folders(media_root):
    """The mounted memory cards: folders in media_root (/run/media/<user>)."""
    try:
        names = sorted(os.listdir(media_root))
    except OSError:
        return []
    return [os.path.join(media_root, name) for name in names
            if os.path.isdir(os.path.join(media_root, name))]
