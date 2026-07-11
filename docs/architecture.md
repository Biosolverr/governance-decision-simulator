# Architecture

## Purpose

The AI Governance Decision Simulator is a GenLayer Intelligent Contract that
turns a DAO governance proposal into a **decision-support report**: a set of
plausible future scenarios, never a recommendation, score, or vote.

It exists to demonstrate three GenLayer-specific capabilities in one
concrete, useful project:

1. **Nondeterministic execution** — LLM calls that legitimately produce
   different text across runs/validators.
2. **Validator consensus over AI-generated reasoning** — using
   `gl.eq_principle.prompt_comparative` instead of strict equality, since
   scenario wording naturally differs between validators even when the
   underlying reasoning is sound.
3. **On-chain structured decision support** — a smart contract that reasons
   about the future rather than just executing deterministic rules.

## Pipeline

```
Proposal (raw text)
      |
      v
[1] Proposal Parser  ───────────► structured parameters
      |                            (percent change, from/to, $ amount)
      v
[2] Proposal Classifier ───────► category (10 types) + compound flag
      |
      v
[3] Simulation Prompt Builder ─► category-specific nondet prompt
      |
      v
[4] Scenario Generator ────────► gl.eq_principle.prompt_comparative(fn, principle)
      |                            fn: zero-argument nondet LLM call
      |                            GenVM runs fn once for the leader, once
      |                            per validator, and has each validator
      |                            judge its own result against the
      |                            leader's via NLP using `principle`
      v
[5] Scenario Normalizer ───────► fill missing fields, dedupe/merge similar
      |                            scenarios (Jaccard similarity, no LLM)
      v
[6] Risk & Assumption Engine ──► fallback risk/assumption injection,
      |                            cross-scenario recurrence aggregation
      v
[7] Consensus Layer ────────────► consensus_scenarios / minor_differences /
      |                            unique_insights bucketing
      v
[8] Simulation Report Builder ─► final structured JSON report
      |
      v
Returned to caller + stored on-chain (TreeMap[u256, str])
```

Modules 1-2 and 5-8 are fully deterministic (no LLM call, cheap, safe to run
on every validator without consensus concerns). Only module 4 is
nondeterministic, and it's the only place `gl.eq_principle.prompt_comparative`
is used.

## Why `prompt_comparative`, not `strict_eq`

Two validators independently calling the same LLM prompt will produce
different scenario titles, different phrasing, sometimes a different number
of scenarios. `gl.eq_principle.strict_eq` would treat all of that as
disagreement and return `UNDETERMINED` almost every time. `prompt_comparative`
instead asks: *"do these two outputs represent the same kind of reasoning,
in a similar structural shape?"* — which is the actual bar we want for
accepting a nondet LLM result on-chain.

Its signature is `prompt_comparative(fn, principle)`: a zero-argument
callable and a plain-language equivalence principle. GenVM calls `fn` once
for the leader and once per validator internally and handles the
leader-vs-validator comparison itself — the contract does not manually
orchestrate a leader/validator pair or call `gl.vm.run_nondet` directly for
this. (An earlier draft of this contract did call it with 3 positional
arguments, mimicking a manual comparator — that crashed every validator
with a `TypeError` in live Studio testing; see `demo/proof.json` for the
corrected, working transactions.)

## Storage layout

```python
owner: Address
simulations_count: u256
reports: TreeMap[u256, str]     # simulation_id -> full JSON report
proposals: TreeMap[u256, str]   # simulation_id -> original raw proposal text
```

Reports are stored as JSON strings rather than typed nested structures,
since GenVM storage types don't support arbitrarily nested dicts/lists —
this also makes reports trivially returnable to any frontend as-is.

## Hard constraints (enforced at multiple layers)

| Constraint | Enforced by |
|---|---|
| Never approve/reject | Never modeled as a field anywhere in the pipeline — there is no boolean/score field to set |
| Never score/rank | `Scenario` has no numeric score field; `confidence` is qualitative (High/Medium/Low/Very Low), not a rank |
| Always multiple scenarios | Prompt Builder explicitly requires ≥3; Normalizer merges but never reduces below what the LLM returned as distinct threads |
| Always explicit assumptions | Risk & Assumption Engine injects a fallback assumption if the LLM omitted one |
| Avoid false certainty | `disclaimer` field on every report; confidence is about internal consistency, not correctness (documented in Scenario docstring) |

## Frontend

Single-file `frontend/index.html` (deployed as a static site to Vercel),
using ephemeral `createAccount()` accounts (no wallet UI), following the
same pattern used in the earlier Decentralized Fact Checker project. Calls
`simulate_proposal` directly via `genlayer-js`, polls for the transaction
receipt, and renders the structured report (scenarios, effects, risks,
consensus summary) as cards.

## Known limitations (by design, for a research PoC)

- The deterministic parser (regex-based) can occasionally double-count a
  percent value already captured by a from/to pair — harmless, since the
  LLM stage reasons over the raw text regardless.
- The Consensus Layer operates on the already-agreed final scenario set,
  not on each individual validator's raw output — GenVM does not expose
  per-validator raw results to the contract after consensus.
- Malformed/non-JSON LLM output degrades gracefully (empty scenario list +
  warning) rather than reverting the transaction.
- In practice (see `demo/proof.json`), `consensus_summary.areas_of_agreement`
  has stayed empty across all test runs so far — the Consensus Layer looks
  for a recurring risk/assumption with matching text across scenarios, and
  with only 3-4 LLM-generated scenarios per run, an exact text match rarely
  happens even when scenarios are thematically related. This is a real,
  observed behavior of the current implementation, not a hypothetical edge
  case.
