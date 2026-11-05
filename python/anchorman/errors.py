"""Error type shared by the EPUB modules."""


class EpubError(Exception):
    """A book cannot be used.

    code is a fixed English keyword that QML maps to a translated message:
    not_zip, not_epub, too_many_files, too_large, no_space, unsafe_path,
    bad_xml, forbidden_dtd, bad_package, bad_overlay, drm.
    detail is a short English text for the log, e.g. the file concerned.
    """

    def __init__(self, code, detail=""):
        super().__init__(code, detail)
        self.code = code
        self.detail = detail

    def __str__(self):
        if self.detail:
            return "{}: {}".format(self.code, self.detail)
        return self.code
