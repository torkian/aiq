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

"""Wikipedia search tool.

Queries the public MediaWiki API (https://en.wikipedia.org/w/api.php). No API
key is required. Uses a single ``list=search`` + ``prop=extracts`` query to
return page titles, plain-text intro extracts, and canonical URLs. Network and
parse failures degrade to a readable error string rather than raising.
"""

import logging
from typing import Any
from urllib.parse import quote

import aiohttp

logger = logging.getLogger(__name__)

_USER_AGENT = "nvidia-aiq-blueprint/wikipedia_search (https://github.com/NVIDIA-AI-Blueprints/aiq)"


class WikipediaSearchTool:
    """Async client that searches Wikipedia and formats results for an agent."""

    def __init__(
        self,
        api_url: str = "https://en.wikipedia.org/w/api.php",
        timeout: int = 30,
        max_results: int = 5,
        max_content_length: int | None = 1000,
    ) -> None:
        """Configure the search client.

        Args:
            api_url: MediaWiki API endpoint (override for other language wikis).
            timeout: Per-request timeout in seconds.
            max_results: Maximum number of articles to return.
            max_content_length: If set, truncate each extract to this many
                characters to reduce token usage.
        """
        self.api_url = api_url
        self.timeout = timeout
        self.max_results = max_results
        self.max_content_length = max_content_length

    async def search(self, query: str) -> str:
        """Search Wikipedia for articles matching ``query``.

        Returns a formatted string of results, or a readable error message.
        """
        if not query or not query.strip():
            return "Error: 'query' argument is required"

        params = {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": query,
            "gsrlimit": str(self.max_results),
            "prop": "extracts|info",
            "exintro": "1",
            "explaintext": "1",
            "inprop": "url",
            "redirects": "1",
        }

        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            async with (
                aiohttp.ClientSession(timeout=timeout, headers={"User-Agent": _USER_AGENT}) as session,
                session.get(self.api_url, params=params) as response,
            ):
                if response.status != 200:
                    logger.warning("Wikipedia search returned HTTP %s", response.status)
                    return f"Wikipedia search failed: returned HTTP {response.status}."
                data = await response.json()
        except TimeoutError:
            return f"Wikipedia search failed: timed out after {self.timeout}s. Try again or narrow the query."
        except aiohttp.ClientError as exc:
            logger.warning("Wikipedia search request failed: %s", exc)
            return "Wikipedia search failed: unable to reach Wikipedia."

        return self.format_results(self._parse(data))

    def _parse(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract normalized article dicts from a MediaWiki query response."""
        pages = ((data or {}).get("query") or {}).get("pages") or {}
        articles = []
        for page in pages.values():
            extract = " ".join((page.get("extract") or "").split())
            if self.max_content_length is not None and len(extract) > self.max_content_length:
                extract = extract[: self.max_content_length].rstrip() + "…"
            articles.append(
                {
                    "title": page.get("title", "Untitled"),
                    "extract": extract,
                    "url": page.get("fullurl") or self._title_url(page.get("title", "")),
                    "index": page.get("index", 0),
                }
            )
        # MediaWiki returns pages keyed by id; 'index' preserves search rank.
        articles.sort(key=lambda a: a["index"])
        return articles

    @staticmethod
    def _title_url(title: str) -> str:
        """Build a canonical Wikipedia URL from a page title."""
        if not title:
            return ""
        return "https://en.wikipedia.org/wiki/" + quote(title.replace(" ", "_"))

    @staticmethod
    def format_results(articles: list[dict[str, Any]]) -> str:
        """Format normalized Wikipedia results into a numbered, citable string."""
        if not articles:
            return "No Wikipedia articles found."

        formatted = []
        for i, article in enumerate(articles, 1):
            formatted.append(
                f"{i}. **{article.get('title', 'Untitled')}**\n"
                f"   - **Summary**: {article.get('extract', '')}\n"
                f"   - **Link**: {article.get('url', '')}"
            )
        return "\n\n".join(formatted)
