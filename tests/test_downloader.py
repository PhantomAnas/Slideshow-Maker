import http.server
import os
import threading

import pytest

from conftest import make_image
from slideshow_maker import downloader


def test_parse_links_filters_junk():
    text = """
    # comment
    https://example.com/a.jpg
    not a link
    http://example.com/b.png

    HTTPS://EXAMPLE.COM/C.webp
    """
    assert downloader.parse_links(text) == [
        "https://example.com/a.jpg", "http://example.com/b.png", "HTTPS://EXAMPLE.COM/C.webp"]


def test_chunk_keeps_every_item():
    items = list(range(10))
    groups = downloader.chunk(items, 3)
    assert groups == [[0, 1, 2, 3], [4, 5, 6], [7, 8, 9]]
    assert downloader.chunk(items, 1) == [items]
    assert downloader.chunk(items, 50) == [[i] for i in items]
    assert downloader.chunk([], 3) == []


@pytest.fixture
def http_folder(tmp_path):
    root = tmp_path / "www"
    make_image(str(root / "big.jpg"), 400, 300)
    make_image(str(root / "small.png"), 20, 20)
    (root / "fake.jpg").write_bytes(b"not an image at all")

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):  # noqa: D102
            pass

    handler = lambda *a, **k: Quiet(*a, directory=str(root), **k)  # noqa: E731
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_download_images_keeps_good_skips_bad(tmp_path, http_folder):
    urls = [f"{http_folder}/big.jpg", f"{http_folder}/small.png",
            f"{http_folder}/fake.jpg", f"{http_folder}/missing.jpg"]
    logs, prog = [], []
    out = downloader.download_images(urls, str(tmp_path / "dl"), min_w=100, min_h=100,
                                     workers=2, progress=lambda d, t: prog.append((d, t)),
                                     log=logs.append)
    assert len(out) == 1 and out[0].endswith("001.jpg") and os.path.isfile(out[0])
    assert prog[-1] == (4, 4)
    assert any("too small" in m for m in logs)
    assert any("not an image" in m for m in logs)
    assert any("download failed" in m for m in logs)
    assert not [n for n in os.listdir(tmp_path / "dl") if n.endswith(".part")]
