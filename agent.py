from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass
from datetime import datetime

from tools import AgentState, _run, git_commit, create_pr

MAX_ATTEMPTS = 3     # initial attempt + up to 2 repair passes
CLAUDE_TIMEOUT = 300  # seconds per claude -p invocation


@dataclass
class IssueJob:
    repo_path: str          # absolute local path to the cloned repo
    issue_title: str
    issue_body: str
    issue_number: int | None = None  # set when originating from GitHub


# ---------------------------------------------------------------------------
# Test-command detection (deterministic; LLM no longer discovers this)
# ---------------------------------------------------------------------------

def _detect_test_cmd(repo_path: str) -> str:
    names = set(os.listdir(repo_path))
    if names & {"pyproject.toml", "setup.py", "setup.cfg", "pytest.ini", "tox.ini"}:
        return "pytest"
    if "package.json" in names:
        return "npm test"
    if "Makefile" in names:
        return "make test"
    return "pytest"  # safe default for doc-summarizer


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def _make_prompt(job: IssueJob, branch: str, test_output: str | None) -> str:
    header = (
        f"You are a software engineer resolving a GitHub issue.\n"
        f"Repository: current working directory  |  Branch: {branch}\n\n"
        f"Issue: {job.issue_title}\n\n"
        f"{job.issue_body}\n\n"
    )

    if test_output is None:
        task = (
            "Task:\n"
            "1. Investigate the codebase to locate the relevant code.\n"
            "2. Identify the root cause (bug) or the right location (feature).\n"
            "3. Implement the fix or feature by editing the appropriate source files.\n"
            "When done, briefly describe what you changed and why.\n\n"
        )
    else:
        task = (
            "Your previous implementation was applied, but the test suite failed:\n\n"
            f"{test_output}\n\n"
            "Task:\n"
            "1. Read the test failures above carefully.\n"
            "2. Re-read the relevant source files to understand what went wrong.\n"
            "3. Fix the implementation so all tests pass.\n"
            "When done, briefly describe what you changed.\n\n"
        )

    rules = (
        "Rules — follow exactly:\n"
        "- Do NOT run the test suite (tests are run separately after you finish).\n"
        "- Do NOT run any git commands (add, commit, push, checkout).\n"
        "- Do NOT create a pull request.\n"
        "- Only read and edit source files to implement the change.\n"
    )

    return header + task + rules


# ---------------------------------------------------------------------------
# Claude Code invocation
# ---------------------------------------------------------------------------

def _invoke_claude(prompt: str, repo_path: str) -> tuple[int, str]:
    """
    Run `claude -p <prompt>` headlessly in repo_path.
    Returns (returncode, stdout).
    Claude Code uses its own built-in tools (Read, Edit, Bash, …).
    Git/test/PR operations are intentionally excluded via the prompt rules.
    """
    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--allowedTools", "Bash,Edit,Read,Write"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=CLAUDE_TIMEOUT,
        )
        return result.returncode, result.stdout
    except subprocess.TimeoutExpired:
        return -1, "error: claude -p timed out"
    except FileNotFoundError:
        return -1, "error: 'claude' not found — is Claude Code installed and on PATH?"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_agent(job: IssueJob) -> tuple[bool, str]:
    """
    Resolve one issue.  Returns (True, pr_url) or (False, reason).

    Invariants (enforced by Python, not by the LLM):
    - Branch is created before any work starts.
    - Tests are run deterministically by Python after each Claude pass.
    - create_pr is called only when state.tests_passed is True.
    - Loop is bounded by MAX_ATTEMPTS.
    """
    # 1. Create working branch (deterministic; fail-fast before spending LLM budget)
    branch = f"agent/{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    rc, _, err = _run(f"git checkout -b {shlex.quote(branch)}", cwd=job.repo_path)
    if rc != 0:
        return False, f"error: branch creation failed: {err.strip()}"

    state = AgentState(repo_path=job.repo_path, branch=branch)
    test_cmd = _detect_test_cmd(job.repo_path)
    test_output: str | None = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        # 2. LLM pass: investigate + edit files only
        print(f"[attempt {attempt}/{MAX_ATTEMPTS}] invoking Claude Code")
        prompt = _make_prompt(job, branch, test_output)
        rc, claude_out = _invoke_claude(prompt, job.repo_path)
        if rc != 0:
            return False, f"error: Claude Code exited {rc}: {claude_out[:400]}"

        # 3. Deterministic gate: Python runs tests, Python checks result
        print(f"[attempt {attempt}/{MAX_ATTEMPTS}] running: {test_cmd}")
        t_rc, t_out, t_err = _run(test_cmd, cwd=job.repo_path, timeout=120)
        state.tests_passed = (t_rc == 0)
        test_output = f"returncode: {t_rc}\nstdout:\n{t_out}\nstderr:\n{t_err}"
        print(f"[attempt {attempt}/{MAX_ATTEMPTS}] tests {'PASSED' if state.tests_passed else 'FAILED'}")

        if state.tests_passed:
            # 4. Commit (deterministic Python)
            commit_out = git_commit(f"fix: {job.issue_title[:60]}", state)
            print(f"[commit] {commit_out[:120]}")
            if not commit_out.startswith("returncode: 0"):
                return False, f"error: git commit failed (no changes?)\n{commit_out}"

            # 5. Push + open PR (gated by state.tests_passed inside create_pr)
            pr_out = create_pr(job.issue_title, claude_out.strip(), state)
            if pr_out.startswith("error:"):
                return False, pr_out
            return True, pr_out

    return False, f"error: tests still failing after {MAX_ATTEMPTS} attempts\n{test_output}"
