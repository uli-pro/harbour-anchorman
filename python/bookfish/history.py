"""The listening history: when which sentence was heard, per book.

Kept in a file of its own beside the positions, so a damaged history never
costs a position. An entry is a dict: time (seconds since 1970), kind (see
KINDS), spine (index of the chapter) and id (element id of the sentence).
Only the place is stored; the text shown comes from the book.

File format: {"books": {key: [entry, ...]}}, oldest entry first.
"""

import json
import math

from . import jsonfile

# start of listening, a mark every few minutes while listening, and the
# ways listening ends.
KINDS = ("start", "mark", "pause", "interrupted", "timer", "close", "end")
MAX_ENTRIES = 200
MAX_BOOKS = 20
# A pause this short, resumed at the same sentence, does not end listening.
SHORT_PAUSE = 120
MAX_SIZE = 1024 * 1024
_MAX_ID_LENGTH = 1000


def add(path, key, kind, place, now):
    """Add an entry of kind at place {spine, id} for the book key.

    Starting again at the sentence of a short pause takes that pause back.
    Keeps the newest MAX_ENTRIES entries per book and the MAX_BOOKS books
    heard last. A damaged file is replaced.
    """
    entry = _valid({"time": now, "kind": kind,
                    "spine": place.get("spine") if isinstance(place, dict) else None,
                    "id": place.get("id") if isinstance(place, dict) else None})
    if entry is None:
        raise ValueError("invalid history entry")
    books = _read_all(path)
    entries = books.get(key, [])
    last = entries[-1] if entries else None
    if (kind == "start" and last is not None and last["kind"] == "pause"
            and (last["spine"], last["id"]) == (entry["spine"], entry["id"])
            and 0 <= now - last["time"] <= SHORT_PAUSE):
        entries.pop()
    else:
        entries.append(entry)
    if entries:
        books[key] = entries[-MAX_ENTRIES:]
    else:
        books.pop(key, None)
    # The books heard longest ago go, never the one just heard; also while
    # the file would be too large to be read again (long ids).
    others = sorted((b for b in books if b != key), key=lambda b: books[b][-1]["time"])
    while others and (len(books) > MAX_BOOKS or _size(books) > MAX_SIZE):
        del books[others.pop(0)]
    while key in books and _size(books) > MAX_SIZE:
        books[key] = books[key][len(books[key]) // 2 + 1:]
        if not books[key]:
            del books[key]
    jsonfile.write(path, {"books": books})


def _size(books):
    # As jsonfile.write stores it.
    return len(json.dumps({"books": books}, sort_keys=True))


def load(path, key):
    """The entries of the book key, oldest first."""
    return _read_all(path).get(key, [])


def sessions(entries):
    """entries grouped into listening sessions, each beginning with a start:
    [{start, end, entries}], times of the first and last entry; newest
    session first, and in each the newest entry first."""
    groups = []
    for entry in entries:
        if entry["kind"] == "start" or not groups:
            groups.append([])
        groups[-1].append(entry)
    return [{"start": group[0]["time"], "end": group[-1]["time"], "entries": group[::-1]}
            for group in reversed(groups)]


def _read_all(path):
    stored = jsonfile.read(path, MAX_SIZE)
    books = stored.get("books") if isinstance(stored, dict) else None
    if not isinstance(books, dict):
        return {}
    result = {}
    for key, entries in books.items():
        if not isinstance(entries, list):
            continue
        valid = [e for e in (_valid(entry) for entry in entries) if e is not None]
        if valid:
            result[key] = valid
    return result


def _valid(entry):
    """A clean copy of entry, or None if it is not a valid entry."""
    if not isinstance(entry, dict):
        return None
    time = entry.get("time")
    kind = entry.get("kind")
    spine = entry.get("spine")
    sentence = entry.get("id")
    # A number from QML may come as a float.
    if isinstance(spine, float) and spine.is_integer():
        spine = int(spine)
    # bool is a subclass of int, but true is no chapter number.
    if (not isinstance(time, (int, float)) or isinstance(time, bool) or not math.isfinite(time)
            or kind not in KINDS
            or not isinstance(spine, int) or isinstance(spine, bool) or spine < 0
            or not isinstance(sentence, str) or len(sentence) > _MAX_ID_LENGTH):
        return None
    return {"time": time, "kind": kind, "spine": spine, "id": sentence}
