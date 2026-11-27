"""Tests for the SharePoint session probe."""

import httpx
import pytest

from teamsleech.core.config import settings
from teamsleech.services import session_probe as sp

COOKIES = (
    '[{"name": "FedAuth", "value": "x",'
    ' "domain": ".tenant.sharepoint.com"}]'
)


def test_session_host_found():
    assert sp.session_host(COOKIES) == "tenant.sharepoint.com"


def test_session_host_skips_login_and_root_domains():
    raw = (
        '[{"name": "a", "value": "1", "domain": ".login.sharepoint.com"},'
        ' {"name": "b", "value": "2", "domain": ".sharepoint.com"}]'
    )
    assert sp.session_host(raw) is None


def test_session_host_bad_json():
    assert sp.session_host("not json") is None
    assert sp.session_host("") is None
    assert sp.session_host('{"cookies": "nope"}') is None


@pytest.mark.asyncio
async def test_probe_no_cookies(monkeypatch):
    monkeypatch.setattr(settings, "sp_cookies_json", "")
    ok, detail = await sp.probe_sharepoint_session()
    assert ok is False
    assert "no saved cookies" in detail


@pytest.mark.asyncio
async def test_probe_ok(monkeypatch, respx_mock):
    monkeypatch.setattr(settings, "sp_cookies_json", COOKIES)
    respx_mock.get(
        "https://tenant.sharepoint.com/_api/web?$select=Title"
    ).mock(return_value=httpx.Response(200, json={"Title": "t"}))
    ok, detail = await sp.probe_sharepoint_session()
    assert ok is True
    assert detail == "session OK"


@pytest.mark.asyncio
async def test_probe_expired_401(monkeypatch, respx_mock):
    monkeypatch.setattr(settings, "sp_cookies_json", COOKIES)
    respx_mock.get(
        "https://tenant.sharepoint.com/_api/web?$select=Title"
    ).mock(return_value=httpx.Response(401))
    ok, detail = await sp.probe_sharepoint_session()
    assert ok is False
    assert "expired" in detail
    assert "401" in detail


@pytest.mark.asyncio
async def test_probe_expired_redirect_to_login(monkeypatch, respx_mock):
    monkeypatch.setattr(settings, "sp_cookies_json", COOKIES)
    respx_mock.get(
        "https://tenant.sharepoint.com/_api/web?$select=Title"
    ).mock(return_value=httpx.Response(
        302,
        headers={"location": "https://login.microsoftonline.com/x"},
    ))
    ok, detail = await sp.probe_sharepoint_session()
    assert ok is False
    assert "expired" in detail


@pytest.mark.asyncio
async def test_probe_unexpected_status(monkeypatch, respx_mock):
    monkeypatch.setattr(settings, "sp_cookies_json", COOKIES)
    respx_mock.get(
        "https://tenant.sharepoint.com/_api/web?$select=Title"
    ).mock(return_value=httpx.Response(500))
    ok, detail = await sp.probe_sharepoint_session()
    assert ok is False
    assert "unexpected" in detail


@pytest.mark.asyncio
async def test_probe_network_error(monkeypatch, respx_mock):
    monkeypatch.setattr(settings, "sp_cookies_json", COOKIES)
    respx_mock.get(
        "https://tenant.sharepoint.com/_api/web?$select=Title"
    ).mock(side_effect=httpx.ConnectError("boom"))
    ok, detail = await sp.probe_sharepoint_session()
    assert ok is False
    assert "probe failed" in detail
