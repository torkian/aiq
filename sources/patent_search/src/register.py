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

"""NAT register function for the patent search tool (PatentsView).

This realizes the ``patent_search`` example from
``docs/source/extending/adding-a-data-source.md`` as a working data source.
"""

import logging
import os

from pydantic import Field
from pydantic import SecretStr

from nat.builder.builder import Builder
from nat.builder.function_info import FunctionInfo
from nat.cli.register_workflow import register_function
from nat.data_models.function import FunctionBaseConfig

from .search import PatentSearchClient

logger = logging.getLogger(__name__)

_missing_key_warned = False

_SIGNUP_URL = "https://patentsview.org/apis/keyrequest"


class PatentSearchConfig(FunctionBaseConfig, name="patent_search"):
    """Configuration for the patent search data source.

    Searches the PatentsView (USPTO) patent database. Requires a free
    ``PATENT_API_KEY`` (environment variable or config value).
    """

    timeout: int = Field(default=30, description="Timeout in seconds for search requests")
    max_results: int = Field(default=10, description="Maximum number of results to return")
    api_key: SecretStr | None = Field(default=None, description="API key for the PatentsView service")


@register_function(config_type=PatentSearchConfig)
async def patent_search(tool_config: PatentSearchConfig, builder: Builder):
    """Register the patent search data source."""
    if not os.environ.get("PATENT_API_KEY") and tool_config.api_key:
        os.environ["PATENT_API_KEY"] = tool_config.api_key.get_secret_value()

    api_key = os.environ.get("PATENT_API_KEY")

    if not api_key:
        global _missing_key_warned
        if not _missing_key_warned:
            logger.warning(
                "PATENT_API_KEY not found. The patent search tool will be registered but "
                "will return an error when called. Get a free key from %s.",
                _SIGNUP_URL,
            )
            _missing_key_warned = True

        async def _patent_search_stub(query: str, year: str | None = None) -> str:
            """Patent search (unavailable - missing PATENT_API_KEY)."""
            return (
                "Error: Patent search is unavailable because PATENT_API_KEY is not set.\n"
                "To enable this tool:\n"
                f"1. Get a free API key from {_SIGNUP_URL}\n"
                "2. Set PATENT_API_KEY in your environment or .env file\n"
                "3. Restart the application"
            )

        yield FunctionInfo.from_fn(
            _patent_search_stub,
            description=(
                "Search patents and intellectual-property filings (PatentsView). Registered in a "
                "degraded state because PATENT_API_KEY is not configured; calling it returns setup "
                "instructions instead of results."
            ),
        )
        return

    client = PatentSearchClient(
        api_key=api_key,
        timeout=tool_config.timeout,
        max_results=tool_config.max_results,
    )

    async def _patent_search(query: str, year: str | None = None) -> str:
        """Searches for patents and intellectual-property filings.

        Returns patents from the PatentsView (USPTO) database with titles,
        abstracts, grant dates, and links. Use for queries about inventions,
        prior art, technology patents, and IP research.

        Args:
            query (str): The search query describing the invention or technology.
            year (str | None): Optional grant-year filter (e.g., "2024").

        Returns:
            str: Formatted patent search results.
        """
        return await client.search(query, year)

    yield FunctionInfo.from_fn(
        _patent_search,
        description=_patent_search.__doc__,
    )
