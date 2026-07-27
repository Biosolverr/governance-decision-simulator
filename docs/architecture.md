# Architecture

## Purpose

AI Governance Decision Simulator is a GenLayer Intelligent Contract that generates structured governance simulation reports for DAO proposals.

The contract does not approve, reject, rank, or score proposals. Instead, it produces several plausible future scenarios that help participants evaluate possible consequences before voting.

The project demonstrates how GenLayer can combine nondeterministic LLM execution with validator consensus while preserving deterministic on chain state.

---

## System Overview

The project consists of two components.

### Intelligent Contract

The Intelligent Contract performs the complete simulation pipeline.

Its responsibilities include:

- proposal parsing (structured numeric parameters),
- proposal classification (category detection, including compound proposals),
- optional external treasury context retrieval with numeric-tolerance consensus,
- LLM based scenario generation,
- validator consensus via substantive equivalence principle,
- deterministic normalization,
- report generation,
- report storage,
- statistics aggregation,
- simulation comparison,
- audit support.

### Frontend

The frontend is a lightweight static application that communicates directly with the deployed Intelligent Contract.

It exposes every public contract method and provides an interface for:

- creating simulations,
- viewing reports,
- browsing history,
- comparing simulations,
- inspecting normalization results,
- viewing contract statistics.

No backend server is required.

---

# Simulation Pipeline

Every proposal follows the same execution pipeline.

```
Proposal Text
      │
      ▼
Proposal Parser (numeric parameters)
      │
      ▼
Proposal Classification (category + compound detection)
      │
      ▼
Optional Treasury Context Fetch (with numeric tolerance consensus)
      │
      ▼
Prompt Builder
      │
      ▼
LLM Scenario Generation
      │
      ▼
Validator Consensus (substantive equivalence)
      │
      ▼
Deterministic Normalization
      │
      ▼
Report Builder
      │
      ▼
Store Report
      │
      ▼
Update Statistics
```

The three public simulation methods

- `simulate_proposal()`
- `simulate_proposal_with_reference()`
- `simulate_variant()`

all delegate to the same internal pipeline (`_run_pipeline_and_store`) before storing the resulting report. This guarantees identical processing logic regardless of how the simulation was triggered.

---

# Proposal Parsing

Before simulation begins, the proposal text is parsed to extract structured numeric information where possible.

The parser may identify:

- percentage changes (e.g. "increase by 8%"),
- numeric from-to ranges (e.g. "from 5% to 8%"),
- absolute amounts with currency (e.g. "$50,000 USDC").

These extracted values are used to improve prompt construction and to support proposal variants.

The parser does **not** determine the proposal category or type — that is handled by the separate Proposal Classification stage.

The original proposal text is always preserved.

---

# Proposal Classification

The contract classifies each proposal into one or more supported governance categories using keyword heuristics.

If the proposal text matches keywords from multiple categories, it is marked as a **compound proposal** (`is_compound_proposal: true`). The primary category (first match) is used to select the prompt template, but the report retains the compound flag for transparency.

The detected category determines:

- prompt template,
- report structure,
- optional treasury grounding,
- stored category statistics.

The detected category and compound flag are stored inside every report.

---

# Optional Treasury Context

Treasury proposals may optionally use external financial context.

When enabled by the contract owner, the contract fetches treasury information from a configured JSON endpoint. The fetch itself runs through GenLayer nondeterministic execution and validator consensus using `gl.eq_principle.prompt_comparative` with a **numeric tolerance principle** — exact byte equality is not required because live balances drift between validator requests.

The retrieved data may include:

- treasury balance,
- monthly spending,
- runway.

If fetching or parsing fails for any reason, the simulation continues normally without external context, and a warning is recorded in `parser_warnings`.

The report records whether external context was used through the `onchain_context_used` field.

---

# Scenario Generation

Scenario generation is the only stage where the LLM creates new content.

The contract performs nondeterministic execution through GenLayer and validator consensus using `gl.eq_principle.prompt_comparative`.

The equivalence principle evaluates whether validator outputs are substantively compatible rather than requiring identical wording.

Validator outputs may differ in:

- wording,
- scenario titles,
- ordering,
- writing style,
- exact scenario count.

They are expected to remain consistent regarding:

- overall proposal effects (net direction per category),
- major risk themes,
- governance implications.

The equivalence principle also requires that generated reports do not approve, reject, score, or recommend governance proposals.

---

# Deterministic Normalization

After consensus, the accepted output is normalized without additional LLM calls.

Normalization includes:

- completing missing fields with safe defaults,
- normalizing confidence values to `High | Medium | Low | Very Low`,
- normalizing risk severity to `low | medium | high | critical`,
- normalizing risk likelihood to `low | medium | high`,
- merging near-duplicate scenarios using Jaccard similarity (threshold 0.55),
- clamping unexpected LLM values to valid schema values.

If normalization reduces the final scenario count below the intended minimum of 3, the report includes an explicit warning in `parser_warnings`.

---

# Report Generation

Each simulation produces a structured JSON report with the following top-level shape:

```json
{
  "schema_version": 1,
  "principle_version": "v2-substantive-2026-07-20",
  "simulation_id": 0,
  "proposal_summary": "...",
  "detected_proposal_type": "treasury",
  "is_compound_proposal": false,
  "simulation_time_horizon": "3-9 months",
  "onchain_context_used": false,
  "generated_scenarios": [
    {
      "title": "...",
      "narrative": "...",
      "key_assumptions": [...],
      "treasury_effects": [...],
      "governance_effects": [...],
      "validator_effects": [...],
      "community_effects": [...],
      "protocol_effects": [...],
      "risk_factors": [...],
      "confidence": "Medium"
    }
  ],
  "consensus_summary": {
    "areas_of_agreement": [...],
    "areas_of_disagreement": [...],
    "interesting_alternative_outcomes": [...],
    "confidence_distribution": {...}
  },
  "risk_and_assumption_overview": {
    "recurring_risks": [...],
    "recurring_assumptions": [...],
    "confidence_histogram": {...},
    "total_scenarios": 3
  },
  "parser_warnings": [...],
  "disclaimer": "..."
}
```

Key points:

- Effect lists, risk factors, and confidence exist **inside each scenario object**, not at the report root.
- `risk_and_assumption_overview` provides a cross-scenario aggregate view of recurring risks and assumptions.
- `simulation_time_horizon` is determined deterministically by category.
- `onchain_context_used` indicates whether real external data was successfully fetched for this run.

Every report is stored on chain.

---

# Consensus Version Tracking

Every report stores the field:

`principle_version`

This value records which version of the equivalence principle was used when validator consensus accepted the report.

Older reports retain the version that was active when they were generated.

The contract does not modify historical reports after they have been stored.

---

# Prompt Injection Mitigation

Proposal text is treated as untrusted input.

Before insertion into the prompt, the contract:

- wraps the proposal text in explicit delimiters,
- strips delimiter-like sequences from the user text,
- collapses long runs of quotes, backticks, and section-break characters,
- explicitly labels the proposal text as user-supplied data rather than executable instructions.

This reduces the likelihood of prompt injection affecting the generated scenarios.

This mitigation improves robustness but should not be considered a complete guarantee against all prompt injection techniques.

---

# Storage Layout

The contract stores:

- simulation reports (`reports`),
- original proposal text (`proposals`),
- raw accepted LLM output (`raw_llm_outputs`),
- proposal source references (`source_references`),
- variant relationships (`variant_of`),
- optional treasury context actually used (`onchain_contexts`),
- category statistics (`category_counts`),
- confidence-level running totals per category (`category_confidence_totals`),
- simulation counter (`simulations_count`),
- owner configuration (`max_proposal_length`, `onchain_context_enabled`, `treasury_data_source_url`).

Reports are stored as JSON strings, allowing the frontend to retrieve and display them directly without additional serialization.

---

# Public Methods

The contract exposes write methods for creating simulations and managing owner configuration, as well as read methods for inspecting stored data.

## Write Methods

### `simulate_proposal(proposal_text)`

The main simulation entry point.

It:

1. validates the proposal length (default cap: 4000 characters),
2. parses numeric parameters and classifies the proposal (including compound detection),
3. optionally retrieves treasury context when enabled and configured,
4. generates scenarios through nondeterministic LLM execution,
5. applies GenLayer validator consensus via substantive equivalence,
6. normalizes the accepted result,
7. builds the final report,
8. stores the report and related metadata,
9. updates category and confidence statistics.

The method does not return a governance recommendation.

---

### `simulate_proposal_with_reference(proposal_text, source_reference)`

Runs the same simulation pipeline as `simulate_proposal`.

In addition, it stores an external reference associated with the simulation.

The reference can point to an external governance proposal or discussion, for example a Snapshot or Tally URL.

The reference can later be retrieved with:

`get_source_reference(simulation_id)`

The reference itself is metadata and does not affect the simulation logic.

---

### `simulate_variant(simulation_id, new_percent)`

Creates a new simulation based on an existing stored proposal.

The method:

1. retrieves the original proposal,
2. replaces the **first** percentage value found in the text with `new_percent`,
3. runs the standard simulation pipeline again,
4. stores the new result as a separate simulation,
5. records the relationship between the new simulation and its parent.

The relationship can be retrieved with:

`get_variant_parent(simulation_id)`

The variant is a new simulation and does not modify the original report.

Constraints:

- `new_percent` is passed as a string rather than a floating point value.
- `new_percent` must be greater than 0 and at most 1000.

---

## Owner Configuration Methods

### `set_max_proposal_length(new_max)`

Changes the maximum allowed proposal length.

The limit is checked before the simulation pipeline starts.

The default limit is 4000 characters.

This method is restricted to the contract owner.

---

### `set_onchain_context_enabled(enabled)`

Enables or disables optional external treasury context retrieval.

The feature is disabled by default.

This method is restricted to the contract owner.

---

### `set_treasury_data_source(url)`

Sets the external JSON data source used for treasury context retrieval.

Passing an empty string clears the configured data source.

This method is restricted to the contract owner.

---

## Read Methods

### Basic Accessors

#### `get_simulations_count()`

Returns the number of successfully stored simulations.

---

#### `get_report(simulation_id)`

Returns the complete stored JSON report for a simulation.

---

#### `get_proposal(simulation_id)`

Returns the original proposal text associated with a simulation.

---

#### `get_owner()`

Returns the contract owner address.

---

#### `get_max_proposal_length()`

Returns the currently configured proposal length limit.

---

### On Chain Context

#### `get_onchain_context_config()`

Returns the current configuration of the optional treasury context feature.

This includes:

- whether the feature is enabled,
- the configured data source URL.

This method returns configuration for the contract as a whole.

It does not return the context used by a particular simulation.

---

#### `get_onchain_context(simulation_id)`

Returns the external context that was actually used for a specific simulation.

If no external context was used, the method returns an empty string.

This makes it possible to distinguish between:

- the current contract configuration,
- the data actually used during a historical simulation.

---

### Statistics

#### `get_category_stats()`

Returns the number of stored simulations for each detected proposal category.

The values are maintained incrementally as simulations are stored.

---

#### `get_confidence_trend(category)`

Returns accumulated confidence totals for simulations belonging to a selected category.

This provides a historical view of confidence levels across simulations rather than the confidence of one individual report.

The values are based on the confidence distribution stored for each simulation.

---

### Simulation History

#### `list_recent_simulations(limit)`

Returns a compact list of recent simulations.

The newest simulations are returned first.

This allows a frontend to display simulation history without retrieving every complete report individually.

---

#### `find_similar_simulations(category, limit)`

Returns recent simulations that belong to the same detected proposal category.

This is a category based lookup.

It does not perform semantic similarity search, embeddings, or natural language similarity analysis.

The search is bounded to the most recent 1000 simulations to prevent unbounded scanning costs.

---

### Simulation Relationships

#### `get_source_reference(simulation_id)`

Returns the external source reference stored for a simulation.

If no reference was provided, the result is empty.

---

#### `get_variant_parent(simulation_id)`

Returns the parent simulation ID associated with a variant.

This allows the frontend or another caller to trace a variant back to the original simulation.

---

### Simulation Comparison

#### `compare_simulations(id1, id2)`

Performs a deterministic comparison of two stored reports.

The comparison includes:

- whether the detected categories match,
- confidence distributions,
- scenario titles shared by both reports,
- scenario titles unique to each report.

The comparison does not call an LLM.

It operates only on already stored simulation data.

This makes it useful for examining different simulations of similar proposals or comparing a variant with its parent.

---

### Normalizer Inspection

#### `get_normalizer_diff(simulation_id)`

Compares the raw accepted LLM output with the final normalized report.

The method provides information about changes introduced during normalization, including:

- raw scenario count,
- final scenario count,
- the number of scenarios merged or dropped,
- raw scenario titles,
- final scenario titles.

The method exists to make deterministic post processing more transparent.

---

### Markdown Export

#### `get_report_markdown(simulation_id)`

Returns the stored report rendered as Markdown.

The Markdown is generated deterministically from the stored report.

No additional LLM call is performed.

This provides a readable representation suitable for copying into governance discussions, forums, or chat applications.

---

# Design Constraints

The contract applies several constraints throughout the simulation pipeline.

## No Governance Recommendation

The contract does not contain a proposal approval or rejection field.

The generated report is designed to describe possible outcomes rather than make a governance decision.

The report also contains an explicit disclaimer explaining that the output is informational and does not approve, reject, score, or recommend a proposal.

The validator equivalence principle additionally treats approval, rejection, scoring, or recommendation as invalid behavior for the generated output.

This is a combination of prompt level and consensus level protection.

It should not be interpreted as a formal guarantee that an LLM can never produce recommendation like language.

---

## Qualitative Confidence

Scenario confidence is represented using qualitative values:

- High
- Medium
- Low
- Very Low

Confidence is not a proposal score.

It describes the internal confidence associated with an individual generated scenario.

The contract does not calculate a numeric governance score or ranking.

---

## Risk Normalization

Risk objects contain normalized severity and likelihood values.

Severity is restricted to the supported qualitative values.

Likelihood is also normalized to the supported qualitative values.

Unexpected LLM values are replaced with valid schema values during deterministic normalization.

---

## Scenario Count

The prompt requests at least three scenarios.

This is not an absolute runtime guarantee.

The LLM may return fewer scenarios, and deterministic normalization may merge scenarios that are considered sufficiently similar according to the Jaccard threshold (0.55).

If the final number of scenarios is below the intended minimum, the report records a warning in `parser_warnings`.

The contract therefore exposes the condition rather than silently claiming that three distinct scenarios were produced.

---

## Assumptions

The report is expected to contain scenario assumptions.

If the LLM does not provide an explicit assumption for a scenario, the deterministic processing stage can insert a fallback assumption.

This ensures that the final report retains an explicit indication that the scenario depends on assumptions.

---

## Proposal Length Limit

The proposal length limit is enforced before LLM execution.

The owner can change the limit without redeploying the contract.

This prevents arbitrarily large proposal inputs from entering the simulation pipeline.

The default maximum proposal length is 4000 characters.

---

## External Context Failure Handling

External treasury context is optional.

If context retrieval is unavailable or cannot be parsed into the expected structure, the simulation continues without external context.

The report records the condition through `parser_warnings`.

The simulation is therefore not dependent on successful access to the configured external data source.

---

## Variant Constraints

Variant simulation replaces only the **first** percentage value detected in the original proposal text.

If the original text contains no detectable percentage pattern, the variant call fails with an error.

The replacement percent must be greater than 0 and at most 1000.

---

# Frontend

The frontend is located in:

`frontend/index.html`

It is a single static HTML file with no build step.

The application communicates directly with the GenLayer contract through `genlayer-js`.

The interface is divided into write and read operations.

## Write Interface

The frontend provides access to:

- proposal simulation,
- proposal simulation with an optional source reference,
- variant simulation,
- proposal length configuration,
- treasury context configuration.

Owner only methods are subject to the same ownership checks as direct contract calls.

---

## Read Interface

The frontend provides access to:

- stored reports,
- Markdown reports,
- original proposals,
- source references,
- variant relationships,
- Normalizer differences,
- treasury context,
- contract configuration,
- category statistics,
- confidence trends,
- recent simulations,
- category based historical lookup,
- simulation comparison,
- simulation count.

The frontend renders the structured report and its main sections for human inspection.

---

# Data Flow Between Contract and Frontend

The frontend does not independently reproduce the simulation logic.

The contract remains responsible for:

- proposal parsing,
- classification,
- LLM execution,
- validator consensus,
- normalization,
- report generation,
- storage.

The frontend primarily acts as an interface for submitting inputs and reading stored results.

This means the same stored report can also be accessed directly through the contract read methods without using the frontend.

---

# Known Limitations

The project is a research proof of concept and has several known limitations.

## LLM Output

The scenarios are generated by an LLM.

They represent plausible possibilities and should not be interpreted as reliable predictions.

The contract does not verify that a scenario will actually occur.

---

## Consensus Is Not Truth Verification

The GenLayer equivalence principle checks whether validator outputs are substantively compatible.

It does not prove that the generated scenarios are factually correct.

Consensus means that validators accepted the outputs as sufficiently equivalent under the defined principle.

It does not mean that the predicted future is guaranteed to be accurate.

---

## Consensus Summary

The report contains fields for consensus information.

The `areas_of_agreement` field may remain empty when scenarios do not contain recurring risks or assumptions that match the deterministic aggregation rules.

This does not necessarily mean that validators disagreed.

It can simply mean that the final scenarios did not contain matching text suitable for the aggregation logic.

---

## Similar Simulation Search

`find_similar_simulations()` is limited to category based matching.

For example, a treasury proposal is matched with previous simulations classified as `treasury`.

The method does not determine whether two proposals are semantically similar.

---

## On Chain Context Scope

External context grounding is currently implemented for the treasury category.

Other proposal categories do not currently have an equivalent external data fetcher.

The feature is also disabled by default and requires owner configuration.

---

## External Data Freshness

Treasury context is retrieved from an external source at simulation time.

The data may change between validator requests.

The context consensus principle therefore allows limited numeric differences between independent validator fetches.

The external data source itself is not permanently stored as an immutable historical oracle.

The simulation stores the context actually used when available, allowing the historical report to be inspected later.

---

## Prompt Injection Mitigation

Proposal text is treated as untrusted input and is separated from system instructions in the generated prompt.

The contract also sanitizes selected delimiter patterns.

These measures reduce common prompt injection patterns but do not constitute a formal security guarantee.

The mitigation has not been demonstrated to prevent every possible adversarial prompt injection technique.

---

## Normalization

The Normalizer is deterministic, but deterministic processing cannot determine whether an LLM scenario is factually correct.

It only ensures that the final report follows the expected structure and applies predefined normalization rules.

Scenario merging may occasionally combine scenarios that are similar according to the implemented similarity logic.

If this reduces the number of final scenarios below the intended minimum, a warning is added to the report.

---

## Empty String Display in GenLayer Studio

Some read methods can legitimately return an empty string when no value was stored.

Depending on the GenLayer Studio interface, an empty string may appear visually as if no response was returned.

This can affect methods such as:

- `get_onchain_context()`
- `get_source_reference()`
- `get_variant_parent()`

when the requested simulation has no corresponding value.

This is a display behavior of the interface and does not necessarily indicate a contract execution failure.

---

# Research Status

The project should be treated as a research and demonstration implementation.

It demonstrates a complete workflow combining:

- nondeterministic LLM execution,
- GenLayer validator consensus,
- deterministic normalization,
- structured on chain reports,
- optional external context,
- historical simulation data.

It is not an audited production governance system.

The generated reports are intended to support human analysis and discussion, not replace governance processes or human judgment.
