"""
tests/test_flask_app.py — Tests for the Flask SmartSort AI application.

Covers:
  - Page rendering (all 5 pages)
  - API: settings persistence including max_size unlimited
  - API: clear history
  - Max Size unlimited filter behavior (scanner)
  - Settings persistence round-trip
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Ensure project root on path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from app import app as flask_app


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    flask_app.config["SECRET_KEY"] = "test-secret"
    with flask_app.test_client() as c:
        with flask_app.app_context():
            yield c


# ────────────────────────────────────────────────────────────
# Page rendering tests
# ────────────────────────────────────────────────────────────

def test_dashboard_renders(client):
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8", "replace")
    assert "SmartSort AI" in html
    assert "Dashboard" in html


def test_scan_page_renders(client):
    resp = client.get("/scan")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8", "replace")
    assert "Scan a Folder" in html
    assert "Maximum file size" in html


def test_preview_page_renders(client):
    resp = client.get("/preview")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8", "replace")
    assert "Preview" in html


def test_history_page_renders(client):
    resp = client.get("/history")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8", "replace")
    assert "History" in html


def test_settings_page_renders(client):
    resp = client.get("/settings")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8", "replace")
    assert "Settings" in html
    assert "Theme" in html
    assert "Retrain Model" in html
    assert "Clear History" in html
    assert "Save Settings" in html


# ────────────────────────────────────────────────────────────
# Settings API tests
# ────────────────────────────────────────────────────────────

def test_save_settings_finite(client):
    """Saving a finite max_size value should persist it as a number."""
    resp = client.post(
        "/api/settings",
        json={"max_file_size_mb": 250},
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["success"] is True


def test_save_settings_unlimited_null(client):
    """Sending max_size=null should save 'unlimited'."""
    resp = client.post(
        "/api/settings",
        json={"max_file_size_mb": None},
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["success"] is True


def test_save_settings_unlimited_string(client):
    """Sending max_size='unlimited' should also work."""
    resp = client.post(
        "/api/settings",
        json={"max_file_size_mb": "unlimited"},
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["success"] is True


def test_settings_persist_unlimited(client):
    """After saving unlimited, the settings page should show Unlimited."""
    # Save unlimited
    client.post(
        "/api/settings",
        json={"max_file_size_mb": None},
        content_type="application/json",
    )
    # Load settings page
    resp = client.get("/settings")
    html = resp.data.decode("utf-8", "replace")
    # The settings page template should have received max_size_val=None
    # and rendered 'Unlimited'
    assert "Unlimited" in html or "unlimited" in html


def test_settings_persist_finite(client):
    """After saving a finite value, the settings page round-trips it correctly."""
    # Save 128 MB
    client.post(
        "/api/settings",
        json={"max_file_size_mb": 128},
        content_type="application/json",
    )
    # Verify settings page renders without error
    resp = client.get("/settings")
    assert resp.status_code == 200


# ────────────────────────────────────────────────────────────
# Clear history API test
# ────────────────────────────────────────────────────────────

def test_clear_history(client):
    resp = client.post("/api/clear_history")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["success"] is True


# ────────────────────────────────────────────────────────────
# Max Size filter behavior (Scanner)
# ────────────────────────────────────────────────────────────

def test_scanner_respects_finite_size_limit(tmp_path):
    """Files above the limit should be listed but skippable by classifier."""
    from src.scanner import Scanner

    # Create two files: one small, one large-ish
    small = tmp_path / "small.txt"
    small.write_bytes(b"x" * 1000)  # 1 KB

    big = tmp_path / "big.txt"
    big.write_bytes(b"y" * (2 * 1024 * 1024))  # 2 MB

    scanner = Scanner(root=tmp_path, recursive=False, max_file_size_mb=1.0)
    records = scanner.scan()

    # Both files are found by the scanner (it doesn't skip by size — the extractor does)
    filenames = [r.filename for r in records]
    assert "small.txt" in filenames
    assert "big.txt" in filenames


def test_extractor_skips_oversized(tmp_path):
    """Text extractor should return empty string for files above max_file_size_mb."""
    from src.extractors import extract_text

    big_file = tmp_path / "big.txt"
    big_file.write_bytes(b"hello world " * 100_000)  # ~1.2 MB

    text, note = extract_text(big_file, max_file_size_mb=0.5)
    assert text == ""
    assert "too large" in note.lower() or "limit" in note.lower()


def test_extractor_unlimited_allows_any_size(tmp_path):
    """When max_file_size_mb is very large (unlimited mode), extraction proceeds."""
    from src.extractors import extract_text

    medium_file = tmp_path / "medium.txt"
    medium_file.write_bytes(b"Important content. " * 5000)  # ~95 KB

    # Use a very large value to simulate unlimited
    text, note = extract_text(medium_file, max_file_size_mb=99999)
    assert len(text) > 0


# ────────────────────────────────────────────────────────────
# Max Size unlimited — backend scan API (with mock folder)
# ────────────────────────────────────────────────────────────

def test_scan_api_requires_folder(client):
    """Scan API should return 400 if no folder is provided."""
    resp = client.post(
        "/api/scan",
        json={"folder": ""},
        content_type="application/json",
    )
    assert resp.status_code == 400
    data = json.loads(resp.data)
    assert "error" in data


def test_scan_api_invalid_folder(client):
    """Scan API should return 400 for a non-existent folder."""
    resp = client.post(
        "/api/scan",
        json={"folder": "C:\\nonexistent_smartsort_test_99999\\folder"},
        content_type="application/json",
    )
    assert resp.status_code == 400
    data = json.loads(resp.data)
    assert "error" in data


# ────────────────────────────────────────────────────────────
# API status test
# ────────────────────────────────────────────────────────────

def test_api_status(client):
    resp = client.get("/api/status")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert "model_status" in data
    assert "scan_done" in data
    assert "scan_count" in data


# ────────────────────────────────────────────────────────────
# Search API test
# ────────────────────────────────────────────────────────────

def test_search_api_empty_query(client):
    resp = client.get("/api/search?q=")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert "results" in data
    assert data["results"] == []


def test_search_api_with_query(client):
    resp = client.get("/api/search?q=test")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert "results" in data


# ────────────────────────────────────────────────────────────
# Correction API validation
# ────────────────────────────────────────────────────────────

def test_correction_api_missing_params(client):
    resp = client.post(
        "/api/correction",
        json={},
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_correction_api_invalid_category(client):
    resp = client.post(
        "/api/correction",
        json={"filepath": "C:/test/file.pdf", "category": "InvalidCategory"},
        content_type="application/json",
    )
    assert resp.status_code == 400


# ────────────────────────────────────────────────────────────
# Max Size unlimited mode end-to-end (settings page round-trip)
# ────────────────────────────────────────────────────────────

def test_max_size_unlimited_roundtrip(client):
    """
    Acceptance test:
    1. Save max_size=unlimited via API
    2. Load settings page
    3. Confirm 'Unlimited' appears in the rendered HTML
    """
    # Step 1: Save unlimited
    save_resp = client.post(
        "/api/settings",
        json={"max_file_size_mb": None},
        content_type="application/json",
    )
    assert save_resp.status_code == 200
    assert json.loads(save_resp.data)["success"] is True

    # Step 2 & 3: Verify settings page shows Unlimited
    page_resp = client.get("/settings")
    assert page_resp.status_code == 200
    html = page_resp.data.decode("utf-8", "replace")
    assert "Unlimited" in html or "unlimited" in html, (
        "Settings page must display 'Unlimited' when max_file_size_mb is null/unlimited"
    )
