---
title: "For AI agents"
description: "How AI agents should use daymet-mcp: which tool to call first, how to read aggregation labels, and how to cite."
type: Guide
tags:
  - agents
  - llms
generated:
  by: "claude/opus-5.5"
  at: "2026-11-15T00:00:00Z"
sources:
  - id: design
    resource: "DESIGN.md"
    title: "daymet-mcp design"
    author: "team:daymet-mcp"
status: stable
---

# For AI agents

* For Daymet **data**, connect to the daymet-mcp server and call its tools; do not scrape these
  pages. Start with `daymet_list_variables` or `daymet_locate_cell`.
* Read `aggregation`, `units` and `fieldLabel` on every summary series. Monthly and annual `prcp`
  are **sums** (`prcp_monthly_total_mm`); never describe them as averages.
* Every Daymet year has 365 days; leap years have no December 31.
* Follow `nextSteps` in results; data tools end with `daymet_get_citation`. Include the citations
  and the access date when you report values.
* If a result has `page.truncated: true`, call again with `offset = page.nextOffset`.
* Errors are tool results with `error.code`; `query_too_large` and `auth_required` name the limit
  and a smaller alternative.
* The documentation corpus is at `llms.txt` and `llms-full.txt`; any page URL plus `index.md`
  returns its Markdown source. Pages without `verified:` are unverified.
