# Neuralese kernel — self-decoding execution vocabulary

Purpose:= compress roadmap surface while preserving execution-relevant distinctions. No RA prior knowledge required.

```text
REL{ A→B transform/sequence; A⇒B conditional implication; A⇄B feedback;
     A∧B conjunction; A∨B alternative; A≠B distinction; A⊂B containment;
     A⊥B operational independence; A?→B candidate; A!→B rejected/blocked }
MOD{ ! MUST/invariant; ? unknown/candidate; ~ approximation; @ evidence-ref; Δ change }
STATUS:= {PASS|FAIL|OPEN|UNKNOWN}; SUPPORT:= {SUPPORTED|EXPERIMENTAL|UNSUPPORTED|UNKNOWN}
```

Core semantics:

```text
Σ := DomainSpec → ActionContract → Plan → Run → Evidence* → Verdict
Plan := canonical+immutable execution materialization; hash(Plan) binds confirmation/execution.
Evidence := {claim,scope,time/env,producer,inputHashes,method,result,artifacts,limits}
Capability := scoped predicate(requirements,Evidence*)→SUPPORT
Reconcile(desired,observed,ownership)→decision     // owned mutable resources only
Projection := GUI|CLI|search|help|docs; Projection !≠ semantic authority
```

Roadmap execution:

```text
HP := hyperpatch = max coherent/reviewable/recoverable transition fitting one work cycle.
PC := PATCH_CONTRACT{thesis,scope,invariants,nonGoals,falsifiers,acceptance,dataMigration,rollback,impact}
SA := SPEC_AMENDMENT{before,after,newEvidence,reason,downstreamImpact}

PRE(HP): reForensics(HEAD) → impactProbe → freeze(PC+fixtures+falsifiers+inputHashes)
RUN(HP): implementation; !silent weakening(PC)
REVIEW(HP): review{PC,diff,evidence}; narrative secondary
ACCEPT(HP): accepted → new HEAD → reForensics → assumptions{confirmed,falsified,new}
            → semanticRollback/SA where needed → recompile(remaining DAG+version candidates)
```

! Roadmap := provisional compiled hypothesis; future P0x has zero authority over contradictory current evidence.
! Evidence authority is claim-relative, never globally `code>runtime>upstream>docs`.
! UNKNOWN ∈ {historically_unrecoverable,environment_contingent,resolvable_blocking,resolvable_nonblocking}; UNKNOWN→PASS requires evidence, not prose.
! truth > convenience; observation≠mutation; desired≠observed≠applied; owned≠present; PID_alive≠ready; SOCKS_CONNECT≠route; parser_green≠semantic_fidelity; new_upstream≠compatible.

Compression contract:

```text
Q := {patch thesis/dependencies/invariants/steps/gates/rollback,
      G01..G21, F01..F35, R01..R30, deferred scope,
      version/provenance axes, evidence/UNKNOWN semantics, golden journeys}
NeuraleseArchive ≈_Q SourceArchive
```

Symbols reduce repetition only; unresolved distinctions must remain explicit.


Это сохранённый оригинал плана квалификации. Он описывает требования и не является доказательством их исполнения. Текущий статус, профиль кандидата и фактические блокеры опубликованы отдельно в документации текущего релиза. Условия финального повышения не заменяются исторической или контейнерной проверкой.
