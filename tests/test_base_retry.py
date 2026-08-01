"""
Tests for base.py's retry behavior — added alongside the fix for a real
incident (2026-08-02): a single connection timeout to kinopilotu.cz during
one scheduled run silently dropped that cinema from the app for the whole
day. These mock requests.get directly (no fixture site involved, and no new
dependency beyond the stdlib) and stub out time.sleep so the "retries
exhaust" cases don't actually wait out the real backoff.

Run them with:   python -m pytest tests -v
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from scrapers.base import RETRY_ATTEMPTS, fetch, fetch_json


def _response(status=200, text="", json_body=None):
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status
    resp.text = text
    resp.encoding = "utf-8"
    resp.apparent_encoding = "utf-8"
    resp.json.return_value = json_body
    if status >= 400:
        error = requests.HTTPError(response=resp)
        resp.raise_for_status.side_effect = error
    else:
        resp.raise_for_status.side_effect = None
    return resp


@patch("scrapers.base.time.sleep")
@patch("scrapers.base.requests.get")
def test_succeeds_on_the_first_try_without_retrying(mock_get, mock_sleep):
    mock_get.return_value = _response(200, text="<html>ok</html>")
    assert fetch("https://example.test/") == "<html>ok</html>"
    assert mock_get.call_count == 1
    mock_sleep.assert_not_called()


@patch("scrapers.base.time.sleep")
@patch("scrapers.base.requests.get")
def test_recovers_after_a_transient_connection_error(mock_get, mock_sleep):
    """The exact shape of the real incident: fails once, then works."""
    mock_get.side_effect = [
        requests.ConnectionError("timed out"),
        _response(200, text="<html>recovered</html>"),
    ]
    assert fetch("https://example.test/") == "<html>recovered</html>"
    assert mock_get.call_count == 2
    mock_sleep.assert_called_once()  # waited before the 2nd attempt, not after


@patch("scrapers.base.time.sleep")
@patch("scrapers.base.requests.get")
def test_gives_up_after_exhausting_every_attempt(mock_get, mock_sleep):
    mock_get.side_effect = requests.ConnectionError("still down")
    with pytest.raises(requests.ConnectionError):
        fetch("https://example.test/")
    assert mock_get.call_count == RETRY_ATTEMPTS
    assert mock_sleep.call_count == RETRY_ATTEMPTS - 1  # never sleeps after the last failure


@patch("scrapers.base.time.sleep")
@patch("scrapers.base.requests.get")
def test_retries_a_5xx_the_same_as_a_connection_error(mock_get, mock_sleep):
    mock_get.side_effect = [_response(503), _response(200, text="ok")]
    assert fetch("https://example.test/") == "ok"
    assert mock_get.call_count == 2


@patch("scrapers.base.time.sleep")
@patch("scrapers.base.requests.get")
def test_a_4xx_raises_immediately_without_retrying(mock_get, mock_sleep):
    """A 404/403/etc. means the request itself is wrong — retrying it three
    times would just fail the same way three times, slower."""
    mock_get.return_value = _response(404)
    with pytest.raises(requests.HTTPError):
        fetch("https://example.test/")
    assert mock_get.call_count == 1
    mock_sleep.assert_not_called()


@patch("scrapers.base.time.sleep")
@patch("scrapers.base.requests.get")
def test_fetch_json_also_retries(mock_get, mock_sleep):
    mock_get.side_effect = [
        requests.Timeout("slow"),
        _response(200, json_body={"ok": True}),
    ]
    assert fetch_json("https://example.test/api") == {"ok": True}
    assert mock_get.call_count == 2
