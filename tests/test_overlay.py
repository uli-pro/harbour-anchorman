import unittest

from anchorman.errors import EpubError
from anchorman.overlay import Fragment, Overlay, parse_clock, read_overlay

from .helpers import MINI_DIR, TempDirTestCase, write_files

SMIL = """<?xml version="1.0"?>
<smil xmlns="http://www.w3.org/ns/SMIL" version="3.0"><body>{}</body></smil>"""


def par(text, audio=None, begin=None, end=None):
    attrs = ""
    if begin is not None:
        attrs += ' clipBegin="{}"'.format(begin)
    if end is not None:
        attrs += ' clipEnd="{}"'.format(end)
    audio_tag = '<audio src="{}"{}/>'.format(audio, attrs) if audio else ""
    return '<par><text src="{}"/>{}</par>'.format(text, audio_tag)


class ParseClockTest(unittest.TestCase):

    def test_valid(self):
        for text, ms in [("17.780s", 17780), ("0.000s", 0), ("01:40:08.79", 6008790),
                         ("21:58.97", 1318970), ("100:00:00", 360000000),
                         ("500ms", 500), ("2.5min", 150000), ("1h", 3600000),
                         ("17.78", 17780), (" 3s ", 3000), ("0.0004s", 0)]:
            with self.subTest(text=text):
                self.assertEqual(parse_clock(text), ms)

    def test_invalid(self):
        for text in ["", "abc", "1:2", "00:60:00", "00:00:60", "-1s", "1.s",
                     "1e3s", "1:00:00:00", "5 s", "5sec", "1" + "0" * 310 + "h",
                     "9" * 5000 + ":00:00", "\u0661s"]:
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    parse_clock(text)


class ReadOverlayTest(TempDirTestCase):

    def overlay(self, body):
        write_files(self.tmp, {"OPS/mo/c1.smil": SMIL.format(body)})
        return read_overlay(self.tmp, "OPS/mo/c1.smil")

    def assertFails(self, code, body):
        with self.assertRaises(EpubError) as cm:
            self.overlay(body)
        self.assertEqual(cm.exception.code, code)

    def test_mini(self):
        overlay = read_overlay(MINI_DIR, "OEBPS/MediaOverlays/chapter.smil")
        audio = "OEBPS/Audio/00001-00001.mp3"
        self.assertEqual(overlay.fragments, [
            Fragment("OEBPS/chapter.xhtml", "chapter-s0", audio, 0, 17780),
            Fragment("OEBPS/chapter.xhtml", "chapter-s1", audio, 17780, 29660),
            Fragment("OEBPS/chapter.xhtml", "chapter-s2", audio, 29660, 39000),
        ])

    def test_nested_seq_in_document_order(self):
        overlay = self.overlay(
            "<seq>" + par("../c1.xhtml#a", "../a.mp3", "0s", "1s")
            + "<seq>" + par("../c1.xhtml#b", "../a.mp3", "1s", "2s") + "</seq>"
            + par("../c1.xhtml#c", "../a.mp3", "2s", "3s") + "</seq>")
        self.assertEqual([f.text_id for f in overlay.fragments], ["a", "b", "c"])

    def test_unplayable_pars_skipped(self):
        overlay = self.overlay(
            par("../c1.xhtml#no-audio")
            + par("../c1.xhtml", "../a.mp3", "0s", "1s")          # no id
            + par("../c1.xhtml#web", "https://example.com/a.mp3", "0s", "1s")
            + par("../c1.xhtml#ok", "../a.mp3", "1s", "2s")
            + par("../c1.xhtml#bad-clock", "../a.mp3", "soon", "3s")
            + par("../c1.xhtml#empty", "../a.mp3", "3s", "3s")
            + par("../c1.xhtml#backwards", "../a.mp3", "4s", "3.5s")
            + '<par><text src="../c1.xhtml#no-src"/><audio/></par>'
            + par("../c1.xhtml#ok2", "../a.mp3", "4s", "5s"))
        self.assertEqual([f.text_id for f in overlay.fragments], ["ok", "ok2"])
        self.assertEqual(overlay.skipped, 7)

    def test_open_clip(self):
        overlay = self.overlay(par("../c1.xhtml#a", "../a.mp3"))
        self.assertEqual(overlay.fragments, [
            Fragment("OPS/c1.xhtml", "a", "OPS/a.mp3", 0, None)])
        self.assertEqual(overlay.skipped, 0)

    def test_no_fragments(self):
        self.assertFails("bad_overlay", par("../c1.xhtml#a"))

    def test_only_broken_fragments(self):
        self.assertFails("bad_overlay", par("../c1.xhtml#a", "../a.mp3", "2s", "1s"))

    def test_audio_leaving_book(self):
        self.assertFails("unsafe_path",
                         par("../c1.xhtml#a", "../../../x.mp3", "0s", "1s"))

    def test_missing_file(self):
        with self.assertRaises(EpubError) as cm:
            read_overlay(self.tmp, "missing.smil")
        self.assertEqual(cm.exception.code, "bad_overlay")


class OverlayTest(unittest.TestCase):

    def setUp(self):
        # File a: an announcement until 300 ms, then sentences with a gap
        # from 2000 to 2500 ms. File b: the last sentence runs to the end.
        self.overlay = Overlay([
            Fragment("c.xhtml", "s0", "a.mp3", 300, 1000),
            Fragment("c.xhtml", "s1", "a.mp3", 1000, 2000),
            Fragment("c.xhtml", "s2", "a.mp3", 2500, 3000),
            Fragment("c.xhtml", "s3", "b.mp3", 0, 500),
            Fragment("c.xhtml", "s4", "b.mp3", 500, None),
        ])

    def test_index_of(self):
        self.assertEqual(self.overlay.index_of("s0"), 0)
        self.assertEqual(self.overlay.index_of("s4"), 4)
        self.assertIsNone(self.overlay.index_of("nope"))

    def test_index_at(self):
        for audio, ms, index in [
                ("a.mp3", 0, None),       # announcement
                ("a.mp3", 299, None),
                ("a.mp3", 300, 0),        # exactly on a begin
                ("a.mp3", 999, 0),
                ("a.mp3", 1000, 1),       # end of one is begin of the next
                ("a.mp3", 2000, None),    # gap
                ("a.mp3", 2499, None),
                ("a.mp3", 2500, 2),
                ("a.mp3", 3000, None),    # after the last sentence
                ("b.mp3", 0, 3),
                ("b.mp3", 10 ** 9, 4),    # open end
                ("c.mp3", 0, None)]:      # unknown file
            with self.subTest(audio=audio, ms=ms):
                self.assertEqual(self.overlay.index_at(audio, ms), index)

    def test_overlap_later_clip_wins(self):
        overlay = Overlay([Fragment("c.xhtml", "long", "a.mp3", 0, 5000),
                           Fragment("c.xhtml", "short", "a.mp3", 1000, 2000)])
        self.assertEqual(overlay.index_at("a.mp3", 500), 0)
        self.assertEqual(overlay.index_at("a.mp3", 1500), 1)
        self.assertIsNone(overlay.index_at("a.mp3", 3000))

    def test_first_occurrence_of_id_wins(self):
        overlay = Overlay([Fragment("c.xhtml", "s", "a.mp3", 0, 1),
                           Fragment("c.xhtml", "s", "a.mp3", 1, 2)])
        self.assertEqual(overlay.index_of("s"), 0)
