from __future__ import annotations

import argparse
import os
import sys

from agent import IssueJob, run_agent


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the git issue agent against a local repository.")
    parser.add_argument("--repo", required=True, help="Path to the local git repository")

    issue_group = parser.add_mutually_exclusive_group(required=True)
    issue_group.add_argument("--issue", help="Issue text (title + body) as a string")
    issue_group.add_argument("--issue-file", help="Path to a file containing the issue text")

    args = parser.parse_args()

    repo_path = os.path.abspath(args.repo)

    if args.issue:
        issue_text = args.issue
    else:
        try:
            with open(args.issue_file) as f:
                issue_text = f.read()
        except OSError as e:
            print(f"error: cannot read issue file: {e}", file=sys.stderr)
            sys.exit(2)

    lines = issue_text.splitlines()
    issue_title = lines[0][:72] if lines else "(no title)"
    job = IssueJob(repo_path=repo_path, issue_title=issue_title, issue_body=issue_text)

    success, message = run_agent(job)
    print(message)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
