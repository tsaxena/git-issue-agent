# Design: Git Issue Agent

## Architecture Choice and Rationale

**ReAct-style single agent using Claude tool_use.**

A single LLM agent with a curated tool set. Tasks are sequential, share state, and don't benefit from parallelism. Claude's `tool_use` API gives structured dispatch without fragile output parsing. The agent drives the loop; we constrain it with a max-turn limit and a system prompt that encodes policy.

Language: Python. No framework. One dependency: `anthropic`. Git and GitHub ops via `gh` CLI (already handles auth).

---

## Main Components

| Component | File | Responsibility |
|-----------|------|----------------|
| Entry point | `main.py` | CLI args, call `run_agent()`, print result, exit |
| Agent loop | `agent.py` | Control loop, Claude API calls, tool dispatch, system prompt |
| Tools | `tools.py` | Tool implementations + `TOOL_SCHEMAS` list |

---

## Agent Control Loop

```
run_agent(issue: str, repo_path: str):
  branch = f"agent/{timestamp}"
  run: git checkout -b {branch}
  messages = [user_message(issue)]

  while api_calls < MAX_TURNS:
    response = claude.messages.create(system=SYSTEM_PROMPT, messages=messages, tools=TOOL_SCHEMAS)
    api_calls += 1

    append response to messages

    if response.stop_reason == "end_turn":
      break

    # stop_reason == "tool_use"
    for tool_call in response.content:
      result_str = dispatch(tool_call.name, tool_call.input)
      append tool_result(tool_call.id, result_str) to messages

  if state.pr_opened:
    print PR URL; exit(0)
  else:
    print last assistant message; exit(1)
```

`api_calls` increments once per `messages.create()` call, not once per tool. **MAX_TURNS = 20.** Enough for investigate + implement + a few test-retry cycles without runaway cost.

---

## System Prompt (required content)

The system prompt must include:
- Role: autonomous software engineer agent
- Repo path and branch name (injected at runtime as f-string)
- Mandatory workflow: investigate → implement → run tests → PR only if tests pass
- Hard rule: **never call `create_pr` unless the immediately preceding `run_command` for tests returned `returncode: 0`**
- Hard rule: always call `git_commit` before `create_pr`
- Encourage reading existing tests first to understand the test command

---

## Tools

All tool results are **strings**. No exceptions escape the dispatch layer.

### `read_file(path: str) → str`
Read file at path relative to repo root. Returns file contents or an error string.

### `write_file(path: str, content: str) → str`
Write (create or overwrite) file at path relative to repo root. Returns `"ok"` or error string.

### `run_command(cmd: str) → str`
Run shell command in repo root with 60s timeout. Returns:
```
returncode: <n>
stdout: <text>
stderr: <text>
```
Used for everything: tests (`pytest`), inspection (`find`, `cat`, `grep`), reading repo structure. No separate `list_files` tool needed.

### `git_commit(message: str) → str`
Runs `git add -A && git commit -m <message>` in repo root. Returns stdout/stderr or error string. Agent does not track which files changed — `git add -A` handles it.

### `create_pr(title: str, body: str) → str`
Terminal action. Runs:
1. `git push -u origin <branch>`
2. `gh pr create --title <title> --body <body>`

Returns PR URL string on success, error string on failure. Sets `state.pr_opened = True` on success.

**`TOOL_SCHEMAS`** — list of Claude input_schema dicts for the above 5 tools, defined in `tools.py` alongside implementations.

---

## State

```python
@dataclass
class AgentState:
    repo_path: str   # absolute path, used by all tools
    branch: str      # working branch name
    pr_opened: bool  # True once create_pr succeeds
```

`issue` and all tool results live in `messages` — no need to duplicate in state. No disk persistence.

---

## Failure Handling

| Failure | Response |
|---------|----------|
| Tests fail | Agent sees `returncode: 1` + stdout/stderr; retries fix in next iterations |
| Agent calls `create_pr` before tests pass | System prompt forbids it; if it does anyway, we accept it (prompt is the only gate) |
| Tool execution error | Return error string; agent adapts |
| MAX_TURNS reached | Loop exits; print last assistant message; exit(1) |
| `run_command` timeout (>60s) | Subprocess killed; return `"error: command timed out"` |
| Malformed tool call | Catch `KeyError`/`Exception` in dispatch; return error string; continue loop |

---

## Validation Gate

**Pre-PR**: System prompt requires `run_command("pytest")` (or equivalent) exit code 0 before `create_pr`. This is enforced by instruction, not by code. There is no programmatic interception — keeping it simple is the right call for 45 minutes.

---

## GitHub PR Flow

1. **At init**: `git checkout -b agent/<YYYYMMDD-HHMMSS>` — timestamp slug, no parsing of issue text needed.
2. **Agent implements**: calls `write_file` repeatedly, then `git_commit`.
3. **Agent opens PR**: calls `create_pr(title, body)` — tool pushes branch and runs `gh pr create`.
4. PR URL returned to agent, agent emits it in final `end_turn` message.

Requires: `gh` CLI authenticated and `ANTHROPIC_API_KEY` in environment.

---

## Implementation Order

Build and verify in this order — each step is independently testable:

1. **`tools.py`** — implement and manually test each function:
   - `run_command` first (everything depends on it)
   - `read_file`, `write_file`
   - `git_commit`
   - `create_pr`
   - `TOOL_SCHEMAS` (5 Claude input_schema dicts)

2. **`agent.py`** — implement `run_agent()`:
   - Hardcode a short system prompt first; refine after smoke test
   - Wire dispatch: `if name == "run_command": ...` for each of the 5 tools
   - Test with a trivial issue: "add a comment to main.py" against a scratch repo

3. **`main.py`** — thin CLI wrapper last:
   - `--repo` (path), `--issue` (string) or `--issue-file` (path to text file)
   - Call `run_agent()`, exit with its return code

4. **Refine system prompt** — run against `doc-summarizer` with a real issue; iterate on prompt wording until behavior is correct.

---

## File Structure

```
git-issue-agent/
├── main.py          # ~30 lines
├── agent.py         # ~80 lines
├── tools.py         # ~100 lines
└── requirements.txt # anthropic
```

Total: ~210 lines. `requirements.txt` has one entry.
