# git-issue-agent

Autonomous agent that resolves a GitHub issue in a local repository: investigates the code, applies a fix, runs the test suite, and opens a pull request — without human intervention.

---

## How it works

```
issue text + repo path
        |
        v
   main.py  — parse args, build IssueJob
        |
        v
   run_agent()
        |
        ├─ git checkout -b agent/<timestamp>        [Python]
        ├─ detect test command from repo layout     [Python]
        |
        └─ for each attempt (max 3):
              |
              ├─ claude -p <prompt> --allowedTools Bash,Edit,Read,Write
              |        Claude Code investigates, edits files, returns PR description
              |
              ├─ run test suite                     [Python]
              |
              ├─ tests pass?
              |    yes → git commit                 [Python]
              |         → git push + gh pr create  [Python]
              |         → return PR URL
              |
              └─ tests fail? → feed failure output into next prompt, retry
```

### Separation of responsibilities

| Claude Code (`claude -p`) | Python harness |
|---|---|
| Read and interpret the issue | Create the working branch |
| Navigate the codebase | Detect the test command |
| Identify root cause / insertion point | Run the test suite |
| Modify source files | Enforce the tests-passed gate |
| Write the PR description | Commit, push, open PR |
| Repair code after test failure | Bound the retry loop (max 3 attempts) |

The tests-passed gate is enforced in `create_pr()` in Python code — not by prompt instruction alone. No amount of LLM misbehavior can open a PR for code that has not passed tests.

---

## Prerequisites

- **Python 3.10+**
- **Git**
- **Claude Code** — installed and authenticated locally
  ```
  npm install -g @anthropic-ai/claude-code
  claude   # complete auth on first run
  ```
- **GitHub CLI (`gh`)** — installed and authenticated
  ```
  brew install gh        # macOS
  gh auth login
  ```
- The **target repository must already be cloned locally**. The agent does not clone repos.
- The target repository must have a **GitHub remote** (required for `git push` and `gh pr create`).

### Verify Claude Code authentication

```bash
claude -p "say hello" --allowedTools Bash
# should print a response; exit 0
```

### Verify GitHub CLI authentication

```bash
gh auth status
# should show: Logged in to github.com as <user>
```

---

## Installation

```bash
git clone https://github.com/tsaxena/git-issue-agent
cd git-issue-agent
# no dependencies to install — uses only the Python standard library
```

---

## Usage

### Pass the issue as a string

```bash
python main.py \
  --repo /path/to/target-repo \
  --issue "Bug: summarize() returns None for empty input instead of empty string"
```

### Pass the issue from a file

```bash
python main.py \
  --repo /path/to/target-repo \
  --issue-file issues/doc-summarizer-issue-3.txt
```

`--issue` and `--issue-file` are mutually exclusive; one is required.

The first line of the issue text (up to 72 characters) becomes the PR title. The full text becomes the PR body seed passed to Claude Code.

**Exit codes:** `0` on success (PR opened), `1` on failure.

---

## Expected behavior

On a successful run you will see:

```
[attempt 1/3] invoking Claude Code
[attempt 1/3] running: pytest
[attempt 1/3] tests PASSED
[commit] returncode: 0 ...
https://github.com/<owner>/<repo>/pull/<N>
```

### If tests fail

The agent feeds the full test output (returncode, stdout, stderr) into the next Claude Code prompt as a repair task. It retries up to 3 attempts total. If all attempts fail:

```
error: tests still failing after 3 attempts
returncode: 1
stdout: ...
stderr: ...
```

No code is committed or pushed. Exit code is `1`.

### If the target repo has no GitHub remote

`git push -u origin <branch>` fails with a non-zero exit code. `create_pr` returns:

```
error: git push failed
returncode: 128
stderr: fatal: 'origin' does not appear to be a git repository
```

Exit code is `1`. No PR is created.

---

## Test command detection

Python inspects the repo root before invoking Claude Code and selects the test command deterministically:

| File present | Command used |
|---|---|
| `pyproject.toml`, `setup.py`, `setup.cfg`, `pytest.ini`, `tox.ini` | `pytest` |
| `package.json` | `npm test` |
| `Makefile` | `make test` |
| (none of the above) | `pytest` (default) |

Claude Code is told the fix is complete; it does not discover or run the test command itself.

---

## Minimal local smoke test

```bash
# 1. Clone a test repo that has a test suite and a GitHub remote
git clone https://github.com/<your-org>/doc-summarizer /tmp/doc-summarizer

# 2. Create a simple issue file
echo "Bug: handle edge case where input is None" > /tmp/test-issue.txt

# 3. Run the agent
python main.py --repo /tmp/doc-summarizer --issue-file /tmp/test-issue.txt

# 4. On success, the printed URL is the new PR
```

---

## Project structure

```
git-issue-agent/
├── main.py        — CLI entry point; parses args, builds IssueJob, calls run_agent()
├── agent.py       — run_agent() loop: branch, prompt, invoke claude, test, commit, PR
├── tools.py       — AgentState, _run/_fmt helpers, git_commit, create_pr
├── issues/        — sample issue text files for testing
├── prompts/       — prompt templates used during development of this agent
├── templates/     — INTENT and DESIGN document templates
├── INTENT.md      — requirements and invariants
├── DESIGN.md      — architecture decisions and rationale
└── CHALLENGE.md   — original problem statement
```

---

## Limitations

- **One issue at a time** — no concurrency or job queue.
- **Repo must be pre-cloned** — the agent does not clone repositories.
- **Shell access is unsandboxed** — Claude Code runs with the same filesystem and network access as the local user. Do not point this at untrusted repositories.
- **Max 3 attempts** — if the test suite still fails after 3 Claude passes, the agent gives up.
- **`gh` auth is user-scoped** — the agent can open PRs on any repo the authenticated user has write access to.

### Production extensions

- **Webhook adapter** — a `main_webhook.py` that receives `issues.opened` events and calls `run_agent()` unchanged.
- **Sandboxing** — run Claude Code inside a container with restricted filesystem and network.
- **Observability** — replace `print` statements with structured logging or a trace backend.
- **Human-in-the-loop** — pause after `git commit`, await approval before `create_pr`.
- **Cost control** — add per-run token or wall-clock budget enforcement.
