"""Safe extraction of an EPUB into a directory."""

import os
import shutil
import stat
import zipfile
import zlib

from .errors import EpubError

# Limits against zip bombs that do not cap the length of a book. Audio barely
# compresses, so a real readaloud unpacks to about the size of the EPUB file
# (The Happy Prince: 100 MB -> 101 MB); a zip bomb unpacks to thousands of
# times its size. The headroom covers text-heavy books whose XHTML compresses
# well. Long audiobooks are large but legitimate (51 h at 64 kbit/s = 1.5 GB),
# so the real risk is filling the phone: keep MIN_FREE_SPACE free afterwards.
MAX_ENTRIES = 10000
MAX_RATIO = 2
HEADROOM = 100 * 1024 * 1024
MIN_FREE_SPACE = 500 * 1024 * 1024

_CHUNK = 64 * 1024
_MIMETYPE = b"application/epub+zip"
# What zipfile raises for damaged, encrypted or unsupported entries.
_CORRUPT = (zipfile.BadZipFile, zlib.error, EOFError, NotImplementedError,
            RuntimeError)


def extract(epub_path, dest_dir, max_entries=MAX_ENTRIES, max_ratio=MAX_RATIO,
            headroom=HEADROOM, min_free_space=MIN_FREE_SPACE):
    """Unpack the EPUB at epub_path into dest_dir, which must not exist.

    Unpacks into dest_dir + ".part" first and renames it at the end, so an
    interrupted extraction never looks like a complete one.
    """
    if os.path.lexists(dest_dir):
        raise ValueError("destination exists: " + dest_dir)
    try:
        archive = zipfile.ZipFile(epub_path)
    except _CORRUPT as e:
        raise EpubError("not_zip", str(e))
    with archive:
        try:
            infos = archive.infolist()
            if len(infos) > max_entries:
                raise EpubError("too_many_files", str(len(infos)))
            _check_mimetype(archive)
            max_size = max_ratio * os.path.getsize(epub_path) + headroom
            declared = sum(info.file_size for info in infos)
            if declared > max_size:
                raise EpubError("too_large", str(declared))
            parent = os.path.dirname(os.path.abspath(dest_dir))
            _check_space(parent, declared, min_free_space)

            tmp_dir = dest_dir + ".part"
            _remove(tmp_dir)
            os.makedirs(tmp_dir)
            try:
                _extract_entries(archive, infos, tmp_dir, max_size,
                                 min_free_space)
                os.rename(tmp_dir, dest_dir)
            except BaseException:
                _remove(tmp_dir)
                raise
        except _CORRUPT as e:
            raise EpubError("not_zip", str(e))


def _check_mimetype(archive):
    try:
        info = archive.getinfo("mimetype")
    except KeyError:
        raise EpubError("not_epub", "no mimetype")
    with archive.open(info) as f:
        content = f.read(len(_MIMETYPE) + 2)
    if content.strip() != _MIMETYPE:
        raise EpubError("not_epub", "wrong mimetype")


def _check_space(directory, needed, min_free_space):
    if shutil.disk_usage(directory).free - needed < min_free_space:
        raise EpubError("no_space", "{} bytes needed".format(needed))


def _extract_entries(archive, infos, root, max_size, min_free_space):
    seen = set()
    written = 0
    for info in infos:
        name = _safe_name(info.filename)
        if stat.S_ISLNK(info.external_attr >> 16):
            continue
        if not name:
            if info.is_dir():
                continue
            raise EpubError("unsafe_path", info.filename)
        if name in seen:
            raise EpubError("unsafe_path", "duplicate " + info.filename)
        seen.add(name)
        target = os.path.join(root, *name.split("/"))
        try:
            if info.is_dir():
                os.makedirs(target, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            _check_space(root, info.file_size, min_free_space)
            # Mode "xb" never overwrites, and permissions from the archive
            # are ignored on purpose.
            with archive.open(info) as src, open(target, "xb") as dst:
                while True:
                    chunk = src.read(_CHUNK)
                    if not chunk:
                        break
                    # zipfile already stops at the declared size; counting
                    # ourselves keeps the limit should that ever change.
                    written += len(chunk)
                    if written > max_size:
                        raise EpubError("too_large", info.filename)
                    dst.write(chunk)
        except (FileExistsError, NotADirectoryError, IsADirectoryError):
            # A file and a directory with the same name.
            raise EpubError("unsafe_path", info.filename)


def _safe_name(name):
    """Return name as a clean relative path, or raise for unsafe names."""
    if (not name or name.startswith("/") or "\\" in name or ":" in name
            or "\0" in name):
        raise EpubError("unsafe_path", name)
    parts = name.split("/")
    if ".." in parts:
        raise EpubError("unsafe_path", name)
    return "/".join(p for p in parts if p not in ("", "."))


def _remove(path):
    if os.path.islink(path) or os.path.isfile(path):
        os.remove(path)
    elif os.path.isdir(path):
        shutil.rmtree(path)
