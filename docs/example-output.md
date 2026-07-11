# Example output

**Note:** this is a synthetic example — the deterministic pipeline stages
(Parser → Classifier → Normalizer → Risk & Assumption Engine → Consensus
Layer → Report Builder) ran for real locally, but the LLM step itself was
stubbed with a hand-written fake scenario set, since this was produced
before the contract was deployed to GenLayer Studio. It shows the exact
output *shape*, not a real model response.

**For real, on-chain LLM-generated output, see [`demo/proof.json`](../demo/proof.json)**
— three actual `simulate_proposal` transactions run on GenLayer Studionet,
with real validator consensus, real tx hashes, and real generated
scenarios.

This synthetic example, run against the proposal from the project spec's
own example:

**Input:** `"Increase validator rewards from 5% to 8%."`

```json
{
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

Note all three scenarios landed in `interesting_alternative_outcomes` here
— that's correct given none of these three fabricated test scenarios
shared a recurring risk/assumption with each other. In a real LLM run
across multiple validators, scenarios that genuinely converge on the same
underlying risk (e.g. multiple validators independently flagging
"long-term sustainability decreases") would surface in
`areas_of_agreement` instead.
