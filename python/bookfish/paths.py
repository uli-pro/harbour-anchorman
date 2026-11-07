"""Paths inside an unpacked book.

All paths are relative to the book root, use "/" and are percent-decoded,
e.g. "OEBPS/Audio/00001-00001.mp3".
"""

import os
import posixpath
from urllib.parse import unquote, urlsplit

from .errors import EpubError


def resolve(referrer, href):
    """Return (path, fragment) for href found in the file referrer.

    Returns None for external resources (http:, data: ...) and raises
    EpubError for references that leave the book.
    """
    try:
        parts = urlsplit(href)
    except ValueError:
        # Malformed URLs such as "//[x" cannot be fetched from the book.
        return None
    if parts.scheme or parts.netloc:
        return None
    path = unquote(parts.path)
    fragment = unquote(parts.fragment)
    if not path:
        return referrer, fragment
    if path.startswith("/") or "\0" in path:
        raise EpubError("unsafe_path", href)
    path = posixpath.normpath(posixpath.join(posixpath.dirname(referrer), path))
    if path == ".." or path.startswith("../"):
        raise EpubError("unsafe_path", href)
    return path, fragment


def local_path(root, path):
    """Turn a book path into a file system path below root."""
    return os.path.join(root, *path.split("/"))
