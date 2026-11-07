"""The reading state, kept in one small JSON file: the position in every
book and the book read last.

A position is a dict: spine (index of the chapter), id (element id of the
first sentence starting on the page, "" if none), fraction (0 to 1, how
far into the chapter the page is), heard (true if id is the sentence
heard last rather than the top of the page read last; listening resumes
there) and offset (first character of the page read in the chapter's text,
in UTF-16 code units; -1 if not known, as when listening). The sentence id
and offset survive changes of font size and orientation; fraction is the
fallback for pages without either.

File format: {"books": {key: position}, "last": path of the EPUB file,
"recent": paths of the EPUB files opened last, newest first}.
"""

import math
import os

from . import jsonfile

MAX_SIZE = 1024 * 1024
RECENT = 3
_MAX_ID_LENGTH = 1000


def load(path, key):
    """The position stored for key, or None."""
    return _valid(_read_all(path)["books"].get(key))


def save(path, key, position):
    """Store position for key. A damaged file is replaced."""
    position = _valid(position)
    if position is None:
        raise ValueError("invalid position")
    state = _read_all(path)
    state["books"][key] = position
    _write(path, state)


def load_last(path):
    """The EPUB file read last, or None if there is none or it is gone."""
    last = _read_all(path)["last"]
    return last if isinstance(last, str) and os.path.isfile(last) else None


def save_last(path, epub_path):
    state = _read_all(path)
    state["last"] = epub_path
    state["recent"] = ([epub_path] + [p for p in state["recent"] if p != epub_path])[:RECENT]
    _write(path, state)


def load_recent(path):
    """The EPUB files opened last that still exist, newest first."""
    return [p for p in _read_all(path)["recent"] if os.path.isfile(p)]


def _read_all(path):
    state = {"books": {}, "last": None, "recent": []}
    stored = jsonfile.read(path, MAX_SIZE)
    if isinstance(stored, dict):
        if isinstance(stored.get("books"), dict):
            state["books"] = stored["books"]
        state["last"] = stored.get("last")
        recent = stored.get("recent")
        if isinstance(recent, list):
            state["recent"] = [p for p in recent if isinstance(p, str)][:RECENT]
    return state


def _write(path, state):
    jsonfile.write(path, state)


def _valid(position):
    """A clean copy of position, or None if it is not a valid position."""
    if not isinstance(position, dict):
        return None
    spine = position.get("spine")
    sentence = position.get("id")
    fraction = position.get("fraction")
    # bool is a subclass of int, but true is no chapter number.
    if (not isinstance(spine, int) or isinstance(spine, bool) or spine < 0
            or not isinstance(sentence, str) or len(sentence) > _MAX_ID_LENGTH
            or not isinstance(fraction, (int, float))
            or isinstance(fraction, bool) or not math.isfinite(fraction)
            or not 0 <= fraction <= 1):
        return None
    # Files from before listening have no "heard", from before the reading
    # history no "offset".
    heard = position.get("heard", False) is True
    offset = position.get("offset", -1)
    if isinstance(offset, float) and offset.is_integer():
        offset = int(offset)
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        offset = -1
    return {"spine": spine, "id": sentence, "fraction": float(fraction),
            "heard": heard, "offset": offset}
