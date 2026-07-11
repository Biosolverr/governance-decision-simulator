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

## Status

Tested live on GenLayer Studionet — three `simulate_proposal` transactions
finalized successfully with real validator consensus. See
[`demo/proof.json`](demo/proof.json) for the actual transaction hashes,
validator votes, and reports. Written up in
[`docs/architecture.md`](docs/architecture.md).

This is a research demo, not an audited or production-hardened contract.

## Repository structure

```
governance-decision-simulator/
├── contract/
│   └── governance_simulator.py   # the Intelligent Contract (single file, GenVM-deployable)
├── frontend/
│   └── index.html                # single-file frontend, no build step
├── demo/
│   ├── proposals.json            # example proposals (used as chips in the frontend)
│   └── proof.json                # real Studio test results: tx hashes, consensus, reports
├── docs/
│   ├── architecture.md           # pipeline diagram + design decisions
│   └── example-output.md         # a synthetic example of the report shape
├── .env.example
├── .gitignore
└── LICENSE
```

## Running it

1. Deploy `contract/governance_simulator.py` to GenLayer Studionet.
2. Copy the deployed contract address into `frontend/index.html`
   (`CONTRACT_ADDRESS` constant near the top of the `<script>` block).
3. Deploy this repository to Vercel with **Root Directory set to the
   repository root** (not `frontend/`). The frontend fetches
   `../demo/proposals.json` at runtime for its example-proposal chips, so
   `demo/` needs to be served alongside `frontend/`. Open
   `<your-deployment>/frontend/index.html`.
4. Paste a governance proposal (or click one of the example chips) and
   submit — the contract returns the structured simulation report.

`.env.example` documents the RPC endpoint and contract address you'll need,
but note that `frontend/index.html` has no build step and does not read
`.env` at runtime — set `CONTRACT_ADDRESS` and `RPC_URL` directly as
constants in the script instead.

## Known rough edges

- `consensus_summary.areas_of_agreement` has been empty in every real test
  so far — the contract's Consensus Layer looks for an exact-text match on
  a recurring risk or assumption across scenarios, which rarely happens
  with only 3-4 LLM-generated scenarios per run. See
  [`docs/architecture.md`](docs/architecture.md#known-limitations-by-design-for-a-research-poc)
  for details.
- The frontend's `genlayer-js` import path/method names follow the pattern
  used in earlier GenLayer demos but weren't verified against a live SDK
  build in this environment — check them against the current `genlayer-js`
  docs if the page fails to load a client.

## License

MIT — see [LICENSE](LICENSE).
