"""Finding the books in the library folders and what the library shows
of them, kept in a cache file so that a memory card is not read again."""

import collections
import hashlib
import json
import math
import os
import re
import stat
import struct
import zipfile

from .errors import EpubError
from .package import check_encryption, package_path, read_info
from .xmlutil import MAX_XML_SIZE, parse_xml_data

MAX_CACHE_SIZE = 16 * 1024 * 1024
MAX_COVER_SIZE = 5 * 1024 * 1024
# PNG and GIF are decoded at full size before they are scaled down; a small
# file can hold a huge image. JPEG is decoded scaled.
MAX_COVER_PIXELS = 4096
# Raised whenever what is read from a book changes, so that all are read again.
_CACHE_VERSION = 3
# Errors that say something about the book. Others (a card pulled out, no
# memory) may pass, so the book is read again next time.
_BOOK_ERRORS = (EpubError, zipfile.BadZipFile, zipfile.LargeZipFile, KeyError, ValueError,
                EOFError, NotImplementedError, RuntimeError)
_UNREAD = [-1, -1]
# Prefixes of the same identifier: Storyteller writes "uuid:…" where the
# book it started from had "urn:uuid:…" or nothing.
_ID_PREFIXES = ("urn:", "uuid:", "url:", "asin:")
_COVER_FILE = re.compile(r"^([0-9a-f]{16})(\.[a-z]+)?(\.part)?$")
_INFO_FIELDS = {"identifier": str, "title": str, "authors": list, "sort": str,
                "series": str, "index": (float, type(None)),
                "cover": (str, type(None)), "audio": bool, "broken": bool}

BookFile = collections.namedtuple("BookFile", "path name")
BookFile.__doc__ = "An EPUB file; name is the file name without extension."


def list_books(folders):
    """Return the EPUB files below folders, sorted by name.

    Hidden files and folders are left out. Symbolic links to folders are not
    followed, so a link cannot make the walk endless. Missing folders are
    ignored, and so are names that are not valid UTF-8: QML could not show
    or open them.
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
                if real in seen:
                    continue
                seen.add(real)
                books.append(BookFile(path, stem))
    books.sort(key=lambda book: (book.name.casefold(), book.path))
    return books


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

    Raises EpubError, OSError or zipfile errors if the book is unusable. A
    book with DRM is listed, marked broken: opening it says why.
    """
    with _open_regular(path) as f, zipfile.ZipFile(f) as archive:
        container = parse_xml_data(_member(archive, "META-INF/container.xml"),
                                   "META-INF/container.xml")
        opf_path = package_path(container)
        info = read_info(parse_xml_data(_member(archive, opf_path), opf_path), opf_path)
        broken = False
        if "META-INF/encryption.xml" in archive.namelist():
            try:
                check_encryption(parse_xml_data(_member(archive, "META-INF/encryption.xml"),
                                                "META-INF/encryption.xml"))
            except EpubError:
                broken = True
    return {"identifier": info.identifier, "title": info.title, "authors": info.authors,
            "sort": info.sort, "series": info.series, "index": info.series_index,
            "cover": info.cover, "audio": info.audio, "broken": broken}


def broken_info(path):
    """The entry of a book that cannot be read: listed by its file name, so
    that opening it explains what is wrong."""
    return {"identifier": "", "title": os.path.splitext(os.path.basename(path))[0],
            "authors": [], "sort": "", "series": "", "index": None, "cover": None,
            "audio": False, "broken": True}


def scan(folders, cache_file):
    """All EPUBs below folders as ([{path, stamp, info}], changed).

    Only files that are new or changed since the cache file was written are
    read; reading every book from a memory card took 93 s on the device.
    The cache keeps the books of other folders and of folders that are
    missing now, e.g. a memory card taken out. changed is false if the
    entries are those of the cache.
    """
    cached = load_cached(cache_file)
    walked = tuple(os.path.join(folder, "") for folder in folders if os.path.isdir(folder))
    known = {e["path"]: e for e in cached if e["path"].startswith(walked)}
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
        old = known.get(book.path)
        if old is not None and old["stamp"] == stamp:
            info = old["info"]
        else:
            changed = True
            try:
                info = book_info(book.path)
            except _BOOK_ERRORS:
                info = broken_info(book.path)
            except Exception:
                info = broken_info(book.path)
                stamp = _UNREAD
        entries.append({"path": book.path, "stamp": stamp, "info": info})
    # A folder gone during the walk, e.g. a card pulled out: what was seen
    # of it may be incomplete, so its books stay as they were.
    gone = tuple(folder for folder in walked if not os.path.isdir(folder))
    if gone:
        entries = ([e for e in entries if not e["path"].startswith(gone)]
                   + [e for e in known.values() if e["path"].startswith(gone)])
    changed = changed or {e["path"] for e in entries} != set(known)
    if changed:
        others = [e for e in cached if e["path"] not in known]
        _save_cache(cache_file, others + entries)
    return entries, changed


def load_cached(cache_file):
    """The entries of the last scan, without looking at the books; [] if the
    cache file is missing or damaged."""
    try:
        with open(cache_file, "rb") as f:
            data = f.read(MAX_CACHE_SIZE + 1)
        if len(data) > MAX_CACHE_SIZE:
            return []
        stored = json.loads(data.decode("utf-8"))
    except (OSError, ValueError, RecursionError):
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
        with _open_regular(epub_path) as f, zipfile.ZipFile(f) as archive:
            data = _member(archive, cover, MAX_COVER_SIZE)
    except Exception:
        return False
    if not _small_image(data):
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


def _small_image(data):
    """False for PNG and GIF images larger than MAX_COVER_PIXELS a side."""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        width, height = struct.unpack(">II", data[16:24])
    elif data[:6] in (b"GIF87a", b"GIF89a") and len(data) >= 10:
        width, height = struct.unpack("<HH", data[6:10])
    else:
        return True
    return width <= MAX_COVER_PIXELS and height <= MAX_COVER_PIXELS


def _open_regular(path):
    """Open path for reading only if it is a regular file. Opened without
    blocking first: a FIFO put in place of a book would block forever."""
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise EpubError("not_epub", "not a regular file")
        return os.fdopen(fd, "rb")
    except BaseException:
        os.close(fd)
        raise


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
            and all(isinstance(a, str) for a in info["authors"])
            and (info["index"] is None or math.isfinite(info["index"])))
