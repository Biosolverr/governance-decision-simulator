# Example output

Note: this is a synthetic example. The deterministic pipeline stages
(Parser, Classifier, Normalizer, Risk & Assumption Engine, Consensus
Layer, Report Builder) ran for real locally, but the LLM step itself was
stubbed with a hand written fake scenario set, since this was produced
before the contract was deployed to GenLayer Studio. It shows the exact
output shape, not a real model response.

For real, on chain LLM generated output, see `demo/proof.json` once fresh
Studionet transactions have been run against the current contract version
(the previous `demo/proof.json` was captured against an earlier revision
and should be treated as outdated until it is regenerated).

This synthetic example uses the proposal from the project spec's own
example.

Input: `"Increase validator rewards from 5% to 8%."`

```json
{
  "schema_version": 1,
  "principle_version": "v2-substantive-2026-07-20",
  "simulation_id": 0,
  "proposal_summary": "Increase validator rewards from 5% to 8%.",
  "detected_proposal_type": "validator_incentive",
  "is_compound_proposal": false,
  "simulation_time_horizon": "1-6 months",
  "generated_scenarios": [
    {
      "title": "Higher participation",
      "narrative": "Validator participation increases as rewards rise.",
      "key_assumptions": [
        {"statement": "Token price remains stable", "category": "market"}
      ],
      "treasury_effects": ["Treasury expenses rise"],
      "governance_effects": [],
      "validator_effects": ["New validators join"],
      "community_effects": [],
      "protocol_effects": [],
      "risk_factors": [
        {"description": "Long-term sustainability decreases", "severity": "medium", "likelihood": "medium"}
      ],
      "confidence": "High"
    },
    {
      "title": "Minimal participation change",
      "narrative": "Validator participation changes little despite the raise.",
      "key_assumptions": [
        {"statement": "No explicit assumptions were provided by the model for this scenario; broader market and governance conditions are assumed to remain roughly stable.", "category": "general"}
      ],
      "treasury_effects": ["Treasury spending increases unnecessarily"],
      "governance_effects": [],
      "validator_effects": [],
      "community_effects": [],
      "protocol_effects": [],
      "risk_factors": [],
      "confidence": "Medium"
    },
    {
      "title": "Decentralization improves",
      "narrative": "Higher rewards improve decentralization and network security.",
      "key_assumptions": [
        {"statement": "No explicit assumptions were provided by the model for this scenario; broader market and governance conditions are assumed to remain roughly stable.", "category": "general"}
      ],
      "treasury_effects": [],
      "governance_effects": [],
      "validator_effects": [],
      "community_effects": ["Community confidence increases"],
      "protocol_effects": [],
      "risk_factors": [],
      "confidence": "Medium"
    }
  ],
  "consensus_summary": {
    "areas_of_agreement": [],
    "areas_of_disagreement": [],
    "interesting_alternative_outcomes": [
      "Higher participation",
      "Minimal participation change",
      "Decentralization improves"
    ],
    "confidence_distribution": {"High": 1, "Medium": 2, "Low": 0, "Very Low": 0}
  },
  "risk_and_assumption_overview": {
    "recurring_risks": [],
    "recurring_assumptions": [],
    "confidence_histogram": {"High": 1, "Medium": 2, "Low": 0, "Very Low": 0},
    "total_scenarios": 3
  },
  "parser_warnings": [],
  "disclaimer": "This report presents multiple plausible futures for informational purposes only. It does not approve, reject, score, or recommend any decision about this proposal."
}
```

Note all three scenarios landed in `interesting_alternative_outcomes` here.
That is correct given none of these three fabricated test scenarios shared
a recurring risk or assumption with each other. In a real LLM run across
multiple validators, scenarios that genuinely converge on the same
underlying risk (for example, multiple validators independently flagging
"long-term sustainability decreases") would surface in
`areas_of_agreement` instead.

Two fields on this report are new since the pipeline shape above was
first documented:

- `schema_version` marks the overall report shape. It stays at `1` as
  long as no field is renamed or removed; new fields can be added without
  bumping it.
- `principle_version` records which version of the `_generate_scenarios`
  equivalence principle this specific simulation was accepted under. See
  `docs/architecture.md` for what changed between principle versions.

## Other ways to read a stored simulation

Beyond `get_report(simulation_id)`, which returns the exact JSON shape
above, the contract exposes a few read only views built from the same
stored data, useful for a frontend or for manual inspection in Studio:

- `get_report_markdown(simulation_id)` renders the same report as
  readable Markdown instead of JSON.
- `get_normalizer_diff(simulation_id)` shows how many scenarios the raw
  LLM output contained before the Normalizer merged or dropped any of
  them, and which titles did not make it into the final report.
- `compare_simulations(id1, id2)` diffs two stored reports directly:
  same category or not, confidence distribution side by side, and which
  scenario titles are unique to each versus shared. This is the natural
  way to inspect the result of `simulate_variant`, since a variant and
  its parent are two separate stored simulations.
- `get_confidence_trend(category)` and `get_category_stats()` give
  running totals across all simulations of a category, rather than a
  single simulation's detail.

None of these change what `simulate_proposal` returns; they only offer
different views onto data that is already stored on chain.
