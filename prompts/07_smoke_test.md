Read:

* `CHALLENGE.md`
* `INTENT.md`
* `DESIGN.md`
* the completed implementation

Treat `DESIGN.md` as frozen.

We are now testing the complete system end-to-end against the example repository.

Do not redesign or refactor the system unless a concrete test failure reveals a correctness bug.

## Step 1 — Inspect the example repo

Inspect `doc-summarizer` and propose 2–3 small synthetic issues that:

* are realistic bug fixes or features
* have an objectively verifiable expected outcome
* exercise the full issue → investigation → edit → validation flow
* are small enough for a smoke test
* do not require external services or major architectural changes

For each candidate, state the expected behavior and how we can independently verify success.

## Step 2 — Choose the simplest issue

Select the smallest candidate that exercises the complete vertical slice.

Run the Git Issue Agent against it exactly as an external user would through the CLI.

Do not directly fix the issue yourself outside the agent.

## Step 3 — Observe the trajectory

Capture:

* issue received
* branch created
* Claude headless invocation
* repository investigation
* files changed
* deterministic test result
* repair attempt, if any
* final validation
* commit
* PR creation or expected PR-boundary failure

## Step 4 — Independently verify

After the agent finishes:

* inspect `git diff`
* inspect the commit
* run the test command independently
* verify the requested behavior directly where practical

Do not count the agent's own statement of success as validation.

## Step 5 — Report

Report:

1. synthetic issue used
2. expected behavior
3. actual trajectory
4. files changed
5. validation result
6. whether the agent actually solved the issue
7. any concrete implementation bug discovered
8. the smallest fix needed, if applicable

Do not add features or optimize the system yet.

Stop after reporting the smoke-test result.
