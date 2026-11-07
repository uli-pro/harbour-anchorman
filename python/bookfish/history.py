"""The history of reading and listening: where one was when, per book.

Kept in a file of its own beside the positions, so a damaged history never
costs a position. An entry is a dict: time (seconds since 1970), kind (see
LISTENING and READING), spine (index of the chapter) and the place in it:
id (element id of the sentence heard) when listening, offset (first
character of the page in the chapter's text, in UTF-16 code units) when
reading. Only the place is stored; the text shown comes from the book.

File format: {"books": {key: [entry, ...]}}, oldest entry first.
"""

import json
import math

from . import jsonfile

# Listening: its start, a mark every few minutes, and the ways it ends.
LISTENING = ("start", "mark", "pause", "interrupted", "timer", "close", "end")
# Reading: its start, a mark every few minutes if pages were turned, the
# place before a jump, and leaving the app or the book.
READING = ("read", "page", "jump", "away", "close")
# Kinds that begin a session.
_STARTS = {"start": "listening", "read": "reading"}
MAX_ENTRIES = 200
MAX_BOOKS = 20
# A pause this short, resumed at the same sentence, does not end listening;
# coming back to the app this soon and reading on in the same chapter does
# not end reading.
SHORT_PAUSE = 120
MAX_SIZE = 1024 * 1024
_MAX_ID_LENGTH = 1000


def add(path, key, kind, place, now):
    """Add an entry of kind at place for the book key: {spine, id} when
    listening, {spine, offset} when reading.

    Starting again at the sentence of a short pause takes that pause back;
    reading on from where one left the app shortly before takes that back.
    Keeps the newest MAX_ENTRIES entries per book and the MAX_BOOKS books
    used last. A damaged file is replaced.
    """
    entry = dict(place) if isinstance(place, dict) else {}
    entry.update(time=now, kind=kind)
    entry = _valid(entry)
    if entry is None:
        raise ValueError("invalid history entry")
    books = _read_all(path)
    entries = books.get(key, [])
    last = entries[-1] if entries else None
    # Reading on needs only the same chapter: while the app was away its
    # page may have been laid out anew (a bar hidden), so it begins elsewhere.
    if (last is not None and 0 <= now - last["time"] <= SHORT_PAUSE
            and (kind == "start" and last["kind"] == "pause" and _place(last) == _place(entry)
                 or kind == "read" and last["kind"] == "away" and last["spine"] == entry["spine"])):
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
    """entries grouped into sessions of reading or listening, each beginning
    with a read or a start: [{mode, start, end, entries}], mode "reading" or
    "listening", start and end the times of the first and last entry; newest
    session first, and in each the newest entry first."""
    groups = []
    for entry in entries:
        if entry["kind"] in _STARTS or not groups:
            groups.append([])
        groups[-1].append(entry)
    return [{"mode": _STARTS.get(group[0]["kind"], "reading" if "offset" in group[0] else "listening"),
             "start": group[0]["time"], "end": group[-1]["time"], "entries": group[::-1]}
            for group in reversed(groups)]


def _place(entry):
    return entry["spine"], entry.get("id"), entry.get("offset")


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
    spine = _index(entry.get("spine"))
    sentence = entry.get("id")
    offset = _index(entry.get("offset"))
    if (not isinstance(time, (int, float)) or isinstance(time, bool) or not math.isfinite(time)
            or spine is None):
        return None
    # Exactly one kind of place, and one that fits the kind of entry.
    if "offset" not in entry:
        if (kind not in LISTENING or not isinstance(sentence, str)
                or len(sentence) > _MAX_ID_LENGTH):
            return None
        return {"time": time, "kind": kind, "spine": spine, "id": sentence}
    if kind not in READING or "id" in entry or offset is None:
        return None
    return {"time": time, "kind": kind, "spine": spine, "offset": offset}


def _index(value):
    """value as an int >= 0, or None."""
    # A number from QML may come as a float.
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    # bool is a subclass of int, but true is no chapter number.
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        return None
    return value
