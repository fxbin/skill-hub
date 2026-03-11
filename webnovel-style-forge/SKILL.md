---
name: webnovel-style-forge
description: Extract, compare, and iteratively refine webnovel writing style prompts. Use this skill when the user wants to imitate a specific webnovel author or book style, reduce obvious AI prose, turn sample chapters into reusable style prompts, or run repeated comparison rounds between generated prose and target text.
---

# Webnovel Style Forge

Use this skill to turn webnovel style analysis into reusable prompting and iterative refinement.

## When To Use

Use `webnovel-style-forge` when the user wants to:

- imitate the prose style of a specific webnovel, author, or chapter set
- extract stable style traits from multiple sample chapters
- reduce obvious AI writing smell in generated prose
- compare generated prose against target text and refine the style prompt
- build a reusable style prompt block for later drafting workflows

## Core Goal

The goal is not to summarize plot. The goal is to isolate how the writing works:

- sentence movement
- dialogue rhythm
- narration density
- character voice
- detail placement
- pacing and scene pressure
- anti-AI cleanup patterns

## Inputs

Prefer:

- at least 3 sample chapters from the same author or work
- non-consecutive samples when possible
- a current generated draft if the user wants refinement
- a target reference excerpt for side-by-side comparison

If the user wants iterative tempering, ask for:

- current generated version such as `v1.txt`
- target text such as `target.txt`

## Resources

Read only what is needed:

- [style-tempering-method.md](references/style-tempering-method.md) for the full iterative method and prompt framing
- [example-output.md](references/example-output.md) for a concrete output pattern
- [anti-ai-checklist.md](references/anti-ai-checklist.md) when the draft still sounds obviously synthetic

## Workflow

### 1. Prepare the samples

- prefer multiple non-consecutive excerpts
- avoid overfitting to one scene or one plot beat
- check whether the source material itself has large internal style shifts

### 2. Extract a first-pass style profile

Analyze expression rather than story:

- sentence construction
- narration stance
- dialogue design
- character portrayal
- sensory and domestic detail usage
- pacing and transition habits

The first pass should produce a usable draft prompt, not a perfect one.

### 3. Establish a no-style baseline

Before using the style prompt, generate one plain baseline draft from the same outline or scene setup.

Use that baseline to identify common AI weaknesses such as:

- excessive explanation
- generic emotional phrasing
- flattened dialogue
- repetitive sentence cadence
- over-obvious summary language

### 4. Test the first style prompt

Generate a styled draft with the same scene setup.

Do not assume success on the first round. The purpose is to expose the gap between:

- target text
- generated baseline
- generated styled draft

### 5. Run iterative comparison

Compare current generated output against target text at the expression layer only.

Focus on:

- what the target does better
- where the generated draft still sounds synthetic
- which style constraints are still too vague
- which prompt instructions are overbroad or decorative

Translate those gaps into the next prompt revision.

### 6. Repeat until useful

Each round should:

1. generate a new draft
2. compare it with target text
3. identify the biggest remaining style gap
4. update the prompt with concrete, reusable constraints

Stop when:

- the prompt is consistently producing usable prose
- further changes are only subjective preference tuning
- model variance becomes larger than the gains from prompt edits

## Key Principles

### Analyze expression, not plot

Do not over-index on story beats, setting facts, or character events. Focus on reusable writing mechanics.

### Comparison is better than abstract praise

Prefer concrete differences between generated prose and target prose over vague judgments like "more vivid" or "more immersive."

### Prompts must be executable

Write instructions as usable constraints:

- what to do
- what to avoid
- what to emphasize

Avoid non-operational language such as "make it more flavorful."

### Fix only a few deltas per round

Do not rewrite the whole style prompt every iteration. Focus on the most important gaps first.

## Output Format

Return results in this structure:

1. `Style diagnosis`
2. `Extracted style traits`
3. `Refinement suggestions`
4. `Reusable style prompt`
5. `Next test recommendation`

## Risks And Limits

- style prompts may not transfer cleanly across models
- too few samples can cause overfitting to plot instead of style
- unstable source material leads to unstable prompt guidance
- prose quality also depends on outline quality, character setup, and scene constraints
