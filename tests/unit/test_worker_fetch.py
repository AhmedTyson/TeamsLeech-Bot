import hashlib

import httpx
import pytest

from worker.downloader import download, download_url
from worker.lister import (
    FileEntry,
    cookie_header,
    folder_api_url,
    list_folder,
    parse_files,
)


def test_folder_api_url():
    url = folder_api_url("https://t.sharepoint.com/sites/X/Shared Documents/Rec/")
    assert url.startswith("https://t.sharepoint.com/sites/X/_api/web/")
    assert "GetFolderByServerRelativeUrl" in url
    with pytest.raises(ValueError):
        folder_api_url("https://t.sharepoint.com/sites/X/Other")
    with pytest.raises(ValueError):
        folder_api_url("http://t.sharepoint.com/sites/X/Shared Documents/")


def test_parse_files():
    payload = {
        "d": {
            "results": [
                {
                    "Name": "a.mp4",
                    "UniqueId": "u1",
                    "Length": "10",
                    "TimeLastModified": "2026-01-01",
                    "ServerRelativeUrl": "/s/a.mp4",
                },
                {"Name": "", "UniqueId": "x"},
            ]
        }
    }
    entries = parse_files(payload)
    assert entries == [
        FileEntry(
            name="a.mp4", unique_id="u1", size=10, modified="2026-01-01", server_path="/s/a.mp4"
        )
    ]


def test_cookie_header():
    assert cookie_header([{"name": "a", "value": "1"}, {"name": "", "value": "x"}]) == "a=1"


def test_list_folder_401_loud():
    req = httpx.Request("GET", "https://t.sharepoint.com/x")
    resp = httpx.Response(401, request=req)
    client = httpx.Client(transport=httpx.MockTransport(lambda r: resp))
    with pytest.raises(PermissionError, match="re-bootstrap"):
        list_folder("https://t.sharepoint.com/sites/X/Shared Documents/", [], client)


def test_download_full_and_hash(tmp_path):
    body = b"0123456789" * 100
    expected = hashlib.sha256(body).hexdigest()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["cookie"] == "a=1"
        if "Range" in request.headers:
            start = int(request.headers["Range"].split("=")[1].split("-")[0])
            content = body[start:]
            return httpx.Response(
                206,
                content=content,
                headers={"Content-Range": f"bytes {start}-{len(body) - 1}/{len(body)}"},
            )
        return httpx.Response(200, content=body)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    dest = str(tmp_path / "f.bin")
    n, digest = download("https://t/x", [{"name": "a", "value": "1"}], dest, client)
    assert (n, digest) == (len(body), expected)


def test_download_resume(tmp_path):
    body = b"0123456789" * 100

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Range"] == "bytes=100-"
        return httpx.Response(206, content=body[100:])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    dest = str(tmp_path / "f.bin")
    with open(dest, "wb") as f:
        f.write(body[:100])
    n, digest = download("https://t/x", [], dest, client)
    assert n == len(body)
    assert digest == hashlib.sha256(body).hexdigest()
    with open(dest, "rb") as f:
        assert f.read() == body


def test_download_401_loud(tmp_path):
    req = httpx.Request("GET", "https://t/x")
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(401, request=req)))
    with pytest.raises(PermissionError, match="re-bootstrap"):
        download("https://t/x", [], str(tmp_path / "f.bin"), client)


def test_download_url():
    assert download_url("https://t.sharepoint.com/sites/X/", "u1") == (
        "https://t.sharepoint.com/sites/X/_layouts/15/download.aspx?UniqueId=u1"
    )
