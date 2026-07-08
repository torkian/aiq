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

"""arXiv paper search tool.

Queries the public arXiv Atom API (https://export.arxiv.org/api/query). No API
key is required, so this tool works out of the box. Network/parse failures
degrade to a readable error string rather than raising, matching the
convention used by the other data-source tools.
"""

import asyncio
import logging
from typing import Any
from urllib.parse import urlencode
from xml.etree import ElementTree

import aiohttp
from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import fromstring as _safe_fromstring

logger = logging.getLogger(__name__)

_ATOM_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}

# arXiv asks callers to identify themselves and to keep request rates modest.
_USER_AGENT = "nvidia-aiq-blueprint/arxiv_paper_search (https://github.com/NVIDIA-AI-Blueprints/aiq)"


class ArxivSearchTool:
    """Async client that searches arXiv and formats results for an agent."""

    BASE_URL = "https://export.arxiv.org/api/query"

    def __init__(self, timeout: int = 30, max_results: int = 10, max_content_length: int | None = None) -> None:
        """Configure the search client.

        Args:
            timeout: Per-request timeout in seconds.
            max_results: Maximum number of papers to return.
            max_content_length: If set, truncate each abstract to this many
                characters to reduce token usage.
        """
        self.timeout = timeout
        self.max_results = max_results
        self.max_content_length = max_content_length

    async def search(self, query: str, max_results: int | None = None) -> str:
        """Search arXiv for papers matching ``query``.

        Args:
            query: The search query string.
            max_results: Optional per-call override of the configured limit.

        Returns:
            A formatted string of results, or a readable error message.
        """
        if not query or not query.strip():
            return "Error: 'query' argument is required"

        limit = max_results or self.max_results
        params = {
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": limit,
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
        url = f"{self.BASE_URL}?{urlencode(params)}"

        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            async with (
                aiohttp.ClientSession(timeout=timeout, headers={"User-Agent": _USER_AGENT}) as session,
                session.get(url) as response,
            ):
                if response.status != 200:
                    logger.warning("arXiv search returned HTTP %s", response.status)
                    return f"Paper search failed: arXiv returned HTTP {response.status}."
                body = await response.text()
        except TimeoutError:
            # Prefixed "Paper search failed" so _search_with_retries retries it.
            return f"Paper search failed: timed out after {self.timeout}s. Try again or narrow the query."
        except aiohttp.ClientError as exc:
            logger.warning("arXiv search request failed: %s", exc)
            return "Paper search failed: unable to reach arXiv."

        try:
            results = self._parse(body)
        except (ElementTree.ParseError, DefusedXmlException) as exc:
            logger.warning("arXiv response could not be parsed: %s", exc)
            return "Paper search failed: arXiv returned a malformed response."

        return self.format_results(results)

    @staticmethod
    def _text(node: ElementTree.Element | None) -> str:
        """Return stripped text for a node, or empty string when absent."""
        if node is None or node.text is None:
            return ""
        return node.text.strip()

    def _parse(self, xml_text: str) -> list[dict[str, Any]]:
        """Parse an arXiv Atom feed into a list of normalized paper dicts.

        Uses defusedxml to guard against XXE / entity-expansion attacks even
        though arXiv is a trusted source (defense in depth).
        """
        root = _safe_fromstring(xml_text)
        papers: list[dict[str, Any]] = []
        for entry in root.findall("atom:entry", _ATOM_NS):
            authors = [self._text(a.find("atom:name", _ATOM_NS)) for a in entry.findall("atom:author", _ATOM_NS)]
            published = self._text(entry.find("atom:published", _ATOM_NS))
            summary = " ".join(self._text(entry.find("atom:summary", _ATOM_NS)).split())
            if self.max_content_length is not None and len(summary) > self.max_content_length:
                summary = summary[: self.max_content_length].rstrip() + "…"
            papers.append(
                {
                    "title": " ".join(self._text(entry.find("atom:title", _ATOM_NS)).split()),
                    "authors": [a for a in authors if a],
                    "year": published[:4] if published else "",
                    "summary": summary,
                    "link": self._text(entry.find("atom:id", _ATOM_NS)),
                }
            )
        return papers

    @staticmethod
    def format_results(results: list[dict[str, Any]]) -> str:
        """Format normalized arXiv results into a numbered, citable string."""
        if not results:
            return "No papers found on arXiv."

        formatted = []
        for i, paper in enumerate(results, 1):
            authors = paper.get("authors") or []
            author_str = ", ".join(authors[:3]) + (" et al." if len(authors) > 3 else "")
            formatted.append(
                f"{i}. **{paper.get('title', 'Unknown Title')}** ({paper.get('year') or 'n.d.'})\n"
                f"   - **Authors**: {author_str or 'Unknown'}\n"
                f"   - **Abstract**: {paper.get('summary', '')}\n"
                f"   - **Link**: {paper.get('link', '')}"
            )
        return "\n\n".join(formatted)


async def _search_with_retries(tool: ArxivSearchTool, query: str, max_retries: int) -> str:
    """Call ``tool.search`` with simple linear backoff on transient failures."""
    attempt = 0
    while True:
        result = await tool.search(query)
        if not result.startswith("Paper search failed") or attempt >= max_retries:
            return result
        attempt += 1
        await asyncio.sleep(attempt)
