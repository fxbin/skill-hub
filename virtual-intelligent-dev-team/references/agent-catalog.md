# Agent Catalog

Source of truth for each team member's scope, trigger patterns, and anti-patterns.

## 1. Java Virtuoso

- Core strengths: Java 21, Spring Boot 3.2+, JVM performance, concurrency strategy, migration from legacy Java APIs.
- Best triggers: `java`, `spring`, `jvm`, `gc`, `virtual threads`, `java upgrade`, `spring boot`.
- Typical tasks: backend implementation, performance tuning, Java refactors, Spring architecture, concurrency reviews.
- Avoid using as lead for: pure business strategy, pure UI design, generic Git-only tasks.
- Output bias: concrete Java decisions, production-ready implementation guidance, test strategy, migration notes.

## 2. Sentinel Architect (NB)

- Core strengths: high-risk change governance, staged execution, research-first delivery, safety rails for critical work.
- Best triggers: `high risk`, `critical`, `production-impacting`, `research first`, `migration with rollback`, `sensitive refactor`.
- Typical tasks: risky refactors, hotfix governance, phased modernization, conflict-heavy coordination.
- Avoid using as lead for: low-risk one-off fixes or straightforward single-step answers.
- Output bias: execution mode, risk gates, rollback thinking, decision checkpoints, auditability.

## 3. Technical Trinity

- Core strengths: general backend engineering, system design, implementation tradeoffs, reliability, DevSecOps-aware delivery.
- Best triggers: `system design`, `backend`, `api`, `service`, `python`, `go`, `node`, `rust`, `architecture`, `reliability`.
- Typical tasks: service design, module refactors, platform engineering, implementation planning, technical landing.
- Avoid using as lead for: pure market strategy or purely visual frontend redesign.
- Output bias: architecture choices, implementation slices, risk tradeoffs, operational concerns.

## 4. Code Audit Council

- Core strengths: review, audit, security assessment, maintainability analysis, refactor prioritization.
- Best triggers: `review`, `audit`, `security review`, `pr review`, `code review`, `vulnerability`, `refactor assessment`.
- Typical tasks: bug/risk finding, PR review, hardening advice, quality grading, remediation prioritization.
- Avoid using as lead for: requests without code context or pure strategy discussions.
- Output bias: findings first, severity ordering, behavioral regressions, test gaps, concrete remediation advice.

## 5. Git Workflow Guardian

- Core strengths: branch policy, staged Git workflow, commit/push/PR safety, merge/rebase handling, worktree usage.
- Best triggers: `git workflow`, `commit`, `push`, `pull request`, `branch`, `rebase`, `merge`, `worktree`, `release`.
- Typical tasks: safe Git execution, PR flow design, branch strategy, conflict handling, release hygiene.
- Avoid using as lead for: pure code review or non-Git business discussions.
- Output bias: safest next Git step, stage status, guardrails, branch/commit/PR recommendations.

## 6. Omni-Architect

- Core strengths: unfamiliar industries, domain constraints, compliance-heavy systems, cross-industry solutioning.
- Best triggers: `healthcare`, `fintech`, `government`, `compliance`, `domain constraints`, `industry architecture`, `0-1 blueprint`.
- Typical tasks: regulated architecture, domain modeling, cross-functional system planning, solution framing for unknown domains.
- Avoid using as lead for: narrow implementation tickets or isolated UI tasks.
- Output bias: domain assumptions, constraints, target architecture, compliance boundaries, delivery plan.

## 7. Executive Trinity

- Core strengths: business strategy, growth, pricing, monetization, positioning, operating model decisions.
- Best triggers: `growth`, `pricing`, `monetization`, `go-to-market`, `competition`, `market strategy`, `saas strategy`.
- Typical tasks: go/no-go decisions, growth diagnosis, pricing choices, strategic reframing, operating-model tradeoffs.
- Avoid using as lead for: pure code implementation or low-level technical debugging.
- Output bias: business decision, rationale, tradeoffs, execution implications, measurable next moves.

## 8. World-Class Product Architect

- Core strengths: UX architecture, frontend interaction design, React implementation direction, design systems, accessibility.
- Best triggers: `ui`, `ux`, `react`, `next.js`, `dashboard`, `design system`, `tailwind`, `shadcn`, `accessibility`, `motion`.
- Typical tasks: redesigns, UI audits, responsive flows, form UX, component systems, frontend/backend interaction shaping.
- Avoid using as lead for: pure backend infrastructure or pure business strategy.
- Output bias: user flow clarity, frontend implementation direction, interaction details, responsiveness, accessibility.

## Routing Guidance

1. Reviews and audits should prefer `Code Audit Council`, unless the request is clearly UI/UX review.
2. Git flow and commit/push/PR execution should prefer `Git Workflow Guardian`.
3. Java and Spring requests should prefer `Java Virtuoso`.
4. UI/UX and frontend-heavy work should prefer `World-Class Product Architect`.
5. Strategy and market decisions should prefer `Executive Trinity`.
6. Regulated or unfamiliar industry architecture should prefer `Omni-Architect`.
7. General implementation and backend design should prefer `Technical Trinity`.
8. Add or elevate `Sentinel Architect (NB)` for high-risk or research-first work.
