import unittest
from xml.etree import ElementTree

from bookfish.search import BookIndex, chapter_of, fold, read_chapter

from .helpers import MINI_DIR, TempDirTestCase, write_files

CONTAINER = """<?xml version="1.0"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
  <rootfiles>
    <rootfile full-path="OPS/package.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""

OPF = """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" xmlns:dc="http://purl.org/dc/elements/1.1/"
         version="3.0" unique-identifier="uid">
  <metadata><dc:identifier id="uid">x</dc:identifier><dc:title>T</dc:title></metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    {items}
  </manifest>
  <spine>{refs}</spine>
</package>"""

NAV = """<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<body><nav epub:type="toc"><ol>{entries}</ol></nav></body></html>"""


def xhtml(body):
    return ('<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Head</title></head>'
            '<body>' + body + '</body></html>')


def chapter(body):
    return chapter_of(ElementTree.fromstring(xhtml(body)).find("{http://www.w3.org/1999/xhtml}body"))


def texts(ch):
    return [ch.text[a:b] for a, b in ch.paragraphs]


class FoldTest(unittest.TestCase):

    def test_accents_case_and_ligatures(self):
        self.assertEqual(fold("Über ÉCOLE Straße ﬁne"), "uber ecole strasse fine")

    def test_punctuation_becomes_space(self):
        self.assertEqual(fold("„Don’t“—go!"), " don t  go ")
        self.assertEqual(fold("don't").split(), fold("don’t").split())

    def test_invisible_characters_go(self):
        # Soft hyphen, zero width space and joiner.
        self.assertEqual(fold("Schwal­be Wort​teil a‍b"), "schwalbe wortteil ab")

    def test_line_breaks_are_spaces(self):
        self.assertEqual(fold("a\nb\tc d"), "a b c d")


class ChapterTest(TempDirTestCase):

    def test_text_like_text_content(self):
        ch = chapter('<p>One <b>two</b> three</p>\n<p>Four</p>')
        self.assertEqual(ch.text, "One two three\nFour")

    def test_paragraphs_at_block_boundaries(self):
        ch = chapter('<div>Loose<p>First <i>para</i></p>tail<div><div>Deep</div></div></div>'
                     '<h2>Head</h2>line<br/>break')
        self.assertEqual(texts(ch), ["Loose", "First para", "tail", "Deep", "Head", "line" + "break"])

    def test_blank_paragraphs_skipped(self):
        ch = chapter('<p>a</p>\n  <p> </p>\n<p>b</p>')
        self.assertEqual([t.strip() for t in texts(ch)], ["a", "b"])

    def test_ids_mark_their_start(self):
        ch = chapter('<p id="p1">ab<span id="s1">cd</span></p><p id="p2">ef</p>')
        self.assertEqual(ch.ids, {"p1": 0, "s1": 2, "p2": 4})

    def test_other_namespaces_hold_text_but_no_blocks(self):
        ch = chapter('<p>a</p><svg xmlns="http://www.w3.org/2000/svg"><text>pic</text></svg>'
                     '<math xmlns="http://www.w3.org/1998/Math/MathML"><mi>x</mi></math>')
        self.assertEqual(ch.text, "apicx")
        self.assertEqual(texts(ch), ["a", "picx"])

    def test_deep_nesting(self):
        ch = chapter("<div>" * 5000 + "deep" + "</div>" * 5000)
        self.assertEqual(texts(ch), ["deep"])

    def test_file_without_namespace(self):
        write_files(self.tmp, {"c.html": "<html><head><title>Not body</title></head>"
                                         "<body><p>a</p><p>b</p></body></html>"})
        ch = read_chapter(self.tmp, "c.html")
        self.assertEqual(texts(ch), ["a", "b"])

    def test_html_entities(self):
        write_files(self.tmp, {"c.xhtml": xhtml("<p>a&nbsp;b&mdash;c</p>")})
        self.assertEqual(read_chapter(self.tmp, "c.xhtml").text, "a b—c")

    def test_unreadable_chapter_is_empty(self):
        write_files(self.tmp, {"bad.xhtml": "<html"})
        self.assertEqual(read_chapter(self.tmp, "bad.xhtml").text, "")
        self.assertEqual(read_chapter(self.tmp, "missing.xhtml").paragraphs, [])

    def test_utf16_counts_like_javascript(self):
        ch = chapter("<p>\U0001F600 x</p>")
        self.assertEqual(ch.utf16(0), 0)
        self.assertEqual(ch.utf16(1), 2)
        self.assertEqual(ch.utf16(3), 4)
        ch = chapter("<p>a\U0001F600b\U0001F601c</p>")
        self.assertEqual([ch.utf16(i) for i in range(6)], [0, 1, 3, 4, 6, 7])
        self.assertEqual(chapter("<p>äx</p>").utf16(1), 1)


class BookIndexTest(TempDirTestCase):

    def book(self, chapters, toc=()):
        """chapters: list of XHTML bodies; toc: (title, href) pairs."""
        files = {"META-INF/container.xml": CONTAINER}
        items = []
        refs = []
        for i, body in enumerate(chapters):
            items.append('<item id="c{0}" href="c{0}.xhtml" media-type="application/xhtml+xml"/>'.format(i))
            refs.append('<itemref idref="c{}"/>'.format(i))
            files["OPS/c{}.xhtml".format(i)] = xhtml(body)
        files["OPS/package.opf"] = OPF.format(items="".join(items), refs="".join(refs))
        files["OPS/nav.xhtml"] = NAV.format(entries="".join(
            '<li><a href="{}">{}</a></li>'.format(href, title) for title, href in toc))
        write_files(self.tmp, files)
        return BookIndex(self.tmp)

    def test_all_words_in_one_paragraph_in_any_order(self):
        index = self.book(['<p>The swallow flew.</p><p>The prince wept.</p>',
                           '<p>Prince and Swallow parted.</p>'])
        result = index.search("swallow prince")
        self.assertEqual(result["total"], 1)
        hit = result["hits"][0]
        self.assertEqual(hit["spine"], 1)
        self.assertEqual(hit["text"], "Prince")

    def test_parts_of_words_case_and_accents(self):
        index = self.book(['<p>Die Schwalben flogen über die Stadt.</p>'])
        self.assertEqual(index.search("SCHWALB uber")["total"], 1)
        self.assertEqual(index.search("schwalbe")["hits"][0]["text"], "Schwalbe")

    def test_place_of_hit_matches_text(self):
        index = self.book(['<p>x</p><p>Ein „Straße“ und <b>stras</b>se</p>',
                           '<p>\U0001F600 Emoji then word</p>'])
        hit = index.search("strasse")["hits"][0]
        text = index.chapters[0].text
        self.assertEqual(hit["text"], "Straße")
        self.assertEqual(text[hit["offset"]:hit["offset"] + hit["length"]], "Straße")
        hit = index.search("word")["hits"][0]
        # UTF-16: the emoji counts twice.
        self.assertEqual(hit["offset"], len("\U0001F600 Emoji then ") + 1)
        self.assertEqual(hit["length"], 4)

    def test_match_keeps_accent_of_decomposed_text(self):
        index = self.book(['<p>un café noir</p>'])
        hit = index.search("cafe")["hits"][0]
        self.assertEqual(hit["text"], "café")
        self.assertEqual(hit["length"], 5)

    def test_match_across_elements_and_soft_hyphen(self):
        index = self.book(['<p>a Schwal­be <i>b</i></p>'])
        hit = index.search("schwalbe")["hits"][0]
        self.assertEqual(hit["text"], "Schwal­be")

    def test_no_words_no_hits(self):
        index = self.book(['<p>text</p>'])
        self.assertEqual(index.search(" ,; "), {"hits": [], "total": 0, "before": -1})

    def test_limit_and_total(self):
        index = self.book(['<p>word</p>' * 5])
        result = index.search("word", limit=3)
        self.assertEqual((len(result["hits"]), result["total"]), (3, 5))

    def test_before_the_place_read(self):
        index = self.book(['<p>word</p><p id="here">word</p><p>word</p>', '<p>word</p>'])
        here = {"spine": 0, "id": "here", "fraction": 0.0}
        self.assertEqual(index.search("word", here)["before"], 1)
        # Without the id, the fraction of the chapter counts.
        self.assertEqual(index.search("word", {"spine": 0, "id": "", "fraction": 1.0})["before"], 3)
        self.assertEqual(index.search("word", {"spine": 1, "id": "", "fraction": 0.0})["before"], 3)
        # No place: no line among the hits.
        self.assertEqual(index.search("word", None)["before"], -1)
        self.assertEqual(index.search("word", {"spine": 7})["before"], -1)
        # QML may hand a whole number over as a float.
        self.assertEqual(index.search("word", {"spine": 0.0, "id": "here"})["before"], 1)

    def test_before_within_the_paragraph(self):
        # Folded text is longer (ß → ss, … → spaces) or shorter (soft
        # hyphen) than the text; the place inside the paragraph still counts.
        index = self.book(['<p>' + "ß" * 30 + ' word <span id="a">x</span> …' + "­" * 30 + ' late</p>'])
        self.assertEqual(index.search("word", {"spine": 0, "id": "a"})["before"], 1)
        self.assertEqual(index.search("late", {"spine": 0, "id": "a"})["before"], 0)

    def test_chapter_titles_from_toc(self):
        index = self.book(['<p>front word</p>',
                           '<h1 id="a">A</h1><p>word one</p><h1 id="b">B</h1><p>word two</p>',
                           '<p>word three</p>'],
                          toc=[("Part A", "c1.xhtml#a"), ("Part B", "c1.xhtml#b"), ("Last", "c2.xhtml")])
        self.assertEqual([h["chapter"] for h in index.search("word")["hits"]],
                         ["", "Part A", "Part B", "Last"])

    def test_snippet(self):
        long = " ".join("w{}".format(i) for i in range(100))
        index = self.book(['<p>' + long + ' swallow ' + long + '</p>'])
        snippet = index.search("swallow")["hits"][0]["snippet"]
        self.assertEqual(snippet[0], {"text": "…", "match": False})
        self.assertEqual(snippet[-1], {"text": "…", "match": False})
        self.assertIn({"text": "swallow", "match": True}, snippet)
        shown = "".join(part["text"] for part in snippet[1:-1])
        # Whole words only, and some context before the match.
        self.assertTrue(shown.startswith("w"))
        self.assertTrue(shown.split()[-1].startswith("w"))
        self.assertGreater(shown.index("swallow"), 30)

    def test_snippet_marks_every_word_and_folds_spaces(self):
        index = self.book(['<p>The   little\nSwallow and the little Prince.</p>'])
        snippet = index.search("little prince")["hits"][0]["snippet"]
        self.assertEqual(snippet, [
            {"text": "The ", "match": False}, {"text": "little", "match": True},
            {"text": " Swallow and the ", "match": False}, {"text": "little", "match": True},
            {"text": " ", "match": False}, {"text": "Prince", "match": True},
            {"text": ".", "match": False}])

    def test_mini_readaloud(self):
        index = BookIndex(MINI_DIR)
        result = index.search("happy prince")
        self.assertGreater(result["total"], 0)
        self.assertEqual(result["hits"][0]["chapter"], "Title Page")
