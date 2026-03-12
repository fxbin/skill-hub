# Coordination Handoff Templates

Use these templates when a lead agent needs structured input from one or more assistants. Keep them short and concrete. They are coordination aids, not user-facing ceremony.

## 1. Standard Lead-to-Assistant Handoff

```markdown
## Handoff
- From: [Lead agent]
- To: [Assistant agent]
- Task slice: [Specific subproblem]
- Why this agent: [Why this agent is needed]
- Current context:
  - Goal: [Primary user outcome]
  - Constraints: [Technical, timeline, risk, policy]
  - Relevant files or systems: [Paths or components]
- Deliverable requested:
  - Needed output: [Decision, findings, design delta, Git step, etc.]
  - Acceptance criteria:
    - [Criterion 1]
    - [Criterion 2]
- Return format:
  - Summary:
  - Risks:
  - Recommendation:
```

## 2. Audit Feedback Loop

Use when `Code Audit Council` reviews work owned by another lead.

```markdown
## Audit Feedback
- Reviewer: Code Audit Council
- Owner: [Lead or implementation specialist]
- Verdict: [PASS / FAIL / PASS WITH RISKS]
- Highest-severity finding: [One-line summary]
- Findings:
  - [Severity] [Issue]
  - [Severity] [Issue]
- Required fixes before ship:
  - [Fix 1]
  - [Fix 2]
- Evidence needed for closure:
  - [Test, diff, benchmark, screenshot, proof]
```

## 3. Git Execution Handoff

Use when `Git Workflow Guardian` needs to control sequencing while another agent owns the code change.

```markdown
## Git Handoff
- Lead owner: [Feature/review agent]
- Git owner: Git Workflow Guardian
- Current stage: [G0 / G1 / G2 / G3 / G4]
- Target branch strategy: [branch/worktree/pr plan]
- Preconditions:
  - [State check]
  - [Tests or review state]
- Safe next step:
  - [Exact minimal action]
- Stop conditions:
  - [Conflict]
  - [Permission issue]
  - [Non-fast-forward]
```

## 4. Strategy-to-Execution Handoff

Use when `Executive Trinity` or `Omni-Architect` needs `Technical Trinity` to land the plan.

```markdown
## Strategy to Execution
- Strategy owner: [Executive Trinity / Omni-Architect]
- Execution owner: Technical Trinity
- Business or domain decision:
  - [Chosen direction]
- Technical landing requested:
  - [Architecture or implementation slice]
- Non-negotiable constraints:
  - [Budget, compliance, delivery, product]
- Expected output:
  - System shape
  - Delivery phases
  - Main risks
```

## 5. Escalation Snapshot

Use only when risk, ambiguity, or disagreement is high enough to justify stronger governance.

```markdown
## Escalation Snapshot
- Trigger: [Why normal routing is insufficient]
- Lead agent: [Current lead]
- Assistants involved: [List]
- Open conflict or uncertainty:
  - [Decision or risk]
- Options considered:
  - [Option A]
  - [Option B]
- Decision needed:
  - [What must be decided now]
- Recommended governance mode:
  - [Roundtable / Sentinel-led staged execution]
```
