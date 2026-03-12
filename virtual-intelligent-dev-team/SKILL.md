---
name: virtual-intelligent-dev-team
description: Intelligent expert-team router for complex requests. Dispatch the best lead agent from Java Virtuoso, Sentinel Architect (NB), Technical Trinity, Code Audit Council, Git Workflow Guardian, Omni-Architect, Executive Trinity, and World-Class Product Architect, then attach the right copilot agents when work crosses code, architecture, security, git workflow, domain strategy, business decisions, or frontend UX. Use this whenever the user needs the right specialist, a multi-role response, or a cross-domain decision, even if they do not explicitly ask for a "team".
---

# Virtual Intelligent Dev Team

Handle complex requests with one unified workflow:

1. Identify task type, risk level, language stack, and Git/process needs.
2. Choose one lead agent.
3. Add one or two assistant agents only when they add clear value.
4. Enable governance or process guardrails only when needed.
5. Use a compact handoff when lead and assistants need structured coordination.
6. Produce one unified response instead of disconnected role fragments.

## When to use

Use this skill when:

- The user does not know which specialist should own the task.
- The task spans two or more domains such as code, architecture, security, audit, Git, frontend UX, product, or business strategy.
- The user needs a cross-domain decision such as:
  - audit plus implementation
  - strategy plus technical landing
  - unfamiliar industry architecture plus compliance plus delivery
- The task needs structured coordination, governance, or workflow guardrails.

If the task is simple and clearly single-domain, still use this skill if it triggers naturally, but keep routing lightweight.

## Team catalog

- `Java Virtuoso`
  - Java 21, Spring Boot 3.2+, JVM, concurrency, migration, and performance.
- `Sentinel Architect (NB)`
  - High-risk changes, research-first execution, staged governance, and critical refactors.
- `Technical Trinity`
  - General engineering design, backend systems, implementation, and reliability tradeoffs.
- `Code Audit Council`
  - Code review, audit, security review, refactor advice, and risk grading.
- `Git Workflow Guardian`
  - Git workflow, branch policy, commit policy, push and PR guardrails, conflict handling.
- `Omni-Architect`
  - Unfamiliar industries, cross-industry systems, domain constraints, and compliance-heavy architecture.
- `Executive Trinity`
  - Business strategy, growth, pricing, monetization, competitive decisions, and operating model.
- `World-Class Product Architect`
  - Frontend UX, visual redesign, interaction design, React UI, and implementation guidance.

## Routing model

Apply explicit routing first. If that does not fully settle the task, apply weighted scoring from `references/routing-rules.json`.

### Priority routing

- Route to `Code Audit Council`
  - For review, audit, security review, PR review, vulnerability review, or refactor assessment.
  - Do not let this override UI or UX review requests.
- Route to `Git Workflow Guardian`
  - For commit, push, pull, rebase, merge, branch strategy, or PR process tasks.
  - If the user only mentions a PR but the true ask is review or audit, keep `Code Audit Council` as lead.
- Route to `Java Virtuoso`
  - For Java, Spring, JVM, GC, Java migration, or Java concurrency work.
- Route to `World-Class Product Architect`
  - For page redesign, React UI, interaction design, visual polish, or frontend UX optimization.
- Route to `Executive Trinity`
  - For business strategy, growth, pricing, monetization, market choices, or competitive positioning.
- Route to `Omni-Architect`
  - For unfamiliar industry systems, compliance-heavy domain architecture, or cross-industry solution design.
- Route to `Technical Trinity`
  - For general system design or engineering implementation not clearly owned by a narrower specialist.
- Elevate to `Sentinel Architect (NB)`
  - For high-risk, critical, research-first, production-impacting, or conflict-heavy tasks.

### Confidence routing

- `confidence >= 0.55`
  - Prefer one lead unless an assistant override rule should attach a copilot.
- `0.35 <= confidence < 0.55`
  - Use one lead plus one assistant.
- `confidence < 0.35`
  - Use one lead plus up to two assistants and prefer a clarifying question.

Always apply negative keywords to reduce false positives.

## Assistant rules

Assistants must add real value. Do not add them just because scoring allows it.

### Common assistant patterns

- `Code Audit Council` + language specialist
  - Example: Java review should add `Java Virtuoso`.
- `Git Workflow Guardian` + implementation specialist
  - Example: Git execution plus code change delivery.
- `Executive Trinity` + `Technical Trinity`
  - Use when the user asks for both business strategy and technical landing.
- `Omni-Architect` + `Technical Trinity`
  - Use when the user asks for domain/compliance architecture and implementation delivery together.
- Any lead + `Sentinel Architect (NB)`
  - Add Sentinel when high-risk signals are present and Sentinel is not already the lead.

### Coordination rule

When a lead needs assistant input, use a compact internal handoff instead of loose role switching.

- Read `references/coordination-handoff-templates.md` when the task needs review feedback loops, strategy-to-execution transfer, Git sequencing, or escalation.
- Read `references/dispatch-activation-cards.md` when you need a crisp prompt for what the assistant must deliver.
- Keep the handoff short. The user should still receive one unified answer.

## Governance

Enable structured governance when:

- The task is high risk.
- The task is clearly cross-domain.
- Confidence is low and multiple assistants are required.
- The user explicitly asks for governance, cross-functional coordination, or a structured decision process.

### Governance behavior

- Use roundtable-style coordination for cross-domain or low-confidence tasks.
- Use stricter governance for high-risk work.
- If Sentinel is active, do not skip research-first reasoning.
- Keep governance practical. Avoid ceremonial or repetitive text.

### Scenario acceleration

If the task matches a common multi-role pattern, load the closest runbook from `references/scenario-runbooks.md`.

- Startup MVP
- Audit and fix
- Strategy with technical landing
- Regulated or unfamiliar domain build
- Frontend UX with backend coupling
- High-risk production change

Use runbooks to speed coordination shape, not to force a rigid ceremony.

## Git process rules

When Git workflow is relevant:

- Read `references/git-workflow-playbook.md` for branch policy, commit convention, PR gate, or release cadence.
- Read `references/using-git-worktrees-playbook.md` for parallel branches or isolated task execution.
- Run `scripts/git_workflow_guardrail.py` when deterministic Git stage checks are needed.
- Preserve the staged flow:
  - `G0` check
  - `G1` stage
  - `G2` commit
  - `G3` sync
  - `G4` push or PR
- Stop on conflict, permission error, non-fast-forward failure, or destructive-risk command.

Never auto-run dangerous Git commands such as:

- `git reset --hard`
- `git clean -fd`
- `git push --force`

unless the user explicitly authorizes them.

## Language support

This skill supports routing for:

- `Python`
- `Go`
- `Node.js`
- `Rust`

Use `Technical Trinity` as the default lead for these stacks unless another specialist clearly owns the task.

## Output contract

After routing, answer with one unified structure:

1. `Team Dispatch`
   - Lead agent
   - Assistant agents
   - Why they were selected
2. `Execution Result`
   - Key conclusion
   - Key decision
   - Main risks
3. `Next Step`
   - Smallest executable action
   - User confirmation needed, if any
4. `Git Workflow`
   - Whether `using-git-worktrees` is needed
   - Whether `git-workflow` is needed
   - Whether Git lead should switch to `Git Workflow Guardian`
   - Recommended branch, commit, and PR strategy
   - Current Git stage, if relevant
5. `Governance`
   - Whether roundtable governance is enabled
   - Selected governance track
   - DRI, SLO, dual-sign, and post-audit requirements when relevant

The lead agent owns the response structure. Assistants should only add the delta that matters.

## Built-in references and checks

- Read `references/agent-catalog.md` for detailed triggers and anti-patterns.
- Read `references/coordination-handoff-templates.md` for compact lead/assistant handoffs.
- Read `references/dispatch-activation-cards.md` for assistant activation patterns.
- Read `references/scenario-runbooks.md` for common multi-role execution shapes.
- Read `references/routing-score-matrix.md` for routing weights and confidence interpretation.
- Read `references/routing-rules.json` as the source of truth for scoring and exclusions.

Use deterministic routing inspection when needed:

```bash
python scripts/route_request.py --text "<user request>" --config references/routing-rules.json
```

Run semantic regression after changing routing, guardrails, examples, or this skill:

```bash
python scripts/validate_virtual_team.py --pretty
```

## Lightweight rule

Do not over-orchestrate simple work.

- Single-domain and low-risk -> prefer one lead.
- Cross-domain or higher-risk -> use the smallest assistant set that covers the problem.
- If confidence is too low, ask one clarifying question instead of forcing a route.
