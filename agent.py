from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from datetime import datetime

import anthropic

from tools import AgentState, TOOL_SCHEMAS, dispatch

MAX_TURNS = 20
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-5")


@dataclass
class IssueJob:
    repo_path: str        # absolute local path to the cloned repository
    issue_title: str
    issue_body: str
    issue_number: int | None = None  # set when originating from GitHub


def _build_system_prompt(repo_path: str, branch: str) -> str:
    return f"""\
You are an autonomous software engineer agent. Your job is to resolve a GitHub \
issue by investigating the codebase, implementing the fix or feature, running \
tests, committing, and opening a pull request.

Repository path: {repo_path}
Working branch: {branch}

## Workflow — follow in this exact order

1. **Investigate**: Use read_file and run_command (ls, find, grep, git log, etc.) \
to understand the repository layout and locate relevant code.
2. **Root-cause** (bugs): Identify the exact file and line(s) responsible.
3. **Implement**: Apply the fix or feature with write_file.
4. **Test**: Call run_tests with the appropriate test command (read existing tests \
first to discover it). Retry the fix if tests fail.
5. **Commit**: Call git_commit after tests pass.
6. **PR**: Call create_pr only after a successful commit.

## Hard rules

- You MUST call run_tests and receive returncode 0 before git_commit or create_pr.
- You MUST call git_commit before create_pr.
- create_pr is enforced server-side: it will be rejected if tests have not passed.
- Use run_tests — not run_command — to execute the test suite.
- All file paths passed to read_file and write_file are relative to the repo root.
- When finished, include the PR URL in your final message.
"""


def run_agent(job: IssueJob) -> tuple[bool, str]:
    """
    Drive the agent loop for *job*.

    Returns (success, message):
      - success=True  → a PR was opened; message contains the PR URL or summary.
      - success=False → loop exhausted or ended without a PR; message is the last
                        assistant text or an error description.
    """
    # ── Create working branch ────────────────────────────────────────────────
    branch = f"agent/{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    result = subprocess.run(
        ["git", "checkout", "-b", branch],
        cwd=job.repo_path,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False, f"error: failed to create branch '{branch}': {result.stderr.strip()}"

    # ── Initialise state and client ──────────────────────────────────────────
    state = AgentState(repo_path=job.repo_path, branch=branch)
    client = anthropic.Anthropic()

    # ── Seed the conversation ────────────────────────────────────────────────
    messages: list[dict] = [
        {
            "role": "user",
            "content": f"{job.issue_title}\n\n{job.issue_body}",
        }
    ]

    last_text = ""
    pr_url = ""

    # ── Agent loop ───────────────────────────────────────────────────────────
    for _ in range(MAX_TURNS):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=4096,
                system=_build_system_prompt(job.repo_path, branch),
                tools=TOOL_SCHEMAS,
                messages=messages,
            )
        except Exception as exc:
            return False, f"error: Anthropic API call failed: {exc}"

        # Append the full assistant turn (may contain text + tool_use blocks).
        messages.append({"role": "assistant", "content": response.content})

        # Track the most recent text for the failure-path return value.
        for block in response.content:
            if hasattr(block, "text"):
                last_text = block.text

        if response.stop_reason == "end_turn":
            break

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result_str = dispatch(block.name, block.input, state)
                    if block.name == "create_pr" and state.pr_opened:
                        pr_url = result_str
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result_str,
                        }
                    )
            messages.append({"role": "user", "content": tool_results})
        else:
            # stop_reason is e.g. "max_tokens" — exit the loop.
            break

    # ── Evaluate outcome ─────────────────────────────────────────────────────
    if state.pr_opened:
        return True, pr_url or last_text
    return False, last_text
