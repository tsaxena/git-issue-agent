**# Design: Git Issue Agent**

**## 0. Design Thesis**

The main risk is the agent producing a plausible code change that appears complete but has not actually been validated. Passing the configured test suite is a necessary publication gate, though not a proof that the issue is fully solved. The design wraps a Claude Code headless invocation inside a deterministic Python harness so that validation and publication decisions are enforced structurally rather than by prompt instruction. Claude Code decides *\*what\** to investigate and *\*how\** to fix it; deterministic Python code decides whether the result can be committed, pushed, and turned into a PR. PR publication therefore does not depend on the model following a prompt-level rule.

\---

**## 1. Architecture Choice**

**\*\*Chosen: Claude Code headless (\`claude -p\`) inside a deterministic Python harness.\*\***

Rather than implementing a ReAct loop in Python (calling the Anthropic API, parsing \`tool\_use\` responses, dispatching to custom tool functions), the implementation delegates the full investigation-and-edit loop to Claude Code itself. Python's role is: create branch, detect test command, invoke Claude Code, run tests, commit, push, open PR.

Claude Code (\`claude -p --allowedTools Read,Grep,Glob,Edit,Write\`) handles:

\- Observe → Reason → Act internally

\- All file reading and editing

\- Codebase navigation

\- PR description generation

Python handles everything that must be deterministic:

\- Branch lifecycle

\- Test execution

\- The tests-passed gate

\- Retry bounds

\- Git and GitHub operations

This reduces the Python harness to \~160 lines with no Anthropic SDK dependency.

**### Alternatives considered**

\| Option | Why not chosen |

\|---|---|

\| **\*\*Python ReAct loop + Anthropic SDK\*\*** | More code, custom tool dispatch, more failure surface. Claude Code already provides the ReAct loop; re-implementing it in Python adds no safety benefit. |

\| **\*\*Deterministic workflow\*\*** | A fixed pipeline cannot replan when tests fail or when investigation reveals unexpected files. |

\| **\*\*Planner/Executor\*\*** | The uncertainty is *\*how\** to execute each step, not what the steps are. A planner adds a second LLM call with no benefit. |

\| **\*\*Multi-agent\*\*** | The task is strictly sequential; parallelism offers nothing within the time box. |

\---

**## 2. System Boundary / Ingress**

\`\`\`

CLI (--repo, --issue / --issue-file)

        |

        v

   [main.py adapter]   ← parse, validate, build IssueJob

        |

        v

     IssueJob

        |

        v

   [run\_agent()]       ← all core logic here

        |

        v

    GitHub PR URL (success) | error message (failure)

\`\`\`

**\*\*Primary trigger:\*\*** CLI — \`python main.py --repo \<path> --issue \<text>\` or \`--issue-file \<path>\`

\- \`--issue \<text>\`: full string becomes \`issue\_body\`; \`issue\_title\` is the first line, truncated to 72 characters.

\- \`--issue-file \<path>\`: reads the file; same title/body extraction rule.

**\*\*Future extension (out of scope):\*\*** GitHub webhook \`issues.opened\` → same \`IssueJob\` → same \`run\_agent()\`.

\---

**## 3. Unit of Work**

\`\`\`python

@dataclass

class IssueJob:

    repo\_path: str          # absolute path to locally cloned repo

    issue\_title: str        # used as PR title on success

    issue\_body: str         # full issue text seeded into the Claude prompt

    issue\_number: int | None = None  # reserved for future webhook trigger

\`\`\`

\`issue\_number\` is not set by the CLI adapter; it is a forward-compatibility placeholder for a webhook adapter.

\---

**## 4. State**

\`\`\`python

@dataclass

class AgentState:

    repo\_path: str          # cwd for all tool calls

    branch: str             # agent's working branch, never main

    tests\_passed: bool = False

\`\`\`

**\*\*Deterministic state\*\*** (Python owns):

\- \`tests\_passed\` — set to \`True\` only by Python after running the test command with returncode 0; reset implicitly on each new attempt because Python runs tests after every Claude Code invocation.

\- \`branch\` — created once at run start, never changed.

No disk persistence. State is in-memory for the lifetime of one \`run\_agent()\` call.

\---

**## 5. High-Level Architecture**

\`\`\`

         CLI input (repo path + issue text)

                        |

                        v

               [CLI Adapter — main.py]

                        |

                 builds IssueJob

                        |

                        v

              [run\_agent() — agent.py]

               creates branch

               detects test command

                        |

              ┌─────────┴──────────────────────────────┐

              │  for attempt in 1..MAX\_ATTEMPTS (3):    │

              │                                         │

              │  \_invoke\_claude(prompt, repo\_path)       │

              │  ┌──────────────────────────────────┐   │

              │  │  claude -p \<prompt>               │   │

              │  │  --allowedTools Read,Grep,Glob,   │   │

              │  │                 Edit,Write         │   │

              │  │                                   │   │

              │  │  Claude Code's internal loop:     │   │

              │  │  Read files → Edit files →        │   │

              │  │  Grep/Glob (inspect) → …               │   │

              │  │  returns PR description on stdout │   │

              │  └──────────────────────────────────┘   │

              │                                         │

              │  Python runs test suite (\_run)           │

              │  state.tests\_passed = (rc == 0)          │

              │                                         │

              │  if tests\_passed:                        │

              │      git\_commit(title, state)            │

              │      create\_pr(title, body, state)       │

              │      return (True, pr\_url)               │

              │                                         │

              │  else: feed test output → next prompt    │

              └─────────────────────────────────────────┘

                        |

              success: PR URL

              failure: error message (exit 1)

\`\`\`

\---

**## 6. Components and Responsibilities**

\| Component | File | Responsibility | LLM or deterministic |

\|---|---|---|---|

\| CLI adapter | \`main.py\` | Parse args, build \`IssueJob\`, call \`run\_agent\`, print result, exit | Deterministic |

\| Agent orchestrator | \`agent.py\` | Create branch, detect test cmd, invoke Claude Code, run tests, commit, PR, retry | Deterministic (harness) |

\| Prompt builder | \`agent.py\` | Build initial prompt and repair-pass prompt with test failure output | Deterministic |

\| Claude Code invocation | \`agent.py\` | Subprocess call to \`claude -p\`; returns stdout (PR description) | LLM (internal to claude) |

\| Test command detection | \`agent.py\` | Inspect repo root files; map to test command | Deterministic |

\| \`git\_commit\` / \`create\_pr\` | \`tools.py\` | Execute git/GitHub operations; enforce tests-passed gate in \`create\_pr\` | Deterministic |

\| \`\_run\` / \`\_fmt\` | \`tools.py\` | Subprocess execution helper; structured output formatting | Deterministic |

\---

**## 7. Control Flow**

\`\`\`

run\_agent(job):

1\. git checkout -b agent/\<YYYYMMDD-HHMMSS>          [deterministic — fail fast]

2\. state = AgentState(repo\_path, branch)

3\. test\_cmd = \_detect\_test\_cmd(repo\_path)            [deterministic]

4\. test\_output = None

5\. for attempt in range(1, MAX\_ATTEMPTS + 1):        [MAX\_ATTEMPTS = 3]

     a. prompt = \_make\_prompt(job, branch, test\_output)

        \# initial prompt: investigate + edit

        \# repair prompt: includes previous test failure output

     b. rc, claude\_out = \_invoke\_claude(prompt, repo\_path)

        \# runs: claude -p \<prompt> --allowedTools Read,Grep,Glob,Edit,Write

        \# claude\_out = stdout from Claude Code (PR description)

        \# if rc != 0: return (False, error)

     c. t\_rc, t\_out, t\_err = \_run(test\_cmd, cwd=repo\_path, timeout=120)

        state.tests\_passed = (t\_rc == 0)

        test\_output = formatted t\_rc / t\_out / t\_err

     d. if state.tests\_passed:

            commit\_out = git\_commit(f"fix: {issue\_title[:60]}", state)

            if commit fails: return (False, error)

            pr\_out = create\_pr(issue\_title, claude\_out, state)

            if pr\_out starts with "error:": return (False, pr\_out)

            return (True, pr\_out)   # pr\_out is the PR URL

6\. return (False, "tests still failing after 3 attempts\n" + test\_output)

\`\`\`

**\*\*Termination conditions:\*\***

\- \`state.tests\_passed\` is True and PR opens successfully → success

\- \`create\_pr\` returns an error (push failed, gh failed) → failure

\- \`git commit\` fails (no changes, git error) → failure

\- \`claude -p\` exits non-zero → failure

\- \`MAX\_ATTEMPTS\` exhausted with tests still failing → failure

\---

**## 8. LLM Responsibilities (Claude Code)**

**### Claude Code owns**

\- Interpreting the issue (bug vs. feature, scope, relevant subsystem)

\- Exploring the codebase: reading files, running inspection commands (grep, ls, git log)

\- Root-cause hypothesis formation for bugs

\- Generating or modifying code to implement the fix or feature

\- Writing the PR description (returned on stdout, used verbatim as PR body)

\- Repairing code when given test failure output in a follow-up prompt

**### Claude Code does NOT own**

\- Whether \`tests\_passed\` is true (enforced by gate in \`create\_pr\`)

\- What test command to run (detected deterministically by Python)

\- Running the test suite (Python runs it after each Claude Code pass)

\- Committing, pushing, or creating the PR (all Python)

\- Retry bounds (enforced by the \`MAX\_ATTEMPTS\` loop)

\- Subprocess timeouts (enforced by \`\_run\`)

**\*\*Principle:\*\*** Prompt instructions guide behavior. Code enforces guarantees.

\---

**## 9. Tools**

**### Claude Code's built-in tools (used by the LLM)**

Claude Code is invoked with \`--allowedTools Read,Grep,Glob,Edit,Write\`. These are Claude Code's own built-in capabilities:

**\*\*Read\*\***

\- Purpose: Read files in the repository to understand code structure and existing behavior.

\- Input: File path within the repo.

\- Output: File contents.

\- Side effects: None.

\- Failure behavior: Returns an error if the file does not exist; Claude Code explores alternate paths.

\- Why the LLM needs this tool: Root-cause analysis requires reading source files, tests, and configuration.

**\*\*Edit\*\***

\- Purpose: Apply targeted edits to source files to implement the fix or feature.

\- Input: File path and replacement content (old string → new string).

\- Output: Confirmation of edit applied.

\- Side effects: Modifies files in the working tree; changes persist until committed or reverted.

\- Failure behavior: Returns an error if the target string is not found or the file does not exist.

\- Why the LLM needs this tool: Code changes must be written to disk for the Python harness to test and commit.

**\*\*Write\*\***

\- Purpose: Create or overwrite files (for cases where a fix requires a new file).

\- Input: File path and full file content.

\- Output: Confirmation of write.

\- Side effects: Creates or overwrites files in the working tree.

\- Failure behavior: Returns an error on permission or path errors.

\- Why the LLM needs this tool: Some fixes require creating new files (e.g., a new module or test fixture).

**\*\*Grep\*\***

\- Purpose: Search file contents by pattern across the repository without shell access.

\- Input: Regex pattern and optional path filter.

\- Output: Matching lines with file paths and line numbers.

\- Side effects: None.

\- Failure behavior: Returns empty results if no matches; does not raise errors.

\- Why the LLM needs this tool: Locating all usages of a symbol or pattern is essential for impact analysis before editing.

**\*\*Glob\*\***

\- Purpose: Search repository paths by file pattern to discover layout and locate modules.

\- Input: Glob pattern and optional root path.

\- Output: List of matching file paths.

\- Side effects: None.

\- Failure behavior: Returns empty results if no matches.

\- Why the LLM needs this tool: Navigating an unfamiliar codebase requires discovering file layout without shell access.

Claude Code is not given shell or GitHub capabilities. Test execution, commits, pushes, and PR creation remain outside the model and are performed only by Python.

**### Python tool functions (in \`tools.py\`)**

These are called directly by Python, not exposed to the LLM:

**#### \`git\_commit(message, state) → str\`**

\- Runs \`git add -A && git commit -m \<message>\` in \`state.repo\_path\`

\- Returns \`\_fmt(rc, stdout, stderr)\`

**#### \`create\_pr(title, body, state) → str\`**

\- **\*\*Gate:\*\*** if \`not state.tests\_passed\`, returns \`"error: PR blocked because tests have not passed"\` — no network calls made

\- Runs \`git push -u origin \<branch>\`; returns error string if push fails

\- Runs \`gh pr create --title \<title> --body \<body>\`

\- Returns the PR URL on success (gh prints it to stdout)

**#### \`\_run(cmd, cwd, timeout=60) → (rc, stdout, stderr)\`**

\- Wraps \`subprocess.run(shell=True, ...)\`; catches \`TimeoutExpired\` and other exceptions

\- Used by both \`git\_commit\`/\`create\_pr\` (in tools.py) and the test runner and branch creation (in agent.py)

**#### \`\_fmt(rc, out, err) → str\`**

\- Formats a subprocess result as \`"returncode: N\nstdout: ...\nstderr: ..."\`

\---

**## 10. Deterministic Invariants / Guardrails**

\| Invariant | Where enforced |

\|---|---|

\| PR cannot open unless tests pass | \`create\_pr()\` checks \`state.tests\_passed\` before any push or \`gh\` call |

\| Tests are always run after each Claude Code pass | \`run\_agent()\` calls \`\_run(test\_cmd)\` unconditionally after every \`\_invoke\_claude\` |

\| Execution is bounded | \`for attempt in range(1, MAX\_ATTEMPTS + 1)\` — hard cap of 3 attempts |

\| Claude Code cannot directly run tests / commit / push | Claude Code is limited to \`Read,Grep,Glob,Edit,Write\`; no Bash or GitHub capability is exposed |

\| Command execution is time-bounded | \`\_run()\` uses \`subprocess.run(..., timeout=60)\`; test runs use \`timeout=120\` |

\| Claude Code invocation is time-bounded | \`subprocess.run(["claude", "-p", ...], timeout=CLAUDE\_TIMEOUT)\` where \`CLAUDE\_TIMEOUT = 300\` |

\| Irreversible ops gated | \`create\_pr()\` is the only function that pushes or calls \`gh\`; guarded by the tests-passed check |

\---

**## 11. Trust Boundaries and Safety**

**\*\*Untrusted inputs:\*\***

\- Issue title and body (arbitrary user text; used only as LLM context, injected into a prompt string)

\- File contents read from the repo (used as LLM context)

**\*\*Capabilities Claude Code has:\*\***

\- Read/write any file under \`repo\_path\` via its built-in tools

**\*\*Accepted risks for prototype:\*\***

\- Claude Code can read and modify repository files. A production system should still isolate each run in a sandbox/container because repository contents and generated edits are untrusted.

\- Python's \`gh\` subprocess inherits the local authenticated GitHub context. A production service would use scoped, per-repository credentials rather than a user-wide CLI login.

\---

**## 12. Failure Handling**

\| Failure | Response |

\|---|---|

\| Tests fail after Claude Code pass | Python feeds full test output into next attempt's prompt; Claude Code repairs the fix |

\| \`create\_pr\` called before tests pass | Returns \`"error: PR blocked because tests have not passed"\` — no push, no PR |

\| \`git commit\` fails (nothing changed, etc.) | \`run\_agent\` returns \`(False, "error: git commit failed (no changes?)\n\<output>")\` |

\| \`git push\` fails in \`create\_pr\` | Returns \`"error: git push failed\n\<details>"\`; \`run\_agent\` returns failure |

\| \`gh pr create\` fails | Returns \`"error: gh pr create failed\n\<details>"\`; \`run\_agent\` returns failure |

\| \`claude -p\` exits non-zero | \`run\_agent\` returns \`(False, "error: Claude Code exited \<rc>: \<first 400 chars>")\` |

\| \`claude -p\` times out (>300s) | \`\_invoke\_claude\` catches \`TimeoutExpired\`, returns \`(-1, "error: claude -p timed out")\` |

\| \`\_run\` command times out | \`\_run()\` catches \`TimeoutExpired\`, returns \`(-1, "", "command timed out")\` |

\| \`claude\` binary not found | \`\_invoke\_claude\` catches \`FileNotFoundError\`, returns descriptive error |

\| \`MAX\_ATTEMPTS\` exhausted | Returns \`(False, "error: tests still failing after 3 attempts\n\<last test output>")\` |

\| Branch creation fails | \`run\_agent\` returns early before spending any LLM budget |

\---

**## 13. Retry / Repair Strategy**

Each attempt is a full Claude Code invocation. On test failure, the next attempt's prompt includes the complete test output (returncode, stdout, stderr) as a repair task. Claude Code sees the failure and is asked to re-read the relevant files and fix only what the test failures indicate.

\`\`\`

attempt 1:

    claude -p \<initial prompt>   → edits files

    python runs tests

    ├─ pass → commit + PR → done

    └─ fail → test\_output captured

attempt 2:

    claude -p \<repair prompt with test\_output>   → edits files

    python runs tests

    ├─ pass → commit + PR → done

    └─ fail → test\_output captured

attempt 3:

    claude -p \<repair prompt with test\_output>   → edits files

    python runs tests

    ├─ pass → commit + PR → done

    └─ fail → return failure (MAX\_ATTEMPTS exhausted)

\`\`\`

**\*\*Maximum attempts:\*\*** 3 (\`MAX\_ATTEMPTS\` in \`agent.py\`)

**\*\*No partial commits:\*\*** code is committed only after a passing test run.

\---

**## 14. Test Command Detection**

For the prototype, Python uses a **\*\*deterministic heuristic\*\*** to choose a likely repository test command before the first Claude Code invocation (\`\_detect\_test\_cmd\`):

\| File present | Prototype command |

\|---|---|

\| \`pyproject.toml\`, \`setup.py\`, \`setup.cfg\`, \`pytest.ini\`, \`tox.ini\` | \`pytest\` |

\| \`package.json\` | \`npm test\` |

\| \`Makefile\` | \`make test\` |

\| (none of the above) | \`pytest\` (default) |

The LLM is not involved in selecting the validation command, so it cannot choose a trivially successful command to satisfy the gate. This mapping is intentionally simple for the prototype and may be wrong for some repositories. A production system should prefer explicit repository configuration (for example, declared test/lint/type-check commands) and use heuristic discovery only as a fallback.

\---

**## 15. Evaluation**

**Test cases**

\| Case \| Input \| Expected outcome \|

\|---\|---\|---\|

\| Happy path \| Clear bug; tests pass on first Claude Code attempt \| PR created; \`tests\_passed\` True; exit 0 \|

\| Repair path \| Bug that requires test feedback; first attempt fails tests; second passes \| PR created on attempt 2; full test output fed into repair prompt \|

\| Max attempts exhausted \| Bug too complex or tests structurally broken \| Returns \`(False, "error: tests still failing after 3 attempts\\n\<output>")\` \|

\| \`claude -p\` timeout \| Claude Code hangs past \`CLAUDE\_TIMEOUT\` \| \`\_invoke\_claude\` returns \`(-1, "error: claude -p timed out")\`; run fails cleanly \|

\| No test suite detected \| Repo with no recognized config file \| Falls back to \`pytest\`; succeeds or fails on returncode \|

\| Prompt injection \| Issue body contains adversarial text \| Text enters Claude's context only; no shell access means no direct filesystem side effect beyond the allowed tools \|

**Deterministic checks**

\- \`create\_pr()\` is never called when \`state.tests\_passed\` is False.

\- Branch name matches \`agent/YYYYMMDD-HHMMSS\` format.

\- \`git commit\` is never called before at least one test run completes.

\- Attempt count does not exceed \`MAX\_ATTEMPTS\`.

**Agent / quality checks**

\- PR description references the issue and is coherent.

\- Only files plausibly related to the issue are modified.

\- No test files are deleted or disabled to manufacture a passing run.

\- Repair prompt on attempt 2+ contains the full test failure output from the previous attempt.

\---

**## 16. Observability**

Progress is printed to stdout:

\`\`\`

[attempt 1/3] invoking Claude Code

[attempt 1/3] running: pytest

[attempt 1/3] tests PASSED

[commit] returncode: 0 ...

https\://github.com/\<owner>/\<repo>/pull/\<N>

\`\`\`

On failure, the error message and last test output are printed; exit code is 1.

No structured logging or trace backend. In the current prototype, the Claude subprocess output is captured and therefore may be buffered until the \`claude -p\` invocation completes; Python's lifecycle messages remain visible while the run is in progress. A debugging/production improvement is to stream Claude events into structured execution logs while preserving the final machine-readable result.

\---

**## 17. Smallest End-to-End Vertical Slice**

\`\`\`

python main.py --repo /path/to/doc-summarizer \\

               \--issue "Function foo returns None instead of empty list"

    ↓

run\_agent():

    git checkout -b agent/20260910-120000

    test\_cmd = "pytest"    (detected from pyproject.toml)

    ↓

attempt 1:

    claude -p "\<prompt>" --allowedTools Read,Grep,Glob,Edit,Write

        (Claude reads src/foo.py, edits it, returns PR description on stdout)

    python: pytest → returncode 0 → state.tests\_passed = True

    git\_commit("fix: Function foo returns None instead of empty lis")

    create\_pr("Function foo...", "\<claude\_out>", state)

        gate: tests\_passed == True ✓

        git push -u origin agent/20260910-120000

        gh pr create --title "..." --body "..."

        returns "https\://github.com/.../pull/42"

    ↓

run\_agent() returns (True, "https\://github.com/.../pull/42")

    ↓

main.py prints PR URL, exits 0

\`\`\`

\---

**## 18. Implementation Order**

Build in dependency order and verify at each stage.

1\. **Core schemas** — \`IssueJob\` and \`AgentState\` dataclasses; import and instantiate with sample values.

2\. **Deterministic helpers** — \`\_run\`, \`\_fmt\`, \`git\_commit\`, \`create\_pr\`, \`\_detect\_test\_cmd\`; run against a temporary git repo without any LLM call.

3\. **Claude Code invocation** — \`\_invoke\_claude\`; call with a trivial prompt and verify stdout is captured and returncode is returned correctly.

4\. **Prompt builder** — \`\_make\_prompt\` for initial and repair variants; inspect output manually.

5\. **\`run\_agent()\` orchestrator** — wire the loop; stub \`\_invoke\_claude\` to return a canned PR description and verify branch / test / commit / PR sequence fires in order.

6\. **CLI adapter** — \`main.py\`; verify \`--repo\` and \`--issue\` / \`--issue-file\` args parse correctly and route to \`run\_agent()\`.

7\. **End-to-end smoke test** — run against a local repo with a seeded one-line bug; confirm a PR is opened.

8\. **Repair path** — seed a bug that requires test feedback to fix; confirm attempt 2 receives the failure output and succeeds.

\---

**## 19. Key Tradeoffs / Interview Questions**

**\*\*Why \`claude -p\` instead of the Anthropic SDK with custom tools?\*\***

Claude Code already implements the Observe→Reason→Act loop, tool dispatch, and error handling. Re-implementing that in Python with the SDK adds \~300 lines of code, a custom tool dispatch table, and a second failure surface, with no additional safety benefit. The tests-passed gate and retry bounds are the invariants that matter — those remain in Python either way.

**\*\*Why is the tests-passed gate in the tool, not the system prompt?\*\***

Prompt instructions are advisory. A check in \`create\_pr()\` runs unconditionally regardless of LLM behavior, including unexpected tool call sequences or prompt injection via issue content.

**\*\*Why is test command detection deterministic?\*\***

If the LLM selects the test command and runs the wrong one (e.g., \`echo done\`), it could receive returncode 0 and the gate would pass for the wrong reason. Detecting the command from repo files in Python eliminates this failure mode entirely.

**\*\*What is the weakest part of the prototype?\*\***

The prototype still operates directly on a local checkout and relies on repository-level test heuristics. A production version would provision an isolated workspace per job and run validation inside a sandbox/container with explicit repository configuration.

**\*\*What would break at production scale?\*\***

\- Direct execution against a shared/local checkout is a workspace-isolation risk.

\- \`gh\` auth is user-scoped; a multi-tenant service would need per-repo token management.

\- No retry on transient failures (network, GitHub API).

\- No per-run cost tracking or token budget enforcement.

**\*\*What would you cut if implementation time were halved?\*\***

The repair loop. A single Claude Code pass with no retry still exercises the core thesis (LLM edits → deterministic test gate → PR). Retry is a reliability improvement, not an architectural necessity.

**\*\*What would you build next with another day?\*\***

Sandbox isolation: run each job inside a container with a writable clone and read-only access outside that workspace. This eliminates the workspace-isolation risk without changing \`agent.py\` or \`tools.py\`.

\---

**## 20. Deliberately Out of Scope**

\| Not building | Rationale |

\|---|---|

\| GitHub webhook ingress | CLI is sufficient to validate the agent; adding a webhook adapter requires only a new entrypoint, not changes to \`agent.py\` |

\| Persistent job storage | One synchronous run; in-memory state is sufficient |

\| Multi-repo or concurrent execution | One issue at a time validates the architecture |

\| Net-new test generation | Running existing tests satisfies the gate |

\| Automatic repo cloning | Repo must be pre-cloned |

\| Sandboxing / container isolation | Accepted risk for prototype |

\| Token budget management | \`MAX\_ATTEMPTS\` and \`CLAUDE\_TIMEOUT\` are the proxies |

\---

**## 21. Production Evolution**

The architecture extends without redesigning the core:

\- **\*\*Webhook adapter:\*\*** \`main\_webhook.py\` receives \`issues.opened\`, builds \`IssueJob\`, calls \`run\_agent()\` — zero changes to \`agent.py\` or \`tools.py\`.

\- **\*\*Sandboxing:\*\*** Run each job in an isolated container/worktree with a writable repo workspace, read-only access outside that workspace, resource/time limits, and scoped credentials. Validation commands execute inside the same isolated workspace.

\- **\*\*Concurrency:\*\*** Provision an isolated clone/worktree/container per job, then execute independent jobs through a worker pool or task queue. Concurrent jobs must not share the same mutable checkout.

\- **\*\*Observability:\*\*** Replace \`print\` calls with structured log emitters; pipe Claude Code's output to a trace sink.

\- **\*\*Human-in-the-loop:\*\*** After \`git\_commit\`, pause and await approval before \`create\_pr\`.

\- **\*\*Cost control:\*\*** Add per-run wall-clock and attempt-count budget; abort and return failure if exceeded.