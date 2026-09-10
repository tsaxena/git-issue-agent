Read:

* `CHALLENGE.md`
* `INTENT.md`

Review `INTENT.md` against the original challenge.

Do not design the architecture yet.

Check specifically:

1. Did `INTENT.md` preserve every explicit requirement from `CHALLENGE.md`?
2. Are requirements clearly separated from assumptions?
3. Is the end-to-end job to be done correct?
4. Is the primary failure mode actually the most important failure for this system?
5. Are the core invariants strong enough to protect against that failure even if the LLM behaves incorrectly?
6. Is the system boundary complete, including how work enters the system and what counts as completion?
7. Is the unit of work/state clear without prematurely designing storage or architecture?
8. Is the division between LLM judgment and deterministic enforcement sensible?
9. Is the evaluation strategy sufficient to test the system before the hidden interviewer test?
10. Is the proposed vertical slice realistic within the implementation time box?
11. Is anything unnecessarily complex or prematurely productionized?
12. Is anything important missing?

For every issue you find:

* explain why it matters
* propose the smallest correction

Then update `INTENT.md` only where necessary.

Do not choose ReAct, planner/executor, multi-agent, frameworks, model runtimes, webhook technology, or module structure yet.

After updating, summarize only the 3–5 most consequential changes and stop.
