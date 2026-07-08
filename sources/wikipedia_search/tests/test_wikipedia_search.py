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

"""Tests for the Wikipedia search tool. All HTTP is mocked — no live network."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from wikipedia_search.wikipedia_search import WikipediaSearchTool

_RESPONSE = {
    "query": {
        "pages": {
            "12345": {
                "title": "Transformer (deep learning architecture)",
                "extract": "A transformer is a deep learning architecture based on attention.",
                "fullurl": "https://en.wikipedia.org/wiki/Transformer_(deep_learning_architecture)",
                "index": 1,
            },
            "67890": {
                "title": "Attention (machine learning)",
                "extract": "Attention is a technique in machine learning.",
                "fullurl": "https://en.wikipedia.org/wiki/Attention_(machine_learning)",
                "index": 2,
            },
        }
    }
}


class _FakeResponse:
    def __init__(self, status: int, payload):
        self.status = status
        self._payload = payload

    async def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, response=None, exc=None):
        self._response = response
        self._exc = exc
        self.requested_params = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def get(self, url, params=None):
        session = self
        session.requested_params = params

        @asynccontextmanager
        async def _cm():
            if session._exc is not None:
                raise session._exc
            yield session._response

        return _cm()


def _patch_session(session=None, **kwargs):
    fake = session if session is not None else _FakeSession(**kwargs)
    return patch("wikipedia_search.wikipedia_search.aiohttp.ClientSession", return_value=fake)


@pytest.mark.asyncio
async def test_search_formats_results_in_rank_order():
    """Results are formatted and ordered by the search 'index' rank."""
    tool = WikipediaSearchTool()
    with _patch_session(response=_FakeResponse(200, _RESPONSE)):
        out = await tool.search("transformers")
    assert out.index("1. **Transformer") < out.index("2. **Attention")
    assert "en.wikipedia.org/wiki/Transformer" in out


@pytest.mark.asyncio
async def test_query_sends_search_generator_params():
    """The request uses the MediaWiki search generator with the query."""
    session = _FakeSession(response=_FakeResponse(200, {"query": {"pages": {}}}))
    tool = WikipediaSearchTool(max_results=3)
    with _patch_session(session=session):
        await tool.search("neural networks")
    params = session.requested_params
    assert params["generator"] == "search"
    assert params["gsrsearch"] == "neural networks"
    assert params["gsrlimit"] == "3"
    assert params["explaintext"] == "1"


@pytest.mark.asyncio
async def test_empty_query_rejected():
    """A blank query short-circuits before any network call."""
    tool = WikipediaSearchTool()
    assert await tool.search("  ") == "Error: 'query' argument is required"


@pytest.mark.asyncio
async def test_no_results_message():
    """An empty page set yields a friendly message."""
    tool = WikipediaSearchTool()
    with _patch_session(response=_FakeResponse(200, {"query": {"pages": {}}})):
        assert await tool.search("zzz") == "No Wikipedia articles found."


@pytest.mark.asyncio
async def test_missing_query_key_is_handled():
    """A response with no 'query' key (e.g. zero hits) is handled gracefully."""
    tool = WikipediaSearchTool()
    with _patch_session(response=_FakeResponse(200, {})):
        assert await tool.search("zzz") == "No Wikipedia articles found."


@pytest.mark.asyncio
async def test_http_error_degrades_gracefully():
    """A non-200 response returns an error string, not an exception."""
    tool = WikipediaSearchTool()
    with _patch_session(response=_FakeResponse(500, None)):
        out = await tool.search("q")
    assert out == "Wikipedia search failed: returned HTTP 500."


@pytest.mark.asyncio
async def test_timeout_degrades_gracefully():
    """A timeout is reported, not raised."""
    tool = WikipediaSearchTool(timeout=8)
    with _patch_session(exc=TimeoutError()):
        out = await tool.search("q")
    assert "timed out after 8s" in out


@pytest.mark.asyncio
async def test_extract_truncation():
    """max_content_length truncates long extracts with an ellipsis."""
    tool = WikipediaSearchTool(max_content_length=15)
    with _patch_session(response=_FakeResponse(200, _RESPONSE)):
        out = await tool.search("q")
    assert "…" in out


@pytest.mark.asyncio
async def test_url_falls_back_to_title_when_missing():
    """When fullurl is absent, a canonical URL is derived from the title."""
    payload = {"query": {"pages": {"1": {"title": "Alan Turing", "extract": "x", "index": 1}}}}
    tool = WikipediaSearchTool()
    with _patch_session(response=_FakeResponse(200, payload)):
        out = await tool.search("q")
    assert "en.wikipedia.org/wiki/Alan_Turing" in out
