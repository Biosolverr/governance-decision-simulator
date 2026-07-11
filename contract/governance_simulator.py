# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""
AI Governance Decision Simulator — GenLayer Intelligent Contract
==================================================================

STAGE 10 — full pipeline complete: Parser -> Classifier -> Prompt Builder ->
Scenario Generator (nondet LLM + validator consensus via prompt_comparative)
-> Scenario Normalizer -> Risk & Assumption Engine -> Consensus Layer ->
Simulation Report Builder. `simulate_proposal` now returns the final, clean
report shape described in the spec (no more "stage_N_placeholder" status).
Demo proposals, tests, and documentation polish are covered in stages 11-15
— see docs/progress.md for the full build log.

This contract is a research / proof-of-concept decision-support layer for
DAO governance. It NEVER approves, rejects, scores, ranks, or votes on
proposals. It only generates multiple plausible future scenarios that
describe what could happen if a proposal were accepted, so that human
governance participants can make a more informed decision.

Full pipeline (implemented incrementally, stage by stage):

    1. Proposal Parser        -> extract structured parameters from free text
    2. Proposal Classifier    -> detect proposal category (treasury, quorum, ...)
    3. Simulation Prompt Builder -> category-specific nondet prompt
    4. Scenario Generator      -> nondeterministic LLM call (leader/validator)
    5. Scenario Normalizer     -> dedupe / merge similar scenarios
    6. Risk & Assumption Engine
    7. Consensus Aggregator    -> compare validator outputs
    8. Confidence Estimator
    9. Simulation Report Builder

This file currently only defines the contract shell: storage layout,
constructor, and public entry points as stubs. Each later stage fills in
one module at a time — see docs/progress.md for the build log.
"""

from genlayer import *
import json
import re


# ---------------------------------------------------------------------------
# Module: Proposal Parser
# ---------------------------------------------------------------------------
# Extracts structured parameters out of a free-text governance proposal.
# This is a lightweight, deterministic, regex/heuristic based parser: it
# does NOT call the LLM. Its only job is to give the classifier and prompt
# builder something structured to work with, and to fail gracefully with an
# empty parameter set if the text doesn't match any known pattern (the LLM
# stages later still get the raw text regardless, so nothing is lost).

_PERCENT_CHANGE_RE = re.compile(
    r"(increase|decrease|raise|lower|reduce|cut|boost)\s+.*?(?:by\s+)?(\d+(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)

_FROM_TO_RE = re.compile(
    r"from\s+(\d+(?:\.\d+)?)\s*%?\s+to\s+(\d+(?:\.\d+)?)\s*%?",
    re.IGNORECASE,
)

_ABSOLUTE_AMOUNT_RE = re.compile(
    r"(\$|USDC?|ETH)\s?(\d[\d,]*(?:\.\d+)?)",
    re.IGNORECASE,
)

_QUORUM_KEYWORDS = ("quorum",)
_THRESHOLD_KEYWORDS = ("voting threshold", "approval threshold", "pass threshold")
_TREASURY_KEYWORDS = ("treasury spending", "treasury budget", "treasury allocation", "treasury")
_EMISSION_KEYWORDS = ("emission", "inflation rate", "token issuance")
_VALIDATOR_KEYWORDS = ("validator reward", "validator incentive", "validator commission")
_STAKING_KEYWORDS = ("staking reward", "staking apr", "staking yield")
_GRANT_KEYWORDS = ("grant program", "grants budget", "grant pool")
_FEE_KEYWORDS = ("protocol fee", "swap fee", "transaction fee", "trading fee")
_PARTICIPATION_KEYWORDS = ("participation incentive", "governance incentive", "voter reward")


def parse_proposal(raw_text: str) -> dict:
    """
    Deterministic structured-parameter extraction from proposal free text.

    Returns a dict of the shape used by Proposal.parameters, e.g.:
        {"direction": "increase", "change_percent": 25.0}
        {"from_value": 5.0, "to_value": 8.0}
        {"absolute_amount": 50000.0, "currency": "USDC"}

    Never raises — worst case returns {} and the pipeline falls back to
    pure LLM reasoning over the raw text.
    """
    text = raw_text.strip()
    params: dict = {}

    from_to = _FROM_TO_RE.search(text)
    if from_to:
        try:
            params["from_value"] = float(from_to.group(1))
            params["to_value"] = float(from_to.group(2))
        except ValueError:
            pass

    pct = _PERCENT_CHANGE_RE.search(text)
    if pct:
        direction_word = pct.group(1).lower()
        direction = "increase" if direction_word in ("increase", "raise", "boost") else "decrease"
        params["direction"] = direction
        try:
            params["change_percent"] = float(pct.group(2))
        except ValueError:
            pass

    amount = _ABSOLUTE_AMOUNT_RE.search(text)
    if amount:
        currency_raw = amount.group(1).upper()
        currency = "USD" if currency_raw == "$" else currency_raw
        try:
            params["absolute_amount"] = float(amount.group(2).replace(",", ""))
            params["currency"] = currency
        except ValueError:
            pass

    return params


def validate_parsed_proposal(raw_text: str, params: dict) -> list[str]:
    """
    Lightweight sanity checks. Returns a list of human-readable warnings
    (never raises, never blocks execution — the simulator's job is to
    reason under uncertainty, not to reject malformed input).
    """
    warnings: list[str] = []

    if not raw_text or not raw_text.strip():
        warnings.append("Proposal text is empty.")
        return warnings

    if len(raw_text.strip()) < 10:
        warnings.append("Proposal text is very short; simulation quality may be low.")

    if "from_value" in params and "to_value" in params:
        if params["from_value"] == params["to_value"]:
            warnings.append("Parsed 'from' and 'to' values are identical — no actual change detected.")

    if "change_percent" in params and params["change_percent"] > 500:
        warnings.append("Parsed percentage change is unusually large — double-check extraction.")

    if not params:
        warnings.append(
            "No structured parameters could be extracted; simulation will rely "
            "entirely on free-text LLM reasoning."
        )

    return warnings


# ---------------------------------------------------------------------------
# Module: Proposal Classifier
# ---------------------------------------------------------------------------
# Routes a proposal to one of the 10 supported categories using keyword
# heuristics over the raw text. Deterministic and cheap — this decides which
# category-specific prompt the Prompt Builder (stage 5) will use, and which
# simulation dimensions get emphasized in the report.
#
# Supported categories:
#   treasury, emission, staking_reward, validator_incentive, quorum,
#   voting_threshold, treasury_allocation, grant_program,
#   participation_incentive, protocol_fee
#
# If nothing matches, returns "unknown" — the pipeline still runs (the LLM
# stages fall back to fully generic reasoning over the raw text), it's just
# less targeted.

_CLASSIFIER_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("quorum", _QUORUM_KEYWORDS),
    ("voting_threshold", _THRESHOLD_KEYWORDS),
    ("grant_program", _GRANT_KEYWORDS),
    ("treasury_allocation", ("treasury allocation",)),
    ("treasury", _TREASURY_KEYWORDS),
    ("emission", _EMISSION_KEYWORDS),
    ("validator_incentive", _VALIDATOR_KEYWORDS),
    ("staking_reward", _STAKING_KEYWORDS),
    ("protocol_fee", _FEE_KEYWORDS),
    ("participation_incentive", _PARTICIPATION_KEYWORDS),
]


def classify_proposal(raw_text: str) -> str:
    """
    Keyword-based deterministic classifier. Rule order matters: more
    specific categories (e.g. "treasury_allocation", "quorum") are checked
    before broader ones (e.g. "treasury") to avoid a generic keyword
    swallowing a more specific match.

    Returns one of the 10 supported category strings, or "unknown".
    """
    text_lower = raw_text.lower()

    for category, keywords in _CLASSIFIER_RULES:
        for kw in keywords:
            if kw in text_lower:
                return category

    return "unknown"


def classify_with_confidence(raw_text: str) -> dict:
    """
    Like classify_proposal, but also reports how many distinct category
    rule-sets matched (useful as a debugging / transparency signal — if
    more than one category matched, the proposal is likely a mixed/compound
    proposal and the report should say so rather than silently picking one).
    """
    text_lower = raw_text.lower()
    matched: list[str] = []

    for category, keywords in _CLASSIFIER_RULES:
        if any(kw in text_lower for kw in keywords):
            matched.append(category)

    if not matched:
        return {"proposal_type": "unknown", "matched_categories": [], "is_compound": False}

    return {
        "proposal_type": matched[0],
        "matched_categories": matched,
        "is_compound": len(matched) > 1,
    }


# ---------------------------------------------------------------------------
# Module: Simulation Prompt Builder
# ---------------------------------------------------------------------------
# Builds a category-specific prompt instructing the LLM to generate MULTIPLE
# plausible future scenarios for a governance proposal. Every prompt shares
# a common contract (never approve/reject/score/rank, always multiple
# futures, always explicit assumptions, always avoid false certainty) plus
# category-specific dimensions to focus on.

_COMMON_SIMULATION_CONTRACT = """\
You are a governance simulation engine, NOT a governance decision-maker.

STRICT RULES — never violate these:
- Do NOT approve or reject the proposal.
- Do NOT assign a score, rank, or grade to the proposal.
- Do NOT recommend accepting or rejecting it.
- Do NOT claim certainty about the future — every prediction is a plausible
  scenario, not a fact.
- ALWAYS generate MULTIPLE distinct scenarios (at least 3), never just one.
- ALWAYS state the explicit assumptions each scenario depends on.
- Reason about economic and governance tradeoffs, not just upside.

Respond ONLY with valid JSON matching this shape (no markdown, no prose
outside the JSON):
{
  "scenarios": [
    {
      "title": "short scenario name",
      "summary": "2-4 sentence narrative",
      "assumptions": [{"statement": "...", "category": "market|governance|protocol|community|general"}],
      "treasury_effects": ["..."],
      "governance_effects": ["..."],
      "validator_effects": ["..."],
      "community_effects": ["..."],
      "protocol_effects": ["..."],
      "risks": [{"description": "...", "severity": "low|medium|high|critical", "likelihood": "low|medium|high"}],
      "confidence": "High|Medium|Low|Very Low"
    }
  ]
}
"""

_CATEGORY_FOCUS: dict[str, str] = {
    "treasury": (
        "Focus especially on: treasury runway (months of spending covered), "
        "monthly spending rate, reserve growth/depletion, and whether "
        "increased spend is offset by ecosystem growth or contributor influx."
    ),
    "treasury_allocation": (
        "Focus especially on: how reallocating treasury funds shifts "
        "priorities between areas (e.g. grants vs core dev vs marketing), "
        "and second-order effects on contributor incentives."
    ),
    "emission": (
        "Focus especially on: token supply growth, inflationary pressure on "
        "price, staking/holding incentives, and long-term dilution vs "
        "network growth tradeoffs."
    ),
    "staking_reward": (
        "Focus especially on: staking participation rate, APR sustainability, "
        "token lock-up effects on liquidity, and whether higher rewards are "
        "funded sustainably or draw down treasury/emission reserves."
    ),
    "validator_incentive": (
        "Focus especially on: validator profitability, retention, new "
        "validator attraction, decentralization (validator count and "
        "distribution), and network security implications."
    ),
    "quorum": (
        "Focus especially on: expected voter turnout, probability future "
        "proposals reach quorum, risk of governance paralysis vs risk of "
        "low-legitimacy decisions, and whale/large-holder influence."
    ),
    "voting_threshold": (
        "Focus especially on: how threshold changes affect the ease of "
        "passing contentious vs uncontentious proposals, and minority "
        "protection vs decision-making speed tradeoffs."
    ),
    "grant_program": (
        "Focus especially on: grant applications volume, contributor and "
        "developer growth, treasury drawdown from the grant pool, and "
        "risk of low-quality or low-impact grant spending."
    ),
    "participation_incentive": (
        "Focus especially on: voter turnout changes, quality vs quantity of "
        "governance participation, risk of incentivizing uninformed voting, "
        "and treasury cost of the incentive program."
    ),
    "protocol_fee": (
        "Focus especially on: protocol revenue, usage/volume elasticity to "
        "fee changes, competitiveness vs other protocols, and treasury "
        "income sustainability."
    ),
    "unknown": (
        "The proposal category could not be determined automatically. "
        "Reason generally across treasury, governance, validator economics, "
        "community, and protocol health dimensions as applicable."
    ),
}


def build_simulation_prompt(proposal_text: str, proposal_type: str, parsed_params: dict) -> str:
    """
    Assemble the full nondeterministic-execution prompt for a given
    proposal: common contract + category-specific focus + the proposal
    itself + any structured parameters extracted by the parser.
    """
    focus = _CATEGORY_FOCUS.get(proposal_type, _CATEGORY_FOCUS["unknown"])

    params_block = ""
    if parsed_params:
        params_block = f"\nStructured parameters extracted from the proposal: {json.dumps(parsed_params)}\n"

    prompt = (
        f"{_COMMON_SIMULATION_CONTRACT}\n"
        f"Proposal category: {proposal_type}\n"
        f"{focus}\n"
        f"{params_block}\n"
        f"Governance proposal to simulate:\n\"\"\"\n{proposal_text}\n\"\"\"\n\n"
        f"Generate at least 3 distinct plausible future scenarios "
        f"(e.g. optimistic, expected/conservative, and a downside or "
        f"unexpected case) following the JSON shape above."
    )
    return prompt


# ---------------------------------------------------------------------------
# Module: Scenario Generator
# ---------------------------------------------------------------------------
# This is where GenLayer's nondeterministic execution + validator consensus
# actually happens, via gl.eq_principle.prompt_comparative(fn, principle).
# GenVM calls the zero-argument `fn` once for the leader, then once per
# validator; each validator's own result is judged against the leader's
# (encoded as calldata) using NLP per `principle` — all of that happens
# inside prompt_comparative itself, the contract does not manually orchestrate
# leader_fn/validator_fn or call gl.vm.run_nondet directly for this.
#
# Because different validators may get slightly different LLM outputs
# (different random scenarios, different wording), we do NOT use strict
# equality consensus (gl.eq_principle.strict_eq) — that would cause
# UNDETERMINED results almost every time. prompt_comparative instead asks
# an LLM to judge whether two outputs are "close enough" (same structural
# shape, same kind of reasoning) even if the exact scenarios differ. This
# mirrors the lesson learned on the Prediction Market Oracle project:
# float/text drift across validators is expected and should be tolerated,
# not treated as a fault.
#
# CORRECTED (see docs/progress.md): an earlier draft of this module called
# prompt_comparative(candidate, leader_result, principle) — 3 positional
# args — inside a hand-rolled validator_fn passed to gl.vm.run_nondet. That
# crashed every validator with `TypeError: prompt_comparative() takes 2
# positional arguments but 3 were given`, caught live in GenLayer Studio.
# The correct call is prompt_comparative(fn, principle) — see
# _generate_scenarios below.

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _strip_json_fence(text: str) -> str:
    """LLMs sometimes wrap JSON in ```json ... ``` even when told not to."""
    return _JSON_FENCE_RE.sub("", text.strip()).strip()


def generate_scenarios_raw(prompt: str) -> str:
    """
    Called from the zero-argument nondet function passed to
    gl.eq_principle.prompt_comparative (see _generate_scenarios below).
    Performs the actual nondet LLM call and returns the raw text response
    (expected to be JSON, but this function does not parse it — that's the
    Scenario Normalizer's job in stage 7, so a malformed response doesn't
    crash generation itself).
    """
    result = gl.nondet.exec_prompt(prompt)
    return _strip_json_fence(result)


# NOTE: the actual nondet wiring that calls generate_scenarios_raw() lives
# inside the contract class below, as the `_generate_scenarios` method —
# GenVM requires nondet calls to be issued from within the write method
# that needs them, using `gl.eq_principle.prompt_comparative(fn, principle)`,
# not as free module-level functions.


# ---------------------------------------------------------------------------
# Module: Scenario Normalizer
# ---------------------------------------------------------------------------
# Takes the raw list of scenario dicts parsed from the LLM's JSON response
# and: (1) fills in any missing fields with safe defaults so downstream
# code never KeyErrors, (2) deduplicates near-identical scenarios using a
# cheap text-similarity heuristic (no LLM call — this stage must be fast
# and deterministic), (3) merges scenarios whose titles/summaries are
# highly similar into a single scenario with combined effect lists.

_SCENARIO_DEFAULT_FIELDS = {
    "title": "Untitled scenario",
    "summary": "",
    "assumptions": [],
    "treasury_effects": [],
    "governance_effects": [],
    "validator_effects": [],
    "community_effects": [],
    "protocol_effects": [],
    "risks": [],
    "confidence": "Medium",
}

_VALID_CONFIDENCE_LEVELS = ("High", "Medium", "Low", "Very Low")


def _normalize_single_scenario(raw: dict) -> dict:
    """Fill missing fields, coerce types, clamp confidence to known values."""
    scenario = dict(_SCENARIO_DEFAULT_FIELDS)
    if isinstance(raw, dict):
        for key in _SCENARIO_DEFAULT_FIELDS:
            if key in raw and raw[key] is not None:
                scenario[key] = raw[key]

    if scenario["confidence"] not in _VALID_CONFIDENCE_LEVELS:
        scenario["confidence"] = "Medium"

    # Coerce list fields that the LLM might have returned as a single string.
    for list_field in (
        "assumptions", "treasury_effects", "governance_effects",
        "validator_effects", "community_effects", "protocol_effects", "risks",
    ):
        if isinstance(scenario[list_field], str):
            scenario[list_field] = [scenario[list_field]] if scenario[list_field] else []
        elif not isinstance(scenario[list_field], list):
            scenario[list_field] = []

    return scenario


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _jaccard_similarity(a: str, b: str) -> float:
    tokens_a, tokens_b = _tokenize(a), _tokenize(b)
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = len(tokens_a & tokens_b)
    union = len(tokens_a | tokens_b)
    return intersection / union if union else 0.0


_MERGE_SIMILARITY_THRESHOLD = 0.55


def _merge_two_scenarios(a: dict, b: dict) -> dict:
    """Merge b into a: union effect lists/risks/assumptions, keep a's title,
    combine summaries, and average confidence toward the more conservative
    (lower) of the two — merging should never silently claim more
    confidence than either source scenario had."""
    merged = dict(a)
    for list_field in (
        "assumptions", "treasury_effects", "governance_effects",
        "validator_effects", "community_effects", "protocol_effects", "risks",
    ):
        combined = list(a[list_field])
        for item in b[list_field]:
            if item not in combined:
                combined.append(item)
        merged[list_field] = combined

    if a["summary"] != b["summary"]:
        merged["summary"] = f"{a['summary']} Additionally: {b['summary']}".strip()

    order = {"Very Low": 0, "Low": 1, "Medium": 2, "High": 3}
    merged["confidence"] = min(
        a["confidence"], b["confidence"], key=lambda c: order.get(c, 2)
    )
    return merged


def normalize_and_dedupe_scenarios(raw_scenarios: list) -> list[dict]:
    """
    Full Scenario Normalizer entry point: normalize each scenario's shape,
    then merge any pair whose title+summary similarity exceeds the merge
    threshold. Deterministic, no LLM call.
    """
    normalized = [_normalize_single_scenario(s) for s in raw_scenarios]

    merged: list[dict] = []
    for scenario in normalized:
        did_merge = False
        for i, existing in enumerate(merged):
            sim = _jaccard_similarity(
                existing["title"] + " " + existing["summary"],
                scenario["title"] + " " + scenario["summary"],
            )
            if sim >= _MERGE_SIMILARITY_THRESHOLD:
                merged[i] = _merge_two_scenarios(existing, scenario)
                did_merge = True
                break
        if not did_merge:
            merged.append(scenario)

    return merged


# ---------------------------------------------------------------------------
# Module: Risk & Assumption Engine
# ---------------------------------------------------------------------------
# Cross-cutting analysis over the normalized scenario set: makes sure every
# scenario actually has explicit assumptions and risk factors (scenarios
# that skip this in the LLM output get sensible deterministic fallbacks
# derived from their confidence level), and produces an aggregate view
# across ALL scenarios — which risks/assumptions recur, and which
# confidence levels dominate. This aggregate view feeds directly into the
# Consensus Layer (stage 9) and the final report (stage 10).

_LOW_CONFIDENCE_FALLBACK_RISK = {
    "description": "Scenario has low internal consistency; treat predicted effects as speculative.",
    "severity": "medium",
    "likelihood": "medium",
}

_GENERIC_FALLBACK_ASSUMPTION = {
    "statement": "No explicit assumptions were provided by the model for this scenario; broader market and governance conditions are assumed to remain roughly stable.",
    "category": "general",
}


def enrich_risks_and_assumptions(scenarios: list[dict]) -> list[dict]:
    """
    Ensures every scenario has at least one assumption and, for Low/Very Low
    confidence scenarios, at least one explicit risk factor (a scenario the
    model itself flagged as low-confidence but listed zero risks is treated
    as incomplete, not as risk-free).
    """
    enriched = []
    for scenario in scenarios:
        s = dict(scenario)
        if not s.get("assumptions"):
            s["assumptions"] = [dict(_GENERIC_FALLBACK_ASSUMPTION)]
        if s.get("confidence") in ("Low", "Very Low") and not s.get("risks"):
            s["risks"] = [dict(_LOW_CONFIDENCE_FALLBACK_RISK)]
        enriched.append(s)
    return enriched


def aggregate_risk_and_assumption_view(scenarios: list[dict]) -> dict:
    """
    Cross-scenario aggregate: which risk descriptions and assumption
    statements recur across multiple scenarios (a recurring risk across
    otherwise-different futures is a stronger signal than a risk mentioned
    in just one scenario), plus a confidence-level histogram.
    """
    risk_counts: dict[str, int] = {}
    assumption_counts: dict[str, int] = {}
    confidence_histogram = {"High": 0, "Medium": 0, "Low": 0, "Very Low": 0}

    for scenario in scenarios:
        for risk in scenario.get("risks", []):
            desc = risk.get("description", "").strip() if isinstance(risk, dict) else str(risk)
            if desc:
                risk_counts[desc] = risk_counts.get(desc, 0) + 1

        for assumption in scenario.get("assumptions", []):
            statement = (
                assumption.get("statement", "").strip()
                if isinstance(assumption, dict)
                else str(assumption)
            )
            if statement:
                assumption_counts[statement] = assumption_counts.get(statement, 0) + 1

        conf = scenario.get("confidence", "Medium")
        if conf in confidence_histogram:
            confidence_histogram[conf] += 1

    recurring_risks = sorted(
        [{"description": k, "scenario_count": v} for k, v in risk_counts.items() if v > 1],
        key=lambda r: -r["scenario_count"],
    )
    recurring_assumptions = sorted(
        [{"statement": k, "scenario_count": v} for k, v in assumption_counts.items() if v > 1],
        key=lambda a: -a["scenario_count"],
    )

    return {
        "recurring_risks": recurring_risks,
        "recurring_assumptions": recurring_assumptions,
        "confidence_histogram": confidence_histogram,
        "total_scenarios": len(scenarios),
    }


# ---------------------------------------------------------------------------
# Module: Consensus Layer
# ---------------------------------------------------------------------------
# GenVM's own validator consensus (via prompt_comparative in stage 6)
# already ensures the LEADER's output was judged "close enough in
# structure/approach" by every validator before the transaction finalizes —
# that's blockchain-level consensus on WHETHER to accept the leader's
# result at all. This module is a separate, complementary layer: given the
# (already-agreed-upon) final scenario set, it produces a human-readable
# breakdown of which individual scenarios show strong internal agreement
# vs weak/edge signals, framed as "Consensus Scenarios" / "Minor
# Differences" / "Unique Insights" per the spec — using confidence and
# recurrence (from stage 8's aggregate view) as the basis, since GenVM does
# not expose each individual validator's raw scenario set to the contract
# after consensus (only the agreed final result is available on-chain).

def build_consensus_result(
    scenarios: list[dict], risk_assumption_view: dict
) -> dict:
    """
    Derives a ConsensusResult-shaped dict from the final agreed scenario
    set + its aggregate risk/assumption view.

    - consensus_scenarios: High/Medium confidence scenarios whose key risk
      or assumption recurs elsewhere in the set (broad agreement signal).
    - minor_differences: Medium/Low confidence scenarios that don't share
      recurring risks/assumptions with the rest (same rough shape, weaker
      corroboration).
    - unique_insights: Very Low confidence scenarios, or any scenario whose
      title appears only once and shares nothing recurring — the
      "interesting alternative outcome" bucket, kept rather than discarded.
    """
    recurring_risk_texts = {r["description"] for r in risk_assumption_view.get("recurring_risks", [])}
    recurring_assumption_texts = {
        a["statement"] for a in risk_assumption_view.get("recurring_assumptions", [])
    }

    consensus_scenarios: list[str] = []
    minor_differences: list[str] = []
    unique_insights: list[str] = []

    for scenario in scenarios:
        title = scenario.get("title", "Untitled scenario")
        confidence = scenario.get("confidence", "Medium")

        has_recurring_risk = any(
            (r.get("description", "") if isinstance(r, dict) else str(r)) in recurring_risk_texts
            for r in scenario.get("risks", [])
        )
        has_recurring_assumption = any(
            (a.get("statement", "") if isinstance(a, dict) else str(a)) in recurring_assumption_texts
            for a in scenario.get("assumptions", [])
        )
        shares_something_recurring = has_recurring_risk or has_recurring_assumption

        if confidence == "Very Low":
            unique_insights.append(title)
        elif confidence in ("High", "Medium") and shares_something_recurring:
            consensus_scenarios.append(title)
        elif shares_something_recurring:
            minor_differences.append(title)
        else:
            unique_insights.append(title)

    confidence_distribution = dict(risk_assumption_view.get("confidence_histogram", {}))

    return {
        "consensus_scenarios": consensus_scenarios,
        "minor_differences": minor_differences,
        "unique_insights": unique_insights,
        "confidence_distribution": confidence_distribution,
    }


# ---------------------------------------------------------------------------
# Module: Simulation Report Builder
# ---------------------------------------------------------------------------
# Final assembly stage: takes everything produced by the pipeline so far
# (parsed proposal, classification, enriched/consensus-bucketed scenarios,
# risk/assumption overview) and produces the clean, final report shape
# described in the spec's "Output Structure" section. This is the shape
# returned to callers going forward — no more "stage_N_placeholder" status.

_TIME_HORIZON_BY_CATEGORY = {
    "treasury": "3-9 months",
    "treasury_allocation": "3-9 months",
    "emission": "6-18 months",
    "staking_reward": "3-12 months",
    "validator_incentive": "1-6 months",
    "quorum": "1-3 months",
    "voting_threshold": "1-3 months",
    "grant_program": "6-12 months",
    "participation_incentive": "1-6 months",
    "protocol_fee": "1-6 months",
    "unknown": "3-6 months",
}


def estimate_time_horizon(proposal_type: str) -> str:
    """
    Deterministic lookup of a sensible simulation time horizon per
    category. Treasury/emission/grant effects play out over longer windows
    than quorum/threshold changes, which show up almost immediately in the
    next few votes.
    """
    return _TIME_HORIZON_BY_CATEGORY.get(proposal_type, _TIME_HORIZON_BY_CATEGORY["unknown"])


def build_simulation_report(
    simulation_id: int,
    proposal_text: str,
    proposal_type: str,
    is_compound: bool,
    scenarios: list[dict],
    risk_assumption_view: dict,
    consensus_result: dict,
    parser_warnings: list[str],
) -> dict:
    """
    Assembles the final, clean Simulation Report per the spec's Output
    Structure: Proposal Summary, Detected Proposal Type, Simulation Time
    Horizon, Generated Scenarios (each with all 5 effect categories + risks
    + confidence), and Consensus Summary (agreements / disagreements /
    alternative outcomes).
    """
    time_horizon = estimate_time_horizon(proposal_type)

    report = {
        "simulation_id": simulation_id,
        "proposal_summary": proposal_text[:280],
        "detected_proposal_type": proposal_type,
        "is_compound_proposal": is_compound,
        "simulation_time_horizon": time_horizon,
        "generated_scenarios": [
            {
                "title": s.get("title", "Untitled scenario"),
                "narrative": s.get("summary", ""),
                "key_assumptions": s.get("assumptions", []),
                "treasury_effects": s.get("treasury_effects", []),
                "governance_effects": s.get("governance_effects", []),
                "validator_effects": s.get("validator_effects", []),
                "community_effects": s.get("community_effects", []),
                "protocol_effects": s.get("protocol_effects", []),
                "risk_factors": s.get("risks", []),
                "confidence": s.get("confidence", "Medium"),
            }
            for s in scenarios
        ],
        "consensus_summary": {
            "areas_of_agreement": consensus_result.get("consensus_scenarios", []),
            "areas_of_disagreement": consensus_result.get("minor_differences", []),
            "interesting_alternative_outcomes": consensus_result.get("unique_insights", []),
            "confidence_distribution": consensus_result.get("confidence_distribution", {}),
        },
        "risk_and_assumption_overview": risk_assumption_view,
        "parser_warnings": parser_warnings,
        "disclaimer": (
            "This report presents multiple plausible futures for "
            "informational purposes only. It does not approve, reject, "
            "score, or recommend any decision about this proposal."
        ),
    }
    return report


# ---------------------------------------------------------------------------
# Storage layout
# ---------------------------------------------------------------------------
# NOTE: plain typed class attributes are used for on-chain storage (GenVM
# handles allocation automatically). Do NOT use gl.storage.inmem_allocate —
# that pattern is deprecated in current GenVM releases.

class GovernanceDecisionSimulator(gl.Contract):
    # Address that deployed the contract (owner / demo administrator).
    owner: Address

    # Running counter of how many simulations have been produced so far.
    simulations_count: u256

    # simulation_id -> raw JSON report (string), so the frontend can fetch
    # historical simulations by id.
    reports: TreeMap[u256, str]

    # simulation_id -> original raw proposal text, kept for auditability.
    proposals: TreeMap[u256, str]

    def __init__(self):
        self.owner = gl.message.sender_address
        self.simulations_count = u256(0)
        self.reports = TreeMap()
        self.proposals = TreeMap()

    # -----------------------------------------------------------------
    # Public read methods
    # -----------------------------------------------------------------

    @gl.public.view
    def get_simulations_count(self) -> u256:
        return self.simulations_count

    @gl.public.view
    def get_report(self, simulation_id: u256) -> str:
        """Return the stored JSON report for a given simulation id."""
        if simulation_id not in self.reports:
            return json.dumps({"error": "simulation not found"})
        return self.reports[simulation_id]

    @gl.public.view
    def get_proposal(self, simulation_id: u256) -> str:
        if simulation_id not in self.proposals:
            return json.dumps({"error": "proposal not found"})
        return self.proposals[simulation_id]

    @gl.public.view
    def get_owner(self) -> str:
        return str(self.owner)

    # -----------------------------------------------------------------
    # Internal: nondeterministic Scenario Generator (stage 6)
    # -----------------------------------------------------------------

    def _generate_scenarios(self, prompt: str) -> str:
        """
        Runs the simulation prompt through GenLayer's nondeterministic
        execution with validator consensus, via
        `gl.eq_principle.prompt_comparative(fn, principle)`.

        IMPORTANT — corrected API usage (see docs/progress.md, stage 6
        hotfix): this call takes exactly two arguments, a zero-argument
        callable and a principle string. It is NOT a manual comparator you
        call yourself with (candidate, leader_result, criteria) — GenVM
        calls `fn` once for the leader and once per validator internally,
        encodes the leader's result as calldata, and has each validator
        judge equivalence against it via NLP using `principle`. An earlier
        version of this method hand-rolled `gl.vm.run_nondet(leader_fn,
        validator_fn)` and called `prompt_comparative` with 3 positional
        args inside validator_fn, which is simply the wrong shape for this
        API and crashed every validator with a TypeError (caught during
        Studio testing).

        Returns the raw (fence-stripped) LLM text, expected to be JSON per
        the prompt's contract. Parsing/validation happens in stage 7
        (Scenario Normalizer) so a malformed response here doesn't crash
        the whole write transaction.
        """

        def nondet_fn() -> str:
            return generate_scenarios_raw(prompt)

        principle = (
            "Both texts should describe multiple plausible future "
            "governance scenarios in a similar structural format (JSON "
            "with scenarios, assumptions, effects, risks, confidence). "
            "They do not need identical wording or identical predictions "
            "— only a similar structure and reasoning approach."
        )

        return gl.eq_principle.prompt_comparative(nondet_fn, principle)

    # -----------------------------------------------------------------
    # Public write method — main entry point (STUB for stage 1)
    # -----------------------------------------------------------------

    @gl.public.write
    def simulate_proposal(self, proposal_text: str) -> str:
        """
        Main entry point: receives a raw governance proposal as free text
        and will eventually run it through the full simulation pipeline.

        This is the final entry point: Proposal Parser -> Classifier ->
        Prompt Builder -> Scenario Generator (nondet LLM + validator
        consensus) -> Scenario Normalizer -> Risk & Assumption Engine ->
        Consensus Layer -> Simulation Report Builder. Returns a clean,
        stable JSON report shape per the spec's Output Structure section.
        The contract NEVER approves, rejects, scores, ranks, or recommends
        a decision — see the `disclaimer` field on every report.
        """
        simulation_id = self.simulations_count

        parsed_params = parse_proposal(proposal_text)
        parser_warnings = validate_parsed_proposal(proposal_text, parsed_params)
        classification = classify_with_confidence(proposal_text)
        proposal_type = classification["proposal_type"]
        simulation_prompt = build_simulation_prompt(proposal_text, proposal_type, parsed_params)

        raw_llm_output = self._generate_scenarios(simulation_prompt)

        # Best-effort parse — malformed LLM output never fails the
        # transaction; the Normalizer tolerates missing/odd fields, and if
        # parsing fails entirely we simply proceed with an empty scenario
        # list rather than reverting (a governance simulation tool should
        # degrade gracefully, not brick a transaction over LLM formatting).
        raw_scenarios: list = []
        try:
            parsed = json.loads(raw_llm_output)
            raw_scenarios = parsed.get("scenarios", [])
        except (json.JSONDecodeError, AttributeError):
            parser_warnings = parser_warnings + [
                "LLM output could not be parsed as JSON; scenario list may be incomplete."
            ]

        normalized_scenarios = normalize_and_dedupe_scenarios(raw_scenarios)

        # IMPORTANT: aggregate the risk/assumption view BEFORE enrichment.
        # enrich_risks_and_assumptions injects a shared fallback risk/
        # assumption string into every low-confidence scenario that lacks
        # one; if we aggregated AFTER enrichment, that synthetic shared
        # text would get miscounted as "recurring" (multiple scenarios
        # independently agreeing) when it's really just the same fallback
        # text reused verbatim. Aggregating first keeps recurrence a
        # genuine cross-scenario signal.
        risk_assumption_view = aggregate_risk_and_assumption_view(normalized_scenarios)
        enriched_scenarios = enrich_risks_and_assumptions(normalized_scenarios)
        consensus_result = build_consensus_result(enriched_scenarios, risk_assumption_view)

        report = build_simulation_report(
            simulation_id=int(simulation_id),
            proposal_text=proposal_text,
            proposal_type=proposal_type,
            is_compound=classification["is_compound"],
            scenarios=enriched_scenarios,
            risk_assumption_view=risk_assumption_view,
            consensus_result=consensus_result,
            parser_warnings=parser_warnings,
        )
        report_json = json.dumps(report)

        self.proposals[simulation_id] = proposal_text
        self.reports[simulation_id] = report_json
        self.simulations_count = u256(int(simulation_id) + 1)

        return report_json
