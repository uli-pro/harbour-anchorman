"""Parsing XML files taken from a book."""

from xml.etree import ElementTree
from xml.parsers import expat

from .errors import EpubError

MAX_XML_SIZE = 10 * 1024 * 1024


def parse_xml(path, max_size=MAX_XML_SIZE):
    """Return the root element of the XML file at path.

    Raises EpubError for oversized, malformed or DTD-carrying files and lets
    OSError through, so callers can report a missing file in their own terms.
    """
    with open(path, "rb") as f:
        data = f.read(max_size + 1)
    if len(data) > max_size:
        raise EpubError("too_large", path)
    _reject_dtd(data, path)
    try:
        return ElementTree.fromstring(data)
    except ElementTree.ParseError as e:
        raise EpubError("bad_xml", "{}: {}".format(path, e))


def _reject_dtd(data, path):
    # Only expat >= 2.4.1 limits entity expansion ("billion laughs"), and the
    # expat shipped with older Sailfish OS releases is unknown. No file in an
    # EPUB 3 needs its own DTD, so refuse internal subsets and entity
    # declarations before ElementTree ever sees them. A plain
    # <!DOCTYPE html> stays allowed; ElementTree never loads external DTDs.
    def on_doctype(name, sysid, pubid, has_internal_subset):
        if has_internal_subset:
            raise EpubError("forbidden_dtd", path)

    def on_entity(*args):
        raise EpubError("forbidden_dtd", path)

    parser = expat.ParserCreate()
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    parser.StartDoctypeDeclHandler = on_doctype
    parser.EntityDeclHandler = on_entity
    try:
        parser.Parse(data, True)
    except expat.ExpatError as e:
        raise EpubError("bad_xml", "{}: {}".format(path, e))
