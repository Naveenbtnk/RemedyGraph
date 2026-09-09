# RemedyBench Design Plan

Status: Design review draft. This document proposes synthetic cases only; it does not freeze contracts or create fixtures.

## 1. Purpose and verdict contract

RemedyBench evaluates whether RemedyGraph can audit corrective actions from a synthetic postmortem against a synthetic repository. It measures atomic-action extraction, evidence retrieval, deterministic verification, conservative verdict assignment, citations, and CI-guard proposals. It does not evaluate an agent applying remediations.

The only action-level verdicts are:

| Verdict | Gold interpretation |
|---|---|
| `VERIFIED` | Required deterministic checks pass and adequate implementation plus regression proof exists. |
| `PARTIAL` | Meaningful implementation/protection exists, but material proof is absent or contradictory. |
| `MISSING` | Credible implementation is absent, or a core deterministic check fails. |
| `UNVERIFIABLE` | Required runtime, external, or human/process context is unavailable to the audit. |

Deterministic failures cannot be upgraded by semantic confidence. Documentation and Git history are supporting evidence only. Every verdict cites evidence or states the missing proof.

## 2. Proposed matrix

The set contains **15 incidents and 45 atomic corrective actions**. Gold balance is **14 VERIFIED, 12 PARTIAL, 12 MISSING, and 7 separately identified UNVERIFIABLE** actions.

| ID | Incident / fault categories | Actions | Gold distribution | Primary guard |
|---|---|---:|---|---|
| I01 | Failed-release rollback | 3 | V1/P1/M1 | deployment policy |
| I02 | Payments timeout | 3 | V1/M1/U1 | timeout test |
| I03 | Retry storm and jitter | 3 | V1/P1/M1 | seeded timing test |
| I04 | Circuit breaker and fallback | 3 | V1/P1/M1 | state-transition test |
| I05 | Partner rate limiting | 3 | V1/P1/U1 | rate-window test |
| I06 | Unbounded worker queue | 3 | V1/P1/M1 | queue-capacity test |
| I07 | Misleading health check | 3 | V1/M1/U1 | readiness test |
| I08 | Missing saturation alert | 3 | V1/P1/M1 | alert-rule test |
| I09 | Missing database index | 3 | V1/P1/U1 | schema/query-plan check |
| I10 | Absent regression protection | 3 | V1/P1/M1 | behavioral test |
| I11 | Feature-flag kill switch | 3 | V1/M1/U1 | flag switch test |
| I12 | Unsafe schema migration | 3 | V1/P1/M1 | migration test |
| I13 | Duplicate event processing | 3 | V1/P1/M1 | idempotency test |
| I14 | Secret-rotation follow-up | 3 | V1/P1/U1 | secret policy |
| I15 | Capacity/failover follow-up | 3 | P1/M1/U1 | load/config check |

`V/P/M/U` abbreviate the four accepted verdicts only in this summary.

## 3. Incident specifications

Paths are design suggestions, not frozen contracts. Each row is one atomic promised action.

### I01 — Orders release required rollback

Cause: release `v2.7.0` introduced an unbounded request cache and was reportedly rolled back.

| Action | Gold | Required evidence | Contradiction/missing proof | Deterministic check | Guard |
|---|---|---|---|---|---|
| A01.1 Roll back to last-known-good image. | VERIFIED | Deploy manifest and synthetic deployment record pin `v2.6.3`. | Git message alone is insufficient. | Compare effective image tag/digest with baseline. | deployment-policy |
| A01.2 Block the faulty image. | PARTIAL | Denylist names `v2.7.0` but uses a mutable tag. | Immutable digest absent. | Require known-bad digest in parsed denylist. | config-policy |
| A01.3 Add bounded-cache regression test. | MISSING | No executable eviction/load test. | README says memory is bounded. | Discover and run fixed-workload eviction test. | regression-test |

### I02 — Checkout hangs on payments

Cause: the payments client lacks an effective request deadline and exhausts workers during a stall.

| Action | Gold | Required evidence | Contradiction/missing proof | Deterministic check | Guard |
|---|---|---|---|---|---|
| A02.1 Apply a five-second timeout. | VERIFIED | Typed setting is wired into the specific client. | Unused similarly named setting is a hard negative. | Config/AST check plus virtual-clock timeout test. | config + unit-test |
| A02.2 Return a typed timeout error. | MISSING | Call still returns generic 500. | Comment promises graceful degradation. | Inject timeout and assert public error type. | integration-test |
| A02.3 Confirm gateway deadline exceeds client deadline. | UNVERIFIABLE | Gateway state is outside the fixture. | Example config cannot prove production state. | Return unavailable-context reason. | runtime evidence request |

### I03 — Notification retry storm

Cause: workers retry at a fixed interval and synchronize after a broker outage.

| Action | Gold | Required evidence | Contradiction/missing proof | Deterministic check | Guard |
|---|---|---|---|---|---|
| A03.1 Bound retries to three. | PARTIAL | Config says three; one path bypasses the policy. | Docs claim all retries are bounded. | Enumerate retry call sites and policy use. | AST/config-policy |
| A03.2 Use capped exponential backoff with jitter. | VERIFIED | Injected RNG and fixed-seed tests prove range/cap. | Unseeded random sleep is weak proof. | Assert deterministic schedules, range, and cap. | unit-test |
| A03.3 Route exhaustion to DLQ. | MISSING | No DLQ declaration or publish path. | Unused `dead_letter` variable misleads retrieval. | Fake-broker exhaustion test plus config check. | integration-test |

### I04 — Recommendations cascade into catalog

Cause: catalog synchronously depends on recommendations without isolation or a safe degraded response.

| Action | Gold | Required evidence | Contradiction/missing proof | Deterministic check | Guard |
|---|---|---|---|---|---|
| A04.1 Add a circuit breaker. | MISSING | Retry logic exists but no breaker state machine. | Unused `CircuitBreakerConfig` class. | Drive open/half-open/closed transitions. | state-machine test |
| A04.2 Serve a safe fallback while open. | PARTIAL | Fallback exists but lacks freshness bound. | Happy-path test never opens breaker. | Force open and verify degraded schema/freshness. | integration-test |
| A04.3 Test half-open recovery. | VERIFIED | Virtual-clock test proves one trial and success-only close. | Sleep-based test alone is inadequate. | Run deterministic transition test. | regression-test |

### I05 — Partner API quota storm

Cause: unbounded synchronization exceeds quota and mishandles HTTP 429.

| Action | Gold | Required evidence | Contradiction/missing proof | Deterministic check | Guard |
|---|---|---|---|---|---|
| A05.1 Share one token-bucket limiter across calls. | VERIFIED | One limiter is injected into all partner paths. | Per-worker limiters exceed aggregate quota. | Virtual-clock rate-window test. | integration-test |
| A05.2 Honor bounded `Retry-After`. | PARTIAL | Header parsed; maximum wait absent. | Test covers only a small value. | Test valid, invalid, and excessive values. | unit-test |
| A05.3 Confirm external quota remains 100/min. | UNVERIFIABLE | Partner contract portal is unavailable. | Repository comment may be stale. | Require external contract evidence. | manual evidence request |

### I06 — Worker queue grows without bounds

Cause: producers outpace workers, allowing memory exhaustion.

| Action | Gold | Required evidence | Contradiction/missing proof | Deterministic check | Guard |
|---|---|---|---|---|---|
| A06.1 Set queue capacity to 500. | PARTIAL | Main constructor bounded; alternate path unbounded. | Example YAML alone proves nothing. | Instantiate and inspect every constructor path. | AST/config-policy |
| A06.2 Backpressure or reject at capacity. | MISSING | Producer always enqueues. | Library supports bounds but wiring does not. | Fill queue and assert bounded overload behavior. | integration-test |
| A06.3 Add queue-depth regression test. | VERIFIED | Test proves depth <=500 and overload observable. | Initial-capacity snapshot is insufficient. | Fixed producer/consumer schedule. | regression-test |

### I07 — False-ready health endpoint

Cause: readiness stays green while a required database is unavailable.

| Action | Gold | Required evidence | Contradiction/missing proof | Deterministic check | Guard |
|---|---|---|---|---|---|
| A07.1 Include database in readiness. | MISSING | Handler checks process only. | Runbook says DB is checked. | Fail fake DB and expect non-ready. | integration-test |
| A07.2 Keep liveness dependency-independent. | VERIFIED | Separate endpoints/tests preserve liveness on DB failure. | Shared handler would cause restart loops. | Exercise both probes under injected failure. | regression-test |
| A07.3 Prove old pods were removed during incident. | UNVERIFIABLE | Historical cluster events unavailable. | Current YAML cannot prove past behavior. | Return missing runtime-history reason. | runtime evidence request |

### I08 — Saturation alert never fires

Cause: pool exhaustion is measurable, but the promised actionable alert is ineffective.

| Action | Gold | Required evidence | Contradiction/missing proof | Deterministic check | Guard |
|---|---|---|---|---|---|
| A08.1 Alert above 90% for five minutes. | VERIFIED | Expression/duration and synthetic-series test agree. | Dashboard panel is not an alert. | Evaluate fixed firing/non-firing series. | alert-rule test |
| A08.2 Route to DB on-call. | PARTIAL | Route uses deprecated team label. | Ownership docs name new team. | Resolve synthetic routing labels. | config-policy |
| A08.3 Add valid runbook annotation. | MISSING | Annotation or target absent. | Git subject says “add runbook.” | Validate annotation and local target. | metadata guard |

### I09 — Product search lacks index

Cause: a frequent query filters by tenant and status without the promised composite index.

| Action | Gold | Required evidence | Contradiction/missing proof | Deterministic check | Guard |
|---|---|---|---|---|---|
| A09.1 Add `(tenant_id,status)` index. | PARTIAL | Migration creates reversed columns. | Index name implies correct order. | Parse ordered schema columns. | schema-policy |
| A09.2 Add query-plan regression check. | VERIFIED | Seeded test asserts index use for exact query. | Benchmark prose is not executable. | Run `EXPLAIN` on fixed data. | DB integration-test |
| A09.3 Prove production p95 improved. | UNVERIFIABLE | Production telemetry unavailable. | Synthetic timing is not production p95. | Return unavailable-telemetry reason. | runtime evidence request |

### I10 — Refund fix lacks protection

Cause: duplicate refunds remain possible and the original sequence is incompletely tested.

| Action | Gold | Required evidence | Contradiction/missing proof | Deterministic check | Guard |
|---|---|---|---|---|---|
| A10.1 Enforce refund idempotency. | MISSING | Handler creates a refund per request. | Design doc proposes a key. | Repeat request and assert one persisted refund. | integration-test |
| A10.2 Add incident regression test. | VERIFIED | Test reproduces sequence and checks side effects. | Test name alone is insufficient. | Run targeted test with local DB. | regression-test |
| A10.3 Cover concurrent duplicates. | PARTIAL | Sequential case covered; race absent. | Comment claims lock safety. | Two requests at deterministic barrier. | concurrency test |

### I11 — Parser kill switch bypass

Cause: a risky parser is globally enabled and one entry point bypasses its feature flag.

| Action | Gold | Required evidence | Contradiction/missing proof | Deterministic check | Guard |
|---|---|---|---|---|---|
| A11.1 Gate all entry points. | VERIFIED | References and tests show shared flag at each entry. | Bypass path would contradict verification. | Enumerate entries; test both states. | static + integration-test |
| A11.2 Default production flag off. | MISSING | Production overlay sets true. | Base default false is overridden. | Resolve layered effective config. | config-policy |
| A11.3 Prove operator tested kill switch. | UNVERIFIABLE | Signed operational event unavailable. | Commit time cannot prove execution. | Require external audit event. | manual evidence request |

### I12 — Unsafe schema migration

Cause: failure can leave partially applied DDL.

| Action | Gold | Required evidence | Contradiction/missing proof | Deterministic check | Guard |
|---|---|---|---|---|---|
| A12.1 Make migration atomic/resumable. | PARTIAL | Marker written after one unsafe statement. | Description claims atomicity. | Inject failure after each statement. | migration test |
| A12.2 Supply tested rollback. | MISSING | Down migration empty. | Rollback ticket is not evidence. | Apply up/down; compare schema. | migration guard |
| A12.3 Detect partial state at startup. | VERIFIED | Startup refuses writes on fixture partial schema. | Logging only is insufficient. | Boot against partial schema. | startup test |

### I13 — Duplicate event processing

Cause: redelivery repeats a non-idempotent inventory decrement.

| Action | Gold | Required evidence | Contradiction/missing proof | Deterministic check | Guard |
|---|---|---|---|---|---|
| A13.1 Persist event ID atomically with update. | MISSING | ID recorded in later transaction. | Function named `process_once`. | Crash between commits and redeliver. | integration-test |
| A13.2 Bound dedup retention correctly. | PARTIAL | TTL shorter than redelivery window. | Config key exists but threshold fails. | Compare parsed TTL to invariant. | config-policy |
| A13.3 Add redelivery regression test. | VERIFIED | Duplicate ID causes one decrement. | Mock call count without state is weak. | Run against persistence double. | regression-test |

### I14 — Credential rotation follow-up

Cause: an exposed credential was reportedly rotated; repository evidence proves only cleanup/prevention.

| Action | Gold | Required evidence | Contradiction/missing proof | Deterministic check | Guard |
|---|---|---|---|---|---|
| A14.1 Remove credential and references. | VERIFIED | Seeded secret absent; env reference used. | Copied token elsewhere fails. | Scan current synthetic tree/history marker. | secret-policy |
| A14.2 Add CI secret scanning. | PARTIAL | Workflow excludes YAML containing seeded negative. | Badge/README claim is insufficient. | Run scanner over seeded files. | CI policy test |
| A14.3 Confirm provider revocation. | UNVERIFIABLE | Provider state unavailable. | Local deletion is not revocation. | Require provider audit receipt. | manual evidence request |

### I15 — Capacity and failover follow-up

Cause: traffic exceeded worker capacity; postmortem mixes repository-checkable and operational promises.

| Action | Gold | Required evidence | Contradiction/missing proof | Deterministic check | Guard |
|---|---|---|---|---|---|
| A15.1 Cap concurrency and shed load. | PARTIAL | Cap exists; overload response lacks retry hint. | Summary claims graceful shedding. | Fixed-load test for cap/status/metadata. | bounded load-test |
| A15.2 Add capacity alert. | MISSING | Dashboard query exists without alert. | Screenshot is supporting only. | Search/evaluate alert configuration. | alert-policy |
| A15.3 Confirm quarterly failover rehearsal. | UNVERIFIABLE | Exercise records unavailable. | Runbook schedule does not prove execution. | Request signed exercise evidence. | manual evidence request |

## 4. Retrieval vocabulary

| Category | Postmortem terms | Code/config/test synonyms |
|---|---|---|
| Rollback | revert, last known good, bad deploy | image tag, digest, deployment revision, denylist |
| Timeout | deadline, hung call, stall | timeout_ms, requestTimeout, cancellation, abort |
| Retry jitter | retry storm, herd, backoff | max_attempts, exponential, RNG, seed, DLQ |
| Circuit breaker | isolate failure, cascade | open, half_open, threshold, recovery timeout |
| Rate limiting | quota, 429, throttle | token bucket, permits, Retry-After, requests_per_minute |
| Queue bounds | backlog, overload | maxsize, capacity, bounded channel, backpressure, shed |
| Health checks | readiness, liveness | `/ready`, `/healthz`, dependency/startup probe, 503 |
| Alerts | page, threshold, SLO | alert rule, `for`, severity, route, receiver, runbook_url |
| Fallbacks | degraded mode, fail soft | cached/default response, stale-if-error, optional dependency |
| Database indexes | slow query, full scan | CREATE INDEX, composite, btree, migration, EXPLAIN |
| Regression tests | prevent recurrence | fixture, assertion, integration test, seeded failure |
| Feature flags | kill switch, dark launch | toggle, default false, rollout percentage, gate |

## 5. Hard negatives

- README says retries are bounded while an alternate path bypasses the policy.
- Git subject says “add circuit breaker” while the diff adds only unused names.
- Closed ticket says an alert shipped, but no alert rule exists.
- Index name suggests correct columns while ordered definition is wrong.
- Incident-named test never asserts the failure mechanism.
- Safe base config is overridden by an unsafe production overlay.
- Runbook describes rollback/rotation/failover without execution proof.
- Commented-out code contains exact retrieval terms but is not executable.

Annotations must label these supporting-only or contradictory so retrieval success is not mistaken for verification.

## 6. Annotation and adjudication

For each atomic action record its normalized invariant, gold verdict/rationale, required evidence types, exact gold spans, contradictory/supporting-only evidence, deterministic check and expected result, unavailable-context reason, and guard family.

- `VERIFIED`: core behavior passes required checks and regression proof exists.
- `PARTIAL`: meaningful implementation exists, but wiring/scope/threshold/contradiction/regression proof is incomplete.
- `MISSING`: core implementation absent or core check fails.
- `UNVERIFIABLE`: required fact is outside available context; never use it for failed retrieval.
- Documentation/Git cannot independently yield `VERIFIED`.
- Two annotators label independently; a third resolves written disagreements without seeing model predictions.

## 7. Licensing and provenance

- Newly author all postmortems, code, logs, commits, identities, metrics, and operational records.
- Do not copy or lightly paraphrase copyrighted reports, proprietary code, leaks, or customer data.
- Public reports may inspire broad categories only; record sources internally and write independent scenarios.
- Use compatible dependency licenses and retain required notices.
- Use reserved domains, fake organizations, and obviously synthetic seeded credentials.
- Record author, date, license, inspiration category, and synthetic-material declaration per case.
- Run secret, license, and similarity checks before release.

## 8. First five smoke cases

1. I02 Timeout: smallest code/config/test vertical slice.
2. I03 Retry jitter: numeric invariants and seeded randomness.
3. I04 Circuit breaker/fallback: multi-part state transitions.
4. I06 Queue bounds: alternate-path hard negative and runtime bound.
5. I11 Feature flag: layered config, entry-point coverage, and UNVERIFIABLE proof.

## 9. Evaluation metrics

- Macro-F1 and per-class precision/recall for four verdicts.
- Evidence Recall@5/10 and citation precision.
- Deterministic-check selection and result agreement.
- Unsupported-VERIFIED and Git/document-only-VERIFIED rates (both must be zero).
- Guard-type accuracy and extraction precision/recall.
- Measured model calls, rounds, latency, and tokens; never invent unmeasured values.

## 10. Risks and integration-owner questions

Risks include vocabulary leakage, unequal class difficulty, unstable query plans, drifting line spans, unrealistic doubles, misuse of UNVERIFIABLE, and overfit generated guards.

Before creating fixtures or ground-truth JSON, resolve:

1. Frozen IDs/schema versions for incidents, actions, invariants, evidence, checks, verdicts, and guards?
2. Are multiple required checks conjunctive by default?
3. How are hashes/spans represented after MarkItDown normalization?
4. Canonical reason codes for absent, contradictory, unavailable, and tool-failure evidence?
5. Is UNVERIFIABLE excluded from coverage denominator but retained in classification metrics?
6. Minimum regression proof for configuration/documentation actions?
7. Canonical layered-config resolution rules?
8. Which deterministic checks are allowlisted?
9. Does evaluation compare evidence IDs, spans, or both?
10. How are retrieval ties and multiple valid spans scored?
11. Supported database/version matrix for query-plan checks?
12. Which guards are preview-only versus sandbox-executable?

## 11. Completeness audit

- 15 incidents; 45 actions.
- VERIFIED 14; PARTIAL 12; MISSING 12; UNVERIFIABLE 7.
- All 12 required fault categories represented.
- Every incident includes cause, action verdicts, evidence, contradictions, deterministic checks, and guards.
- Vocabulary, hard negatives, annotation/adjudication, provenance, smoke order, metrics, risks, and contract questions included.
- Fixture repositories and ground-truth JSON intentionally absent.
