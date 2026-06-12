# Verification Council Log

`council-log.jsonl` is the append-only finding log of the sonic-kb verification
council (Phase 5). The council verifies KB content by **blind re-derivation**:
domain agents never see the candidate content — they independently derive
answers from their evidence source, and a mechanical diff against the candidate
produces findings. One adversarial fault-finder scores findings (severity x
confidence, evidence-gated) as a foil against echo-chamber agreement.

One JSON object per line; schema in `council-log.schema.json`.

## Council members (differ by evidence source)

| Agent        | Evidence source                              | Claim types        |
|--------------|----------------------------------------------|--------------------|
| config       | build/artifacts/db_schemas.json (206 tables) | config-syntax      |
| architecture | build/repos/ source clones (cites file:line) | source-ref         |
| rfc          | protocol specs (cites RFC/IEEE section)      | protocol-behavior  |
| logic        | none — internal reasoning; also whole-checker| internal-logic     |
| fault-finder | any of the above; required to escalate       | scores all findings|

The whole-check (completeness / consistency / entailment) runs after parts
verify and is never skipped — completeness guards the decomposer
single-point-of-failure.

## Tiers (split by persistence — KB errors compound forever)

- **0** interactive question: one routed domain agent, logged inline
- **1** content entering the KB: full council, no escalation round
- **2** `/sonic-council` or user dispute: full council + one-round escalation,
  capped at DISPUTED (a valid terminal state, surfaced to the user)

## Running

The council is a workflow script: `scripts/council/sonic-council.workflow.js`
(invoked via the Claude Code Workflow tool with
`args: {files: ["knowledge-base/..."], tier: 1|2}`). The workflow returns
records; the caller stamps `ts` + `run_id` and appends them here.

## Acceptance test

`tests/fixtures/council/vlan-create-seeded.json` is a copy of the vlan-create
code path with 6 deliberately seeded errors (invented CONFIG_DB field, wrong
VID range, nonexistent function, invented VlanOrch class/file, wrong redis DB
number, VID-to-RID mapping in the wrong DB). Re-running the council at tier 2
on the real file plus this fixture should confirm the seeds on the fixture
and produce no false confirmed errors on the real file. The 2026-06-12 run
(wf_ab99446a-f19) confirmed 6 findings on the seeded copy and surfaced 2
genuine errors in the "known-good" file (Linux command order/MAC param and a
missing 'bridge vlan del vid 1' step), both then fixed against
cfgmgr/vlanmgr.cpp.

Trend aggregation:

```bash
python3 scripts/council/aggregate_log.py            # counts by agent/verdict/area
python3 scripts/council/aggregate_log.py --disputes # disputed/confirmed detail
```
