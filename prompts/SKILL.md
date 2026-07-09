---
name: llm-council
description: Simulates a council of distinct analytical perspectives that independently answer a hard question, cross-review each other, then synthesize one final recommendation. Use for high-stakes decisions, tradeoff-heavy questions, or explicit requests for multiple perspectives or a second opinion.
---

# LLM Council (Single-Model Deliberation)

## What this is
Inspired by multi-model "council" tools (e.g. querying GPT, Gemini, Grok, Claude in parallel via an API and having them cross-review each other). This version runs on a single Claude model with no external API keys, simulating the same deliberative process through distinct personas, independent generation, and structured synthesis.

**Disclose this limitation the first time the skill runs in a conversation:** this is one model reasoning from several independent angles, not literally different AI models. It reduces single-shot bias and surfaces disagreement, but it is not a substitute for genuinely diverse model architectures.

## When to use
Trigger this skill when the user:
- Explicitly asks to "use the council", "pakai council", "minta pendapat dewan", or similar
- Asks for "multiple perspectives", "second opinion", or to "sanity check" a decision
- Poses a genuinely hard tradeoff question (career choice, architecture decision, a risky claim, a big purchase, etc.) and wants a thorough take

Do not trigger for simple factual questions, quick lookups, or casual chat — that just adds noise.

## Workflow

### Step 1 — Define the council
Pick 3-4 personas suited to the actual question. Default general-purpose set:
1. **The Pragmatist** — optimizes for what's actually achievable given real-world constraints (time, money, risk tolerance)
2. **The Skeptic** — actively looks for flaws, unstated assumptions, and reasons the obvious answer might be wrong
3. **The Domain Specialist** — applies deep technical or field-specific knowledge to the question
4. **The Long-Game Strategist** — weighs second-order effects and how this decision looks in 1-3 years

Swap in more relevant personas when the question calls for it (e.g. a financial decision might want Pragmatist, Risk Analyst, Contrarian, Long-Game Strategist instead).

### Step 2 — Independent answers
Answer the question once as each persona, without letting later personas see or react to earlier ones. Keep each answer focused (roughly 150-250 words), opinionated, and grounded in that persona's lens — no hedging into mush. Label clearly, e.g.:

**Council Member 1 — The Pragmatist**
[answer]

**Council Member 2 — The Skeptic**
[answer]

(and so on)

### Step 3 — Cross-review
After all answers are drafted, review them as a group. For each one, note in 1-2 sentences: the strongest point, and the weakest or most disputable point. Explicitly flag where members agree and where they genuinely conflict — the conflict is the useful signal, don't paper over it.

### Step 4 — Chairman synthesis
Write a final synthesized recommendation, framed as the Chairman:
- State the actual recommendation clearly
- Explain which persona's reasoning carried the most weight, and why
- Name explicitly what is being traded off or given up by that choice
- If the personas genuinely couldn't be reconciled, say so plainly and state what information would resolve it

### Step 5 — Disclose
Close with a one-line reminder that this was a single model examining the question from multiple angles, not independent models — treat it as structured self-critique rather than true model diversity.

## Notes
- Use headers and bold labels so council members are easy to visually tell apart.
- If the user pushes back on the synthesis, treat that as new input for the Chairman to revise — don't re-run the whole council from scratch.
- Skip this skill for trivial or time-sensitive queries where a direct answer serves the user better.
