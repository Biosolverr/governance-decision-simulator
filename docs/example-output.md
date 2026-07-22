# Example output

## Synthetic pipeline-shape example

This first example is synthetic. The deterministic pipeline stages
(Parser, Classifier, Normalizer, Risk & Assumption Engine, Consensus
Layer, Report Builder) ran for real locally, but the LLM step itself was
stubbed with a hand written fake scenario set, since this was produced
before the contract was deployed to GenLayer Studio. It shows the exact
output shape, not a real model response. A real, live-captured example
follows further down.

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
  "onchain_context_used": false,
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
`areas_of_agreement` instead. In practice, real runs so far have still
landed everything in `interesting_alternative_outcomes` too, see
`docs/architecture.md`'s Known limitations section for why.

Fields worth calling out on this report shape:

- `schema_version` marks the overall report shape. It stays at `1` as
  long as no field is renamed or removed; new fields can be added without
  bumping it.
- `principle_version` records which version of the `_generate_scenarios`
  equivalence principle this specific simulation was accepted under. See
  `docs/architecture.md` for what changed between principle versions.
- `onchain_context_used` is `true` only when the On-chain Context Fetcher
  successfully grounded this specific simulation in real fetched data
  (treasury category only, and only if the owner enabled the feature and
  configured a data source). It is `false` here since this example
  predates that feature entirely.

## Real, live-captured example: on-chain context grounding

Unlike the example above, this one is a real transaction accepted on
GenLayer Studionet, with the on-chain context grounding feature (see
`docs/architecture.md`) enabled and pointed at a public JSON snapshot
serving:

```json
{"treasury_balance_usd": 4200000, "monthly_spend_usd": 175000, "runway_months": 24}
```

Input: `"Proposal to increase treasury spending by 10% to fund additional
grants over the next two quarters."`

Relevant excerpt of the accepted report (trimmed to the fields that show
the grounding effect; full scenario objects also include
`governance_effects`, `validator_effects`, `community_effects`,
`protocol_effects`, and `risk_factors` per the schema above):

```json
{
  "simulation_id": 1,
  "detected_proposal_type": "treasury",
  "onchain_context_used": true,
  "generated_scenarios": [
    {
      "title": "Ecosystem Growth Outpaces Spend Increase",
      "treasury_effects": [
        "Monthly spend rises to ~$192,500 (10% increase)",
        "Runway initially drops to ~21.8 months (4200000 / 192500)",
        "New revenue streams add ~$50,000/month after 6 months, stabilizing runway at ~24 months"
      ],
      "confidence": "Medium"
    }
  ]
}
```

The LLM computed `~$192,500` as 10% over the fetched `monthly_spend_usd`
of `175000`, and `~21.8 months` as the fetched `treasury_balance_usd` of
`4200000` divided by that new spend rate, both figures traceable directly
to the on-chain context rather than invented. The Equivalence Principle
output for the context-fetch step on this same transaction showed the
identical JSON snapshot above, confirming the validator that produced it
fetched the URL independently rather than copying the leader's value.

`get_onchain_context(1)` returns exactly the snapshot JSON shown above;
`get_onchain_context(0)` (a simulation made before the feature was
enabled) returns an empty string, meaning no context was used for that
run.

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
- `get_onchain_context(simulation_id)` returns the JSON context actually
  used for that specific simulation (empty string if none was used),
  distinct from `get_onchain_context_config()`, which returns the
  contract-wide feature toggle and configured data source URL rather than
  anything tied to one simulation.

None of these change what `simulate_proposal` returns; they only offer
different views onto data that is already stored on chain.
