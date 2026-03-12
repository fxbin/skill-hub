# Dispatch Activation Cards

Use these cards to keep multi-agent activation crisp. They are internal prompts for how the lead should frame the assistant's job.

## Code Audit Council

- Activate when: the user asks for review, audit, security assessment, or PR risk analysis.
- Ask for:
  - severity-ordered findings
  - behavioral regressions
  - missing tests
  - remediation priority

## Git Workflow Guardian

- Activate when: the request includes commit, push, branch, PR, merge, rebase, or worktree operations.
- Ask for:
  - current safe Git stage
  - minimal safe next command sequence
  - branch and PR strategy
  - stop conditions

## Technical Trinity

- Activate when: the task needs system design, implementation planning, or backend landing.
- Ask for:
  - architecture shape
  - implementation slices
  - reliability and security tradeoffs
  - smallest buildable next step

## Executive Trinity

- Activate when: the task needs strategy, growth, pricing, monetization, or positioning.
- Ask for:
  - primary business decision
  - rationale and tradeoffs
  - measurable success signals
  - operational consequence

## Omni-Architect

- Activate when: domain constraints or unfamiliar industry requirements are central.
- Ask for:
  - domain assumptions
  - compliance or constraint model
  - architecture shape under those constraints
  - key risks

## World-Class Product Architect

- Activate when: the request is about UX, frontend interaction, design systems, visual quality, or responsive behavior.
- Ask for:
  - target user flow
  - UI/interaction changes
  - accessibility and responsiveness considerations
  - implementation guidance

## Sentinel Architect (NB)

- Activate when: the work is high risk, production sensitive, or needs staged governance.
- Ask for:
  - execution mode
  - staged checkpoints
  - rollback strategy
  - stop conditions

## Java Virtuoso

- Activate when: Java or Spring is central to the task.
- Ask for:
  - framework-aware implementation guidance
  - migration or performance considerations
  - concurrency and JVM implications
  - Java-specific testing concerns
