Goal — Given a software issue, autonomously investigate → implement → test → open PR.
Assumptions — One repo, one issue at a time, repo already cloned, GitHub auth available, existing tests available, local/sandbox execution, 45-minute implementation favors simplicity.
Acceptance criteria — Agent can inspect code, diagnose bugs, modify code, run tests, retry on failure, and only open a PR if validation passes.
Constraints — LLM is nondeterministic, code execution can be dangerous, finite context, agent must terminate, only 45 minutes to implement.
Ambiguities/default decisions — “I will build a single coding agent with tools rather than a multi-agent system unless the architecture analysis shows a reason otherwise.”