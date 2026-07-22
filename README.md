# AI Governance Decision Simulator

A **GenLayer Intelligent Contract** that simulates the possible consequences
of a DAO governance proposal before it's voted on.

> The contract does **not** approve, reject, score, or rank proposals.
> It only generates multiple plausible future scenarios to support human
> decision-making. Every report ends with an explicit disclaimer saying so.

## Idea

Instead of asking *"Is this proposal good?"*, the contract asks:

> "If this proposal is accepted, what could realistically happen over the
> following months?"

It classifies the proposal into one of 10 categories, builds a
category-specific prompt, runs it through GenLayer's nondeterministic LLM
execution with validator consensus (`gl.eq_principle.prompt_comparative`),
then deterministically normalizes, deduplicates, and structures the
resulting scenarios into a JSON report (effects on treasury, governance,
validators, community, and protocol; risk factors; confidence; a rough
consensus summary).

For the treasury category specifically, the contract can optionally
ground its reasoning in real, current data instead of pure LLM assumption
- see On-chain context grounding below.

The contract exposes 6 write methods (`simulate_proposal`,
`simulate_proposal_with_reference`, `simulate_variant`,
`set_max_proposal_length`, `set_onchain_context_enabled`,
`set_treasury_data_source`, the last three owner-only) and 16 read methods
for browsing, comparing, and auditing stored simulations (`get_report`,
`get_report_markdown`, `get_proposal`, `get_owner`,
`get_max_proposal_length`, `get_onchain_context_config`,
`get_onchain_context`, `get_category_stats`, `list_recent_simulations`,
`find_similar_simulations`, `get_confidence_trend`,
`get_source_reference`, `get_variant_parent`, `get_normalizer_diff`,
`compare_simulations`, `get_simulations_count`). Written up in
[`docs/architecture.md`](docs/architecture.md).

This is a research demo, not an audited or production-hardened contract.

### Deploy note

An earlier version of the contract failed on deploy with:

```
AssertionError: Is right the same storage type? `TreeMap` <- `TreeMap`
```

This happened because `__init__` explicitly reassigned every `TreeMap`
field with a bare `TreeMap()` call. GenVM storage starts zero-initialized
at deploy time, so every `TreeMap`-typed field already exists as an empty
instance of its own declared generic type before `__init__` ever runs;
reassigning a bare, generic-less `TreeMap()` over it crashed every
validator. The fix was simply to stop touching those fields in `__init__`
and let GenVM's zero-initialization do its job. This matches every
official GenLayer example: none of them assign `TreeMap()` in `__init__`
for a `TreeMap`-typed field. No other contract logic changed.

### On-chain context grounding (proof of concept, treasury category only)

By default the LLM reasons purely from `proposal_text`, with no anchor in
the DAO's actual current financial position. This optional module lets
the owner configure a data source URL; when enabled, `simulate_proposal`
fetches real `treasury_balance_usd`, `monthly_spend_usd`, and
`runway_months` and tells the LLM to treat them as ground truth rather
than inventing its own numbers.

The fetch itself is independent per validator (each one hits the URL on
its own) and reconciled through its own `prompt_comparative` call with a
numeric-tolerance equivalence principle (small drift between two live
readings a few seconds apart is expected and tolerated; a missing field,
non-numeric value, or drift beyond the tolerance is not). This has been
tested live end-to-end: enabling the feature, pointing it at a public
JSON snapshot, and confirming the LLM's scenarios computed directly off
the fetched numbers (e.g. deriving a new runway from the fetched balance
and spend rate) rather than guessing.

Disabled by default (`onchain_context_enabled = False`, empty data source
URL), so existing behavior and report shape are unaffected until the
owner opts in via `set_onchain_context_enabled` and
`set_treasury_data_source`. Currently wired up for the `treasury` category
only; extending to another category is adding one entry to
`_ONCHAIN_CONTEXT_FETCHERS` plus a category-specific parser in
`contract/governance_simulator.py`, no pipeline changes needed.

## Repository structure

```
governance-decision-simulator/
├── contract/
│   └── governance_simulator.py   # the Intelligent Contract (single file, GenVM-deployable)
├── docs/
│   ├── architecture.md           # pipeline diagram + design decisions
│   └── example-output.md         # a synthetic example of the report shape
├── frontend/
│   ├── index.html                # single-file frontend, no build step, exposes all 22 contract methods
│   └── proposals.json            # example proposals, one per category, used for the demo chips
├── .env.example
├── .gitignore
└── LICENSE
```

## Frontend

`frontend/index.html` is a single static file with no build step, split
into a Write methods section and a Read methods section:

- **Simulate a proposal** - calls `simulate_proposal`, or
  `simulate_proposal_with_reference` automatically if a source link is
  filled in.
- **Re-run as a variant** - calls `simulate_variant` against an existing
  simulation ID.
- **Proposal length cap** - calls `set_max_proposal_length`. Owner-only.
- **On-chain context grounding** - calls `set_onchain_context_enabled` and
  `set_treasury_data_source`. Owner-only.
- **Look up a simulation** - `get_report`, `get_report_markdown`,
  `get_proposal`, `get_source_reference`, `get_variant_parent`,
  `get_normalizer_diff`, `get_onchain_context`, all keyed by simulation ID.
- **Registry overview** - `get_simulations_count`, `get_owner`,
  `get_max_proposal_length`, `get_onchain_context_config`,
  `get_category_stats`, `list_recent_simulations`,
  `find_similar_simulations`, `get_confidence_trend`.
- **Compare two simulations** - `compare_simulations`.

Every owner-only write is expected to fail with a `UserError` unless
called from the account that deployed the contract; the page's ephemeral
account is never that account, so this is the contract enforcing
ownership correctly, not a bug in the page.

## Running it

1. Deploy `contract/governance_simulator.py` to GenLayer Studionet.
2. Copy the deployed contract address into `frontend/index.html`
   (`CONTRACT_ADDRESS` constant near the top of the `<script>` block).
   The currently deployed instance is at
   `0x698Fd7107f5dDBf3aA255277512f94DbF5d5a919`. Re-check this after any
   redeploy, an old address points at a stale contract instance with a
   different state history.
3. Deploy this repository to Vercel with **Root Directory set to
   `frontend`**. `index.html` fetches `./proposals.json`, which lives in
   the same folder, so this works regardless of other Root Directory
   settings. Vercel will serve `index.html` at your deployment's root URL
   automatically.
4. Paste a governance proposal (or click one of the example chips) and
   submit. The contract returns the structured simulation report. Use the
   Read methods panels below to look up, browse, or compare simulations
   already stored on-chain.

`.env.example` documents the RPC endpoint and contract address you'll need,
but note that `frontend/index.html` has no build step and does not read
`.env` at runtime. Set `CONTRACT_ADDRESS` and `RPC_URL` directly as
constants in the script instead.

## Known rough edges

- `consensus_summary.areas_of_agreement` tends to come back empty. The
  contract's Consensus Layer looks for an exact-text match on a recurring
  risk or assumption across scenarios, which rarely happens with only 3-4
  LLM-generated scenarios per run. See
  [`docs/architecture.md`](docs/architecture.md#known-limitations-by-design-for-a-research-poc)
  for details.
- `simulate_variant` (and, less often, `simulate_proposal`) can land on
  `UNDETERMINED` consensus if enough validators judge the leader's
  scenario set as substantively different under the `prompt_comparative`
  equivalence principle. When that happens the transaction can still show
  as finalized in Studio but the write never actually commits (the
  simulation ID is not incremented and nothing is stored). Check
  `get_simulations_count` after any write that looked slow or contentious
  in the Consensus History panel, and simply resubmit if the count didn't
  change.
- Any `@gl.public.view` method that returns an empty string renders
  nothing at all in Studio's Call Contract response panel, no `""`, no
  placeholder. Confirmed via the raw RPC response (a minimal, non-error,
  non-null result) - this is a Studio UI display issue, not a contract
  bug. `get_onchain_context`, `get_source_reference`, and
  `get_variant_parent` all hit this for simulations where nothing was
  stored; the frontend works around it by rendering an explicit "not
  used" note instead of leaving the box blank, but calling these methods
  directly in Studio for an empty case will look like no response
  happened.
- The frontend's `genlayer-js` import path and client method names follow
  the pattern used in earlier GenLayer demos and have been confirmed
  working against a live Studio deployment for both write and read calls,
  including the non-LLM web fetch used by on-chain context grounding
  (`gl.nondet.web.render`). If a future SDK version renames these,
  check the current `genlayer-js` docs and see the READ-CALL SHAPE note
  near the top of `index.html`'s script block.

## License

MIT, see [LICENSE](LICENSE).
