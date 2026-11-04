"""The reading position of every book, kept in one small JSON file.

A position is a dict: spine (index of the chapter), id (element id of the
first sentence on the page, "" if none) and fraction (0 to 1, how far into
the chapter the page is). The sentence id survives changes of font size and
orientation; fraction is the fallback for chapters without sentences.
"""

import json
import math
import os

MAX_SIZE = 1024 * 1024
_MAX_ID_LENGTH = 1000


def load(path, key):
    """The position stored for key, or None."""
    return _valid(_read_all(path).get(key))


def save(path, key, position):
    """Store position for key.

    Writes a new file and renames it over the old one, so a crash never
    leaves a half-written file. A damaged file is replaced.
    """
    position = _valid(position)
    if position is None:
        raise ValueError("invalid position")
    entries = _read_all(path)
    entries[key] = position
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _read_all(path):
    try:
        with open(path, "rb") as f:
            data = f.read(MAX_SIZE + 1)
        if len(data) > MAX_SIZE:
            return {}
        entries = json.loads(data.decode("utf-8"))
    except (OSError, ValueError, RecursionError):
        return {}
    return entries if isinstance(entries, dict) else {}


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
    return {"spine": spine, "id": sentence, "fraction": float(fraction)}
