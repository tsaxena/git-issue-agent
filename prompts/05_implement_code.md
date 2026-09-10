Read:

* `CHALLENGE.md`
* `INTENT.md`
* `DESIGN.md`

Treat `DESIGN.md` as approved and frozen.

Implement only the **next unfinished step** in the `Implementation Order`.

## Runtime constraint

The coding-agent runtime is **locally authenticated Claude Code running headlessly via `claude -p`**.

Do not replace this with:

* the Anthropic Python SDK
* `anthropic.Anthropic()`
* the Messages API
* a custom `tool_use` loop
* custom tool schemas or dispatch machinery
* LangChain / LangGraph / another agent framework

Python should remain the **outer deterministic orchestrator**.

Claude Code headless should be used only for the agentic software-engineering work defined in `DESIGN.md`, such as:

* repository investigation
* root-cause analysis
* reasoning about the implementation
* editing code
* repairing an implementation after deterministic validation fails

Deterministic Python code should continue to own the lifecycle and invariants defined in `DESIGN.md`, such as:

* branch creation
* test/validation execution
* retry limits
* checking whether validation passed
* commit
* push
* PR creation

Keep Claude Code's capabilities limited to those explicitly allowed by `DESIGN.md`.

## Implementation rules
- Do not redesign the architecture.
- Do not change previously completed modules unless a concrete integration bug requires it.
- Do not add frameworks, services, agents, persistence, queues, or infrastructure not present in DESIGN.md.
- Keep the implementation minimal enough for the interview time box.
- Follow the contracts, invariants, trust boundaries, and failure behavior in DESIGN.md.
- If the current implementation step includes an external input or integration explicitly required by DESIGN.md, implement the smallest real adapter for it rather than substituting manually supplied data.
- Prefer the smallest code change that completes this implementation step.
- Reuse the existing local Claude Code authentication; do not require a separate Anthropic API key.
- If a design issue truly blocks implementation, stop and explain the blocker rather than silently redesigning around it.


After implementation:

1. List the files changed.
2. Summarize what was implemented.
3. Show the key code path I should review.
4. Show where `claude -p` is invoked if this step touches the Claude runtime.
5. Give the smallest verification command/test for this step.
6. Call out any implementation assumption you made.
7. State the next unfinished implementation step.
8. Stop.

Do not continue to the next implementation step automatically.

