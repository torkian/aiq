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

"""Client for the PatentsView PatentSearch API.

PatentsView (https://search.patentsview.org) is the USPTO-funded public patent
search service. It requires a free API key
(https://patentsview.org/apis/keyrequest) supplied via the ``X-Api-Key`` header.

The request/response mapping here follows the documented PatentSearch v1 API.
The client is separated from the NAT registration so it can be tested in
isolation; all network access is mocked in the test suite.
"""

import json
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_BASE_URL = "https://search.patentsview.org/api/v1/patent/"
_FIELDS = ["patent_id", "patent_title", "patent_abstract", "patent_date"]


class PatentSearchClient:
    """Async client for searching patents via the PatentsView API."""

    def __init__(self, api_key: str, timeout: int = 30, max_results: int = 10):
        """Configure the client.

        Args:
            api_key: PatentsView API key (sent as the ``X-Api-Key`` header).
            timeout: Per-request timeout in seconds.
            max_results: Maximum number of patents to return.
        """
        self.api_key = api_key
        self.timeout = timeout
        self.max_results = max_results

    def _build_params(self, query: str, year: str | None) -> dict[str, str]:
        """Build the PatentsView query params (JSON-encoded per the API spec)."""
        criteria: list[dict[str, Any]] = [{"_text_any": {"patent_title": query}}]
        if year:
            criteria.append({"_gte": {"patent_date": f"{year}-01-01"}})
            criteria.append({"_lte": {"patent_date": f"{year}-12-31"}})
        q: dict[str, Any] = {"_and": criteria} if len(criteria) > 1 else criteria[0]
        return {
            "q": json.dumps(q),
            "f": json.dumps(_FIELDS),
            "o": json.dumps({"size": self.max_results}),
        }

    async def search(self, query: str, year: str | None = None) -> str:
        """Search for patents matching ``query``.

        Args:
            query: The search query describing the invention or technology.
            year: Optional grant-year filter (e.g., "2024").

        Returns:
            Formatted patent results, or a readable error string. Never raises
            on network/HTTP/parse failure so a transient outage cannot crash a
            research run.
        """
        if not query or not query.strip():
            return "Error: 'query' argument is required"

        params = self._build_params(query, year)
        headers = {"X-Api-Key": self.api_key, "Accept": "application/json"}

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(_BASE_URL, params=params, headers=headers)
                response.raise_for_status()
                data = response.json()
        except httpx.TimeoutException:
            return f"Patent search failed: timed out after {self.timeout}s. Try again or narrow the query."
        except httpx.HTTPStatusError as exc:
            logger.warning("Patent search returned HTTP %s", exc.response.status_code)
            return f"Patent search failed: PatentsView returned HTTP {exc.response.status_code}."
        except httpx.HTTPError as exc:
            logger.warning("Patent search request failed: %s", exc)
            return "Patent search failed: unable to reach PatentsView."
        except json.JSONDecodeError:
            return "Patent search failed: PatentsView returned a malformed response."

        # Guard against an unexpected JSON shape (e.g. a top-level list) before
        # treating the payload as the documented {"patents": [...]} object.
        if not isinstance(data, dict):
            return "Patent search failed: PatentsView returned a malformed response."
        patents = data.get("patents")
        if not isinstance(patents, list):
            patents = []
        return self.format_results(patents, query)

    @staticmethod
    def format_results(patents: list[dict[str, Any]], query: str) -> str:
        """Format PatentsView results into a numbered, citable string."""
        # Skip any non-dict entries defensively (unexpected item shapes).
        patents = [p for p in patents if isinstance(p, dict)]
        if not patents:
            return f"No patents found for query: {query}"

        results = []
        for i, patent in enumerate(patents, 1):
            patent_id = patent.get("patent_id", "")
            title = patent.get("patent_title", "Untitled")
            abstract = (patent.get("patent_abstract") or "").strip()
            date = patent.get("patent_date", "")
            url = f"https://patents.google.com/patent/US{patent_id}" if patent_id else ""
            results.append(
                f"{i}. **{title}** ({patent_id})\n"
                f"   - **Granted**: {date}\n"
                f"   - **Abstract**: {abstract}\n"
                f"   - **Link**: {url}"
            )
        return "\n\n".join(results)
