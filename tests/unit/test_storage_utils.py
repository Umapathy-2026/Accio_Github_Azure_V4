import io

from app.utils.storage import allowed_file, save_file, get_file_path, get_download_url


class FakeFile:
    """Mimics werkzeug FileStorage enough for allowed_file()/save_file()."""

    def __init__(self, filename, content=b"hello world"):
        self.filename = filename
        self._stream = io.BytesIO(content)

    def read(self, n=-1):
        return self._stream.read(n)

    def seek(self, pos):
        return self._stream.seek(pos)

    def save(self, path):
        with open(path, "wb") as f:
            self._stream.seek(0)
            f.write(self._stream.read())


def test_allowed_file_rejects_no_extension(app):
    with app.app_context():
        is_valid, err = allowed_file(FakeFile("noextension"))
        assert is_valid is False
        assert "extension" in err


def test_allowed_file_rejects_disallowed_extension(app):
    with app.app_context():
        is_valid, err = allowed_file(FakeFile("virus.exe"))
        assert is_valid is False
        assert ".exe" in err


def test_allowed_file_accepts_pdf_extension(app):
    with app.app_context():
        # python-magic may be unavailable on the test host; allowed_file()
        # falls back to extension-only validation in that case, so a .pdf
        # name should pass either way.
        is_valid, err = allowed_file(FakeFile("invoice.pdf", content=b"%PDF-1.4 test"))
        assert is_valid is True
        assert err is None


def test_save_file_local_fallback(app):
    with app.app_context():
        original_name, saved_name = save_file(FakeFile("report.pdf"))
        assert original_name == "report.pdf"
        assert saved_name.endswith("_report.pdf")
        import os
        assert os.path.exists(get_file_path(saved_name))


def test_save_file_no_file_returns_none(app):
    with app.app_context():
        original_name, saved_name = save_file(None)
        assert original_name is None
        assert saved_name is None


def test_get_download_url_none_when_no_azure_configured(app):
    with app.app_context():
        assert get_download_url("some-blob-name") is None
