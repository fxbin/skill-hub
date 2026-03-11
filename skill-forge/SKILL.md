---
name: skill-forge
description: Build, repair, evaluate, and refine reusable skills end to end. Use this skill whenever the user wants to create a new skill, fix or rewrite an existing SKILL.md, generate agents/openai.yaml, add evals, run validation or benchmark loops, or improve a skill's triggering and iteration workflow.
---

# Skill Forge

Use this skill as the unified engineering workflow for reusable skills.

## When To Use

Use `skill-forge` when the user wants to:

- create a new skill scaffold
- repair or rewrite an existing skill
- normalize `SKILL.md`, frontmatter, `VERSION`, or `agents/openai.yaml`
- add `evals/evals.json` or a benchmark workflow
- validate a skill before commit
- improve a skill through review, regression, and iteration

## Positioning

`skill-forge` owns the full skill lifecycle:

1. define the skill boundary
2. scaffold the folder and metadata
3. write or repair the skill instructions
4. add eval prompts and validation
5. run benchmarks and review outcomes
6. iterate until the skill is stable

Do not treat this as only a scaffold generator. It is the project-local skill engineering entry point.

## Workflow

### 1. Capture intent and boundary

Clarify:

- what the skill should enable
- when it should trigger
- what good output looks like
- whether the work needs scripts, references, assets, evals, or benchmarks

Keep the skill focused. One skill should solve one coherent problem.

### 2. Initialize or repair the scaffold

Create a new skill:

```powershell
python skill-forge/scripts/init_skill.py skill-name --path .
```

Create a new skill with placeholder resources:

```powershell
python skill-forge/scripts/init_skill.py skill-name --path . --with-examples
```

Use repository rules explicitly:

```powershell
python skill-forge/scripts/init_skill.py skill-name --path . --config skill-forge/references/generic-skill-config.json
```

When updating an existing skill, preserve the directory name and frontmatter `name`.

### 3. Write or repair `SKILL.md`

The frontmatter must explain both function and trigger context.

Minimum shape:

```yaml
---
name: skill-name
description: What the skill does, when to use it, and which requests should trigger it.
---
```

The body should stay lean and practical. Prefer this structure:

```markdown
# Skill Name

One-sentence purpose.

## When To Use
- scenario 1
- scenario 2

## Workflow
1. clarify the task
2. load only relevant resources
3. produce the expected output

## Output
- conclusion
- key decisions
- risks
- next step
```

Move long references, templates, or deterministic helpers into `references/`, `assets/`, or `scripts/`.

### 4. Generate or refresh `agents/openai.yaml`

```powershell
python skill-forge/scripts/generate_openai_yaml.py ./skill-name
```

Override interface fields when needed:

```powershell
python skill-forge/scripts/generate_openai_yaml.py ./skill-name ^
  --interface display_name="My Skill" ^
  --interface short_description="Create and optimize this skill cleanly." ^
  --interface default_prompt="Use $my-skill to scaffold, validate, or refine this skill."
```

### 5. Add eval prompts

Every skill that supports objective checking should have `evals/evals.json`.

Initialize a starter eval file:

```powershell
python skill-forge/scripts/init_evals.py ./skill-name
```

Good eval prompts should be realistic, user-like, and cover:

- primary path
- edge cases
- mixed or ambiguous requests
- obvious regressions the skill must not reintroduce

### 6. Validate the skill

Quick validation:

```powershell
python skill-forge/scripts/quick_validate.py ./skill-name
```

Repository validation:

```powershell
python scripts/validate_skills.py
```

### 7. Run benchmark and review

Use the local benchmark runner to combine validation, eval structure checks, category summaries, and report generation:

```powershell
python skill-forge/scripts/run_skill_benchmarks.py ./skill-name --pretty ^
  --output ./skill-name/evals/benchmark-results.json ^
  --markdown-output ./skill-name/evals/benchmark-report.md
```

For iteration-to-iteration comparison:

```powershell
python skill-forge/scripts/run_skill_benchmarks.py ./skill-name ^
  --previous-output ./skill-name-workspace/iteration-2/benchmark-results.json ^
  --output ./skill-name/evals/benchmark-results.json ^
  --markdown-output ./skill-name/evals/benchmark-report.md
```

For repository-wide reporting:

```powershell
python skill-forge/scripts/generate_skill_portfolio_report.py . ^
  --output ./skill-forge/evals/portfolio-report.json ^
  --markdown-output ./skill-forge/evals/portfolio-report.md
```

For richer review loops, create a sibling workspace such as:

```text
my-skill-workspace/
  iteration-1/
  iteration-2/
```

Within each iteration, compare current outputs against a baseline, keep `eval_metadata.json`, and summarize what improved or regressed.

### 8. Iterate with evidence

When improving a skill:

- generalize from user feedback instead of overfitting to one prompt
- remove prompt weight that does not change outcomes
- explain why instructions matter instead of writing rigid rules everywhere
- convert repeated manual work into scripts when it clearly recurs

## Evaluation Guidance

Use both qualitative and quantitative signals.

Quantitative checks:

- does the skill validate
- does it have eval prompts
- do benchmark runs pass
- do eval categories cover the skill lifecycle
- does the benchmark report expose per-eval status
- do trigger descriptions stay within constraints

Qualitative checks:

- is the skill readable
- does the workflow feel coherent
- are the outputs stable across similar prompts
- does the skill avoid bloated or contradictory instructions

## Output Contract

When working on a skill, prefer to return:

1. a short assessment of current issues
2. the concrete files updated
3. validation or benchmark results
4. remaining risks and the next improvement step

## Resources

Read only what is needed:

- [configuration.md](references/configuration.md)
- [generic-skill-config.json](references/generic-skill-config.json)
- [openai_yaml.md](references/openai_yaml.md)
