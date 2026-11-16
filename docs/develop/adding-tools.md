---
title: "Adding a tool"
description: "How to add a daymet-mcp tool: input and output models, registration rules, tests, and regenerating the tool reference."
type: Guide
tags:
  - develop
  - tools
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

# Adding a tool

1. **Models** in `src/daymet_mcp/models/`: an input model subclassing `DaymetInput` (every field
   described; unknown fields are rejected) and an output model subclassing `ToolResultBase`.
   Nullable output fields need a default so the dumped result matches its `outputSchema`.
2. **Handler** in `src/daymet_mcp/tools/<family>.py`:

```python
@register_tool(
    "daymet_example",
    title="Example",
    description="What it returns, in at most 600 characters. Next: call daymet_get_citation.",
    input_model=ExampleInput,
    output_model=ExampleOutput,
    surface="point",
    endpoints=[ENDPOINT],
)
async def daymet_example(args: ExampleInput, ctx: ToolContext) -> ExampleOutput: ...
```

   Names match `^daymet_[a-z_]+$`; descriptions end with a `Next:` sentence; `nextSteps` must not
   be empty and data tools end it with `daymet_get_citation`.
3. **Tests**: a hermetic test in `tests/tools/` (through `call_ok`/`call_err`), a live test in
   `tests/live/test_live.py`, and an entry in `tests/helpers.EVERY_TOOL_CALL` so the protocol tests
   call it. `tests/test_integration_meta.py` fails otherwise.
4. **Docs**: `python scripts/gen_tools_reference.py` and `python scripts/gen_llms_txt.py`, then a
   `docs/log.md` entry.
