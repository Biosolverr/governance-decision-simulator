## Purpose

The AI Governance Decision Simulator is a GenLayer Intelligent Contract that
turns a DAO governance proposal into a decision support report: a set of
plausible future scenarios, never a recommendation, score, or vote.

It exists to demonstrate three GenLayer specific capabilities in one
concrete, useful project:

1. Nondeterministic execution: LLM calls that legitimately produce
   different text across runs and validators.
2. Validator consensus over AI generated reasoning, using
   `gl.eq_principle.prompt_comparative` instead of strict equality, since
   scenario wording naturally differs between validators even when the
   underlying reasoning is sound.
3. On chain structured decision support: a smart contract that reasons
   about the future rather than just executing deterministic rules.

## Pipeline

```
Proposal (raw text)
      |
      v
[1] Proposal Parser        -> structured parameters
      |                        (percent change, from/to, $ amount)
      v
[2] Proposal Classifier    -> category (10 types) + compound flag
      |
      v
[3] Simulation Prompt Builder -> category specific nondet prompt,
      |                          with prompt injection mitigation
      v
[4] Scenario Generator     -> gl.eq_principle.prompt_comparative(fn, principle)
      |                        fn: zero argument nondet LLM call
      |                        GenVM runs fn once for the leader, once
      |                        per validator, and has each validator
      |                        judge its own result against the
      |                        leader's via NLP using `principle`
      v
[5] Scenario Normalizer    -> fill missing fields, clamp risk severity
      |                        and likelihood, dedupe/merge similar
      |                        scenarios (Jaccard similarity, no LLM),
      |                        flag it if the result drops below 3
      v
[6] Risk & Assumption Engine -> fallback risk/assumption injection,
      |                          cross scenario recurrence aggregation
      v
[7] Consensus Layer        -> consensus_scenarios / minor_differences /
      |                        unique_insights bucketing
      v
[8] Simulation Report Builder -> final structured JSON report
      |
      v
Returned to caller, stored on chain, and folded into the running
per category counters (category_counts, category_confidence_totals)
```

Stages 1, 2, and 5 through 8 are fully deterministic (no LLM call, cheap,
safe to run on every validator without consensus concerns). Only stage 4 is
nondeterministic, and it is the only place
`gl.eq_principle.prompt_comparative` is used.

`simulate_proposal`, `simulate_proposal_with_reference`, and
`simulate_variant` all run this exact same pipeline through a single shared
internal method, `_run_pipeline_and_store`, so the three entry points never
drift apart from one another.

## Why `prompt_comparative`, not `strict_eq`

Two validators independently calling the same LLM prompt will produce
different scenario titles, different phrasing, sometimes a different number
of scenarios. `gl.eq_principle.strict_eq` would treat all of that as
disagreement and return `UNDETERMINED` almost every time.

An earlier version of this contract's `principle` asked validators only
"is this a similarly structured JSON scenario set?". That checks that the
leader formatted its answer correctly, but not whether the answer is
actually sound. That is the "leader output only validation" anti pattern
the GenLayer equivalence principle docs warn against: a validator that only
checks a result for a valid JSON shape is not performing real consensus.
Two validators could return scenario sets that directly contradict each
other on substance (one says treasury runway improves, the other says it
collapses) and both would still pass, because only the JSON shape was being
compared.

The current `principle` instead asks validators to judge substantive
agreement on the parts of the output that function as decision fields:

- Neither output may approve, reject, score, or recommend the proposal.
- For each effect category both outputs cover, the net direction implied
  (positive, negative, neutral, or mixed) must not directly contradict the
  other output.
- Neither output may ignore a risk theme the other treats as
  high severity or major.

Titles, phrasing, exact scenario count, and which specific assumptions are
listed remain free to differ, since those are legitimately subjective.
`strict_eq` was never the right tool for them. This keeps the "do these two
outputs represent the same kind of reasoning" bar `prompt_comparative` is
good at, while removing the pure rubber stamp failure mode described above.

Its signature is `prompt_comparative(fn, principle)`: a zero argument
callable and a plain language equivalence principle. GenVM calls `fn` once
for the leader and once per validator internally, and handles the
leader vs validator comparison itself. The contract does not manually
orchestrate a leader/validator pair or call `gl.vm.run_nondet` directly for
this. An earlier draft of this contract called `prompt_comparative` with
3 positional arguments, mimicking a manual comparator. That crashed every
validator with a `TypeError` in live Studio testing before it was
corrected to the current 2 argument form.

## Report field: `principle_version`

Every report also carries a `principle_version` string
(`_EQUIVALENCE_PRINCIPLE_VERSION` in the contract), bumped whenever the
`principle` text above changes in a meaningful way. This makes it possible
to tell, just by reading a stored report, which consensus rules it was
accepted under. Reports generated under an older principle simply carry
an older version string; nothing is retroactively rewritten.

## Prompt injection mitigation

`proposal_text` is fully attacker controlled and is embedded inside the
LLM prompt. Two defenses are layered on top of the "STRICT RULES" block
that already instructs the model never to approve, score, or rank:

1. `_sanitize_for_prompt_embedding` strips the contract's own delimiter
   token if it appears inside the proposal text, and collapses long runs
   of quote, backtick, or dash characters, the most common patterns an
   injection attempt would lean on to fake a "new instruction block".
2. The prompt explicitly labels the proposal text block as untrusted
   user submitted data that cannot override the rules above it, even if
   it contains text that reads like a command.

This is defense in depth, not a formal guarantee. It raises the bar
against a casual injection attempt, it does not eliminate the risk of a
sufficiently creative one, and it has not yet been stress tested against
adversarial inputs on live Studionet validators.

## Storage layout

```python
owner: Address
simulations_count: u256
reports: TreeMap[u256, str]               # simulation_id -> full JSON report
proposals: TreeMap[u256, str]             # simulation_id -> original raw proposal text
category_counts: TreeMap[str, u256]       # category -> simulation count
max_proposal_length: u256                 # owner configurable input length cap, default 4000
source_references: TreeMap[u256, str]     # simulation_id -> external reference, if set
raw_llm_outputs: TreeMap[u256, str]       # simulation_id -> raw accepted LLM text
category_confidence_totals: TreeMap[str, str]  # category -> JSON encoded confidence totals
variant_of: TreeMap[u256, u256]           # variant simulation_id -> parent simulation_id
```

Reports are stored as JSON strings rather than typed nested structures,
since GenVM storage types don't support arbitrarily nested dicts and
lists. This also makes reports trivially returnable to any frontend as is.

Important: none of the TreeMap fields above are reassigned inside
`__init__`. GenVM zero initializes every declared storage field at deploy
time, so each TreeMap already exists as an empty instance of its own
specific generic type (`TreeMap[u256, str]`, `TreeMap[str, u256]`, and so
on) before `__init__` ever runs. An earlier version of this contract wrote
`self.category_counts = TreeMap()` (and similar lines) for every TreeMap
field in `__init__`, out of habit from plain Python classes. That crashed
every validator on deploy with:

```
AssertionError: Is right the same storage type? `TreeMap` <- `TreeMap`
```

The runtime could not match the newly constructed, generic-less
`TreeMap()`'s type descriptor against the specific generic instantiation
already bound to that storage slot. None of the official GenLayer examples
reassign a bare `TreeMap()` onto a `TreeMap`-typed field in `__init__`;
they simply leave it alone. `__init__` here only assigns the three
non-collection fields (`owner`, `simulations_count`, `max_proposal_length`)
and otherwise does nothing.

## Public methods

Write methods (each goes through `_run_pipeline_and_store`, except
`set_max_proposal_length` which touches no simulation data):

- `simulate_proposal(proposal_text)`: the main entry point.
- `simulate_proposal_with_reference(proposal_text, source_reference)`:
  identical pipeline, additionally records an external reference such as
  a Snapshot or Tally URL, retrievable via `get_source_reference`.
- `simulate_variant(simulation_id, new_percent)`: re-runs the pipeline on
  a copy of a previously stored proposal with its percentage swapped for
  `new_percent`, linked back to the original via `get_variant_parent`.
  `new_percent` is a string (for example `"12"` or `"7.5"`), not a float:
  GenVM's calldata type system has no float type, since floating point is
  not a safe, cross validator deterministic calldata primitive. Only
  int, bigint, str, bool, bytes, Address, and the DynArray/TreeMap
  collection types are supported. A `float` type hint on a public method
  parameter fails contract schema loading entirely rather than raising an
  ordinary Python error at call time.
- `set_max_proposal_length(new_max)`: owner only, adjusts the length cap
  enforced on every `proposal_text` without needing a redeploy.

Read methods:

- `get_simulations_count`, `get_report`, `get_proposal`, `get_owner`,
  `get_max_proposal_length`: direct accessors.
- `get_category_stats`: category to simulation count, from the
  incrementally maintained `category_counts` map.
- `list_recent_simulations(limit)`: newest first compact history, so a
  frontend does not need to fetch every full report individually.
- `get_source_reference(simulation_id)`, `get_variant_parent(simulation_id)`:
  accessors for the two linking maps above.
- `find_similar_simulations(category, limit)`: most recent simulations
  matching a category, scanning at most the most recent 1000 simulations
  regardless of `limit`, so cost stays bounded even with a long history.
- `get_confidence_trend(category)`: running confidence level totals for
  one category, from `category_confidence_totals`.
- `compare_simulations(id1, id2)`: deterministic diff between two stored
  reports (category match, confidence distribution, shared vs unique
  scenario titles). No LLM call, pure comparison of already agreed JSON.
- `get_normalizer_diff(simulation_id)`: compares the raw accepted LLM text
  against the final report, to show how many scenarios were merged or
  dropped by the Normalizer.
- `get_report_markdown(simulation_id)`: the same report rendered as
  readable Markdown, for pasting into a forum post or chat without a JSON
  parser.

## Hard constraints (enforced at multiple layers)

| Constraint | Enforced by |
|---|---|
| Never approve/reject | Never modeled as a field anywhere in the pipeline. There is no boolean or score field to set. This is a prompt level rule as well: nothing in the pipeline inspects generated text for accidental recommendation or score language, but the equivalence `principle` (see above) now also rejects any nondet result where either the leader or validator output did approve, reject, or score. |
| Never score/rank | `Scenario` has no numeric score field; `confidence` is qualitative (High/Medium/Low/Very Low), not a rank. |
| Resist prompt injection | See "Prompt injection mitigation" above. Defense in depth, not a hard guarantee. |
| At least 3 scenarios | The Prompt Builder explicitly requests at least 3. This is a request to the LLM, not a hard guarantee: the LLM can return fewer, and the Normalizer's similarity merge can, rarely, collapse distinct scenarios that share a default title or summary into one. Both cases are detected and surfaced as a `parser_warnings` entry on the report rather than failing silently. |
| Risk severity/likelihood stay in schema | `_normalize_single_risk` clamps `severity` to low/medium/high/critical and `likelihood` to low/medium/high, the same way `confidence` is clamped for the scenario as a whole. |
| Always explicit assumptions | The Risk & Assumption Engine injects a fallback assumption if the LLM omitted one. |
| Avoid false certainty | `disclaimer` field on every report; confidence is about internal consistency, not correctness (documented in the Scenario docstring). |
| Bounded per call cost | `max_proposal_length` (owner configurable, default 4000 characters) rejects an oversized `proposal_text` before any LLM call or state write happens. |

## Frontend

Single file `frontend/index.html` (deployed as a static site to Vercel),
using ephemeral `createAccount()` accounts (no wallet UI), following the
same pattern used in the earlier Decentralized Fact Checker project. Calls
`simulate_proposal` directly via `genlayer-js`, polls for the transaction
receipt, and renders the structured report (scenarios, effects, risks,
consensus summary) as cards. The proposal text field enforces the same
length cap client side as `max_proposal_length` defaults to on chain, with
a live character counter, so an oversized submission fails fast in the UI
rather than after a wasted transaction.

## Known limitations (by design, for a research proof of concept)

- The deterministic parser (regex based) can occasionally double count a
  percent value already captured by a from/to pair. This is harmless,
  since the LLM stage reasons over the raw text regardless.
- The Consensus Layer operates on the already agreed final scenario set,
  not on each individual validator's raw output. GenVM does not expose
  per validator raw results to the contract after consensus.
- Malformed or non JSON LLM output degrades gracefully (empty scenario
  list plus warning) rather than reverting the transaction.
- In earlier testing, `consensus_summary.areas_of_agreement` stayed empty
  across every run. The Consensus Layer looks for a recurring risk or
  assumption with matching text across scenarios, and with only 3 to 4
  LLM generated scenarios per run, an exact text match rarely happens
  even when scenarios are thematically related. This observation predates
  the current substantive `principle` and the risk normalization changes
  described above, and should be re-checked against fresh runs rather
  than assumed to still hold exactly as before.
- Prompt injection mitigation has not been stress tested against
  adversarial inputs on live Studionet validators. Treat it as raising
  the bar, not as a hardened guarantee.


