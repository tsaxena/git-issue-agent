Read:

* `CHALLENGE.md`
* `INTENT.md`
* `DESIGN.md`

Review `DESIGN.md` against the challenge and intent.

Do not implement code yet.

Check specifically:

1. Does the architecture directly address the primary failure mode from `INTENT.md`?
2. Are the core invariants enforced structurally rather than only through prompts?
3. Is the architecture simpler than necessary, or more complex than necessary?
4. Is the system boundary complete, including ingress and final output/side effects?
5. Is the chosen architecture justified versus simpler alternatives?
6. Is the split between LLM judgment and deterministic logic appropriate?
7. Are model capabilities/tools constrained to only what is required?
8. Are all loops, retries, and agent trajectories bounded?
9. Are failure paths explicit and safe?
10. Is the evaluation strategy strong enough to catch plausible-but-wrong behavior?
11. Is the smallest vertical slice actually end-to-end?
12. Can the implementation realistically be completed in the stated time box?
13. Are there unnecessary frameworks, services, abstractions, agents, databases, or production infrastructure?
14. Does the implementation order minimize integration risk and produce a working vertical slice early?
15. Are there contradictions or underspecified contracts that would block implementation?

For every issue:

* explain why it matters
* propose the smallest correction

Update `DESIGN.md` only where necessary.

Do not add new architecture unless required to fix a concrete problem.

After updating:

* summarize the 3–5 most consequential changes
* state whether the design is ready to freeze
* identify the first implementation step
* stop
