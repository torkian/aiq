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

"""NAT register function for the Wikipedia search tool."""

import logging

from pydantic import Field

from nat.builder.builder import Builder
from nat.builder.function_info import FunctionInfo
from nat.cli.register_workflow import register_function
from nat.data_models.function import FunctionBaseConfig

from .wikipedia_search import WikipediaSearchTool

logger = logging.getLogger(__name__)


class WikipediaSearchToolConfig(FunctionBaseConfig, name="wikipedia_search"):
    """Configuration for the Wikipedia search tool.

    Searches Wikipedia via the public MediaWiki API. No API key is required, so
    this tool works out of the box.
    """

    api_url: str = Field(
        default="https://en.wikipedia.org/w/api.php",
        description="MediaWiki API endpoint (override for other language wikis)",
    )
    timeout: int = Field(default=30, description="Timeout in seconds for each search request")
    max_results: int = Field(default=5, description="Maximum number of articles to return")
    max_content_length: int | None = Field(
        default=1000,
        description="Max characters per extract. If set, truncates to reduce token usage.",
    )


@register_function(config_type=WikipediaSearchToolConfig)
async def wikipedia_search(tool_config: WikipediaSearchToolConfig, builder: Builder):
    """Register the Wikipedia search tool (no API key required)."""
    tool = WikipediaSearchTool(
        api_url=tool_config.api_url,
        timeout=tool_config.timeout,
        max_results=tool_config.max_results,
        max_content_length=tool_config.max_content_length,
    )

    async def _wikipedia_search(query: str) -> str:
        """Searches Wikipedia for encyclopedic background on a topic.

        Use this for definitions, overviews, historical context, and general
        reference on people, places, organizations, concepts, and events.
        Returns article titles, intro summaries, and Wikipedia links suitable
        for citation.

        Args:
            query (str): The search query string.

        Returns:
            str: Formatted string with the matching articles.
        """
        return await tool.search(query)

    yield FunctionInfo.from_fn(
        _wikipedia_search,
        description=_wikipedia_search.__doc__,
    )
