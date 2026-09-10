from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass


@dataclass
class AgentState:
    repo_path: str   # absolute path; used as cwd by all tools
    branch: str      # working branch name
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
        return out.strip()  # gh prints the PR URL to stdout
    return f"error: gh pr create failed\n{_fmt(rc, out, err)}"
