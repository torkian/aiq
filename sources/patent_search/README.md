<!--
SPDX-FileCopyrightText: Copyright (c) 2025-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# Patent Search Tool

A NAT data-source tool that searches patents via
[PatentsView](https://search.patentsview.org) (the USPTO-funded public patent
search API). This package realizes the `patent_search` example from
[`docs/source/extending/adding-a-data-source.md`](../../docs/source/extending/adding-a-data-source.md)
as a working, tested data source.

## Configuration

```yaml
functions:
  patent_search_tool:
    _type: patent_search
    max_results: 10       # patents to return (default 10)
    timeout: 30           # per-request timeout in seconds (default 30)
    api_key: ${PATENT_API_KEY}
```

Register `patent_search_tool` in your `data_source_registry` to expose it in the
UI. The tool inherits the standard graceful-degradation behavior: when
`PATENT_API_KEY` is not set it registers a stub that returns setup instructions
instead of failing at startup.

| Field | Default | Description |
| :-- | :-- | :-- |
| `max_results` | `10` | Maximum number of patents returned. |
| `timeout` | `30` | Per-request timeout in seconds. |
| `api_key` | `None` | PatentsView API key; falls back to `PATENT_API_KEY`. |

## API key

PatentsView requires a **free** API key. Request one at
<https://patentsview.org/apis/keyrequest> and set it as `PATENT_API_KEY`.

## Behavior

- **Graceful degradation.** Timeouts, HTTP errors, and malformed responses
  return a readable error string rather than raising.
- **Citable output.** Each result includes a Google Patents link.

## Maintainer note

The request/response mapping follows the documented PatentsView v1 PatentSearch
API. The unit tests mock all HTTP, so they validate the client's request
construction and parsing but **not** the live endpoint. Before enabling this
source in a shipped config, confirm the live PatentsView contract (endpoint,
`X-Api-Key` header, and `patents[]` field names) against current API docs.
