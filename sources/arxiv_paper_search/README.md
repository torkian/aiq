<!--
SPDX-FileCopyrightText: Copyright (c) 2025-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# arXiv Paper Search Tool

A NAT data-source tool that searches [arXiv](https://arxiv.org) for scientific
preprints and papers. It queries the public arXiv Atom API, which **requires no
API key**, so the tool works out of the box — a useful default academic source
for the AI-Q research blueprint.

## Configuration

Add the tool to a workflow YAML under `functions`:

```yaml
functions:
  arxiv_paper_search_tool:
    _type: arxiv_paper_search
    max_results: 10        # papers to return (default 10)
    timeout: 30            # per-request timeout in seconds (default 30)
    max_retries: 2         # retries on transient network failures (default 2)
    # max_content_length: 500   # optional: truncate each abstract to N chars
```

To expose it in the UI, register it in your `data_source_registry` alongside the
other search tools.

| Field | Default | Description |
| :-- | :-- | :-- |
| `max_results` | `10` | Maximum number of papers returned. |
| `timeout` | `30` | Per-request timeout in seconds. |
| `max_retries` | `2` | Retries on transient network failures (linear backoff). |
| `max_content_length` | `None` | If set, truncates each abstract to reduce token usage. |

## Behavior

- **No API key required.** arXiv's API is public.
- **Graceful degradation.** Network timeouts, HTTP errors, and malformed
  responses return a readable error string rather than raising, so a transient
  arXiv outage never crashes a research run.
- **Citable output.** Each result includes the paper's arXiv URL, suitable for
  the citation verifier.
- **Safe XML parsing.** Responses are parsed with `defusedxml` to guard against
  XXE / entity-expansion attacks (defense in depth).

## Output format

```
1. **Attention Is All You Need** (2017)
   - **Authors**: Ashish Vaswani, Noam Shazeer, Niki Parmar et al.
   - **Abstract**: The dominant sequence transduction models ...
   - **Link**: https://arxiv.org/abs/1706.03762
```
