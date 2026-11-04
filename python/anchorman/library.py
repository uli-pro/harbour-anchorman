"""Finding the books in the library folders."""

import collections
import os

BookFile = collections.namedtuple("BookFile", "path name")
BookFile.__doc__ = "An EPUB file; name is the file name without extension."


def list_books(folders):
    """Return the EPUB files below folders, sorted by name.

    Hidden files and folders are left out. Symbolic links to folders are not
    followed, so a link cannot make the walk endless. Missing folders are
    ignored.
    """
    books = []
    for folder in folders:
        for dirpath, dirnames, filenames in os.walk(folder):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for filename in filenames:
                stem, ext = os.path.splitext(filename)
                if ext.lower() == ".epub" and not filename.startswith("."):
                    books.append(BookFile(os.path.join(dirpath, filename), stem))
    books.sort(key=lambda book: (book.name.casefold(), book.path))
    return books
