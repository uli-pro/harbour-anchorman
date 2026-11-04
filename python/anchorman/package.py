"""The package document (OPF): reading order, metadata, table of contents."""

import collections

from .errors import EpubError
from .overlay import parse_clock
from .paths import local_path, resolve
from .xmlutil import parse_xml

_CONTAINER = "{urn:oasis:names:tc:opendocument:xmlns:container}"
_OPF = "{http://www.idpf.org/2007/opf}"
_DC = "{http://purl.org/dc/elements/1.1/}"
_XHTML = "{http://www.w3.org/1999/xhtml}"
_EPUB = "{http://www.idpf.org/2007/ops}"

DEFAULT_ACTIVE_CLASS = "-epub-media-overlay-active"

Book = collections.namedtuple(
    "Book", "identifier title authors language cover duration active_class "
            "spine toc")
# overlay is the path of the chapter's SMIL file, or None.
SpineItem = collections.namedtuple(
    "SpineItem", "path media_type overlay linear")
# path is None for headings without a link; level 0 is the top level.
TocEntry = collections.namedtuple("TocEntry", "title path fragment level")

_Item = collections.namedtuple("_Item", "path media_type properties overlay_id")


def read_package(root):
    """Read the book unpacked at root."""
    try:
        container = parse_xml(local_path(root, "META-INF/container.xml"))
    except OSError:
        raise EpubError("not_epub", "no META-INF/container.xml")
    opf_path = None
    for rootfile in container.iter(_CONTAINER + "rootfile"):
        if rootfile.get("media-type") == "application/oebps-package+xml":
            opf_path = rootfile.get("full-path")
            break
    if not opf_path:
        raise EpubError("not_epub", "no package document")
    target = resolve("", opf_path)
    if not target:
        raise EpubError("bad_package", opf_path)
    opf_path = target[0]
    try:
        opf = parse_xml(local_path(root, opf_path))
    except OSError:
        raise EpubError("bad_package", "missing " + opf_path)

    manifest = _read_manifest(opf, opf_path)
    spine = _read_spine(opf, manifest)
    metadata = opf.find(_OPF + "metadata")
    if metadata is None:
        metadata = opf.makeelement(_OPF + "metadata", {})

    toc = []
    nav = next((i for i in manifest.values() if "nav" in i.properties), None)
    if nav is not None:
        try:
            toc = read_nav(root, nav.path)
        except (EpubError, OSError):
            pass

    return Book(
        identifier=_identifier(opf, metadata),
        title=_first_text(metadata, _DC + "title"),
        authors=_authors(metadata),
        language=_first_text(metadata, _DC + "language"),
        cover=_cover(metadata, manifest),
        duration=_duration(metadata),
        active_class=(_meta(metadata, "media:active-class")
                      or DEFAULT_ACTIVE_CLASS),
        spine=spine,
        toc=toc)


def read_nav(root, nav_path):
    """Read the table of contents from the navigation document nav_path."""
    doc = parse_xml(local_path(root, nav_path))
    navs = list(doc.iter(_XHTML + "nav"))
    toc_navs = [n for n in navs if "toc" in n.get(_EPUB + "type", "").split()]
    navs = toc_navs or navs
    if not navs:
        return []
    top = navs[0].find(_XHTML + "ol")
    if top is None:
        return []
    entries = []
    # Iterative walk, so a hostile file cannot exhaust the recursion limit.
    stack = [(iter(top.findall(_XHTML + "li")), 0)]
    while stack:
        items, level = stack[-1]
        li = next(items, None)
        if li is None:
            stack.pop()
            continue
        label = li.find(_XHTML + "a")
        if label is None:
            label = li.find(_XHTML + "span")
        if label is not None:
            path, fragment = None, ""
            href = label.get("href")
            if href:
                target = resolve(nav_path, href)
                if target:
                    path, fragment = target
            entries.append(TocEntry(_text(label), path, fragment, level))
        sub = li.find(_XHTML + "ol")
        if sub is not None:
            stack.append((iter(sub.findall(_XHTML + "li")), level + 1))
    return entries


def _read_manifest(opf, opf_path):
    manifest = {}
    for item in opf.iterfind(_OPF + "manifest/" + _OPF + "item"):
        item_id = item.get("id")
        href = item.get("href")
        if not item_id or not href:
            continue
        target = resolve(opf_path, href)
        if target is None:
            continue
        manifest[item_id] = _Item(
            target[0], item.get("media-type", ""),
            item.get("properties", "").split(), item.get("media-overlay"))
    return manifest


def _read_spine(opf, manifest):
    spine = []
    for ref in opf.iterfind(_OPF + "spine/" + _OPF + "itemref"):
        item = manifest.get(ref.get("idref"))
        if item is None:
            continue
        overlay = manifest.get(item.overlay_id) if item.overlay_id else None
        if overlay is not None and overlay.media_type != "application/smil+xml":
            overlay = None
        spine.append(SpineItem(item.path, item.media_type,
                               overlay.path if overlay else None,
                               ref.get("linear") != "no"))
    if not spine:
        raise EpubError("bad_package", "empty spine")
    return spine


def _identifier(opf, metadata):
    uid = opf.get("unique-identifier")
    identifiers = metadata.findall(_DC + "identifier")
    for identifier in identifiers:
        if uid and identifier.get("id") == uid:
            return _text(identifier)
    return _text(identifiers[0]) if identifiers else ""


def _authors(metadata):
    # EPUB 3 states roles in <meta refines="#id" property="role">,
    # EPUB 2 in an opf:role attribute. Narrators are not authors.
    roles = {}
    for meta in metadata.iterfind(_OPF + "meta"):
        refines = meta.get("refines", "")
        if meta.get("property") == "role" and refines.startswith("#"):
            roles[refines[1:]] = _text(meta)
    authors = []
    for creator in metadata.iterfind(_DC + "creator"):
        role = roles.get(creator.get("id"), creator.get(_OPF + "role"))
        name = _text(creator)
        if name and role != "nrt":
            authors.append(name)
    return authors


def _cover(metadata, manifest):
    for item in manifest.values():
        if "cover-image" in item.properties:
            return item.path
    for meta in metadata.iterfind(_OPF + "meta"):
        if meta.get("name") == "cover":
            item = manifest.get(meta.get("content"))
            if item is not None:
                return item.path
    return None


def _duration(metadata):
    value = _meta(metadata, "media:duration")
    if not value:
        return None
    try:
        return parse_clock(value)
    except ValueError:
        return None


def _meta(metadata, prop):
    """Text of the first <meta property=prop> that refines nothing."""
    for meta in metadata.iterfind(_OPF + "meta"):
        if meta.get("property") == prop and not meta.get("refines"):
            return _text(meta)
    return ""


def _first_text(parent, tag):
    element = parent.find(tag)
    return _text(element) if element is not None else ""


def _text(element):
    return " ".join("".join(element.itertext()).split())
