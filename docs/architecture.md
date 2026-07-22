## Purpose

The AI Governance Decision Simulator is a GenLayer Intelligent Contract that
turns a DAO governance proposal into a decision support report: a set of
plausible future scenarios, never a recommendation, score, or vote.

It exists to demonstrate four GenLayer specific capabilities in one
concrete, useful project:

1. Nondeterministic execution: LLM calls that legitimately produce
   different text across runs and validators.
2. Validator consensus over AI generated reasoning, using
   `gl.eq_principle.prompt_comparative` instead of strict equality, since
   scenario wording naturally differs between validators even when the
   underlying reasoning is sound.
3. On chain structured decision support: a smart contract that reasons
   about the future rather than just executing deterministic rules.
4. Optional real-world grounding: an owner-configurable, independently
   fetched external data source that anchors the LLM's reasoning in
   current facts instead of pure assumption, reconciled across
   validators the same way the LLM output is.

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
[3] On-chain Context Fetcher -> optional real-data grounding
      |                          (treasury category only, proof of
      |                          concept). gl.eq_principle.prompt_comparative
      |                          with a numeric-tolerance principle;
      |                          skipped entirely (context = None) unless
      |                          the owner has enabled it and configured
      |                          a data source for this category
      v
[4] Simulation Prompt Builder -> category specific nondet prompt,
      |                          with prompt injection mitigation and,
      |                          if available, the fetched context framed
      |                          as trusted ground truth
      v
[5] Scenario Generator     -> gl.eq_principle.prompt_comparative(fn, principle)
      |                        fn: zero argument nondet LLM call
      |                        GenVM runs fn once for the leader, once
      |                        per validator, and has each validator
      |                        judge its own result against the
      |                        leader's via NLP using `principle`
      v
[6] Scenario Normalizer    -> fill missing fields, clamp risk severity
      |                        and likelihood, dedupe/merge similar
      |                        scenarios (Jaccard similarity, no LLM),
      |                        flag it if the result drops below 3
      v
[7] Risk & Assumption Engine -> fallback risk/assumption injection,
      |                          cross scenario recurrence aggregation
      v
[8] Consensus Layer        -> consensus_scenarios / minor_differences /
      |                        unique_insights bucketing
      v
[9] Simulation Report Builder -> final structured JSON report
      |
      v
Returned to caller, stored on chain, and folded into the running
per category counters (category_counts, category_confidence_totals)
```

Stages 1, 2, 6, 7, 8, and 9 are fully deterministic (no LLM call, cheap,
safe to run on every validator without consensus concerns). Stages 3 and
5 are the only nondeterministic ones, and the only two places
`gl.eq_principle.prompt_comparative` is used, each with its own
equivalence principle tuned to what it is comparing.

`simulate_proposal`, `simulate_proposal_with_reference`, and
`simulate_variant` all run this exact same pipeline through a single shared
internal method, `_run_pipeline_and_store`, so the three entry points never
drift apart from one another.

## Why `prompt_comparative`, not `strict_eq`

Two validators independently calling the same LLM prompt will produce
different scenario titles, different phrasing, sometimes a different number
of scenarios. `gl.eq_principle.strict_eq` would treat all of that as
disagreement and return `UNDETERMINED` almost every time.

An earlier version of this contract's scenario `principle` asked
validators only "is this a similarly structured JSON scenario set?". That
checks that the leader formatted its answer correctly, but not whether the
answer is actually sound. That is the "leader output only validation"
anti pattern the GenLayer equivalence principle docs warn against: a
validator that only checks a result for a valid JSON shape is not
performing real consensus. Two validators could return scenario sets that
directly contradict each other on substance (one says treasury runway
improves, the other says it collapses) and both would still pass, because
only the JSON shape was being compared.

The current scenario `principle` instead asks validators to judge
substantive agreement on the parts of the output that function as
decision fields:

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

## On-chain context grounding (proof of concept, treasury category only)

Every simulation up to this point reasoned purely from `proposal_text`:
the LLM had no anchor in the DAO's actual current financial position, only
its own assumptions about what a plausible treasury might look like. This
module adds an optional, owner-configured step (stage 3 above) that
fetches real data before the prompt is built.

**Why a second, separate `prompt_comparative` call, with its own
principle.** The scenario generator's principle (above) judges whether
two pieces of AI reasoning are substantively compatible. The context
fetch is not AI reasoning at all, it is a raw external data read, but it
still needs cross-validator reconciliation, because the data source is
live and will not return byte-identical values to the leader and to each
validator a few seconds later (a real balance moves). `strict_eq` would
fail almost every time, for a completely different reason than it would
fail on LLM text. So this needed its own principle, tuned for numeric
tolerance rather than semantic equivalence:

> Both texts are JSON snapshots of the same treasury data source, fetched
> moments apart by different validators. They are EQUIVALENT only if:
> (1) both are valid JSON objects containing `treasury_balance_usd`,
> `monthly_spend_usd`, and `runway_months`; (2) each of those three
> numeric fields differs by no more than 5% between the two readings, or
> by no more than 1 unit for `runway_months` specifically; (3) neither
> text is an error message, empty object, or placeholder where the other
> is a real reading. Field ordering, extra fields, formatting, or a
> timestamp do not count as disagreement.

**Degrades gracefully by design.** `_fetch_onchain_context` never raises
and never blocks `simulate_proposal`. If the category has no fetcher
wired up, the owner hasn't configured a URL, the network call itself
fails, or the response does not parse into the expected shape, the method
returns `(None, [warning])` and the pipeline proceeds exactly as if this
feature did not exist, with a `parser_warnings` entry noting what
happened. `onchain_context_used` on the report is `False` in every one of
those cases.

**Confirmed live**, not just designed on paper: with the feature enabled
and pointed at a public JSON snapshot (`treasury_balance_usd: 4200000,
monthly_spend_usd: 175000, runway_months: 24`), a real `simulate_proposal`
call produced scenarios that computed directly off those numbers, for
example deriving a new runway as `4200000 / 192500` after applying the
proposal's own 10% spend increase, rather than inventing unrelated
figures. The Equivalence Principle output for that transaction shows the
raw fetched JSON exactly as configured, confirming each validator
genuinely re-fetched the URL itself rather than trusting the leader's
value.

**Extending beyond treasury.** `_ONCHAIN_CONTEXT_FETCHERS` maps a category
name to `(data-source field name, parser function)`. Adding another
grounded category is adding one entry there plus a matching parser
function; `_fetch_onchain_context`, `build_simulation_prompt`, and
`_run_pipeline_and_store` need no changes.

## Report field: `principle_version`

Every report also carries a `principle_version` string
(`_EQUIVALENCE_PRINCIPLE_VERSION` in the contract), bumped whenever the
scenario `principle` text changes in a meaningful way. This makes it
possible to tell, just by reading a stored report, which consensus rules
it was accepted under. Reports generated under an older principle simply
carry an older version string; nothing is retroactively rewritten. The
context-fetch principle (`_ONCHAIN_NUMERIC_TOLERANCE_PRINCIPLE`) is not
currently versioned the same way, since it governs a proof-of-concept
feature that is off by default.

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

On-chain context, when present, is deliberately handled the opposite way:
it is framed in the prompt as trusted, factual data, since it was
independently fetched and cross-validated rather than supplied by whoever
wrote the proposal. The two blocks are kept clearly distinct in the
prompt so the model does not conflate "data to be skeptical of" with
"data to treat as ground truth".

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
onchain_context_enabled: bool             # owner toggle, default False
treasury_data_source_url: str             # owner configured URL, default "" (unconfigured)
onchain_contexts: TreeMap[u256, str]      # simulation_id -> JSON context actually used, if any
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
they simply leave it alone. `__init__` assigns only the non-collection
fields (`owner`, `simulations_count`, `max_proposal_length`,
`onchain_context_enabled`, `treasury_data_source_url`) and otherwise does
nothing; every `TreeMap` field is left untouched.

## Public methods

Write methods (`simulate_proposal`, `simulate_proposal_with_reference`,
and `simulate_variant` each go through `_run_pipeline_and_store`; the
three owner-only methods touch only their own configuration field and no
simulation data):

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
- `set_onchain_context_enabled(enabled)`: owner only, turns the on-chain
  context fetch attempt on or off globally.
- `set_treasury_data_source(url)`: owner only, sets or clears (with an
  empty string) the URL the treasury category's context fetch reads
  from.

Read methods:

- `get_simulations_count`, `get_report`, `get_proposal`, `get_owner`,
  `get_max_proposal_length`: direct accessors.
- `get_onchain_context_config()`: whether the feature is enabled and
  which data source URL is configured, as a single JSON object.
- `get_onchain_context(simulation_id)`: the JSON context actually used for
  a given simulation, empty string if none was fetched or used for that
  run.
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
| On-chain context never blocks a simulation | `_fetch_onchain_context` catches any fetch/parse failure and returns `(None, [warning])` instead of raising; the pipeline always falls back to proposal-text-only reasoning. |

## Frontend

Single file `frontend/index.html` (deployed as a static site to Vercel),
using ephemeral `createAccount()` accounts (no wallet UI), following the
same pattern used in the earlier Decentralized Fact Checker project.
Split into a Write methods section (Simulate a proposal, Re-run as a
variant, Proposal length cap, On-chain context grounding) and a Read
methods section (Look up a simulation, Registry overview, Compare two
simulations), covering all 22 contract methods. Calls go through
`genlayer-js`, poll for the transaction receipt, and render the
structured report (scenarios, effects, risks, consensus summary,
on-chain grounding indicator) as cards. The proposal text field enforces
the same length cap client side as `max_proposal_length` defaults to on
chain, with a live character counter, so an oversized submission fails
fast in the UI rather than after a wasted transaction.

## Known limitations (by design, for a research proof of concept)

- The deterministic parser (regex based) can occasionally double count a
  percent value already captured by a from/to pair. This is harmless,
  since the LLM stage reasons over the raw text regardless.
- The Consensus Layer operates on the already agreed final scenario set,
  not on each individual validator's raw output. GenVM does not expose
  per validator raw results to the contract after consensus.
- Malformed or non JSON LLM output degrades gracefully (empty scenario
  list plus warning) rather than reverting the transaction.
- `consensus_summary.areas_of_agreement` has stayed empty across every
  real run so far, including runs made after the substantive `principle`
  and risk-normalization changes described above. The Consensus Layer
  looks for a recurring risk or assumption with matching text across
  scenarios, and with only 3 to 4 LLM generated scenarios per run, an
  exact text match rarely happens even when scenarios are thematically
  related. This is a real, reconfirmed observation, not a stale one.
- On-chain context grounding is wired up for the `treasury` category
  only. A live external data source will also occasionally cause the
  context-fetch `prompt_comparative` call itself to land on
  `UNDETERMINED` if validators' independent fetches drift by more than
  the tolerance, or if one validator's fetch fails outright while
  another's succeeds; when that happens the write still finalizes but
  simply proceeds with `onchain_context = None` for that attempt (the
  fetch step raising internally is caught the same way a broken endpoint
  is).
- Prompt injection mitigation has not been stress tested against
  adversarial inputs on live Studionet validators. Treat it as raising
  the bar, not as a hardened guarantee.
- Any `@gl.public.view` method returning an empty string renders nothing
  at all in GenLayer Studio's Call Contract response panel (confirmed via
  the raw RPC response, which is a valid, non-error result). This is a
  Studio UI display issue, not a contract bug, but it means testing
  `get_onchain_context`, `get_source_reference`, or `get_variant_parent`
  for a simulation where nothing was stored will look like no response
  happened in Studio specifically.

