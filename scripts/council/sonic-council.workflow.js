export const meta = {
  name: 'sonic-council',
  description: 'Verification council: blind re-derivation of KB content claims with fault-finder foil',
  whenToUse: 'Run on KB content files before commit (Tier 1) or for deliberate audits / disputes (Tier 2)',
  phases: [
    { title: 'Decompose', detail: 'break file into typed atomic claims', model: 'sonnet' },
    { title: 'Derive', detail: 'blind re-derivation per evidence source' },
    { title: 'Diff', detail: 'mechanical diff derivation vs candidate', model: 'haiku' },
    { title: 'Whole-check', detail: 'completeness / consistency / entailment', model: 'sonnet' },
    { title: 'Fault-finder', detail: 'severity x confidence scoring, evidence-gated', model: 'sonnet' },
    { title: 'Escalate', detail: 'one-round targeted re-exam, capped at DISPUTED' },
  ],
}

// args: { files: ["knowledge-base/...", ...], tier: 1 | 2 }
// Tier 1 = content entering the KB (no escalation round).
// Tier 2 = deliberate audit / user dispute (escalation enabled).
// Tier 0 (interactive question -> one routed domain agent) is NOT a workflow;
// it is handled inline by the main session per the spec.
//
// Returns { records: [...], summary } — records match review/council-log.schema.json
// minus ts/run_id, which the CALLER stamps when appending to review/council-log.jsonl
// (workflow scripts cannot touch the filesystem or the clock).

const ROOT = '/Users/jaime/Documents/sonic-kb'
const tier = (args && args.tier) === 2 ? 2 : 1
const files = (args && args.files) || []
if (!files.length) throw new Error('args.files is required: list of KB file paths to verify')

// ---- claim types -> domain agents (differ by EVIDENCE SOURCE, not persona) ----
const DOMAIN = {
  'config-syntax': {
    agent: 'config',
    model: 'haiku',
    evidence: `Your ONLY external evidence source is ${ROOT}/build/artifacts/db_schemas.json — a JSON dict of CONFIG_DB table name -> {description, fields: {field_name: {type,...}}}, extracted from SONiC 202511 YANG models (206 tables). Query it with python3 or grep via Bash. Also use these fixed facts: redis DB numbering CONFIG_DB=4, APPL_DB=0, ASIC_DB=1, STATE_DB=6, COUNTERS_DB=2. Cite the exact schema table and field names you relied on as evidence.`,
  },
  'source-ref': {
    agent: 'architecture',
    model: 'sonnet',
    evidence: `Your ONLY external evidence source is the cloned SONiC 202511 source in ${ROOT}/build/repos/ (sonic-swss, sonic-sairedis, sonic-utilities, sonic-frr, sonic-buildimage, sonic-platform-daemons, sonic-dbsyncd, sonic-stp). Use grep/Read via Bash to find the actual code. EVERY derivation must cite file:line from those clones. If you cannot ground an answer in the source, answer "underivable" rather than guessing.`,
  },
  'protocol-behavior': {
    agent: 'rfc',
    model: 'sonnet',
    evidence: `Your evidence source is protocol specifications (RFCs, IEEE standards). Derive timer values, state transitions, and message semantics from spec knowledge and cite the RFC/standard number and section for each derivation. Do not speculate about SONiC implementation details — only standard protocol behavior.`,
  },
  'internal-logic': {
    agent: 'logic',
    model: 'sonnet',
    evidence: `You use NO external evidence — internal consistency reasoning only. Derive what must logically hold (ordering constraints, state preconditions, cross-step dependencies) from the goal statement alone.`,
  },
}

const blindRule = (file) =>
  `BLIND PROTOCOL: You are re-deriving answers independently. You must NOT read, grep, or otherwise access ` +
  `${ROOT}/${file}, anything under ${ROOT}/knowledge-base/, or anything under ${ROOT}/build/council-test/ — ` +
  `the candidate content under verification lives there and consulting it invalidates the verification ` +
  `(your derivation would just echo the thing being checked). Derive only from your stated evidence source. ` +
  `If your evidence source cannot answer a goal, answer "underivable" — do not go looking for the candidate.`

// Mechanical breach scan: derivation/evidence text citing the candidate file or KB paths
const breachRe = (file) => {
  const base = file.split('/').pop().replace(/\.json$/, '')
  return new RegExp(`knowledge-base/|council-test/|${base.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}`, 'i')
}

// ---- structured output schemas ----
const CLAIMS_SCHEMA = {
  type: 'object', required: ['claims'],
  properties: {
    claims: {
      type: 'array',
      items: {
        type: 'object',
        required: ['id', 'type', 'blind_goal', 'candidate_answer'],
        properties: {
          id: { type: 'string' },
          type: { enum: ['config-syntax', 'source-ref', 'protocol-behavior', 'internal-logic'] },
          blind_goal: { type: 'string' },
          candidate_answer: { type: 'string' },
          location: { type: 'string' },
        },
      },
    },
  },
}

const DERIVE_SCHEMA = {
  type: 'object', required: ['derivations'],
  properties: {
    derivations: {
      type: 'array',
      items: {
        type: 'object', required: ['claim_id', 'derivation'],
        properties: {
          claim_id: { type: 'string' },
          derivation: { type: 'string' },
          evidence: { type: 'string' },
        },
      },
    },
  },
}

const DIFF_SCHEMA = {
  type: 'object', required: ['findings'],
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object', required: ['claim_id', 'verdict', 'detail'],
        properties: {
          claim_id: { type: 'string' },
          verdict: { enum: ['match', 'partial', 'mismatch', 'underivable'] },
          detail: { type: 'string' },
        },
      },
    },
  },
}

const WHOLE_SCHEMA = {
  type: 'object', required: ['checks'],
  properties: {
    checks: {
      type: 'array',
      items: {
        type: 'object', required: ['check', 'verdict', 'detail'],
        properties: {
          check: { enum: ['completeness', 'consistency', 'entailment'] },
          verdict: { enum: ['pass', 'fail'] },
          detail: { type: 'string' },
        },
      },
    },
    missed_claims: { type: 'array', items: { type: 'string' } },
  },
}

const FAULT_SCHEMA = {
  type: 'object', required: ['scored'],
  properties: {
    scored: {
      type: 'array',
      items: {
        type: 'object', required: ['finding_ref', 'severity', 'confidence', 'rationale'],
        properties: {
          finding_ref: { type: 'string' },
          severity: { enum: ['minor', 'major', 'critical'] },
          confidence: { enum: ['low', 'medium', 'high'] },
          evidence: { type: 'string' },
          rationale: { type: 'string' },
        },
      },
    },
    extra_concerns: {
      type: 'array',
      items: {
        type: 'object', required: ['concern'],
        properties: { concern: { type: 'string' }, evidence: { type: 'string' } },
      },
    },
  },
}

const REEXAM_SCHEMA = {
  type: 'object', required: ['claim_holds', 'detail'],
  properties: {
    claim_holds: { type: 'boolean' },
    detail: { type: 'string' },
    evidence: { type: 'string' },
  },
}

const ADJUDICATE_SCHEMA = {
  type: 'object', required: ['final_verdict', 'detail'],
  properties: {
    final_verdict: { enum: ['confirmed', 'disputed'] },
    detail: { type: 'string' },
  },
}

// ---- per-file council ----
async function council(file) {
  const records = []

  // 1. Decompose (Sonnet) — single point of failure; completeness check below guards it
  const dec = await agent(
    `Read ${ROOT}/${file} (a SONiC troubleshooting KB content file, target SONiC 202511).\n\n` +
    `Decompose it into atomic, independently checkable claims. Type each claim:\n` +
    `- config-syntax: CONFIG_DB/APPL_DB/ASIC_DB/STATE_DB table names, key patterns, field names, redis-cli DB numbers, CLI verify commands\n` +
    `- source-ref: source file paths, function names, call chains, daemon names\n` +
    `- protocol-behavior: standard protocol semantics (timers, state machines, message formats)\n` +
    `- internal-logic: ordering constraints, state preconditions one step assumes another created\n\n` +
    `For EACH claim produce:\n` +
    `- id: short slug (e.g. "step1-table-write")\n` +
    `- blind_goal: a derivation question that does NOT reveal the candidate's answer. Example: candidate says "CLI writes CONFIG_DB table VLAN field vlanid" -> blind_goal "Which CONFIG_DB table and fields does 'config vlan add 100' write?". Never leak table/field/function names from the candidate into the goal. The goal must read as a question about SONiC ITSELF — never mention this KB file, its name, step numbers, "the document", or that a candidate answer exists, or the blind reviewers will go find and read it.\n` +
    `- candidate_answer: the candidate's actual assertion, verbatim enough to diff against\n` +
    `- location: where in the file (e.g. "steps[2].action")\n\n` +
    `Target 10-20 claims; prioritize concrete factual assertions over prose. Merge duplicates.`,
    { label: `decompose:${file}`, phase: 'Decompose', model: 'sonnet', schema: CLAIMS_SCHEMA }
  )
  if (!dec) throw new Error(`decomposer failed for ${file}`)
  const claims = dec.claims
  log(`${file}: ${claims.length} claims decomposed`)

  // 2+3. Group claims by type; each group derives blind then diffs — pipelined, no barrier.
  //      The script routes ONLY blind_goal to derive agents (mechanical blindness guarantee).
  const types = [...new Set(claims.map(c => c.type))]
  const groups = types.map(t => ({ type: t, claims: claims.filter(c => c.type === t) }))

  const leak = breachRe(file)
  const deriveBlind = async (g) => {
    const d = DOMAIN[g.type]
    const goals = g.claims.map(c => `- [${c.id}] ${c.blind_goal}`).join('\n')
    let breached = false
    for (let attempt = 0; attempt < 2; attempt++) {
      const warn = attempt === 0 ? '' :
        `\nWARNING: a previous attempt cited the candidate document under verification, which invalidates ` +
        `the result. Answer ONLY from your stated evidence source; prefer "underivable" over peeking.\n`
      const r = await agent(
        `${blindRule(file)}\n${warn}\n${d.evidence}\n\n` +
        `Independently derive answers to each goal below (context: SONiC 202511 switch). ` +
        `Return one derivation per claim_id with the evidence you used. ` +
        `If your evidence source cannot answer a goal, set derivation to "underivable" and say why.\n\nGoals:\n${goals}`,
        { label: `derive:${d.agent}:${file}${attempt ? ':retry' : ''}`, phase: 'Derive', model: d.model, schema: DERIVE_SCHEMA }
      )
      if (!r) return null
      breached = r.derivations.some(dv => leak.test(`${dv.derivation} ${dv.evidence || ''}`))
      if (!breached) return { group: g, derivations: r.derivations, blind_breach: false }
      log(`${file}: blind breach by ${d.agent} agent (attempt ${attempt + 1})`)
    }
    return { group: g, derivations: [], blind_breach: true }
  }

  const diffed = await pipeline(
    groups,
    g => deriveBlind(g),
    res => {
      if (!res) return null
      if (res.blind_breach) {
        // derive agent kept consulting the candidate even after retry — its output is
        // worthless as verification; record the breach instead of fake verdicts
        return {
          group: res.group, pairs: [], blind_breach: true,
          findings: res.group.claims.map(c => ({
            claim_id: c.id, verdict: 'underivable',
            detail: 'BLIND PROTOCOL BREACH: derive agent consulted the candidate content twice; derivation discarded',
          })),
        }
      }
      const pairs = res.group.claims.map(c => {
        const dv = res.derivations.find(d => d.claim_id === c.id)
        return { claim_id: c.id, candidate: c.candidate_answer, derivation: dv ? dv.derivation : 'NO DERIVATION RETURNED', evidence: dv && dv.evidence }
      })
      return agent(
        `Mechanically diff each candidate assertion against the independent derivation. ` +
        `Work ONLY from the JSON below — do not use tools, read files, or bring outside knowledge; ` +
        `you are a text comparator, not a verifier. ` +
        `Per pair output verdict: "match" (same substance), "partial" (overlap with a concrete discrepancy), ` +
        `"mismatch" (derivation contradicts candidate), "underivable" (the derivation says it could not be made — ` +
        `this verdict is MANDATORY in that case; never upgrade it to match). ` +
        `Quote the exact discrepancy in detail — names, numbers, paths. Do NOT judge which side is right; just diff.\n\n` +
        JSON.stringify(pairs, null, 1),
        { label: `diff:${res.group.type}:${file}`, phase: 'Diff', model: 'haiku', schema: DIFF_SCHEMA }
      ).then(r => r && {
        group: res.group, pairs,
        // mechanical guard: an underivable derivation can never yield a match/partial verdict
        findings: r.findings.map(f => {
          const p = pairs.find(p => p.claim_id === f.claim_id)
          return p && /underivable/i.test(p.derivation) && f.verdict !== 'underivable'
            ? { ...f, verdict: 'underivable', detail: `derivation was underivable from the evidence source (diff agent overrode; forced back) — ${f.detail}` }
            : f
        }),
      })
    }
  )

  const partResults = diffed.filter(Boolean)
  const claimById = Object.fromEntries(claims.map(c => [c.id, c]))
  const evidenceById = {}
  const partFindings = []
  for (const pr of partResults) {
    for (const p of pr.pairs) evidenceById[p.claim_id] = p.evidence || null
    for (const f of pr.findings) partFindings.push({ ...f, type: pr.group.type, blind_breach: !!pr.blind_breach })
  }

  // 4. Whole-check (logic agent) — completeness / consistency / entailment. NEVER skipped.
  const whole = await agent(
    `You are the council's logic agent running the WHOLE-CHECK on a verified-in-parts KB file.\n` +
    `Read the original file ${ROOT}/${file}. Then, given the claim decomposition and part verdicts below, run exactly three checks:\n` +
    `a. completeness — does the claim list cover every substantive factual assertion in the file? List assertions that were NEVER decomposed into a claim (these are unverified leaps hiding in decomposition gaps).\n` +
    `b. consistency — do the verified parts agree with EACH OTHER? (e.g. each step correct in isolation, but step 3 assumes state step 2 never created; or two steps cite different DB numbers for the same DB).\n` +
    `c. entailment — do the verified parts actually add up to the file's overall conclusion / flow?\n` +
    `Use no external evidence — internal reasoning only.\n\n` +
    `Claims:\n${JSON.stringify(claims.map(c => ({ id: c.id, type: c.type, candidate: c.candidate_answer, location: c.location })), null, 1)}\n\n` +
    `Part verdicts:\n${JSON.stringify(partFindings, null, 1)}`,
    { label: `whole-check:${file}`, phase: 'Whole-check', model: 'sonnet', schema: WHOLE_SCHEMA }
  )
  const wholeChecks = whole ? whole.checks : []
  const missed = (whole && whole.missed_claims) || []

  // 5. Fault-finder — the ONE adversarial foil. Evidence-gated scoring.
  const allFindings = [
    ...partFindings.map(f => ({ ref: f.claim_id, kind: 'part', verdict: f.verdict, detail: f.detail })),
    ...wholeChecks.map(c => ({ ref: `whole:${c.check}`, kind: 'whole', verdict: c.verdict, detail: c.detail })),
  ]
  const fault = await agent(
    `You are the council's single fault-finder — an adversarial foil against echo-chamber agreement.\n` +
    `Candidate file: ${ROOT}/${file} (read it). Findings from blind re-derivation and whole-check are below.\n\n` +
    `Score EVERY finding: severity (minor|major|critical) x confidence (low|medium|high).\n` +
    `HARD RULE: to score severity above "minor" you MUST cite concrete evidence — a file:line under ${ROOT}/build/repos/, an RFC/standard section, or a table.field in ${ROOT}/build/artifacts/db_schemas.json. Verify your evidence with grep/Read before citing it. No evidence -> severity stays minor regardless of how suspicious it looks.\n` +
    `"match" verdicts normally score minor/low unless you have evidence BOTH sides are wrong.\n` +
    `You may add extra_concerns the council missed, same evidence rule. Do not manufacture objections to appear thorough.\n\n` +
    `Findings:\n${JSON.stringify(allFindings, null, 1)}`,
    { label: `fault-finder:${file}`, phase: 'Fault-finder', model: 'sonnet', schema: FAULT_SCHEMA }
  )
  const scored = fault ? fault.scored : []
  const scoreByRef = Object.fromEntries(scored.map(s => [s.finding_ref, s]))

  // 6. Escalation (Tier 2 only): one round, capped at DISPUTED.
  //    Major+ AND evidenced -> targeted re-exam: domain agent re-verifies the ORIGINAL
  //    claim fresh, given the fault-finder's evidence — never "do you agree with this fault?".
  const escalationByRef = {}
  if (tier === 2) {
    const escalatable = scored.filter(s =>
      s.severity !== 'minor' && s.evidence && claimById[s.finding_ref])
    log(`${file}: ${escalatable.length} finding(s) escalate to re-exam`)
    await parallel(escalatable.map(s => async () => {
      const c = claimById[s.finding_ref]
      const d = DOMAIN[c.type]
      const re = await agent(
        `${blindRule(file)}\n\n${d.evidence}\n\n` +
        `Re-verify this claim from scratch (SONiC 202511): "${c.candidate_answer}"\n` +
        `Additional evidence has surfaced that you should examine alongside your own: ${s.evidence}\n` +
        `Do NOT assume that evidence is correct — check it against your evidence source. ` +
        `Conclude claim_holds true/false with your own grounding.`,
        { label: `re-exam:${s.finding_ref}`, phase: 'Escalate', model: d.model, schema: REEXAM_SCHEMA }
      )
      if (!re) { escalationByRef[s.finding_ref] = 'disputed'; return }
      if (re.claim_holds) {
        // re-examiner independently backs the candidate against the fault -> standing disagreement
        escalationByRef[s.finding_ref] = 'disputed'
        return
      }
      // re-examiner independently agrees the claim is wrong -> council reconsideration (logic adjudication)
      const adj = await agent(
        `Council reconsideration (logic agent, internal reasoning only). A claim failed blind re-derivation, ` +
        `was scored ${s.severity}/${s.confidence} with evidence, and an independent re-exam also rejected it.\n` +
        `Claim: "${c.candidate_answer}"\nFault evidence: ${s.evidence}\nRe-exam: ${re.detail} (evidence: ${re.evidence || 'none'})\n` +
        `Issue the final verdict: "confirmed" (the claim is wrong) or "disputed" (the rejections do not actually cohere).`,
        { label: `adjudicate:${s.finding_ref}`, phase: 'Escalate', model: 'sonnet', schema: ADJUDICATE_SCHEMA }
      )
      escalationByRef[s.finding_ref] = adj ? adj.final_verdict : 'disputed'
    }))
  }

  // ---- assemble JSONL-ready records (caller stamps ts + run_id) ----
  for (const f of partFindings) {
    const s = scoreByRef[f.claim_id]
    const c = claimById[f.claim_id]
    records.push({
      tier, content_file: file,
      claim_id: f.claim_id, claim: c ? c.candidate_answer : null, claim_type: f.type,
      agent: DOMAIN[f.type].agent, method: 'blind-rederive',
      verdict: f.verdict, detail: f.detail,
      blind_breach: f.blind_breach || undefined,
      evidence: evidenceById[f.claim_id] || null,
      score: s ? { severity: s.severity, confidence: s.confidence, evidence: s.evidence || null } : null,
      escalation_outcome: escalationByRef[f.claim_id] || 'none',
    })
  }
  for (const c of wholeChecks) {
    const ref = `whole:${c.check}`
    const s = scoreByRef[ref]
    records.push({
      tier, content_file: file,
      claim_id: ref, claim: null, claim_type: 'whole',
      agent: 'logic', method: 'whole-check',
      verdict: c.verdict, detail: c.detail + (c.check === 'completeness' && missed.length ? ` | missed: ${missed.join('; ')}` : ''),
      evidence: null,
      score: s ? { severity: s.severity, confidence: s.confidence, evidence: s.evidence || null } : null,
      escalation_outcome: 'none',
    })
  }
  for (const x of (fault && fault.extra_concerns) || []) {
    records.push({
      tier, content_file: file,
      claim_id: 'fault-finder:extra', claim: null, claim_type: 'whole',
      agent: 'fault-finder', method: 'fault-find',
      verdict: 'concern', detail: x.concern,
      evidence: x.evidence || null,
      score: { severity: x.evidence ? 'major' : 'minor', confidence: 'low', evidence: x.evidence || null },
      escalation_outcome: 'none',
    })
  }
  return records
}

phase('Decompose')
const perFile = await pipeline(files, f => council(f))
const records = perFile.filter(Boolean).flat()

const summary = {}
for (const r of records) {
  const k = `${r.content_file}|${r.verdict}`
  summary[k] = (summary[k] || 0) + 1
}
const confirmed = records.filter(r => r.escalation_outcome === 'confirmed')
const disputed = records.filter(r => r.escalation_outcome === 'disputed')
const mismatches = records.filter(r => r.verdict === 'mismatch' || r.verdict === 'fail')
log(`council done: ${records.length} records, ${mismatches.length} mismatch/fail, ${confirmed.length} confirmed, ${disputed.length} disputed`)

return { tier, files, records, summary, confirmed_count: confirmed.length, disputed_count: disputed.length }
