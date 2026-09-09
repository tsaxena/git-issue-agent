# Git Issue Agent — Intent

## Goal

Build an agentic software-engineering system that can receive a bug or feature ticket and autonomously drive it through:

`Receive Issue → Investigate → Implement → Test → Create PR`

The core issue-solving engine should be independent of how the issue enters the system.

## Assumptions

* GitHub Issues are the primary production source of tickets.
* A production integration could receive GitHub issue events through a webhook.
* The core agent should not depend directly on FastAPI, GitHub webhooks, or any particular trigger mechanism.
* A CLI will act as the primary local/test trigger during the 45-minute implementation.
* Both CLI and webhook should normalize input into the same internal job representation.
* One repository and one issue are processed per agent run.
* Repository access and GitHub authentication are already available.
* Existing repository tests are the primary correctness signal.
* We optimize the implementation for the 45-minute constraint rather than production-scale infrastructure.

## Acceptance Criteria

Given an incoming issue/ticket, the system can:

1. Accept the issue from at least one trigger mechanism.
2. Normalize it into an internal job containing repository and issue information.
3. Inspect the repository.
4. For bugs, perform root-cause investigation.
5. Implement the requested fix or feature.
6. Run repository tests.
7. Retry after test failures within a bounded number of iterations.
8. Create a commit.
9. Open a GitHub PR only after tests pass.
10. Return the resulting PR URL or a clear failure result.

The core agent should be callable independently of the trigger layer so additional integrations can be added without changing agent logic.

## Constraints

* 45 minutes for architecture.
* 45 minutes for implementation.
* LLM behavior is nondeterministic.
* Repository and shell operations have side effects.
* Agent execution must be bounded.
* Context is finite; the entire repository should not be loaded into the prompt.
* External integration plumbing should not block development or local testing.
* Production concerns such as persistent queues, distributed workers, and deployment are out of scope for the initial implementation.

## Important Ambiguities

### How is a ticket received?

The challenge does not specify an ingress mechanism.

Default decision:

* Production architecture: GitHub webhook.
* Interview implementation/test harness: CLI.
* Both produce the same internal `IssueJob`.

### Should webhook logic contain agent behavior?

No.

Trigger adapters should only:

* authenticate/validate the event
* extract issue/repository information
* construct an `IssueJob`
* invoke the core engine

Agent reasoning belongs in the core engine.

### Is asynchronous job processing required?

Not for V1.

The interview implementation can execute synchronously. A production version could place jobs onto a queue and process them with workers.

### Single agent or multi-agent?

Use a single ReAct-style agent unless the design reveals a strong need for independent parallel tasks. Investigation, editing, and testing share evolving repository state and are primarily sequential.

## Design Principles

1. **Thin triggers, fat engine**

   * CLI/webhook should contain no reasoning logic.
   * The agent engine should work regardless of how a ticket arrived.

2. **Agentic reasoning, deterministic invariants**

   * Use the LLM for investigation, hypothesis formation, implementation decisions, and repair.
   * Use deterministic code for test gates, iteration limits, git operations, and PR eligibility.

3. **CLI first, integration second**

   * Build and validate the issue-solving engine locally before adding webhook plumbing.

4. **Minimal implementation**

   * Prefer the smallest architecture that demonstrates the complete issue-to-PR workflow within 45 minutes.
