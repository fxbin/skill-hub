# Scenario Runbooks

Use these runbooks when the user request implies a recurring multi-role pattern. They help the lead choose a default coordination shape quickly.

## 1. Startup MVP

- Lead: `Technical Trinity` or `World-Class Product Architect`
- Common assistants: `Executive Trinity`, `Git Workflow Guardian`
- Use when: the user wants a 0-1 product, fast MVP delivery, or launch planning.
- Flow:
  1. Confirm product outcome, target user, and scope boundary.
  2. Define MVP system shape and frontend/user-flow priorities.
  3. Attach strategy support if monetization, growth, or positioning are in scope.
  4. Attach Git guardrails if the user also wants branch/PR delivery.
- Success markers:
  - smallest buildable scope
  - clear user flow
  - technical landing plan
  - explicit launch or validation risk

## 2. Audit and Fix

- Lead: `Code Audit Council`
- Common assistants: language specialist, `Technical Trinity`, `Git Workflow Guardian`
- Use when: the user wants review findings and the remediation path in one motion.
- Flow:
  1. Findings first.
  2. Separate blockers from follow-up improvements.
  3. Attach implementation specialist only for fix design or patch execution.
  4. Attach Git guardrails if PR/commit/push is part of the ask.
- Success markers:
  - severity-ordered findings
  - concrete remediation path
  - no mixing of audit verdict and speculative redesign

## 3. Strategy with Technical Landing

- Lead: `Executive Trinity`
- Common assistants: `Technical Trinity`, `Sentinel Architect (NB)`
- Use when: the user wants growth, monetization, or operating-model decisions plus implementation consequences.
- Flow:
  1. State the business decision first.
  2. Translate it into system, data, or delivery implications.
  3. Add Sentinel only if risk, irreversibility, or production impact is high.
- Success markers:
  - one clear decision
  - measurable business rationale
  - realistic technical landing path

## 4. Regulated or Unfamiliar Domain Build

- Lead: `Omni-Architect`
- Common assistants: `Technical Trinity`, `Code Audit Council`
- Use when: the request involves healthcare, finance, government, enterprise compliance, or an unfamiliar industry.
- Flow:
  1. Surface domain assumptions and compliance boundaries.
  2. Design the system around constraints before implementation detail.
  3. Attach audit support if security/compliance verification is part of the ask.
- Success markers:
  - domain assumptions called out
  - constraints explicitly tied to architecture
  - risk boundaries made visible

## 5. Frontend UX with Backend Coupling

- Lead: `World-Class Product Architect`
- Common assistants: `Technical Trinity`, `Git Workflow Guardian`
- Use when: the request spans user flow, component/UI behavior, and API or auth/error-state coupling.
- Flow:
  1. Define the target user flow and main interaction failures.
  2. Specify frontend implementation direction.
  3. Attach Technical Trinity for API contracts, auth states, or backend coupling.
  4. Attach Git guardrails only when delivery workflow is requested.
- Success markers:
  - improved UX path
  - clear interaction and state model
  - backend contract or implementation coupling called out

## 6. High-Risk Production Change

- Lead: `Sentinel Architect (NB)`
- Common assistants: owning specialist, `Git Workflow Guardian`, `Code Audit Council`
- Use when: the change is production-sensitive, cross-cutting, irreversible, or has outage risk.
- Flow:
  1. Declare the risk and execution mode.
  2. Break work into staged checkpoints.
  3. Define rollback and stop conditions.
  4. Keep coordination tight; do not add assistants without a clear job.
- Success markers:
  - staged plan
  - rollback thinking
  - explicit stop conditions
  - post-change verification
