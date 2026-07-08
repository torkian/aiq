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

"""Tests for the arXiv paper search tool. All HTTP is mocked — no live network."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from arxiv_paper_search.arxiv_search import ArxivSearchTool
from arxiv_paper_search.arxiv_search import _search_with_retries

_ATOM_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>https://arxiv.org/abs/1706.03762</id>
    <title>Attention Is All You Need</title>
    <published>2017-06-12T17:57:34Z</published>
    <summary>The dominant sequence transduction models are based on complex
    recurrent or convolutional neural networks.</summary>
    <author><name>Ashish Vaswani</name></author>
    <author><name>Noam Shazeer</name></author>
    <author><name>Niki Parmar</name></author>
    <author><name>Jakob Uszkoreit</name></author>
  </entry>
</feed>"""

_EMPTY_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"></feed>"""


class _FakeResponse:
    def __init__(self, status: int, body: str):
        self.status = status
        self._body = body

    async def text(self) -> str:
        return self._body


class _FakeSession:
    """Minimal aiohttp.ClientSession stand-in yielding a canned response."""

    def __init__(self, response=None, exc=None):
        self._response = response
        self._exc = exc
        self.requested_url: str | None = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def get(self, url):
        session = self
        session.requested_url = url

        @asynccontextmanager
        async def _cm():
            if session._exc is not None:
                raise session._exc
            yield session._response

        return _cm()


def _patch_session(session: _FakeSession | None = None, **kwargs):
    """Patch aiohttp.ClientSession in the tool module with a fake session."""
    fake = session if session is not None else _FakeSession(**kwargs)
    return patch(
        "arxiv_paper_search.arxiv_search.aiohttp.ClientSession",
        return_value=fake,
    )


@pytest.mark.asyncio
async def test_request_targets_the_arxiv_api_contract():
    """The tool must call the arXiv API endpoint with the documented params."""
    from urllib.parse import parse_qs
    from urllib.parse import urlparse

    session = _FakeSession(response=_FakeResponse(200, _EMPTY_FEED))
    tool = ArxivSearchTool(max_results=7)
    with _patch_session(session=session):
        await tool.search("graph neural networks")

    parsed = urlparse(session.requested_url)
    assert parsed.scheme == "https"
    assert parsed.netloc == "export.arxiv.org"
    assert parsed.path == "/api/query"
    params = parse_qs(parsed.query)
    assert params["search_query"] == ["all:graph neural networks"]
    assert params["max_results"] == ["7"]
    assert params["sortBy"] == ["relevance"]


@pytest.mark.asyncio
async def test_search_parses_and_formats_results():
    """A well-formed Atom feed yields a numbered, citable summary."""
    tool = ArxivSearchTool()
    with _patch_session(response=_FakeResponse(200, _ATOM_FEED)):
        out = await tool.search("transformers")
    assert "1. **Attention Is All You Need** (2017)" in out
    assert "Ashish Vaswani, Noam Shazeer, Niki Parmar et al." in out  # 4th author -> "et al."
    assert "https://arxiv.org/abs/1706.03762" in out


@pytest.mark.asyncio
async def test_empty_query_is_rejected():
    """A blank query short-circuits before any network call."""
    tool = ArxivSearchTool()
    assert await tool.search("   ") == "Error: 'query' argument is required"


@pytest.mark.asyncio
async def test_no_results_message():
    """An empty feed produces a friendly no-results message."""
    tool = ArxivSearchTool()
    with _patch_session(response=_FakeResponse(200, _EMPTY_FEED)):
        assert await tool.search("nonexistent") == "No papers found on arXiv."


@pytest.mark.asyncio
async def test_http_error_degrades_gracefully():
    """A non-200 response returns an error string, not an exception."""
    tool = ArxivSearchTool()
    with _patch_session(response=_FakeResponse(503, "")):
        out = await tool.search("q")
    assert out == "Paper search failed: arXiv returned HTTP 503."


@pytest.mark.asyncio
async def test_timeout_degrades_gracefully():
    """A timeout is reported, not raised."""
    tool = ArxivSearchTool(timeout=5)
    with _patch_session(exc=TimeoutError()):
        out = await tool.search("q")
    assert "timed out after 5s" in out


@pytest.mark.asyncio
async def test_malformed_xml_degrades_gracefully():
    """A malformed body returns the parse-error message."""
    tool = ArxivSearchTool()
    with _patch_session(response=_FakeResponse(200, "<not-valid-xml")):
        out = await tool.search("q")
    assert out == "Paper search failed: arXiv returned a malformed response."


@pytest.mark.asyncio
async def test_abstract_truncation():
    """max_content_length truncates long abstracts with an ellipsis."""
    tool = ArxivSearchTool(max_content_length=20)
    with _patch_session(response=_FakeResponse(200, _ATOM_FEED)):
        out = await tool.search("q")
    assert "…" in out


@pytest.mark.asyncio
async def test_retry_recovers_after_transient_failure():
    """_search_with_retries retries a transient failure then succeeds."""
    tool = ArxivSearchTool()
    calls = {"n": 0}

    async def fake_search(query):
        calls["n"] += 1
        if calls["n"] == 1:
            return "Paper search failed: unable to reach arXiv."
        return "1. **Paper** (2020)"

    with patch.object(tool, "search", side_effect=fake_search), patch("arxiv_paper_search.arxiv_search.asyncio.sleep"):
        out = await _search_with_retries(tool, "q", max_retries=2)
    assert calls["n"] == 2
    assert out.startswith("1. **Paper**")


@pytest.mark.asyncio
async def test_non_transient_failure_is_not_retried():
    """A malformed-response / HTTP error is not retried (won't fix itself)."""
    tool = ArxivSearchTool()
    calls = {"n": 0}

    async def fake_search(query):
        calls["n"] += 1
        return "Paper search failed: arXiv returned a malformed response."

    with patch.object(tool, "search", side_effect=fake_search), patch("arxiv_paper_search.arxiv_search.asyncio.sleep"):
        out = await _search_with_retries(tool, "q", max_retries=3)
    assert calls["n"] == 1  # no retries for a non-transient failure
    assert "malformed" in out
