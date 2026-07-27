# AI Governance Decision Simulator

A **GenLayer Intelligent Contract** that simulates possible outcomes of DAO governance proposals before voting.

The contract does **not** approve, reject, score, rank, or recommend proposals. Its purpose is to generate multiple plausible future scenarios that help DAO participants understand potential consequences before making a governance decision. Every report includes an explicit disclaimer stating this.

This project is a research demonstration and should not be considered a production governance system or a replacement for human decision making.

## Overview

Instead of asking:

> "Should this proposal pass?"

the contract asks:

> "If this proposal is accepted, what are several realistic outcomes over the coming months?"

The contract:

* classifies the proposal into one of several governance categories,
* builds a category specific prompt,
* performs nondeterministic LLM execution through GenLayer,
* reaches validator consensus using `gl.eq_principle.prompt_comparative`,
* deterministically normalizes and structures the accepted output,
* stores the final report on-chain for future reference.

The generated report contains:

* proposal category,
* multiple future scenarios,
* treasury, governance, validator, community, and protocol effects,
* identified risks,
* confidence level,
* consensus summary,
* report metadata,
* principle version used during consensus.

For treasury proposals, the contract can optionally use real financial data instead of relying entirely on LLM assumptions.

---

# Architecture

The project consists of two components.

## Intelligent Contract

The Intelligent Contract is responsible for:

* proposal classification,
* proposal simulation,
* validator consensus,
* deterministic report normalization,
* report storage,
* auditability of LLM output,
* statistics aggregation,
* proposal comparison,
* simulation history.

The contract keeps both the finalized report and selected metadata that make simulations easier to inspect and compare over time.

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

Each simulation is accepted only after GenLayer validators reach consensus under a substantive equivalence principle rather than simply validating JSON structure.

Validators must agree on the overall meaning of the generated report, including expected effects and major risks. The consensus principle also explicitly prevents validators from approving, rejecting, or scoring proposals.

---

## Prompt injection protection

User supplied proposal text is treated as untrusted input.

Before it is inserted into the simulation prompt, the contract sanitizes characters that could imitate prompt structure and explicitly instructs the LLM to treat the proposal as data rather than executable instructions.

This reduces the risk of prompt injection affecting the simulation.

---

## Deterministic normalization

After validator consensus, the accepted LLM output is normalized into a deterministic report.

Normalization includes:

* scenario deduplication,
* scenario merging,
* confidence normalization,
* risk severity normalization,
* likelihood normalization,
* report structure validation.

If normalization reduces the final scenario count below the intended minimum, the report contains an explicit warning.

---

## On-chain context grounding

For treasury proposals, the contract can optionally retrieve current treasury information from an external JSON source.

When enabled, validators independently fetch:

* treasury balance,
* monthly spending,
* runway.

These values are reconciled through a dedicated GenLayer consensus process before being used as factual context during simulation.

This feature is disabled by default and only affects treasury proposals.

---

# Public Write Methods

The contract provides the following write methods:

* `simulate_proposal()`
* `simulate_proposal_with_reference()`
* `simulate_variant()`
* `set_max_proposal_length()` (owner only)
* `set_onchain_context_enabled()` (owner only)
* `set_treasury_data_source()` (owner only)

---

# Public Read Methods

The contract provides read methods for retrieving reports, statistics, and simulation history.

These include:

* report retrieval,
* Markdown report generation,
* proposal lookup,
* source reference lookup,
* variant lookup,
* normalization difference inspection,
* category statistics,
* confidence trends,
* similar simulations,
* simulation comparison,
* recent simulations,
* owner configuration,
* contract configuration,
* simulation count.

---

# Statistics

The contract maintains aggregated statistics across all stored simulations.

Available statistics include:

* simulations per proposal category,
* confidence distribution by category,
* total number of simulations.

These statistics are updated automatically as new simulations are stored.

---

# Simulation History

Every completed simulation receives a unique identifier and remains available for later inspection.

The contract supports:

* browsing recent simulations,
* retrieving previous simulations from the same detected proposal category,
* comparing reports,
* tracking proposal variants,
* preserving source references when provided.

This allows governance discussions to reference earlier simulations instead of treating every proposal as an isolated event.

---

# Report Transparency

Every stored report includes the version of the equivalence principle that was used during validator consensus through the `principle_version` field.

For additional transparency, the contract stores the raw LLM output and provides `get_normalizer_diff()` to compare the original response with the normalized report, including scenario counts and title changes introduced during deterministic normalization.

Reports can also be exported directly as deterministic Markdown through `get_report_markdown()` without using an LLM.

---

# Source References

Simulations may optionally include a source reference pointing to an existing governance proposal such as Snapshot, Tally, or another governance platform.

This creates a direct link between the simulation and the original proposal while remaining optional for standalone simulations.

---

# Proposal Variants

The contract supports creating alternative versions of previously simulated proposals.

`simulate_variant()` reuses the original proposal, replaces the detected percentage value with a new one, and generates a new simulation while preserving a reference to the original simulation.

This allows DAOs to compare alternative parameter choices using the same workflow.

---

# Proposal Length Protection

To prevent unnecessary storage growth and excessive LLM execution, proposal length is validated before simulation begins.

The maximum allowed proposal length is configurable by the contract owner.

---

# Running the Project

1. Deploy `contract/governance_simulator.py` to GenLayer Studio.
2. Configure the deployed contract address inside `frontend/index.html`.
3. Deploy the `frontend` directory as a static website.
4. Submit governance proposals through the frontend or interact directly with the Intelligent Contract.

---

# Known Limitations

* This project is a research demonstration and has not been independently security audited.
* LLM generated scenarios are intended to assist governance discussions and may contain inaccuracies or omissions.
* Consensus validates substantive agreement between validator outputs but cannot guarantee that future events will occur as predicted.
* On-chain context grounding currently supports only treasury proposals.
* Similar proposal lookup is based on the detected proposal category rather than semantic similarity.
* Proposal simulations depend on the proposal text and any optional external treasury data available at execution time.
* Owner only configuration methods require the deploying account.

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
│   ├── index.html
│   └── proposals.json
├── .env.example
├── .gitignore
└── LICENSE
```

---

# License

MIT. See the `LICENSE` file for details.
