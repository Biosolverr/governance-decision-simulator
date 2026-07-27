# AI Governance Decision Simulator

A **GenLayer Intelligent Contract** that simulates possible outcomes of DAO governance proposals before voting.

The contract does **not** approve, reject, score, rank, or recommend proposals. Its purpose is to generate multiple plausible future scenarios that help DAO participants understand potential consequences before making a governance decision. Every report includes an explicit disclaimer stating this.

This project is a research demonstration and should not be considered a production governance system or a replacement for human decision making.

---

## Overview

Instead of asking:

> "Should this proposal pass?"

the contract asks:

> "If this proposal is accepted, what are several realistic outcomes over the coming months?"

The contract:

* parses structured numeric parameters from free-text proposals,
* classifies the proposal into one or more governance categories (with compound-proposal detection),
* builds a category-specific prompt,
* optionally fetches real treasury data from an external JSON source when enabled,
* performs nondeterministic LLM execution through GenLayer,
* reaches validator consensus using `gl.eq_principle.prompt_comparative` with a **substantive equivalence principle** (not strict equality),
* deterministically normalizes and structures the accepted output,
* stores the final report on-chain for future reference.

The generated report contains:

* `schema_version` — report shape version (currently `1`),
* `principle_version` — which equivalence principle accepted this report,
* `simulation_id` — unique identifier for this simulation,
* `proposal_summary` — truncated original text,
* `detected_proposal_type` — primary category (e.g. `treasury`, `emission`, `quorum`),
* `is_compound_proposal` — `true` if the text matched multiple category keywords,
* `simulation_time_horizon` — estimated time window for effects (category-dependent),
* `onchain_context_used` — whether real external treasury data was fetched and used,
* `generated_scenarios` — array of scenario objects, each containing:
  * `title`, `narrative`, `key_assumptions`,
  * `treasury_effects`, `governance_effects`, `validator_effects`, `community_effects`, `protocol_effects`,
  * `risk_factors` (with normalized `severity` and `likelihood`),
  * `confidence` (`High | Medium | Low | Very Low`),
* `consensus_summary` — `areas_of_agreement`, `areas_of_disagreement`, `interesting_alternative_outcomes`, `confidence_distribution`,
* `risk_and_assumption_overview` — cross-scenario recurring risks/assumptions and confidence histogram,
* `parser_warnings` — any issues detected during parsing, normalization, or context fetching,
* `disclaimer` — explicit statement that the report is informational only.

For treasury proposals, the contract can optionally use real financial data instead of relying entirely on LLM assumptions.

---

# Architecture

The project consists of two components.

## Intelligent Contract

The Intelligent Contract is responsible for:

* proposal parsing (numeric parameters only — category is handled separately),
* proposal classification (including compound-proposal detection),
* optional external treasury context retrieval with numeric-tolerance validator consensus,
* LLM-based scenario generation,
* validator consensus via substantive equivalence principle,
* deterministic normalization (deduplication, merging, clamping, structure validation),
* report generation and storage,
* auditability of raw LLM output vs normalized report,
* statistics aggregation (category counts, confidence trends),
* simulation comparison and history browsing.

The contract keeps both the finalized report and selected metadata (raw LLM text, on-chain context used, variant parent links, source references) that make simulations easier to inspect and compare over time.

## Frontend

The frontend is a lightweight HTML, CSS, and JavaScript application with no build step.

It communicates directly with the deployed Intelligent Contract and exposes every public contract method through a simple interface.

Users can:

* simulate governance proposals,
* submit proposals with optional source references,
* create proposal variants,
* browse previous simulations,
* compare simulations,
* inspect normalization differences,
* view statistics,
* view reports in JSON or Markdown format.

No backend server is required for normal operation.

---

# Main Features

## Governance simulation

The contract generates multiple possible future scenarios for governance proposals instead of attempting to predict a single outcome.

Each simulation is accepted only after GenLayer validators reach consensus under a **substantive equivalence principle** rather than simply validating JSON structure or requiring byte-identical responses.

Validators must agree on:

* the overall direction of effects per category (positive, negative, neutral, or mixed),
* major risk themes (neither text may ignore a risk the other treats as major),
* the prohibition on approving, rejecting, scoring, or recommending the proposal.

Differences in wording, scenario titles, ordering, writing style, or exact scenario count are tolerated.

---

## Prompt injection protection

User-supplied proposal text is treated as untrusted input.

Before it is inserted into the simulation prompt, the contract:

* wraps the text in explicit delimiters (`§§§PROPOSAL_TEXT§§§`),
* strips any occurrence of the delimiter token from the user text,
* collapses long runs of quotes, backticks, and section-break characters,
* explicitly instructs the LLM to treat the block as data rather than executable instructions.

This reduces the risk of prompt injection affecting the simulation. It is defense-in-depth, not a formal guarantee.

---

## Deterministic normalization

After validator consensus, the accepted LLM output is normalized into a deterministic report without additional LLM calls.

Normalization includes:

* completing missing fields with safe defaults,
* scenario deduplication and merging using Jaccard similarity (threshold `0.55`),
* confidence normalization to `High | Medium | Low | Very Low`,
* risk severity normalization to `low | medium | high | critical`,
* risk likelihood normalization to `low | medium | high`,
* report structure validation.

If normalization reduces the final scenario count below the intended minimum of 3, the report contains an explicit warning in `parser_warnings`.

---

## On-chain context grounding

For treasury proposals, the contract can optionally retrieve current treasury information from an external JSON source.

When enabled by the owner, validators **independently fetch** the configured URL. Because live balances drift between requests, the context fetch uses its own `prompt_comparative` step with a **numeric tolerance principle** (allowing ~5% drift and minor rounding differences) rather than strict equality consensus.

The retrieved data may include:

* `treasury_balance_usd`,
* `monthly_spend_usd`,
* `runway_months`.

If fetching, parsing, or consensus fails for any reason, the simulation continues on proposal text alone and records a warning.

This feature is **disabled by default** and only affects treasury proposals.

---

# Public Write Methods

| Method | Description | Access |
|---|---|---|
| `simulate_proposal(proposal_text)` | Main entry point. Runs the full pipeline and returns the JSON report. | Public |
| `simulate_proposal_with_reference(proposal_text, source_reference)` | Same as above, but also stores an external reference (e.g. Snapshot/Tally URL). | Public |
| `simulate_variant(simulation_id, new_percent)` | Creates a new simulation by replacing the **first** percentage value in an existing proposal with `new_percent`. `new_percent` is a string, must be `> 0` and `≤ 1000`. | Public |
| `set_max_proposal_length(new_max)` | Changes the proposal length cap (default: 4000 characters). | Owner only |
| `set_onchain_context_enabled(enabled)` | Toggles the treasury context fetcher on/off. | Owner only |
| `set_treasury_data_source(url)` | Sets (or clears) the external JSON URL for treasury context. | Owner only |

---

# Public Read Methods

| Method | Returns |
|---|---|
| `get_report(simulation_id)` | Full JSON report for a simulation. |
| `get_report_markdown(simulation_id)` | Same report rendered as deterministic Markdown (no LLM call). |
| `get_proposal(simulation_id)` | Original proposal text. |
| `get_source_reference(simulation_id)` | External reference, if any (empty string otherwise). |
| `get_variant_parent(simulation_id)` | Parent simulation ID for variants (empty string otherwise). |
| `get_normalizer_diff(simulation_id)` | Comparison of raw LLM output vs final report: scenario counts, merged/dropped titles, raw and final title lists. |
| `get_onchain_context(simulation_id)` | JSON context actually used for that simulation (empty string if none). |
| `get_onchain_context_config()` | Contract-wide feature toggle and configured data source URL. |
| `get_category_stats()` | Simulation count per detected category. |
| `get_confidence_trend(category)` | Running confidence-level totals for a category. |
| `list_recent_simulations(limit)` | Compact list of recent simulations (id, summary, type), newest first. |
| `find_similar_simulations(category, limit)` | Recent simulations matching a category (bounded to the most recent 1000). |
| `compare_simulations(id1, id2)` | Deterministic diff: same category, confidence distributions, shared/unique scenario titles. |
| `get_simulations_count()` | Total number of stored simulations. |
| `get_max_proposal_length()` | Current proposal length limit. |
| `get_owner()` | Contract owner address. |

---

# Statistics

The contract maintains aggregated statistics across all stored simulations.

Available statistics include:

* simulations per proposal category (`get_category_stats`),
* confidence distribution by category (`get_confidence_trend`),
* total number of simulations (`get_simulations_count`).

These statistics are updated incrementally as new simulations are stored, so they remain cheap to query even with a long history.

---

# Simulation History

Every completed simulation receives a unique identifier and remains available for later inspection.

The contract supports:

* browsing recent simulations (`list_recent_simulations`),
* retrieving previous simulations from the same detected proposal category (`find_similar_simulations`),
* comparing two reports side by side (`compare_simulations`),
* tracking proposal variants (`get_variant_parent`),
* preserving source references when provided (`get_source_reference`),
* inspecting what the Normalizer changed (`get_normalizer_diff`),
* viewing the raw on-chain context used (`get_onchain_context`).

This allows governance discussions to reference earlier simulations instead of treating every proposal as an isolated event.

---

# Report Transparency

Every stored report includes:

* `principle_version` — the exact equivalence principle version used during validator consensus,
* `onchain_context_used` — whether real external data grounded this specific simulation.

For additional transparency, the contract stores the raw LLM output and provides `get_normalizer_diff()` to compare the original response with the normalized report, including scenario counts and title changes introduced during deterministic normalization.

Reports can also be exported directly as deterministic Markdown through `get_report_markdown()` without using an LLM.

---

# Source References

Simulations may optionally include a source reference pointing to an existing governance proposal such as Snapshot, Tally, or another governance platform.

This creates a direct link between the simulation and the original proposal while remaining optional for standalone simulations.

---

# Proposal Variants

The contract supports creating alternative versions of previously simulated proposals.

`simulate_variant()`:

1. retrieves the original proposal text,
2. replaces the **first** detected percentage value with the supplied `new_percent`,
3. runs the standard simulation pipeline again,
4. stores the new result as a separate simulation,
5. records a parent-child link retrievable via `get_variant_parent()`.

Constraints:

* `new_percent` is passed as a **string** (GenVM has no float calldata type).
* Must be greater than `0` and at most `1000`.
* If the original text contains no detectable percentage pattern, the call fails with an error.

This allows DAOs to compare alternative parameter choices using the same workflow.

---

# Proposal Length Protection

To prevent unnecessary storage growth and excessive LLM execution, proposal length is validated before the simulation pipeline begins.

The default maximum is **4000 characters** and is configurable by the contract owner via `set_max_proposal_length()` without redeploying the contract.

---

# Running the Project

1. Deploy `contract/governance_simulator.py` to GenLayer Studio.
2. Configure the deployed contract address inside `frontend/index.html`.
3. Deploy the `frontend` directory as a static website.
4. Submit governance proposals through the frontend or interact directly with the Intelligent Contract.

---

# Known Limitations

* This project is a research demonstration and has not been independently security audited.
* LLM-generated scenarios are intended to assist governance discussions and may contain inaccuracies or omissions.
* Consensus validates substantive agreement between validator outputs but cannot guarantee that future events will occur as predicted.
* On-chain context grounding currently supports **only treasury proposals**.
* Similar proposal lookup (`find_similar_simulations`) is based on the detected proposal category rather than semantic similarity.
* Proposal simulations depend on the proposal text and any optional external treasury data available at execution time.
* Owner-only configuration methods require the deploying account.
* The Normalizer may occasionally merge scenarios that are similar according to its Jaccard heuristic; if this drops the count below 3, a warning is recorded.
* Empty-string responses from read methods (e.g. `get_onchain_context`, `get_source_reference`, `get_variant_parent`) indicate the requested value was never set, not a contract failure.

---

# Repository Structure

```
governance-decision-simulator/
├── contract/
│   └── governance_simulator.py
├── docs/
│   ├── architecture.md
│   └── example-output.md
├── frontend/
│   └── index.html
└── README.md
```

---

# License

MIT. See the `LICENSE` file for details.
