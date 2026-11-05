"""Parsing XML files taken from a book."""

import html.entities
import re
from xml.etree import ElementTree
from xml.parsers import expat

from .errors import EpubError

MAX_XML_SIZE = 10 * 1024 * 1024


_XML_ENTITIES = {"amp", "lt", "gt", "quot", "apos"}
_ENTITY = re.compile(rb"&([A-Za-z][A-Za-z0-9]{0,31});")


def parse_xml(path, max_size=MAX_XML_SIZE, html_entities=False):
    """Return the root element of the XML file at path.

    Raises EpubError for oversized, malformed or DTD-carrying files and lets
    OSError through, so callers can report a missing file in their own terms.
    html_entities: accept named HTML characters such as &nbsp;, which XHTML
    files often use without a DTD that declares them.
    """
    with open(path, "rb") as f:
        data = f.read(max_size + 1)
    return parse_xml_data(data, path, max_size, html_entities)


def parse_xml_data(data, name, max_size=MAX_XML_SIZE, html_entities=False):
    """Like parse_xml, for data read from elsewhere; name is for messages."""
    if len(data) > max_size:
        raise EpubError("too_large", name)
    if html_entities:
        data = _ENTITY.sub(_numeric_reference, data)
    # expat looks up the declared encoding among Python's codecs, which fail
    # with LookupError or ValueError (including UnicodeError) on odd names.
    try:
        _reject_dtd(data, name)
        return ElementTree.fromstring(data)
    except (expat.ExpatError, ElementTree.ParseError, LookupError,
            ValueError) as e:
        raise EpubError("bad_xml", "{}: {}".format(name, e))


def _numeric_reference(match):
    name = match.group(1).decode("ascii")
    if name in _XML_ENTITIES or name not in html.entities.name2codepoint:
        return match.group(0)
    return b"&#%d;" % html.entities.name2codepoint[name]


def _reject_dtd(data, path):
    # Only expat >= 2.4.1 limits entity expansion ("billion laughs"), and the
    # expat shipped with older Sailfish OS releases is unknown. No file in an
    # EPUB 3 needs its own DTD, so refuse internal subsets, the only place
    # entities can be declared once external DTDs are never read, before
    # ElementTree ever sees them. A plain <!DOCTYPE html> stays allowed.
    def on_doctype(name, sysid, pubid, has_internal_subset):
        if has_internal_subset:
            raise EpubError("forbidden_dtd", path)

    parser = expat.ParserCreate()
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    parser.StartDoctypeDeclHandler = on_doctype
    parser.Parse(data, True)
