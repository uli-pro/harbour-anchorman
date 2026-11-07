import json
import os
from unittest import mock

from bookfish import history

from .helpers import TempDirTestCase

HERE = {"spine": 2, "id": "s7"}
THERE = {"spine": 2, "id": "s8"}


class HistoryTest(TempDirTestCase):

    def setUp(self):
        super().setUp()
        self.path = os.path.join(self.tmp, "history.json")

    def write(self, content):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(content)

    def kinds(self, key="book"):
        return [entry["kind"] for entry in history.load(self.path, key)]

    def test_add_and_load(self):
        history.add(self.path, "book", "start", HERE, 1000)
        history.add(self.path, "book", "mark", THERE, 1300.5)
        self.assertEqual(history.load(self.path, "book"), [
            {"time": 1000, "kind": "start", "spine": 2, "id": "s7"},
            {"time": 1300.5, "kind": "mark", "spine": 2, "id": "s8"}])
        self.assertEqual(history.load(self.path, "other"), [])
        self.assertEqual(os.listdir(self.tmp), ["history.json"])

    def test_short_pause_at_same_sentence_is_taken_back(self):
        history.add(self.path, "book", "start", HERE, 1000)
        history.add(self.path, "book", "pause", THERE, 2000)
        history.add(self.path, "book", "start", THERE, 2000 + history.SHORT_PAUSE)
        self.assertEqual(self.kinds(), ["start"])

    def test_pause_stays_if_long_elsewhere_or_not_a_pause(self):
        cases = [("pause", THERE, 2000 + history.SHORT_PAUSE + 1),
                 ("pause", HERE, 2010),
                 ("interrupted", THERE, 2010),
                 ("timer", THERE, 2010)]
        for n, (kind, place, again) in enumerate(cases):
            self.path = os.path.join(self.tmp, "history{}.json".format(n))
            history.add(self.path, "book", "start", HERE, 1000)
            history.add(self.path, "book", kind, THERE, 2000)
            history.add(self.path, "book", "start", place, again)
            self.assertEqual(self.kinds(), ["start", kind, "start"], kind)

    def test_clock_set_back_keeps_the_pause(self):
        history.add(self.path, "book", "pause", HERE, 2000)
        history.add(self.path, "book", "start", HERE, 1990)
        self.assertEqual(self.kinds(), ["pause", "start"])

    def test_only_entry_taken_back_leaves_no_book(self):
        history.add(self.path, "book", "pause", HERE, 2000)
        history.add(self.path, "book", "start", HERE, 2010)
        self.assertEqual(history.load(self.path, "book"), [])
        with open(self.path) as f:
            self.assertEqual(json.load(f), {"books": {}})

    def test_newest_entries_kept(self):
        for i in range(history.MAX_ENTRIES + 5):
            history.add(self.path, "book", "mark", HERE, i)
        times = [entry["time"] for entry in history.load(self.path, "book")]
        self.assertEqual(times, list(range(5, history.MAX_ENTRIES + 5)))

    def test_book_heard_longest_ago_goes(self):
        for i in range(history.MAX_BOOKS):
            history.add(self.path, "b{}".format(i), "mark", HERE, 100 + i)
        # Heard again, so no longer the oldest.
        history.add(self.path, "b0", "mark", HERE, 500)
        history.add(self.path, "new", "mark", HERE, 50)
        self.assertEqual(self.kinds("b1"), [])
        self.assertEqual(self.kinds("b0"), ["mark", "mark"])
        self.assertEqual(self.kinds("new"), ["mark"])

    def test_file_stays_small_enough_to_read(self):
        long_id = {"spine": 1, "id": "x" * 1000}
        for book in ("a", "b"):
            for i in range(10):
                history.add(self.path, book, "mark", long_id, i)
        limit = os.path.getsize(self.path) + 500
        with mock.patch.object(history, "MAX_SIZE", limit):
            history.add(self.path, "c", "mark", long_id, 50)
            # The book heard longest ago goes.
            self.assertEqual(history.load(self.path, "a"), [])
            self.assertEqual(len(history.load(self.path, "b")), 10)
            for i in range(40):
                history.add(self.path, "c", "mark", long_id, 100 + i)
            self.assertLessEqual(os.path.getsize(self.path), limit)
            self.assertEqual(history.load(self.path, "b"), [])
            entries = history.load(self.path, "c")
            self.assertTrue(entries)
            self.assertEqual(entries[-1]["time"], 139)

    def test_invalid_entries_refused(self):
        bad = [("stop", HERE, 1), ("start", {"spine": -1, "id": "a"}, 1),
               ("start", {"spine": True, "id": "a"}, 1), ("start", {"spine": 1}, 1),
               ("start", {"spine": 1, "id": "x" * 1001}, 1), ("start", None, 1),
               ("start", HERE, float("nan")), ("start", HERE, True), ([], HERE, 1)]
        for kind, place, now in bad:
            with self.assertRaises(ValueError, msg=(kind, place, now)):
                history.add(self.path, "book", kind, place, now)
        self.assertFalse(os.path.exists(self.path))

    def test_spine_from_qml_may_be_float(self):
        history.add(self.path, "book", "start", {"spine": 3.0, "id": ""}, 1)
        self.assertEqual(history.load(self.path, "book")[0]["spine"], 3)

    def test_damaged_files(self):
        for content in ("", "{", "[]", '{"books": []}', '{"books": {"book": 5}}',
                        json.dumps({"books": {"book": [{"time": 1, "kind": "start", "spine": 1}]}}),
                        json.dumps({"books": {}, "pad": "x" * history.MAX_SIZE})):
            self.write(content)
            self.assertEqual(history.load(self.path, "book"), [], content[:40])
            history.add(self.path, "book", "start", HERE, 1)
            self.assertEqual(self.kinds(), ["start"], content[:40])

    def test_invalid_entries_in_file_dropped(self):
        self.write(json.dumps({"books": {"book": [
            {"time": 1, "kind": "start", "spine": 1, "id": "a"},
            {"time": "2", "kind": "mark", "spine": 1, "id": "a"},
            {"time": 3, "kind": "pause", "spine": 1, "id": "a", "extra": 1}]}}))
        self.assertEqual(history.load(self.path, "book"), [
            {"time": 1, "kind": "start", "spine": 1, "id": "a"},
            {"time": 3, "kind": "pause", "spine": 1, "id": "a"}])


class SessionsTest(TempDirTestCase):

    def entry(self, time, kind):
        return {"time": time, "kind": kind, "spine": 0, "id": "s"}

    def test_sessions_newest_first(self):
        entries = [self.entry(1, "mark"), self.entry(2, "pause"),
                   self.entry(10, "start"), self.entry(11, "mark"), self.entry(12, "timer"),
                   self.entry(20, "start"), self.entry(21, "interrupted"),
                   self.entry(22, "start")]
        result = history.sessions(entries)
        self.assertEqual([(s["start"], s["end"]) for s in result], [(22, 22), (20, 21), (10, 12), (1, 2)])
        self.assertEqual([e["time"] for e in result[2]["entries"]], [12, 11, 10])

    def test_no_entries(self):
        self.assertEqual(history.sessions([]), [])
