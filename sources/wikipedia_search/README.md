<!--
SPDX-FileCopyrightText: Copyright (c) 2025-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# Wikipedia Search Tool

A NAT data-source tool that searches [Wikipedia](https://en.wikipedia.org) via
the public MediaWiki API. It **requires no API key**, so it works out of the
box — a fast, high-recall reference layer for the AI-Q research blueprint.

## Configuration

```yaml
functions:
  wikipedia_search_tool:
    _type: wikipedia_search
    max_results: 5            # articles to return (default 5)
    timeout: 30               # per-request timeout in seconds (default 30)
    # max_content_length: 1000    # truncate each extract (default 1000; null = full)
    # api_url: https://en.wikipedia.org/w/api.php   # override for other wikis
```

Register `wikipedia_search_tool` in your `data_source_registry` to expose it in
the UI.

| Field | Default | Description |
| :-- | :-- | :-- |
| `max_results` | `5` | Maximum number of articles returned. |
| `timeout` | `30` | Per-request timeout in seconds. |
| `max_content_length` | `1000` | Truncates each extract to reduce token usage (`null` for full). |
| `api_url` | en.wikipedia.org | MediaWiki endpoint; override for other language wikis. |

## Behavior

- **No API key required.** The MediaWiki API is public.
- **Single round-trip.** Uses `generator=search` with `prop=extracts` to fetch
  titles, plain-text intro summaries, and canonical URLs in one request.
- **Graceful degradation.** Timeouts and HTTP/transport errors return a readable
  error string rather than raising.
- **Citable output.** Each result includes the article's Wikipedia URL.

## Output format

```
1. **Transformer (deep learning architecture)**
   - **Summary**: A transformer is a deep learning architecture based on the ...
   - **Link**: https://en.wikipedia.org/wiki/Transformer_(deep_learning_architecture)
```
