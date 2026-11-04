"""Entry points called from QML through PyOtherSide.

Returns plain dicts and lists, because PyOtherSide hands namedtuples to QML
as lists without field names. A book that cannot be used is not a program
error: it comes back as {"error": code, "detail": text}, where code is one
of the EpubError codes or "io", and QML shows a translated message.
"""

import os

from . import cache, library, positions
from .errors import EpubError
from .overlay import read_overlay
from .package import read_package


def list_books(folders):
    return [{"path": book.path, "name": book.name}
            for book in library.list_books(folders)]


def open_book(epub_path, cache_dir):
    try:
        root = cache.open_book(epub_path, cache_dir)
        book = read_package(root)
    except EpubError as e:
        return _error(e.code, e.detail)
    except OSError as e:
        return _error("io", str(e))
    spine_index = {}
    for index, item in enumerate(book.spine):
        spine_index.setdefault(item.path, index)
    return {
        "root": root,
        # The identifier stays the same when the file is renamed or synced
        # again, so the reading position follows the book.
        "key": book.identifier or os.path.basename(epub_path),
        "title": book.title,
        "authors": book.authors,
        "language": book.language,
        "duration": book.duration,
        "activeClass": book.active_class,
        "spine": [{"path": item.path, "overlay": item.overlay,
                   "linear": item.linear} for item in book.spine],
        "toc": [{"title": entry.title, "path": entry.path,
                 "fragment": entry.fragment, "level": entry.level,
                 "spine": spine_index.get(entry.path, -1)}
                for entry in book.toc],
    }


def read_chapter(root, chapter_path, smil_path):
    """The sentence ids of the chapter chapter_path, in reading order."""
    try:
        overlay = read_overlay(root, smil_path)
    except EpubError as e:
        return _error(e.code, e.detail)
    except OSError as e:
        return _error("io", str(e))
    ids = []
    seen = set()
    for fragment in overlay.fragments:
        # A SMIL file may point into other chapters; those ids could collide
        # with ids of this page.
        if fragment.text_path == chapter_path and fragment.text_id not in seen:
            seen.add(fragment.text_id)
            ids.append(fragment.text_id)
    return {"ids": ids, "skipped": overlay.skipped}


def load_position(path, key):
    return positions.load(path, key)


def save_position(path, key, position):
    try:
        positions.save(path, key, position)
    except OSError as e:
        return _error("io", str(e))
    return True


def _error(code, detail):
    return {"error": code, "detail": detail}
