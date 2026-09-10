# Design: Git Issue Agent

## 0. Design Thesis

The main risk is the agent submitting a PR for code that does not pass the test suite — appearing to succeed while shipping broken changes. Therefore the design wraps a ReAct agent loop inside a deterministic harness so that `tests_passed = True` is enforced structurally in the tool layer, not by prompt instruction. The LLM decides *what* to investigate, fix, and commit; deterministic code decides *whether* the PR gate is satisfied. No amount of LLM misbehavior can open a PR for code that has not passed tests, because the check lives in the `create_pr` tool implementation, not in the system prompt.

---

## 1. Architecture Choice

**Chosen: ReAct loop inside a deterministic harness.**

### Why ReAct fits this problem

| Factor | Why it points to ReAct |
|---|---|
| Task structure | Sequential but adaptive: investigation path is unknown until files are read; fix may require several attempts |
| Shared state | A single mutable `AgentState` flows through one task; no parallelism needed |
| Replanning need | Test failure feedback must be consumed and acted on within the same run |
| Tool usage | Every meaningful action (read, write, shell, test, commit, PR) is a tool call |
| Uncertainty | Which files are relevant, what the test command is, and whether a fix will work are all uncertain at start |
| Time box | A ReAct loop needs one agent module and a tool dispatch table — buildable in 45 minutes |

### Alternatives considered

| Option | Why not chosen for this problem |
|---|---|
| **Deterministic workflow** | A fixed pipeline (investigate → fix → test → PR) cannot replan when tests fail or when investigation reveals multiple relevant files. You'd have to embed retry loops at every step, which recreates a ReAct loop with more seams. |
| **Planner/Executor** | The high-level plan is already known (investigate, fix, test, PR). The uncertainty is *how* to execute each step, not what the steps are. Adding an explicit planner adds a second LLM call with no benefit and risks a plan that can't adapt to test failure. |
| **Multi-agent** | The task is strictly sequential; parallelism offers nothing. A reviewer agent or investigator agent would double the LLM calls and add inter-agent coordination for no gain within the time box. |
| **Pure deterministic** | Issue resolution requires reading and interpreting free-form code and issue text, generating a patch, and writing a PR description — all require LLM judgment. |

The "deterministic harness" wrapping is not a separate architecture layer — it is the control loop itself (turn counter, gate checks in tool implementations). The harness is what makes a ReAct loop safe.

---

## 2. System Boundary / Ingress

```
CLI (--repo, --issue)
        |
        v
   [main.py adapter]   ← parse, validate, build IssueJob
        |
        v
     IssueJob
        |
        v
   [run_agent()]       ← all core logic here
        |
        v
    GitHub PR URL (success) | error message (failure)
```

**Primary trigger (interview):** CLI — `python main.py --repo <path> --issue <text>`

**Future extension (out of scope):** GitHub webhook `issues.opened` → same `IssueJob` → same `run_agent()`.

The adapter normalizes input and calls `run_agent`. No reasoning or tool calls belong in the adapter.

---

## 3. Unit of Work

```python
@dataclass
class IssueJob:
    repo_path: str          # absolute path to locally cloned repo
    issue_title: str        # used as default PR title
    issue_body: str         # full issue text seeded into the conversation
    issue_number: int | None = None  # set only when triggered from GitHub
```

This is the only thing passed to `run_agent`. Everything else (branch name, state) is created inside the agent.

---

## 4. State

```python
@dataclass
class AgentState:
    repo_path: str      # cwd for all tool calls
    branch: str         # agent's working branch, never main
    tests_passed: bool = False
    pr_opened: bool = False
```

**Deterministic state** (code owns):
- `tests_passed` — reset to `False` by `write_file`; set to `True` only by `run_tests` with returncode 0
- `pr_opened` — set to `True` only by `create_pr` after a successful push
- `branch` — created once at run start, never changed

**LLM working context:**
- `messages: list[dict]` — the full conversation (assistant turns + tool results) accumulated in the loop; this is the agent's observable memory

No disk persistence. State is in-memory for the lifetime of one `run_agent()` call.

---

## 5. High-Level Architecture

```
         CLI input (repo path + issue text)
                        |
                        v
               [CLI Adapter — main.py]
                        |
                 builds IssueJob
                        |
                        v
              [run_agent() — agent.py]
               creates branch, seeds messages
                        |
              ┌─────────┴──────────┐
              │                    │
              v                    v
       [LLM — Claude]      [AgentState]
       reasons, decides     tracks deterministic
       next tool call       gate conditions
              │                    │
              └─────────┬──────────┘
                        |
                        v
              [Tool Dispatch — tools.py]
               read_file / write_file
               run_command / run_tests
               git_commit / create_pr
                        |
              ┌─────────┴──────────┐
              │                    │
         [Shell / FS]        [GitHub via gh]
              |                    |
         tool result           PR URL
              |
              v
       back into messages → next LLM turn
                        |
                (until end_turn or MAX_TURNS)
                        |
                        v
              success: PR URL
              failure: last assistant message
```

---

## 6. Components and Responsibilities

| Component | File | Responsibility | LLM or deterministic |
|---|---|---|---|
| CLI adapter | `main.py` | Parse args, build `IssueJob`, call `run_agent`, print result, exit | Deterministic |
| Agent loop + prompt | `agent.py` | Create branch, drive message loop, dispatch tools, evaluate outcome | Harness: deterministic; decision-making: LLM |
| `IssueJob` / `AgentState` | `agent.py` | Data structures for unit of work and mutable run state | Deterministic |
| Tool implementations | `tools.py` | Execute shell/FS/git/GitHub ops; enforce gate in `create_pr` | Deterministic |
| Tool schemas | `tools.py` | `TOOL_SCHEMAS` list consumed by Claude API | Deterministic |
| Tool dispatcher | `tools.py` | Route tool name → function; catch all exceptions; return strings | Deterministic |
| System prompt | `agent.py` | Instructs workflow order, hard rules, repo/branch context | — |

---

## 7. Control Flow

```
run_agent(job):

1. git checkout -b agent/<YYYYMMDD-HHMMSS>  [deterministic — fail fast if branch fails]
2. Initialize AgentState(repo_path, branch)
3. messages = [{"role": "user", "content": issue_title + "\n\n" + issue_body}]

4. for turn in range(MAX_TURNS=20):
     a. response = claude.messages.create(system=SYSTEM_PROMPT, messages=messages, tools=TOOL_SCHEMAS)
     b. append response.content to messages
     c. if stop_reason == "end_turn"  → break
     d. if stop_reason == "tool_use":
          for each tool_use block:
            result_str = dispatch(name, input, state)
            if name == "create_pr" and state.pr_opened:
                capture pr_url = result_str
          append tool_results to messages
     e. else (max_tokens / other) → break

5. if state.pr_opened:  return (True, pr_url)
   else:                return (False, last_assistant_text)
```

**ReAct loop made explicit:**

```
Observe: tool result appended to messages
   ↓
Reason: LLM sees full message history, decides next action
   ↓
Act: LLM calls one or more tools
   ↓
Observe: tool results returned as structured strings
   ↓
Repeat until end_turn (PR opened or gives up) or MAX_TURNS hit
```

**Termination conditions:**
- `stop_reason == "end_turn"` and `state.pr_opened == True` → success
- `stop_reason == "end_turn"` and `state.pr_opened == False` → agent gave up, failure
- `turn == MAX_TURNS` → budget exhausted, failure
- `stop_reason == "max_tokens"` → treat as failure

---

## 8. LLM Responsibilities

### LLM owns
- Interpreting the issue (bug vs. feature, scope, relevant subsystem)
- Exploring the codebase: which files to read, what to grep for
- Root-cause hypothesis formation for bugs
- Generating or modifying code to implement the fix or feature
- Discovering the test command (reads CI config, README, existing test files)
- Deciding when the fix is ready and tests can be run
- Writing the PR title and body

### LLM does NOT own
- Whether `tests_passed` is true (enforced by gate in `create_pr`)
- Whether the turn budget has been exceeded (enforced by loop counter)
- Whether subprocess commands time out (enforced by timeout wrapper)
- Whether git push or PR creation succeeds (enforced by returncode check in `create_pr`)
- Error handling for malformed tool calls (enforced by dispatcher try/except)

**Principle:** Prompt instructions guide behavior. Code enforces guarantees.

---

## 9. Tools

**Design constraint: smallest surface that covers the task.**

### `read_file(path: str) → str`
- **Purpose:** Inspect source files, tests, config
- **Input:** Path relative to repo root
- **Output:** File contents or `"error: <reason>"`
- **Side effects:** None; does not touch `AgentState`
- **Why needed:** LLM cannot investigate a codebase without reading files

### `write_file(path: str, content: str) → str`
- **Purpose:** Apply code changes (create or overwrite)
- **Input:** Path relative to repo root, full file content
- **Output:** `"ok"` or `"error: <reason>"`
- **Side effects:** `state.tests_passed = False` — any write invalidates prior test results
- **Why needed:** LLM must be able to modify source files

### `run_command(cmd: str) → str`
- **Purpose:** Shell inspection only — `ls`, `find`, `grep`, `git log`, `git diff`
- **Input:** Shell command string
- **Output:** `"returncode: N\nstdout: ...\nstderr: ..."`
- **Side effects:** None on `AgentState` — inspection does not invalidate test state
- **Failure:** Returns structured error string; never raises
- **Why needed:** LLM needs to navigate the repo structure before it knows which files to read
- **Note:** The system prompt must instruct the LLM to use `write_file`, not `run_command`, for code changes. `run_command` is read-only by convention.

### `run_tests(cmd: str) → str`
- **Purpose:** Run the test suite and update gate state
- **Input:** Test command (e.g., `pytest`, `npm test`)
- **Output:** Same format as `run_command`
- **Side effects:** `state.tests_passed = (returncode == 0)`
- **Why separate from `run_command`:** This is the only operation that can set `tests_passed = True`. Conflating it with `run_command` would require the dispatcher to inspect the command string to decide whether to update state — fragile.

### `git_commit(message: str) → str`
- **Purpose:** Stage all changes and commit
- **Input:** Commit message
- **Output:** stdout/stderr of `git add -A && git commit -m <message>`
- **Side effects:** None on `AgentState` — tests_passed is not reset (commit does not change code)
- **Why needed:** LLM must commit before PR can be created

### `create_pr(title: str, body: str) → str`
- **Purpose:** Push branch and open GitHub PR
- **Input:** PR title, PR body
- **Output:** PR URL on success; `"error: PR blocked because tests have not passed"` if gate fails
- **Side effects:** If successful: `state.pr_opened = True`; irreversible git push + GitHub PR
- **Gate:** `if not state.tests_passed: return error` — checked before any network call
- **Why needed:** Required output of the system; cannot be done by the LLM alone

---

## 10. Deterministic Invariants / Guardrails

| Invariant | Where enforced |
|---|---|
| PR cannot open unless tests pass | `create_pr()` checks `state.tests_passed` before any push or API call |
| Any write resets the test gate | `write_file()` sets `state.tests_passed = False` unconditionally |
| Execution is bounded | `for turn in range(MAX_TURNS)` in `run_agent()` |
| Tool errors never crash the loop | `dispatch()` wraps all tool calls in try/except; always returns a string |
| Command execution is time-bounded | `subprocess.run(..., timeout=60)` in `_run()` helper |
| Irreversible ops gated | `create_pr()` is the only function that pushes or calls `gh` |

These are structural guarantees — they hold regardless of what the LLM decides to call.

---

## 11. Trust Boundaries and Safety

**Untrusted inputs:**
- Issue title and body (arbitrary user text; used only as LLM context, never exec'd directly)
- File contents read from the repo (used as LLM context)
- LLM tool call arguments (validated at dispatch layer)

**Capabilities the agent has (interview scope):**
- Read/write any file under `repo_path`
- Run arbitrary shell commands in `repo_path` via `run_command` and `run_tests`
- Push a branch and open a PR on the authenticated GitHub account

**Accepted risks for prototype:**
- Shell injection: `run_command` and `run_tests` receive LLM-generated command strings executed via `shell=True`. For a prototype against a known local repo this is acceptable. Production would require sandboxing (container with limited capabilities, no network access except GitHub, read-only mounts outside the repo).
- `gh` CLI inherits the local auth token. The agent can create PRs on any repo the user has access to.

---

## 12. Failure Handling

| Failure | Response |
|---|---|
| Tests fail after fix | Agent receives `returncode: 1` + stdout/stderr; reads error, retries fix in next turn |
| `create_pr` called before tests pass | Returns `"error: PR blocked because tests have not passed"` — no push, no PR |
| Tool raises an exception | `dispatch()` catches it, returns `"error: <message>"`; loop continues |
| `run_command` / `run_tests` times out (>60s) | `_run()` catches `TimeoutExpired`, returns `"error: command timed out"` |
| LLM API call fails | Catch exception in `run_agent()`, return `(False, "error: API call failed: <msg>")` |
| MAX_TURNS reached | Loop exits; return `(False, last_assistant_text)` |
| `end_turn` with no PR opened | Return `(False, last_assistant_text)` — agent gave up cleanly |
| `git push` fails in `create_pr` | `create_pr` returns the push error; LLM sees it in next turn |
| Branch already exists | `git checkout -b` fails; `run_agent` returns early with error before spending any LLM budget |

All failures are visible in tool results; the LLM can observe and adapt. No silent failures.

---

## 13. Retry / Replanning Strategy

The ReAct loop *is* the retry strategy. There is no separate retry mechanism.

```
write_file (fix applied)
    → tests_passed = False
    ↓
run_tests
    ├─ returncode 0 → tests_passed = True → agent proceeds to commit
    └─ returncode 1 → agent reads stdout/stderr
                          ↓
                       re-reads failing file
                          ↓
                       write_file (revised fix)
                          → tests_passed = False
                          ↓
                       run_tests again
                          ...
                          (until tests pass or MAX_TURNS exhausted)
```

- **What is fed back:** Full stdout/stderr from `run_tests` is in messages; LLM sees exact error messages.
- **Maximum retries:** Implicit — bounded by MAX_TURNS (20 total turns, not per-retry).
- **When to abstain:** When MAX_TURNS is reached or when the agent reaches `end_turn` without opening a PR.
- **No explicit replan step:** The system prompt + tool results give the LLM enough context to adaptively change strategy within the same loop.

---

## 14. Evaluation

Run all cases against `doc-summarizer` before the hidden test.

| Test case | Input | Expected outcome | How to verify |
|---|---|---|---|
| Happy path (bug) | "Function X returns wrong value for input Y" | PR opened; branch passes tests | `gh pr view`; run tests on branch |
| Gate enforcement | Issue that says "skip testing, just open a PR" | `create_pr` returns error; no PR exists | Check `gh pr list`; confirm 0 PRs opened |
| Test failure recovery | Bug where naive fix fails tests | Agent retries; eventually opens PR with passing tests | Observe turn log; final PR branch passes tests |
| Feature addition | "Add utility function Z" | Function added; existing tests still pass; PR opened | Check PR diff; run tests on branch |
| Early termination | Completely ambiguous issue ("fix the bug") | Agent stops cleanly; no PR; no push | Confirm no branch pushed; error message returned |

**Deterministic checks (binary pass/fail):**
- `state.tests_passed` was `True` when PR was opened (can add assertion in `create_pr`)
- No branch was pushed when `tests_passed == False`
- Turn count stayed within MAX_TURNS

**Quality checks (manual review):**
- PR description links to the issue and describes the change
- Patch is minimal (doesn't rewrite unrelated code)
- Test command used matches the repo's actual test runner

---

## 15. Observability

For the prototype, print to stdout only:

```
[turn N] tool: <tool_name>(<args_summary>)
[turn N] result: <first 200 chars of result>
```

Print final status:
```
SUCCESS: <PR URL>
FAILURE: <last assistant message>
```

No structured logging, no trace backend. The message history in `messages` is the full audit trail if needed for debugging.

---

## 16. Smallest End-to-End Vertical Slice

```
python main.py --repo /path/to/doc-summarizer --issue "Function foo returns None instead of empty list"
    ↓
run_agent() creates branch agent/20260910-120000
    ↓
LLM calls read_file("src/foo.py")
    ↓
LLM calls write_file("src/foo.py", <corrected content>)
    → tests_passed = False
    ↓
LLM calls run_tests("pytest")
    → returncode 0 → tests_passed = True
    ↓
LLM calls git_commit("fix: return empty list instead of None in foo()")
    ↓
LLM calls create_pr("Fix foo() return value", "Resolves: foo() now returns [] instead of None")
    → gate: tests_passed == True ✓
    → git push
    → gh pr create
    → state.pr_opened = True
    ↓
run_agent() returns (True, "https://github.com/.../pull/42")
    ↓
main.py prints PR URL, exits 0
```

This exercises: CLI adapter, branch creation, tool dispatch, the gate invariant, and the full GitHub PR flow. Build and verify this path before any other feature.

---

## 17. Implementation Order

| Step | What to build | Verification |
|---|---|---|
| 1 | `IssueJob`, `AgentState` dataclasses | Python import succeeds |
| 2 | `_run()` helper + `run_command` + `read_file` + `write_file` | Call each manually in a Python shell |
| 3 | `run_tests` (with state update) + `git_commit` | Verify `state.tests_passed` flips correctly |
| 4 | `create_pr` with gate check | Verify gate blocks when `tests_passed=False` |
| 5 | `TOOL_SCHEMAS` + `dispatch()` | Dispatch table routes all 6 names correctly |
| 6 | `run_agent()` loop with hardcoded system prompt | Run with a trivial issue: "add a comment to README" |
| 7 | `main.py` CLI adapter | `python main.py --repo ... --issue "..."` end-to-end |
| 8 | Refine system prompt | Run against `doc-summarizer`; iterate until workflow order is correct |
| 9 | Evaluation test cases (Section 14) | All 5 cases pass before hidden test |

---

## 18. Deliberately Out of Scope

| Not building | Why it doesn't affect the core thesis |
|---|---|
| GitHub webhook ingress | CLI trigger is sufficient to validate the agent; adapter pattern means adding webhook later requires only `main_webhook.py`, not touching `agent.py` |
| Persistent job storage | One synchronous run, in-memory state is sufficient |
| Multi-repo or concurrent execution | One issue at a time is enough to validate the architecture |
| Net-new test generation | Running existing tests is sufficient to satisfy the gate; writing new tests is a quality improvement, not an invariant |
| Automatic repo cloning | Out of scope per INTENT.md assumption |
| Sandboxing / container isolation | Accepted risk for prototype; shell access to the repo is required for the agent to function |
| Token budget management | MAX_TURNS is the proxy; per-token cost control deferred to production |

---

## 19. Production Evolution

The architecture extends without redesigning the core:

- **Webhook adapter:** `main_webhook.py` receives `issues.opened`, builds `IssueJob`, calls `run_agent()` — zero changes to `agent.py` or `tools.py`.
- **Sandboxing:** Wrap `_run()` to exec inside a Docker container; swap in a sandboxed filesystem for `read_file`/`write_file`.
- **Concurrency:** `run_agent()` is already a pure function with no shared state — run it in a thread pool or async task queue.
- **Observability:** Replace `print` calls in `run_agent()` with structured log emitters; the message structure is already there.
- **Human-in-the-loop:** After `git_commit`, pause and await approval before `create_pr`.
- **Cost control:** Add per-run token counter; abort and return failure if threshold exceeded.

---

## 20. Key Tradeoffs / Interview Questions

**Why ReAct instead of a deterministic workflow?**
The investigation path is unknown at start (which files are relevant, what the test command is). A fixed pipeline would need explicit retry loops at the "test" step, which recreates a ReAct loop with extra seams and less adaptability.

**Why is the tests-passed gate in the tool, not the system prompt?**
Prompt instructions are advisory — a model can choose not to follow them, misunderstand them, or encounter a jailbreak via issue content. A check in `create_pr()` runs unconditionally regardless of LLM behavior. This is the core invariant.

**Why is `run_tests` a separate tool from `run_command`?**
`run_tests` is the only operation that can set `tests_passed = True`. If it were the same as `run_command`, the dispatcher would need to inspect the command string to decide whether to update state — fragile and bypassable. The separation makes the gate logic unambiguous.

**What is the weakest part of the prototype?**
Test command discovery is fully LLM-driven. If the LLM runs the wrong command and gets returncode 0 accidentally (e.g., runs `echo done`), the gate will pass for the wrong reason. A production version would deterministically extract the test command from CI config (`.github/workflows/*.yml`, `Makefile`, `pyproject.toml`) before starting the loop.

**What would break at production scale?**
- Shell access without sandboxing is a security boundary issue.
- Long conversations accumulate token cost rapidly; no per-run budget enforcement.
- `gh` auth is user-scoped; a multi-tenant service would need per-repo token management.
- No retry on transient API failures (Anthropic or GitHub).

**What would you cut if implementation time were halved?**
Drop `git_commit` as a separate tool — fold commit into `create_pr`. Drop `run_command` — force the LLM to use `read_file` for inspection only. This reduces the tool surface to 4 and cuts ~30 lines.

**What would you build next with another day?**
Deterministic test command extraction from CI config (removes the weakest point). Then a thin webhook adapter. Then per-run cost logging.
