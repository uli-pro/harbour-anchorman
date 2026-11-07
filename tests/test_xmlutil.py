import os

from bookfish.errors import EpubError
from bookfish.xmlutil import parse_xml

from .helpers import TempDirTestCase

BILLION_LAUGHS = """<?xml version="1.0"?>
<!DOCTYPE lolz [
 <!ENTITY lol "lol">
 <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
 <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
 <!ENTITY lol4 "&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;">
 <!ENTITY lol5 "&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;">
 <!ENTITY lol6 "&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;">
 <!ENTITY lol7 "&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;">
 <!ENTITY lol8 "&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;">
 <!ENTITY lol9 "&lol8;&lol8;&lol8;&lol8;&lol8;&lol8;&lol8;&lol8;&lol8;&lol8;">
]>
<lolz>&lol9;</lolz>
"""

EXTERNAL_ENTITY = """<?xml version="1.0"?>
<!DOCTYPE package [<!ENTITY secret SYSTEM "file:///etc/passwd">]>
<package>&secret;</package>
"""


class ParseXmlTest(TempDirTestCase):

    def write(self, content):
        path = os.path.join(self.tmp, "file.xml")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def assertFails(self, code, content, **kwargs):
        with self.assertRaises(EpubError) as cm:
            parse_xml(self.write(content), **kwargs)
        self.assertEqual(cm.exception.code, code)

    def test_valid(self):
        root = parse_xml(self.write('<a xmlns="urn:x"><b>text</b></a>'))
        self.assertEqual(root.tag, "{urn:x}a")
        self.assertEqual(root[0].text, "text")

    def test_html_doctype_allowed(self):
        root = parse_xml(self.write("<!DOCTYPE html>\n<html/>"))
        self.assertEqual(root.tag, "html")

    def test_external_doctype_allowed(self):
        root = parse_xml(self.write(
            '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" '
            '"http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">\n<html/>'))
        self.assertEqual(root.tag, "html")

    # Entities can only be declared in an internal subset, which the
    # doctype check refuses; these two attacks are stopped there.
    def test_billion_laughs(self):
        self.assertFails("forbidden_dtd", BILLION_LAUGHS)

    def test_external_entity(self):
        self.assertFails("forbidden_dtd", EXTERNAL_ENTITY)

    def test_internal_subset_without_entities(self):
        self.assertFails("forbidden_dtd", "<!DOCTYPE a [<!ELEMENT a ANY>]><a/>")

    def test_malformed(self):
        self.assertFails("bad_xml", "<a><b></a>")

    def test_empty(self):
        self.assertFails("bad_xml", "")

    def test_odd_encodings(self):
        for encoding in ("foo", "zlib", "utf-7", "idna", "punycode"):
            with self.subTest(encoding=encoding):
                self.assertFails("bad_xml",
                                 '<?xml version="1.0" encoding="{}"?><a/>'.format(encoding))

    def test_too_large(self):
        self.assertFails("too_large", "<a>" + "x" * 100 + "</a>", max_size=50)

    def test_missing_file(self):
        with self.assertRaises(OSError):
            parse_xml(os.path.join(self.tmp, "missing.xml"))
