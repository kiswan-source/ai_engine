"""Integration tests for api/routes/files.py (Tahap 25).

Closes the gap Tahap 24 found and confirmed live while verifying
`/api/v1/chat/download`'s new ownership check: this router served the
*same* reports/uploads directories with zero authentication, a working
bypass. Also covers the path-traversal fix (`os.path.basename()` was
missing entirely before this Tahap).

`REPORTS_DIR`/`UPLOADS_DIR` are plain module globals read directly inside
each route function (not imported elsewhere via `from X import Y`), so
monkeypatching `api.routes.files.REPORTS_DIR`/`UPLOADS_DIR` is enough to
isolate these tests from the real `~/ai_engine/{reports,uploads}`.
"""
import os

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture(autouse=True)
def _api_keys(monkeypatch):
    monkeypatch.setattr("api.config.settings.API_KEYS", "goodkey:user")


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    reports = tmp_path / "reports"
    uploads = tmp_path / "uploads"
    reports.mkdir()
    uploads.mkdir()
    monkeypatch.setattr("api.routes.files.REPORTS_DIR", str(reports))
    monkeypatch.setattr("api.routes.files.UPLOADS_DIR", str(uploads))
    return reports, uploads


@pytest.fixture
async def app():
    from api.main import app as _app

    yield _app


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _as(key: str) -> dict:
    return {"X-API-Key": key}


# ─── authentication ─────────────────────────────────────────────────────

async def test_list_reports_requires_auth(client, dirs):
    res = await client.get("/reports")
    assert res.status_code == 401


async def test_list_reports_with_valid_key(client, dirs):
    reports, _ = dirs
    (reports / "a.pdf").write_bytes(b"x")
    res = await client.get("/reports", headers=_as("goodkey"))
    assert res.status_code == 200
    assert res.json()["count"] == 1


async def test_download_report_requires_auth(client, dirs):
    reports, _ = dirs
    (reports / "a.pdf").write_bytes(b"x")
    res = await client.get("/reports/a.pdf")
    assert res.status_code == 401


async def test_download_report_with_valid_key(client, dirs):
    reports, _ = dirs
    (reports / "a.pdf").write_bytes(b"hello")
    res = await client.get("/reports/a.pdf", headers=_as("goodkey"))
    assert res.status_code == 200
    assert res.content == b"hello"


async def test_list_uploads_requires_auth(client, dirs):
    res = await client.get("/uploads")
    assert res.status_code == 401


async def test_upload_requires_auth(client, dirs):
    res = await client.post("/upload", files={"file": ("a.txt", b"hi", "text/plain")})
    assert res.status_code == 401


async def test_upload_with_valid_key(client, dirs):
    _, uploads = dirs
    res = await client.post(
        "/upload", files={"file": ("a.txt", b"hi", "text/plain")}, headers=_as("goodkey")
    )
    assert res.status_code == 200
    assert (uploads / "a.txt").read_bytes() == b"hi"


async def test_no_api_keys_configured_behaves_as_before(client, dirs, monkeypatch):
    monkeypatch.setattr("api.config.settings.API_KEYS", "")
    reports, _ = dirs
    (reports / "a.pdf").write_bytes(b"x")

    res = await client.get("/reports")
    assert res.status_code == 200
    res2 = await client.get("/reports/a.pdf")
    assert res2.status_code == 200


# ─── path traversal (Tahap 25 fix) ──────────────────────────────────────

async def test_download_report_basename_sanitized(dirs, monkeypatch):
    """Direct unit-level call to the handler (bypassing HTTP/ASGI routing —
    a request for `/reports/..%2Fsecret.txt` actually gets normalized by
    routing before it ever reaches this handler and falls through to the
    SPA catch-all, serving index.html rather than proving anything about
    this function's own sanitization). Confirms the real defense:
    `os.path.basename()` strips any `../` a caller-supplied string carries,
    regardless of how that string arrived."""
    from fastapi import HTTPException

    from api.routes.files import download_report
    from security.auth import Principal

    reports, _ = dirs
    outside = reports.parent / "secret.txt"
    outside.write_text("top secret")

    with pytest.raises(HTTPException) as exc_info:
        await download_report("../secret.txt", Principal(api_key="goodkey", role="user"))
    assert exc_info.value.status_code == 404


async def test_reports_traversal_via_http_never_leaks_secret_content(client, dirs):
    """Documents the actual observed HTTP-level behavior honestly: the ASGI
    router normalizes `..` out of the path before this app's own routing
    sees it, so the request never reaches `download_report` at all and
    falls through to the SPA catch-all (200, index.html) — not a 404 from
    this handler. The one invariant that actually matters either way: the
    secret file's content must never appear in the response."""
    outside = dirs[0].parent / "secret.txt"
    outside.write_text("top secret")

    res = await client.get("/reports/..%2Fsecret.txt", headers=_as("goodkey"))
    assert "top secret" not in res.text


async def test_upload_filename_sanitized_against_traversal(client, dirs):
    _, uploads = dirs
    res = await client.post(
        "/upload",
        files={"file": ("../../evil.txt", b"payload", "text/plain")},
        headers=_as("goodkey"),
    )
    # Whatever status, the file must never land outside uploads/.
    assert not (uploads.parent.parent / "evil.txt").exists()
    if res.status_code == 200:
        assert res.json()["filename"] == "evil.txt"
        assert (uploads / "evil.txt").exists()
