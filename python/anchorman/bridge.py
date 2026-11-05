"""Entry points called from QML through PyOtherSide.

Returns plain dicts and lists, because PyOtherSide hands namedtuples to QML
as lists without field names. A book that cannot be used is not a program
error: it comes back as {"error": code, "detail": text}, where code is one
of the EpubError codes or "io", and QML shows a translated message.
"""

import collections
import getpass
import hashlib
import math
import os
import threading
import traceback
import unicodedata

from . import cache, library, positions
from .errors import EpubError
from .overlay import read_overlay
from .package import read_package, text_length
from .paths import local_path

_MAX_KEY_LENGTH = 200


_MEDIA_ROOT = "/run/media"


def default_folders(documents):
    """Where books are looked for unless the user chose a folder: the
    documents folder and every memory card."""
    try:
        user = getpass.getuser()
    except (KeyError, OSError):
        return [documents]
    return [documents] + library.card_folders(os.path.join(_MEDIA_ROOT, user))


# SVG left out: QtSvg may load files an image names.
_COVER_TYPES = (".jpg", ".jpeg", ".png", ".gif")
_MAX_WAITING_COVERS = 50


class Worker:
    """A thread that runs requests one after the other, the newest first.

    A request with the key of one still waiting replaces it, so repeated
    requests run once; beyond limit the oldest waiting ones are dropped.
    """

    def __init__(self, run, limit=None):
        self._run = run
        self._limit = limit
        self._waiting = collections.OrderedDict()
        self._condition = threading.Condition()
        self._thread = None

    def submit(self, key, *args):
        with self._condition:
            self._waiting.pop(key, None)
            self._waiting[key] = args
            if self._limit is not None and len(self._waiting) > self._limit:
                self._waiting.popitem(last=False)
            if self._thread is None:
                self._thread = threading.Thread(target=self._loop, daemon=True)
                self._thread.start()
            self._condition.notify()

    def _loop(self):
        while True:
            with self._condition:
                while not self._waiting:
                    self._condition.wait()
                key, args = self._waiting.popitem(last=True)
            try:
                self._run(key, *args)
            except Exception:
                traceback.print_exc()


def _send(*args):
    import pyotherside  # only on the device
    pyotherside.send(*args)


def cached_library(cache_file, folders):
    """The books below folders as last scanned, at once; see library_view."""
    prefixes = tuple(os.path.join(folder, "") for folder in folders)
    return library_view([e for e in library.load_cached(cache_file)
                         if e["path"].startswith(prefixes)])


def scan_library(folders, cache_file, covers_dir, serial):
    """Look for new and changed books in a thread, so that a book can be
    opened meanwhile; the result comes as the event ("library", serial,
    result). Only the latest request waiting is run."""
    _scanner.submit("scan", folders, cache_file, covers_dir, serial)


def _scan(key, folders, cache_file, covers_dir, serial):
    try:
        result = scan_now(folders, cache_file, covers_dir)
    except Exception as e:
        traceback.print_exc()
        result = _error("io", repr(e))
    _send("library", serial, result)


def scan_now(folders, cache_file, covers_dir):
    """The library view of a scan; {"unchanged": true} if the books are the
    ones of the cache, which cached_library has shown already."""
    try:
        entries, changed = library.scan(folders, cache_file)
    except OSError as e:
        return _error("io", str(e))
    if not changed:
        return {"unchanged": True}
    library.prune_covers(covers_dir, {library.cover_name(e)
                                      for e in library.load_cached(cache_file)})
    return library_view(entries)


def library_view(entries):
    """{books, authors} for the library pages.

    books are sorted by author, then series in order, then the other titles;
    authors lists each first author once with the number of books. Authors
    are told apart by their sort name ("Wilde, Oscar"), so "Oscar Wilde" in
    one book and "Wilde, Oscar" in another are one author; group is the key.
    Books that a readaloud replaces are left out.
    """
    entries = library.without_replaced(entries)
    keys = [(library.normal_identifier(e["info"]["identifier"]), e["info"]["title"],
             e["info"]["audio"]) for e in entries]
    copies = collections.Counter(keys)
    books = []
    for entry, key in zip(entries, keys):
        info = entry["info"]
        author = info["authors"][0] if info["authors"] else ""
        sort = info["sort"] or author
        books.append({
            "path": entry["path"], "key": library.cover_name(entry),
            "title": info["title"], "author": author, "authors": "; ".join(info["authors"]),
            "coauthors": [_natural(name) for name in info["authors"][1:]],
            "sort": sort, "group": fold(sort), "letter": _letter(sort),
            "series": info["series"],
            "index": info["index"], "cover": info["cover"], "audio": info["audio"],
            "broken": info["broken"],
            "removable": entry["path"].startswith(_MEDIA_ROOT + "/"),
            # Several copies of one book: say where each is.
            "duplicate": bool(info["identifier"]) and copies[key] > 1,
            "search": fold(" ".join(info["authors"] + [info["title"], info["series"]]))})
    books.sort(key=_order)
    authors = []
    for book in books:
        if authors and authors[-1]["group"] == book["group"]:
            authors[-1]["count"] += 1
        else:
            authors.append({"name": book["author"], "group": book["group"],
                            "letter": book["letter"], "count": 1})
    return {"books": books, "authors": authors}


def request_cover(epub_path, cover_path, name, covers_dir):
    """The file of the book's cover if it is extracted already, else "" and
    it is extracted in a thread, coming as the event ("cover", name, file);
    file is "" if the book has no usable cover."""
    target = _cover_target(cover_path, name, covers_dir)
    if not target:
        return ""
    if os.path.isfile(target):
        return target
    _covers.submit(name, epub_path, cover_path, covers_dir)
    return ""


def _extract(name, epub_path, cover_path, covers_dir):
    _send("cover", name, cover(epub_path, cover_path, name, covers_dir))


def _cover_target(cover_path, name, covers_dir):
    ext = os.path.splitext(cover_path or "")[1].lower()
    return os.path.join(covers_dir, name + ext) if ext in _COVER_TYPES else ""


def cover(epub_path, cover_path, name, covers_dir):
    """The file of the book's cover in covers_dir, extracted on first use;
    "" if there is none."""
    target = _cover_target(cover_path, name, covers_dir)
    if not target:
        return ""
    if os.path.isfile(target):
        return target
    try:
        os.makedirs(covers_dir, exist_ok=True)
    except OSError:
        return ""
    return target if library.extract_cover(epub_path, cover_path, target) else ""


def recent_books(path):
    """The EPUB files opened last, newest first."""
    return positions.load_recent(path)


def fold(text):
    """text for comparing: lower case, without accents (ä → a, ß → ss)."""
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c)).casefold()


def _natural(name):
    """ "Child, Andrew" as "Andrew Child"; other forms stay."""
    parts = name.split(", ")
    return parts[1] + " " + parts[0] if len(parts) == 2 else name


def _letter(sort):
    first = fold(sort)[:1].upper()
    return first if first.isalpha() else ("#" if first else "")


def _order(book):
    # Authors not starting with a letter first, unknown ones last, so that
    # each section appears once.
    return (book["group"] == "", book["letter"] != "#", book["group"], book["series"] == "",
            fold(book["series"]), book["index"] if book["index"] is not None else math.inf,
            fold(book["title"]), book["path"])


def open_book(epub_path, cache_dir):
    try:
        root, book = cache.open_book(epub_path, cache_dir, read_package)
    except EpubError as e:
        return _error(e.code, e.detail)
    except OSError as e:
        return _error("io", str(e))
    spine_index = {}
    for index, item in enumerate(book.spine):
        spine_index.setdefault(item.path, index)
    return {
        "root": root,
        "key": _position_key(book.identifier or os.path.basename(epub_path)),
        "title": book.title,
        "authors": book.authors,
        "language": book.language,
        "duration": book.duration,
        # Shown on the lock screen; a cover named but missing is no cover.
        "cover": (book.cover if book.cover and os.path.isfile(local_path(root, book.cover))
                  else None),
        "activeClass": book.active_class,
        "spine": [{"path": item.path, "overlay": item.overlay,
                   "linear": item.linear} for item in book.spine],
        "toc": [{"title": entry.title, "path": entry.path,
                 "fragment": entry.fragment, "level": entry.level,
                 "spine": spine_index.get(entry.path, -1)}
                for entry in book.toc],
    }


def chapter_lengths(root, paths):
    """Characters of text in each chapter, for estimating page numbers.

    A separate call, so that parsing every chapter does not delay opening
    the book.
    """
    lengths = {}
    for path in paths:
        if path not in lengths:
            lengths[path] = text_length(root, path)
    return [lengths[path] for path in paths]


def read_chapter(root, chapter_path, smil_path):
    """The sentences of the chapter chapter_path, in reading order.

    "ids" lists each sentence element once, for the page; "sentences" lists
    what is played: element id, audio file (path in the book), begin and
    end in ms, end None meaning to the end of the file.
    """
    try:
        overlay = read_overlay(root, smil_path)
    except EpubError as e:
        return _error(e.code, e.detail)
    except OSError as e:
        return _error("io", str(e))
    ids = []
    seen = set()
    sentences = []
    for fragment in overlay.fragments:
        # A SMIL file may point into other chapters; those ids could collide
        # with ids of this page.
        if fragment.text_path != chapter_path:
            continue
        sentences.append({"id": fragment.text_id, "audio": fragment.audio_path,
                          "begin": fragment.begin, "end": fragment.end})
        if fragment.text_id not in seen:
            seen.add(fragment.text_id)
            ids.append(fragment.text_id)
    return {"ids": ids, "sentences": sentences, "skipped": overlay.skipped}


def load_position(path, key):
    return positions.load(path, key)


def save_position(path, key, position):
    try:
        positions.save(path, key, position)
    except OSError as e:
        return _error("io", str(e))
    return True


def load_last_book(path):
    return positions.load_last(path)


def save_last_book(path, epub_path):
    try:
        positions.save_last(path, epub_path)
    except OSError as e:
        return _error("io", str(e))
    return True


def _position_key(name):
    # The identifier stays the same when the file is renamed or synced again,
    # so the reading position follows the book. It comes from the book and
    # has no length limit; a huge one must not fill the positions file.
    if len(name) <= _MAX_KEY_LENGTH:
        return name
    return "sha1:" + hashlib.sha1(name.encode("utf-8", "surrogateescape")).hexdigest()


def _error(code, detail):
    return {"error": code, "detail": detail}


_scanner = Worker(_scan)
_covers = Worker(_extract, _MAX_WAITING_COVERS)
