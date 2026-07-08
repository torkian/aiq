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

"""NAT register function for the arXiv paper search tool."""

import logging

from pydantic import Field

from nat.builder.builder import Builder
from nat.builder.function_info import FunctionInfo
from nat.cli.register_workflow import register_function
from nat.data_models.function import FunctionBaseConfig

from .arxiv_search import ArxivSearchTool

logger = logging.getLogger(__name__)


class ArxivPaperSearchToolConfig(FunctionBaseConfig, name="arxiv_paper_search"):
    """Configuration for the arXiv paper search tool.

    Searches arXiv for scientific preprints and papers. arXiv's public API
    requires no API key, so this tool works out of the box.
    """

    timeout: int = Field(default=30, description="Timeout in seconds for each search request")
    max_results: int = Field(default=10, description="Maximum number of papers to return")
    max_retries: int = Field(default=2, description="Retries on transient network failures")
    max_content_length: int | None = Field(
        default=None,
        description="Max characters per abstract. If set, truncates to reduce token usage.",
    )


@register_function(config_type=ArxivPaperSearchToolConfig)
async def arxiv_paper_search(tool_config: ArxivPaperSearchToolConfig, builder: Builder):
    """Register the arXiv paper search tool (no API key required)."""
    tool = ArxivSearchTool(
        timeout=tool_config.timeout,
        max_results=tool_config.max_results,
        max_content_length=tool_config.max_content_length,
    )

    async def _arxiv_paper_search(query: str) -> str:
        """Searches arXiv for scientific preprints and peer-reviewed papers.

        Use this for research queries needing authoritative scientific sources:
        machine learning, physics, mathematics, computer science, quantitative
        biology, and related fields. Returns titles, authors, abstracts, and
        arXiv links suitable for citation.

        Args:
            query (str): The search query string.

        Returns:
            str: Formatted string with the matching papers.
        """
        from .arxiv_search import _search_with_retries

        return await _search_with_retries(tool, query, tool_config.max_retries)

    yield FunctionInfo.from_fn(
        _arxiv_paper_search,
        description=_arxiv_paper_search.__doc__,
    )
