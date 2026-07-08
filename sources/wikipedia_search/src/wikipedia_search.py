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

import json
import logging
import sys
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
        except (json.JSONDecodeError, ValueError) as exc:
            # A 200 with a non-JSON / malformed body reaches here via .json().
            logger.warning("Wikipedia response could not be parsed: %s", exc)
            return "Wikipedia search failed: Wikipedia returned a malformed response."

        return self.format_results(self._parse(data))

    def _parse(self, data: Any) -> list[dict[str, Any]]:
        """Extract normalized article dicts from a MediaWiki query response.

        Defensive against unexpected shapes: any level that is not the expected
        dict yields no articles rather than raising.
        """
        if not isinstance(data, dict):
            return []
        query = data.get("query")
        pages = query.get("pages") if isinstance(query, dict) else None
        if not isinstance(pages, dict):
            return []
        articles = []
        for page in pages.values():
            if not isinstance(page, dict):
                continue
            extract = " ".join((page.get("extract") or "").split())
            if self.max_content_length is not None and len(extract) > self.max_content_length:
                extract = extract[: self.max_content_length].rstrip() + "…"
            articles.append(
                {
                    "title": page.get("title", "Untitled"),
                    "extract": extract,
                    "url": page.get("fullurl") or self._title_url(page.get("title", "")),
                    # Missing ranks sort last (MediaWiki search 'index' is 1-based).
                    "index": page.get("index", sys.maxsize),
                }
            )
        # MediaWiki returns pages keyed by id; 'index' preserves search rank.
        articles.sort(key=lambda a: a["index"])
        return articles

    def _title_url(self, title: str) -> str:
        """Build a canonical article URL from a page title, honoring api_url.

        Derives the wiki base from the configured MediaWiki endpoint so the
        fallback URL is correct for non-English / self-hosted wikis too.
        """
        if not title:
            return ""
        base = self.api_url.split("/w/api.php")[0].rstrip("/")
        return f"{base}/wiki/" + quote(title.replace(" ", "_"))

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
