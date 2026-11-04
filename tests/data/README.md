# Test data

`mini/` is a minimal readaloud EPUB in unpacked form; the tests zip it at run
time. It follows the structure that Storyteller 2.14 produces (namespaces,
element ids, clock values, `media:active-class`), trimmed by hand to a title
page and the first three sentences.

- Text: Oscar Wilde, *The Happy Prince* (1888), public domain.
- Audio: the first 39 seconds of the LibriVox recording of *The Happy Prince
  and Other Tales* read by Joy Chan (public domain), re-encoded as mono
  32 kbit/s. It starts with the LibriVox announcement, as the original does.

Files that attack the parsers (zip slip, zip bombs, entity expansion ...)
are built by the tests themselves and are not stored here.
