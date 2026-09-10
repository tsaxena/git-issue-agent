# INTENT.md

## 1. Job to Be Done

What end-to-end outcome must the system achieve?

`<input / trigger> → <core work> → <validated output>`

Success means:

* ...
* ...
* ...

## 2. Primary Failure Mode

What is the most important way this system could appear to succeed but actually fail?

> `<one-sentence failure mode>`

Examples:

* Produces a plausible answer that is not grounded in evidence.
* Produces a code change that does not actually solve the issue.
* Takes an irreversible action based on an incorrect model decision.

## 3. Core Invariants

What must remain true regardless of LLM behavior?

* `<important action>` cannot happen unless `<deterministic condition>`.
* Agent execution must be bounded.
* Important side effects must be observable/auditable.
* Failures should fail safely rather than silently.

These should become architectural guardrails later.

## 4. System Boundary

### Input / Trigger

How does work enter the system?

* Primary trigger: ...
* Local/test trigger: ...

### Completion

The system is done when:

* ...
* ...

### External systems

* ...
* ...

## 5. Unit of Work / State

What is the smallest object representing one task?

```python
@dataclass
class Job:
    ...
```

What state evolves while the task is running?

* ...
* ...

Do not design storage yet unless persistence is required.

## 6. Assumptions

The challenge does not specify everything. For the interview, assume:

* ...
* ...
* ...

Prefer reasonable defaults over blocking on unanswered questions.

Clearly distinguish assumptions from requirements given by the interviewer.

## 7. Acceptance Criteria

The system should be able to:

1. ...
2. ...
3. ...
4. ...
5. ...

Include both the happy path and at least one important failure/recovery path.

## 8. Constraints

### Explicit

* Architecture time: ...
* Implementation time: ...
* Required tools/platforms: ...

### Inherent

* LLM behavior is nondeterministic.
* Context is finite.
* Tool calls or external systems may fail.
* Agent loops must terminate.
* Side effects may need stronger guarantees than prompts can provide.

## 9. LLM Judgment vs Deterministic Logic

### LLM is useful for

* interpretation
* reasoning / hypothesis formation
* choosing among ambiguous options
* generating or transforming unstructured content

### Deterministic code should own

* invariants
* validation gates
* retries / limits
* permissions
* irreversible side effects
* exact parsing / comparison when possible

Principle:

`LLM decides where judgment is needed; code guarantees important properties.`

## 10. Deliberately Out of Scope

For this interview version, do not build:

* ...
* ...
* ...

Possible production extensions:

* ...
* ...

## 11. Evaluation Strategy

Before the hidden/final test, how will we know the system works?

### Test cases

1. Happy path
2. Known failure case
3. Recovery case
4. Edge case

### What we measure

* task success
* correctness / validation result
* failure behavior
* trajectory length / retries if relevant

Where possible, create test cases with known expected answers.

## 12. Smallest End-to-End Vertical Slice

Build the smallest path that proves the architecture:

```text
input
  ↓
core reasoning/action
  ↓
deterministic validation
  ↓
output
```

Implement this before adding:

* extra agents
* webhook/UI plumbing
* persistence
* optimization
* production scaling

## 13. Architecture Questions to Resolve Next

Only after this document is reviewed:

* Should control flow be deterministic workflow, ReAct, planner/executor, or multi-agent?
* What tools does the model actually need?
* Where are the deterministic gates?
* What are the trust boundaries?
* What is the minimal module structure?
