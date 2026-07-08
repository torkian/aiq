# SPDX-FileCopyrightText: Copyright (c) 2025-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for the patent search tool. All HTTP is mocked — no live network."""

from __future__ import annotations

import json
from unittest.mock import patch

import httpx
import pytest
from patent_search.search import PatentSearchClient

_RESPONSE = {
    "error": False,
    "count": 1,
    "patents": [
        {
            "patent_id": "10000000",
            "patent_title": "System and method for widget optimization",
            "patent_abstract": "A method for optimizing widgets using a neural network.",
            "patent_date": "2018-06-19",
        }
    ],
}


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, raise_status=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self._raise_status = raise_status

    def raise_for_status(self):
        if self._raise_status is not None:
            raise self._raise_status

    def json(self):
        return self._payload


class _FakeAsyncClient:
    """Minimal httpx.AsyncClient stand-in capturing the request."""

    last_call: dict = {}

    def __init__(self, response=None, exc=None, **kwargs):
        self._response = response
        self._exc = exc
        _FakeAsyncClient.last_call = {}  # reset shared capture between tests

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, params=None, headers=None):
        _FakeAsyncClient.last_call = {"url": url, "params": params, "headers": headers}
        if self._exc is not None:
            raise self._exc
        return self._response


def _patch_client(**kwargs):
    """Patch httpx.AsyncClient to yield our fake regardless of constructor args."""

    def _ctor(*_a, **_kw):
        return _FakeAsyncClient(**kwargs)

    return patch("patent_search.search.httpx.AsyncClient", side_effect=_ctor)


@pytest.mark.asyncio
async def test_search_formats_results_and_sends_api_key():
    """A well-formed response is formatted and the API key header is sent."""
    client = PatentSearchClient(api_key="secret-key", max_results=5)
    with _patch_client(response=_FakeResponse(payload=_RESPONSE)):
        out = await client.search("widget optimization")
    assert "1. **System and method for widget optimization** (10000000)" in out
    assert "2018-06-19" in out
    assert "patents.google.com/patent/US10000000" in out
    assert _FakeAsyncClient.last_call["headers"]["X-Api-Key"] == "secret-key"


@pytest.mark.asyncio
async def test_query_params_follow_patentsview_contract():
    """The q/f/o params are JSON-encoded per the PatentsView API."""
    client = PatentSearchClient(api_key="k", max_results=3)
    with _patch_client(response=_FakeResponse(payload=_RESPONSE)):
        await client.search("neural network", year="2020")
    params = _FakeAsyncClient.last_call["params"]
    q = json.loads(params["q"])
    assert "_and" in q  # query + year filters combined
    assert json.loads(params["o"]) == {"size": 3}
    assert "patent_title" in json.loads(params["f"])


@pytest.mark.asyncio
async def test_empty_query_rejected():
    """A blank query short-circuits before any network call."""
    client = PatentSearchClient(api_key="k")
    assert await client.search("  ") == "Error: 'query' argument is required"


@pytest.mark.asyncio
async def test_no_results_message():
    """An empty patents list yields a friendly message."""
    client = PatentSearchClient(api_key="k")
    with _patch_client(response=_FakeResponse(payload={"patents": []})):
        assert await client.search("xyzzy") == "No patents found for query: xyzzy"


@pytest.mark.asyncio
async def test_http_error_degrades_gracefully():
    """An HTTP error status is reported, not raised."""
    err = httpx.HTTPStatusError("bad", request=httpx.Request("GET", "http://x"), response=httpx.Response(429))
    client = PatentSearchClient(api_key="k")
    with _patch_client(response=_FakeResponse(status_code=429, raise_status=err)):
        out = await client.search("q")
    assert out == "Patent search failed: PatentsView returned HTTP 429."


@pytest.mark.asyncio
async def test_timeout_degrades_gracefully():
    """A timeout is reported, not raised."""
    client = PatentSearchClient(api_key="k", timeout=7)
    with _patch_client(exc=httpx.TimeoutException("slow")):
        out = await client.search("q")
    assert "timed out after 7s" in out


@pytest.mark.asyncio
async def test_network_error_degrades_gracefully():
    """A generic transport error is reported, not raised."""
    client = PatentSearchClient(api_key="k")
    with _patch_client(exc=httpx.ConnectError("no route")):
        out = await client.search("q")
    assert out == "Patent search failed: unable to reach PatentsView."


@pytest.mark.asyncio
async def test_malformed_json_degrades_gracefully():
    """A body that isn't valid JSON returns the malformed-response error."""

    class _BadJson(_FakeResponse):
        def json(self):
            raise json.JSONDecodeError("bad", "", 0)

    client = PatentSearchClient(api_key="k")
    with _patch_client(response=_BadJson(200, {})):
        out = await client.search("q")
    assert out == "Patent search failed: PatentsView returned a malformed response."


@pytest.mark.asyncio
async def test_unexpected_json_shape_is_handled():
    """A non-dict payload or non-dict items don't crash; they yield no results."""
    client = PatentSearchClient(api_key="k")
    # Top-level list instead of the documented {"patents": [...]} object.
    with _patch_client(response=_FakeResponse(payload=["unexpected"])):
        assert await client.search("q") == "Patent search failed: PatentsView returned a malformed response."
    # patents present but containing a non-dict entry.
    with _patch_client(response=_FakeResponse(payload={"patents": ["nope"]})):
        assert await client.search("q") == "No patents found for query: q"
