# INTENT.md

## 1. Job to Be Done

`GitHub issue (bug or feature) → investigate codebase → implement fix/feature → pass tests → open PR`

Success means:

* The agent receives a natural-language issue and fully resolves it without human intervention.
* The implementation passes the repository's existing test suite.
* A pull request exists on GitHub with the changes and a description linking it to the issue.

---

## 2. Primary Failure Mode

> The agent submits a PR for code that does not pass the test suite — appearing to complete the task while shipping broken changes.

This is the primary failure because it is both (a) preventable with a deterministic gate and (b) the most damaging outcome in a real codebase. A secondary but distinct failure is the agent producing a fix that passes tests yet still doesn't address the actual issue — this is an LLM quality problem, not an enforcement problem.

Other failure modes in priority order:

* Hallucinates file paths or function names without reading the actual codebase.
* Loops indefinitely or exhausts budget without making progress.
* Terminates early (declares it cannot solve the issue) without opening a PR.

---

## 3. Core Invariants

* A PR **cannot** be opened unless the test suite has passed on the current state of the code. This must be enforced in code, not by prompt alone.
* Any code modification after a test run **resets** the tests-passed flag — tests must be re-run after each change.
* Agent execution must be bounded (max turns / wall-clock limit).
* All tool calls and their results must be observable (logged to stdout or a trace).
* Irreversible side effects (git push, PR creation) must only occur after deterministic conditions are met.

---

## 4. System Boundary

### Input / Trigger

* **Primary trigger (interview scope):** CLI invocation with `--repo <path>` and `--issue <text>` or `--issue-file <path>`.
* **Future extension (out of scope):** GitHub webhook `issues.opened` event — issue title, body, repo.

Both would normalize to the same unit of work before the agent runs.

### Completion

The system is done when:

* A PR URL has been returned and confirmed open on GitHub (success), **or**
* The agent ends its turn early without opening a PR — agent declared it cannot proceed (failure), **or**
* The agent has exhausted its turn budget without opening a PR (failure).

### External Systems

* **GitHub** — read issue, push branch, open PR (via `gh` CLI or API).
* **Local git repo** — cloned copy in a known path; the agent reads and writes files here.
* **Test runner** — whatever command the repo uses (pytest, npm test, etc.); the agent discovers it by reading existing CI config or test files.
* **LLM provider** — for all reasoning, code generation, and hypothesis formation.

---

## 5. Unit of Work / State

```python
@dataclass
class IssueJob:
    repo_path: str          # absolute path to locally cloned repo
    issue_title: str
    issue_body: str
    issue_number: int | None = None  # set when triggered from GitHub
```

State that evolves during a run:

* `branch: str` — agent's working branch (created at start, never main).
* `tests_passed: bool` — reset to False after every file write; set True only by a passing test run.
* `pr_opened: bool` — set True once `create_pr` succeeds.
* conversation history (tool calls + results) — no separate storage needed.

No disk persistence required for the interview scope.

---

## 6. Assumptions

**Requirement (from challenge):**

* Handle both bugs and feature requests.
* Perform root-cause analysis for bugs.
* Run tests before submitting PR.
* Post PR to GitHub.
* 45-minute architecture phase + 45-minute implementation phase.

**Assumptions (underspecified by challenge):**

* The repository is already cloned locally before the agent runs; the agent does not handle cloning.
* The repo has an existing, runnable test suite. "Testing the implementation" means running that suite; writing net-new tests for added code is a stretch goal, not required to satisfy the gate.
* If no test suite exists, the gate condition is undefined — assume `doc-summarizer` has one (it does).
* "Posting a PR" means using `gh` CLI (already authenticated); no OAuth flow needed.
* The agent runs to completion synchronously; no job queue or async infrastructure is required.
* One agent instance handles one issue at a time; concurrency is out of scope.
* The hidden test will be a realistic bug or small feature against `doc-summarizer`; not an adversarial or multi-repo scenario.
* The number of LLM calls per run is bounded at a fixed ceiling determined during architecture; the exact number is not an intent-level decision.

---

## 7. Acceptance Criteria

1. **Happy path (bug):** Given a bug report, the agent locates the defect, patches it, runs tests, and opens a PR — the PR branch passes the test suite.
2. **Happy path (feature):** Given a feature request, the agent adds the functionality, verifies tests pass, and opens a PR with a meaningful description.
3. **Tests-first gate:** If the agent attempts to open a PR before tests pass, the request is rejected deterministically — not by LLM instruction alone.
4. **Failed test recovery:** If tests fail after the initial fix, the agent retries (re-reads errors, adjusts code) until tests pass or the turn limit is reached.
5. **Turn-limit safety:** If the agent cannot resolve the issue within the budget, it exits without pushing broken code or opening a PR, and prints its last known state.

---

## 8. Constraints

### Explicit

* Architecture phase: 45 minutes.
* Implementation phase: 45 minutes.
* Required tools/platforms: GitHub (`gh` CLI), an LLM API. Language choice is an assumption, not a stated requirement.

### Inherent

* LLM behavior is nondeterministic — same issue may produce different code paths.
* Context window is finite — very large repos or long conversations may exceed limits.
* Tool calls and external systems (git, GitHub) may fail transiently.
* Agent loops must terminate; unbounded loops are a safety and cost risk.
* Side effects (push, PR) need stronger guarantees than prompt instructions provide.

---

## 9. LLM Judgment vs. Deterministic Logic

### LLM is responsible for

* Reading and interpreting the issue (bug vs. feature, scope, intent).
* Exploring the codebase to identify relevant files and root cause.
* Forming hypotheses about what is broken or what needs to be added.
* Generating or modifying code to implement the fix/feature.
* Choosing which test command to run based on repo contents.
* Writing a meaningful PR title and description.

### Deterministic code must own

* Enforcing the tests-passed gate before any PR is created.
* Resetting tests-passed after any file write.
* Bounding the agent loop (max turns).
* Executing shell commands and returning structured output (returncode, stdout, stderr).
* Preventing irreversible GitHub operations (push, PR) when preconditions are unmet.
* All error handling and timeouts around subprocess execution.

**Principle:** `LLM decides what to do; code guarantees that dangerous actions only happen when safe.`

---

## 10. Deliberately Out of Scope

For the interview version, do not build:

* GitHub webhook ingress (FastAPI endpoint, HMAC verification).
* Multi-repo or concurrent issue handling.
* Persistent job storage / database.
* UI or dashboard.
* Caching of LLM calls or embeddings.
* Automatic repo cloning.

Possible production extensions:

* Webhook adapter that receives `issues.opened` events and enqueues jobs.
* Observability (structured logging, traces, cost tracking per run).
* Human-in-the-loop approval before PR is opened.
* Support for repositories without test suites (lint-only gate, etc.).

---

## 11. Evaluation Strategy

Before the hidden test, verify with self-generated issues against `doc-summarizer`:

### Test cases

1. **Happy path (bug):** File a bug where a known function returns wrong output. Expect: correct patch + passing tests + PR opened.
2. **Known failure (skip tests):** Prompt the agent to open a PR immediately. Expect: `create_pr` returns an error; no PR is opened.
3. **Recovery case (test fails first):** File a bug where the obvious fix is wrong. Expect: agent sees failing tests, retries, eventually finds a correct fix.
4. **Edge case (feature addition):** Request a new utility function. Expect: function added, existing tests still pass, PR opened.
5. **Early termination:** Issue so ambiguous the agent cannot proceed. Expect: agent stops without pushing code; error is reported cleanly.

### What we measure

* **Task success:** Was a PR opened? Does the branch pass tests on CI?
* **Correctness:** Does the patch actually address the issue stated?
* **Gate enforcement:** Did `create_pr` ever succeed when `tests_passed = False`?
* **Trajectory length:** How many turns did the agent use? Did it stay within MAX\_TURNS?

---

## 12. Smallest End-to-End Vertical Slice

```text
CLI: issue text + repo path
  ↓
Agent reads one file → writes one fix → runs tests
  ↓
Deterministic gate: tests_passed == True
  ↓
git commit → gh pr create → PR URL returned
```

Implement this before adding:

* Webhook / ingress layer
* Multiple retry strategies
* Persistence or async execution
* Production logging or cost controls
* Support for large or complex repositories

---

## 13. Architecture Questions to Resolve Next

Only after this document is reviewed:

* Should control flow be a deterministic workflow, ReAct loop, planner/executor split, or multi-agent?
* What exact tools does the model need? (read, write, shell, test, commit, PR — or fewer?)
* Where precisely are the deterministic gates, and in which layer do they live?
* What are the trust boundaries between the LLM and the shell environment?
* What is the minimal module structure that supports the CLI adapter now and a webhook adapter later without rewriting the core?
