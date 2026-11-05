"""Finding the books in the library folders and what the library shows
of them, kept in a cache file so that a memory card is not read again."""

import collections
import hashlib
import json
import os
import re
import stat
import zipfile

from .errors import EpubError
from .package import package_path, read_info
from .xmlutil import MAX_XML_SIZE, parse_xml_data

MAX_CACHE_SIZE = 16 * 1024 * 1024
MAX_COVER_SIZE = 5 * 1024 * 1024
_CACHE_VERSION = 1
# Prefixes of the same identifier: Storyteller writes "uuid:…" where the
# book it started from had "urn:uuid:…" or nothing.
_ID_PREFIXES = ("urn:", "uuid:", "url:", "asin:")
_COVER_FILE = re.compile(r"^([0-9a-f]{16})(\.[a-z]+)?(\.part)?$")
_INFO_FIELDS = {"identifier": str, "title": str, "authors": list, "sort": str,
                "series": str, "index": (int, float, type(None)),
                "cover": (str, type(None)), "audio": bool, "broken": bool}

BookFile = collections.namedtuple("BookFile", "path name")
BookFile.__doc__ = "An EPUB file; name is the file name without extension."


def list_books(folders, accept=None):
    """Return the EPUB files below folders, sorted by name.

    Hidden files and folders are left out. Symbolic links to folders are not
    followed, so a link cannot make the walk endless. Missing folders are
    ignored, and so are names that are not valid UTF-8: QML could not show
    or open them. accept, if given, decides about each file by its path.
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
                try:
                    path.encode("utf-8")
                except UnicodeEncodeError:
                    continue
                real = os.path.realpath(path)
                if real in seen or (accept and not accept(path)):
                    continue
                seen.add(real)
                books.append(BookFile(path, stem))
    books.sort(key=lambda book: (book.name.casefold(), book.path))
    return books


def is_readaloud(path):
    """True if the EPUB at path contains SMIL files, i.e. Media Overlays.

    Only the ZIP directory is read: 657 books on a memory card take about
    two seconds. Only regular files are opened; a FIFO would block forever.
    Whatever goes wrong with one file, it is just no readaloud.
    """
    try:
        if not stat.S_ISREG(os.stat(path).st_mode):
            return False
        with zipfile.ZipFile(path) as archive:
            return any(name.lower().endswith(".smil") for name in archive.namelist())
    except Exception:
        return False


def card_folders(media_root):
    """The mounted memory cards: folders in media_root (/run/media/<user>)."""
    try:
        names = sorted(os.listdir(media_root))
    except OSError:
        return []
    return [os.path.join(media_root, name) for name in names
            if os.path.isdir(os.path.join(media_root, name))]


def book_info(path):
    """The library entry of the EPUB at path, read without unpacking.

    Raises EpubError, OSError or zipfile errors if the book is unusable.
    """
    if not stat.S_ISREG(os.stat(path).st_mode):
        raise EpubError("not_epub", "not a regular file")
    with zipfile.ZipFile(path) as archive:
        audio = any(name.lower().endswith(".smil") for name in archive.namelist())
        container = parse_xml_data(_member(archive, "META-INF/container.xml"),
                                   "META-INF/container.xml")
        opf_path = package_path(container)
        info = read_info(parse_xml_data(_member(archive, opf_path), opf_path), opf_path)
    return {"identifier": info.identifier, "title": info.title, "authors": info.authors,
            "sort": info.sort, "series": info.series, "index": info.series_index,
            "cover": info.cover, "audio": audio, "broken": False}


def broken_info(path):
    """The entry of a book that cannot be read: listed by its file name, so
    that opening it explains what is wrong."""
    return {"identifier": "", "title": os.path.splitext(os.path.basename(path))[0],
            "authors": [], "sort": "", "series": "", "index": None, "cover": None,
            "audio": False, "broken": True}


def scan(folders, cache_file):
    """All EPUBs below folders as [{path, stamp, info}].

    Only files that are new or changed since the cache file was written are
    read; reading every book from a memory card took 93 s on the device.
    """
    cached = {entry["path"]: entry for entry in load_cached(cache_file)}
    entries = []
    changed = False
    for book in list_books(folders):
        try:
            st = os.stat(book.path)
        except OSError:
            continue
        if not stat.S_ISREG(st.st_mode):
            continue
        stamp = [st.st_size, st.st_mtime_ns]
        old = cached.get(book.path)
        if old is not None and old["stamp"] == stamp:
            info = old["info"]
        else:
            changed = True
            try:
                info = book_info(book.path)
            except Exception:
                info = broken_info(book.path)
        entries.append({"path": book.path, "stamp": stamp, "info": info})
    if changed or len(entries) != len(cached):
        _save_cache(cache_file, entries)
    return entries


def load_cached(cache_file):
    """The entries of the last scan, without looking at the books; [] if the
    cache file is missing or damaged."""
    try:
        with open(cache_file, "rb") as f:
            data = f.read(MAX_CACHE_SIZE + 1)
        if len(data) > MAX_CACHE_SIZE:
            return []
        stored = json.loads(data.decode("utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(stored, dict) or stored.get("version") != _CACHE_VERSION:
        return []
    books = stored.get("books")
    return [entry for entry in books if _valid_entry(entry)] if isinstance(books, list) else []


def without_replaced(entries):
    """entries without the books that a readaloud of the same book replaces:
    same identifier, prefixes aside, and same title."""
    def key(info):
        return (normal_identifier(info["identifier"]), info["title"])

    narrated = {key(e["info"]) for e in entries
                if e["info"]["audio"] and e["info"]["identifier"]}
    return [e for e in entries
            if e["info"]["audio"] or not e["info"]["identifier"]
            or key(e["info"]) not in narrated]


def normal_identifier(identifier):
    identifier = identifier.strip().lower()
    stripped = True
    while stripped:
        stripped = False
        for prefix in _ID_PREFIXES:
            if identifier.startswith(prefix):
                identifier = identifier[len(prefix):]
                stripped = True
    return identifier


def extract_cover(epub_path, cover, target):
    """Copy the image cover (a path in the book) out of the EPUB to target.

    Returns False if there is no usable image; the library then shows none.
    """
    try:
        with zipfile.ZipFile(epub_path) as archive:
            data = _member(archive, cover, MAX_COVER_SIZE)
    except Exception:
        return False
    tmp = target + ".part"
    try:
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, target)
    except OSError:
        return False
    return True


def cover_name(entry):
    """File name stem of the entry's cover in the covers folder; changes when
    the book file changes."""
    data = "\0".join([entry["path"]] + [str(n) for n in entry["stamp"]])
    return hashlib.sha1(data.encode("utf-8", "surrogateescape")).hexdigest()[:16]


def prune_covers(covers_dir, names):
    """Remove the covers of books no longer in the library."""
    try:
        files = os.listdir(covers_dir)
    except OSError:
        return
    for name in files:
        match = _COVER_FILE.match(name)
        if match and match.group(1) not in names:
            try:
                os.remove(os.path.join(covers_dir, name))
            except OSError:
                pass


def _member(archive, name, max_size=MAX_XML_SIZE):
    """The content of name in the ZIP archive, with the limits used when
    books are unpacked: no encryption, only stored or deflated, no more than
    max_size bytes whatever the header claims."""
    try:
        info = archive.getinfo(name)
    except KeyError:
        raise EpubError("not_epub", "missing " + name)
    if info.flag_bits & 0x1 or info.compress_type not in (zipfile.ZIP_STORED,
                                                           zipfile.ZIP_DEFLATED):
        raise EpubError("not_epub", "unsupported entry " + name)
    if info.file_size > max_size:
        raise EpubError("too_large", name)
    with archive.open(info) as f:
        data = f.read(max_size + 1)
    if len(data) > max_size:
        raise EpubError("too_large", name)
    return data


def _save_cache(cache_file, entries):
    directory = os.path.dirname(cache_file)
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp = cache_file + ".tmp"
    try:
        # ASCII escapes also cover file names that are not valid UTF-8.
        with open(tmp, "w", encoding="ascii") as f:
            json.dump({"version": _CACHE_VERSION, "books": entries}, f)
        os.replace(tmp, cache_file)
    except OSError:
        pass  # without a cache the books are read again next time


def _valid_entry(entry):
    if not (isinstance(entry, dict) and isinstance(entry.get("path"), str)
            and isinstance(entry.get("stamp"), list) and len(entry["stamp"]) == 2
            and all(isinstance(n, int) for n in entry["stamp"])
            and isinstance(entry.get("info"), dict)):
        return False
    info = entry["info"]
    return (all(isinstance(info.get(field), kind) for field, kind in _INFO_FIELDS.items())
            and all(isinstance(a, str) for a in info["authors"]))
