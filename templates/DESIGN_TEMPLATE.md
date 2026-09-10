DESIGN.md

0. Design Thesis

In one paragraph:

What is the system fundamentally trying to guarantee?

What is the primary failure mode from INTENT.md?

What architectural principle addresses it?

Example structure:

The main risk is <failure mode>. Therefore the design uses <core architectural idea> so that <important invariant> is enforced structurally rather than relying on model behavior.

Keep this to 3–5 sentences.

1. Architecture Choice

Chosen architecture

<Deterministic workflow | ReAct | Planner/Executor | Multi-agent | Hybrid>

Why this architecture fits

Explain why it matches:

task structure

shared vs independent state

need for replanning

tool usage

uncertainty

time horizon

implementation time box

Alternatives considered

Option

Why not chosen

Deterministic workflow

...

ReAct

...

Planner / Executor

...

Multi-agent

...

Do not reject alternatives generically. Tie the decision to this specific problem.

2. System Boundary / Ingress

How does work enter the system?

<Trigger A> ─┐
             ├──> <Normalized Job>
<Trigger B> ─┘
                     |
                     v
                 Core Engine

Trigger adapters

Primary implementation trigger:

<CLI / API / webhook / queue / file / etc.>

Production or future trigger:

<...>

Adapters should normalize input but contain no core reasoning logic.

3. Unit of Work

Define the main object flowing through the system.

@dataclass
class Job:
    ...

Include only the information needed to execute one task.

Examples:

task/issue/request

repository/document/context identifier

optional metadata

configuration needed for deterministic execution

4. State

What changes while the task executes?

@dataclass
class State:
    ...

Separate:

Persistent / deterministic state

Examples:

current step

validation status

retry count

side-effect status

output identifiers

LLM working context

Examples:

observations

reasoning history

retrieved evidence

tool results

Do not duplicate state unnecessarily.

5. High-Level Architecture

             INPUT
               |
               v
        <Ingress Adapter>
               |
               v
             Job
               |
               v
        <Core Orchestrator>
               |
        +------+------+ 
        |             |
        v             v
   LLM Judgment   Deterministic
      / Agent       Operations
        |             |
        +------+------+
               |
               v
          Validation
               |
          pass / fail
               |
               v
            OUTPUT

Show only the major components here.

6. Components and Responsibilities

Component

Responsibility

LLM or deterministic?

<component>

...

...

<component>

...

...

<component>

...

...

Every component should have one clear responsibility.

Avoid adding components simply because they are common in production systems.

7. Control Flow

Describe the exact runtime path.

1. Receive job
2. Normalize / validate input
3. ...
4. LLM performs ...
5. Deterministic code validates ...
6. On failure ...
7. On success ...
8. Produce final output / side effect

If agentic, make the loop explicit:

Observe
   ↓
Reason / Decide
   ↓
Act
   ↓
Observe result
   ↓
continue / terminate

If planned:

Goal
 ↓
Plan
 ↓
Execute step
 ↓
Observe
 ↓
Replan if needed

The interviewer should be able to understand termination conditions from this section.

8. LLM Responsibilities

Use an LLM only where judgment is required.

LLM owns

...

...

...

Examples:

interpreting ambiguous requests

hypothesis formation

selecting relevant evidence

choosing the next action

generating/modifying unstructured content

LLM does NOT own

...

...

...

Important invariants should not depend only on prompt compliance.

9. Tools / Capabilities

For each model-accessible tool:

<tool_name>

Purpose:
...

Input:
...

Output:
...

Side effects:
...

Failure behavior:
...

Why the LLM needs this tool:
...

Prefer a small curated tool surface.

10. Deterministic Invariants / Guardrails

Take the invariants from INTENT.md and show exactly where they are enforced.

Invariant

Enforcement

<condition must hold>

<code/tool/gate>

Agent must terminate

max steps / timeout

Side effect only after validation

deterministic check

Invalid evidence/output cannot be promoted

validator

Principle:

Prompt instructions guide behavior. Code enforces guarantees.

11. Trust Boundaries and Safety

What inputs are untrusted?

user/ticket content

repository/document content

retrieved web content

model output

What capabilities are restricted?

shell

filesystem

network

credentials

destructive actions

external writes

State explicitly what is acceptable for the interview prototype and what would require sandboxing in production.

12. Failure Handling

Failure

Response

LLM/tool call fails

...

Validation fails

...

Agent reaches max iterations

...

External system unavailable

...

Partial side effect occurs

...

Malformed model output

...

Prefer failures that reduce confidence or autonomy rather than silently proceeding.

13. Retry / Replanning Strategy

Specify:

what can be retried

what information is fed back

maximum retries

when to replan

when to abstain/fail

Example:

attempt
  ↓
validate
  ├─ pass → continue
  └─ fail → return failure evidence to agent
                 ↓
              repair
                 ↓
             validate

Bound every loop.

14. Evaluation

Design evaluation before implementation.

Test cases

happy path

known failure

recovery path

adversarial/edge case

hidden/final case

Deterministic checks

...

...

Agent / quality checks

task success

correctness

grounding

trajectory quality

number of retries/tool calls

abstention/failure behavior

Where possible, create cases with known expected outcomes.

15. Observability

For the prototype, record only what helps debug:

job id/input

model invocation

tool/action sequence

tool outputs/errors

validation result

retries

final status

Avoid production observability infrastructure unless required.

16. Smallest End-to-End Vertical Slice

Before implementing the full system, prove:

realistic input
      ↓
core reasoning/action
      ↓
deterministic validation
      ↓
realistic output

Define the first slice:

<exact minimal flow>

This should exercise the core architectural thesis.

17. Implementation Order

Build in dependency order and verify after each stage.

1. Core schemas / state
2. Deterministic operations / validators
3. LLM or agent runtime
4. Minimal orchestrator
5. Thin trigger
6. End-to-end smoke test
7. Failure/recovery path
8. Only then add optional features

For each step, identify a minimal verification.

18. Deliberately Out of Scope

Not building for the interview:

...

...

...

Examples:

distributed workers

persistent memory

vector database

multi-agent coordination

sophisticated UI

production auth

autoscaling

complex observability

Explain why these do not affect the core thesis.

19. Production Evolution

If more time were available:

...

...

...

Show how the architecture extends without redesigning the core system.

20. Key Tradeoffs / Interview Questions

Be prepared to defend:

Why this architecture instead of the alternatives?

...

Why is this part agentic?

...

Why is this part deterministic?

...

What is the weakest part of the prototype?

...

What would break at production scale?

...

What would you cut if implementation time were halved?

...

What would you build next with another day?

...
