"""Small JSON files that survive a crash at any moment."""

import json
import os


def read(path, max_size):
    """The data in path, or None if it is missing, larger than max_size
    bytes or not JSON."""
    try:
        with open(path, "rb") as f:
            data = f.read(max_size + 1)
        if len(data) > max_size:
            return None
        return json.loads(data.decode("utf-8"))
    except (OSError, ValueError, RecursionError):
        return None


def write(path, data):
    # A new file renamed over the old one: a crash never leaves a
    # half-written file.
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp = path + ".tmp"
    # ASCII escapes also cover file names that are not valid UTF-8.
    with open(tmp, "w", encoding="ascii") as f:
        json.dump(data, f, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
