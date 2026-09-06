---
name: "documentation_tone"
description: "Enforces RFC 2119/NASA-aligned normative lexicon (SHALL, SHOULD, MAY, DO, DON'T), epistemic honesty, and automated Vale linting for technical documentation."
globs:
  - "docs/**/*.md"          # 실제 프로젝트 기술 명세, 아키텍처, 런북
  - "docs/rules/*.md"    # 레포지토리 표준 및 불변식 규격서
  - ".agents/agents/*.md"   # 전문 에이전트 페르소나 정의서
  - ".agents/skills/**/*.md"  
---

# Enterprise Technical Documentation Tone & Normative Standard (v2.0)

> [!NOTE]
> ### Document Scope & Automated Enforcement
> This specification establishes mandatory linguistic, epistemic, and rhetorical standards for all technical architecture, specifications, decision records, and operational runbooks.
> - **Automated Linter**: Vale CLI (`vale --config=.vale.ini docs/`)
> - **CI Gate**: Blocking on `status: approved` documents; advisory warning on `status: draft`.
> - **Emergency Break-Glass**: Append commit trailer `Doc-Waiver: INCIDENT-<id>` to bypass CI during P0 incidents.

---

## 1. Normative Directives (RFC 2119 & NASA SE Alignment)

Technical requirements, interface contracts, and procedural directives must strictly employ standardized normative keywords conforming to **RFC 2119 / RFC 8174** and **NASA SP-2016-6105 Rev 2**. Ambiguous colloquial modals (`should probably`, `is recommended to`, `might`, `could`) are strictly prohibited in binding specifications.

| Keyword | Domain Target | Binding Level | Operational Semantics & Enforcement |
| :--- | :---: | :---: | :--- |
| **`SHALL`** / **`MUST`** | System / Protocol | **Mandatory** | Absolute requirement. Non-compliance blocks release and automated CI promotion gates. |
| **`SHALL NOT`** / **`MUST NOT`** | System / Protocol | **Prohibitive** | Critical negative constraint. Defines system behaviors that are strictly forbidden. |
| **`SHOULD`** / **`RECOMMENDED`** | System / Architecture | **Advisory Default** | Strongly recommended practice. Deviation is permitted **only** when accompanied by an explicit, documented architectural trade-off. |
| **`MAY`** / **`OPTIONAL`** | Protocol / API | **Elective** | Truly optional extension point, capability negotiation hook, or pluggable feature. |
| **`DO`** | Human / Agent | **Execution Action** | Mandatory step in operational runbooks, disaster recovery procedures, and guides. |
| **`DON'T`** | Human / Agent | **Prohibited Action** | Forbidden operational shortcut, high-risk antipattern, or unsafe procedure. |

### Syntactic Examples
- `[REQ-001]` The Gateway **SHALL** terminate TLS 1.3 handshakes within 10 milliseconds of initiation.
- `[REQ-002]` Storage nodes **SHALL NOT** persist plaintext credentials or unmasked tokens in any persistent volume.
- `[ARCH-001]` Microservices **SHOULD** utilize gRPC for internal RPC transport; HTTP/1.1 is permitted only where client streaming is unneeded and legacy proxies intervene.
- `[API-001]` Ingress controllers **MAY** advertise support for HTTP/3 via `Alt-Svc` headers.
- **DO**: Verify array bounds and null pointer assertions prior to raw memory dereference.
- **DON'T**: Catch generic base exceptions (`catch (Exception e)`) without logging structured contextual telemetry.

---

## 2. The Atomic Action Rule (Single-Outcome Mandate)

A normative statement must not bind multiple independent physical execution actions into a single requirement. This prevents unobservable verification states where Step A succeeds but Step B fails.

### Distinguishing Actions vs. Predicate Conditions

```mermaid
graph TD
    A[Normative Statement] --> B{Conjunction Type?}
    B -->|Compound Action: 'Do X and Do Y'| C[❌ STRICTLY FORBIDDEN<br>Must split into atomic [REQ] entries]
    B -->|Logical Condition: 'When X and Y'| D[✅ PERMITTED<br>Compound predicate qualification]
    B -->|Compound Noun: 'AuthN and AuthZ'| E[✅ PERMITTED<br>Domain terminology]
```

- **❌ Forbidden (Compound Physical Actions)**:
  > The StorageEngine SHALL compress blocks with ZSTD and upload them to S3 within 2 seconds.
- **✅ Permitted (Compound Predicates & Atomic Splitting)**:
  > - `[REQ-STOR-01]` When uncompressed block size exceeds 64KB **and** compaction is idle, the StorageEngine **SHALL** compress the block using ZSTD level 3.
  > - `[REQ-STOR-02]` Upon compression completion, the StorageEngine **SHALL** upload the block to object storage within 2,000 milliseconds.

---

## 3. Epistemic Calibration & Anti-Handwaving

Technical documentation must reflect empirical rigor. Unquantified marketing adjectives and handwaving claims degrade engineering trust and mask operational vulnerabilities.

### 3.1 Prohibited Lexicon (Banned Handwaving)
The following terms are **strictly prohibited** in binding specifications unless accompanied by numerical boundaries:
- `seamless`, `effortless`, `blazing-fast`, `lightning-fast`, `infinitely scalable`, `robust`, `ultra-low latency`, `easy to use`.

### 3.2 Quantified Boundary Invariant
Every performance SLA, throughput target, or resilience claim must specify numerical operating boundaries:
- **❌ Forbidden**: "The cache provides ultra-low latency reads and robust memory handling."
- **✅ Compliant**: "The cache **SHALL** serve 99.9% of read requests in $< 2\text{ms}$ at up to 50,000 QPS with memory consumption $\le 8\text{GB}$."

### 3.3 Standardized Epistemic GFM Schema
Major architectural assertions must be categorized using standardized GitHub-Flavored Markdown (GFM) callouts:

```markdown
> [!NOTE]
> ### Validated Fact `[FACT-001]`
> - **Source / Evidence**: Production benchmark run `#4029` (Telemetry trace `c7a10f`).
> - **Verified Metric**: Sustained 50,000 QPS @ p99 < 2ms under 8GB heap allocation.

> [!WARNING]
> ### Working Assumption `[ASSUMP-001]`
> - **Dependency**: Upstream ingress proxy drops malformed frames before TLS termination.
> - **Residual Risk**: Malformed frames saturate parser CPU if proxy layer fails.
> - **Validation Plan**: Fuzz test scheduled for Sprint 42 (Jira: `ENG-892`).

> [!IMPORTANT]
> ### Hypothesis `[HYP-001]`
> - **Proposed Design**: Migrating connection pool to epoll reduces CPU context-switch latency by >= 20%.
> - **Falsification Criteria**: p99 latency fails to decrease by >= 15% under 40k QPS synthetic load.
```

---

## 4. Multi-Tier Audience Partitioning

Every technical design document must accommodate dual reading velocities:

1. **Executive Fast-Path (< 60 Seconds)**:
   - Positioned immediately beneath document metadata.
   - Summarizes: Core problem statement, selected architectural decision, irreversible financial/operational trade-offs, and residual risk posture.
2. **On-Call Incident Fast-Path (< 30 Seconds)**:
   - Mandatory for all operational runbooks and service specifications.
   - Summarizes: Active monitoring dashboards, on-call Slack/PagerDuty handles, and 1-line emergency kill-switch commands.
3. **Engineering Deep-Path (Full Rigor)**:
   - Uncompromising technical depth: data schemas, wire protocols, failure blast radiuses, concurrency invariants, and deterministic rollbacks.

---

## 5. Operational Runbook Directives (The 4-Phase Schema)

All operational runbooks authored under this standard must isolate executable steps using the deterministic 4-phase schema:

```markdown
### Step 3: Evict Idle Session Partitions

> [!CAUTION]
> **BLAST RADIUS**: High. Evicting session keys forces downstream clients to re-authenticate. CPU spike expected for 30s. Do NOT execute during peak traffic (13:00–18:00 UTC).

1. **Pre-Flight Assertion**:
   ```bash
   redis-cli -p 6379 DBSIZE
   # Expected Output: Integer > 0 (e.g., :542100)
   ```
2. **Execution Directive**:
   ```bash
   redis-cli -p 6379 --scan --pattern "session:idle:*" | xargs -L 100 redis-cli -p 6379 UNLINK
   ```
3. **Deterministic Verification**:
   ```bash
   redis-cli -p 6379 --scan --pattern "session:idle:*" | wc -l
   # Expected Output: 0
   ```
4. **Emergency Rollback**:
   ```bash
   python scripts/restore_cache_snapshot.py --target prod --snapshot latest
   ```
```

---

## 6. Automated CI Enforcement (Vale Configuration)

To eliminate manual review bikeshedding, this specification is deterministically verified via the **Vale** linter engine.

### Configuration (`.vale.ini`)
```ini
StylesPath = .vale/styles
MinAlertLevel = suggestion

[*.md]
BasedOnStyles = NASA

NASA.BannedHandwaving = error
NASA.NormativeModals = error
```

### Style Rule (`.vale/styles/NASA/BannedHandwaving.yml`)
```yaml
extends: existence
message: "NASA Tone Standard Violation: Unquantified term '%s'. Replace with empirical metric."
level: error
ignorecase: true
tokens:
  - seamless
  - effortless
  - blazing-fast
  - lightning-fast
  - infinitely scalable
  - robust
  - ultra-low latency
  - easy to use
```

### Inline Waiver & Exemption Syntax
When citing third-party vendor documentation or discussing legacy constraints, authors may suppress linter alerts using scoped inline comments:
```markdown
<!-- vale NASA.BannedHandwaving = NO -->
The vendor marketing materials claim their cluster is "infinitely scalable".
<!-- vale NASA.BannedHandwaving = YES -->
```

---

## 7. Defensive Trade-Off Rhetoric (Self-Compliance)

In strict accordance with Section 5 of our governance doctrine, this specification documents its own operational trade-offs:

### 7.1 Operational Tax
- **Authoring Overhead**: Initial document draft times increase by approximately 15–25% due to the requirement for quantified boundary metrics and GFM epistemic callouts.
- **Tooling Overhead**: CI build duration increases by ~3.5 seconds per commit to execute Vale AST parsing across modified markdown files.

### 7.2 Failure Blast Radius
- **Blocked Pull Requests**: Overly aggressive linting can block legitimate emergency documentation or hotfix PRs during off-hours if engineers trigger false-positive keyword violations.
- **Mitigation**: Emergency commit bypass (`Doc-Waiver: INCIDENT-<id>`) allows on-call responders to bypass doc linting during active incidents.

### 7.3 Graceful Degradation & Lifecycle Scoping
- Documents bearing frontmatter `status: draft` or `status: rfc` downgrade rule severity from `error` to `warning`, preserving authoring velocity during exploratory architectural phases.
