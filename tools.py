from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass


@dataclass
class AgentState:
    repo_path: str   # absolute path; used as cwd by all tools
    branch: str      # working branch name
    pr_opened: bool = False
    tests_passed: bool = False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _run(cmd: str, cwd: str, timeout: int = 60) -> tuple[int, str, str]:
    """Run a shell command. Returns (returncode, stdout, stderr)."""
    try:
        r = subprocess.run(
            cmd, shell=True, cwd=cwd,
            capture_output=True, text=True, timeout=timeout,
        )
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "command timed out"
    except Exception as e:
        return -1, "", str(e)


def _fmt(rc: int, out: str, err: str) -> str:
    return f"returncode: {rc}\nstdout: {out}\nstderr: {err}"


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def read_file(path: str, state: AgentState) -> str:
    try:
        full_path = os.path.join(state.repo_path, path)
        with open(full_path) as f:
            return f.read()
    except Exception as e:
        return f"error: {e}"


def write_file(path: str, content: str, state: AgentState) -> str:
    try:
        full_path = os.path.join(state.repo_path, path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w") as f:
            f.write(content)
        state.tests_passed = False
        return "ok"
    except Exception as e:
        return f"error: {e}"


def run_command(cmd: str, state: AgentState) -> str:
    return _fmt(*_run(cmd, cwd=state.repo_path))


def run_tests(cmd: str, state: AgentState) -> str:
    rc, out, err = _run(cmd, cwd=state.repo_path)
    state.tests_passed = (rc == 0)
    return _fmt(rc, out, err)


def git_commit(message: str, state: AgentState) -> str:
    cmd = f"git add -A && git commit -m {shlex.quote(message)}"
    return _fmt(*_run(cmd, cwd=state.repo_path))


def create_pr(title: str, body: str, state: AgentState) -> str:
    if not state.tests_passed:
        return "error: PR blocked because tests have not passed"

    rc, out, err = _run(
        f"git push -u origin {shlex.quote(state.branch)}",
        cwd=state.repo_path,
    )
    if rc != 0:
        return f"error: git push failed\n{_fmt(rc, out, err)}"

    rc, out, err = _run(
        f"gh pr create --title {shlex.quote(title)} --body {shlex.quote(body)}",
        cwd=state.repo_path,
    )
    if rc == 0:
        state.pr_opened = True
        return out.strip()  # gh prints the PR URL to stdout
    return f"error: gh pr create failed\n{_fmt(rc, out, err)}"


# ---------------------------------------------------------------------------
# Claude tool schemas
# ---------------------------------------------------------------------------

TOOL_SCHEMAS = [
    {
        "name": "read_file",
        "description": "Read the contents of a file at the given path relative to the repo root.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path relative to repo root"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": (
            "Write (create or overwrite) a file at the given path relative to the repo root. "
            "Resets the tests-passed state, so run_tests must be called again after writes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path relative to repo root"},
                "content": {"type": "string", "description": "Full file content to write"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "run_command",
        "description": (
            "Run a shell command in the repo root (60 s timeout). "
            "Returns returncode, stdout, stderr. "
            "Use for inspection (find, grep, git diff, ls, etc.). "
            "Use run_tests — not this tool — to execute the test suite."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "cmd": {"type": "string", "description": "Shell command to run"},
            },
            "required": ["cmd"],
        },
    },
    {
        "name": "run_tests",
        "description": (
            "Run the repository test command (60 s timeout). "
            "Returns returncode, stdout, stderr. "
            "Sets internal tests-passed state to True only when returncode is 0. "
            "create_pr will be rejected until this returns returncode 0."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "cmd": {"type": "string", "description": "Test command (e.g. 'pytest' or 'npm test')"},
            },
            "required": ["cmd"],
        },
    },
    {
        "name": "git_commit",
        "description": "Stage all changes (git add -A) and commit with the given message.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Git commit message"},
            },
            "required": ["message"],
        },
    },
    {
        "name": "create_pr",
        "description": (
            "Push the current branch and open a GitHub PR. "
            "Will be rejected if run_tests has not returned returncode 0 since the last write_file call. "
            "Returns the PR URL on success."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "PR title"},
                "body": {"type": "string", "description": "PR body / description"},
            },
            "required": ["title", "body"],
        },
    },
]


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def dispatch(name: str, params: dict, state: AgentState) -> str:
    """Route a tool call by name. Always returns a string; never raises."""
    try:
        if name == "read_file":
            return read_file(params["path"], state)
        if name == "write_file":
            return write_file(params["path"], params["content"], state)
        if name == "run_command":
            return run_command(params["cmd"], state)
        if name == "run_tests":
            return run_tests(params["cmd"], state)
        if name == "git_commit":
            return git_commit(params["message"], state)
        if name == "create_pr":
            return create_pr(params["title"], params["body"], state)
        return f"error: unknown tool '{name}'"
    except KeyError as e:
        return f"error: missing required parameter {e}"
    except Exception as e:
        return f"error: {e}"
