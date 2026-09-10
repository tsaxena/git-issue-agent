Read:
- CHALLENGE.md
- INTENT.md
- templates/DESIGN_TEMPLATE.md

Create DESIGN.md.

Before choosing architecture:
1. identify the core failure mode
2. identify the invariant that must be enforced
3. identify what requires LLM judgment
4. identify what should remain deterministic

Then choose the simplest architecture that satisfies INTENT.md.

Include:
- architecture and rationale
- system boundary / ingress
- unit of work / state
- control flow
- tools / capabilities
- deterministic gates
- failure handling
- evaluation
- implementation order
- deliberately out of scope

Optimize for the interview time box.

Do not implement code yet.