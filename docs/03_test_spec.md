# Test Specification

## Test Strategy
- Coverage target: all 5 nodes ≥1 success + ≥1 error/edge unit test; ≥1 full-graph integration
- Test types: Unit (`tests/unit/`) / Integration (`tests/integration/`) / Proof-of-Boundary (`tests/proof_of_boundary/`)

## Framework Compliance Tests (Mandatory) — `tests/unit/test_framework_compliance.py`

| TC-ID | Test | Expected Result | Result |
|-------|------|----------------|--------|
| TC-01 | State contract: flat TypedDict extends `AgentState` | Type check pass, no Pydantic/dataclass | PASS |
| TC-02 | Fail-closed validation on empty/invalid input (all 4 domain nodes) | ERROR dict returned, no raise | PASS |
| TC-03 | No JWT/Credential/`os.environ` in `src/` | 0 violations (regex + literal scan) | PASS |
| TC-04 | InvocationContext via configurable only | Not present in `State` annotations | PASS |
| TC-05 | S-4 domain audit + no backbone re-emit | `emit_trace_event()` present in every node; `node_start`/`node_complete`/`node_error` absent from `execute()` bodies | PASS |
| TC-06 | S-2: `_extra_security_gate_input()` hook present (`InputValidateNode`) | Hook exists, non-`@final` extension point | PASS |
| TC-07 | S-3: `_extra_security_gate_output()` hook present + blocks credential pattern on own `formatted_output` | ERROR dict on credential match | PASS |
| TC-08 | `required_trust_level` declared valid enum + enforced (outer=VERIFIED_EXTERNAL, inner=ANONYMOUS) | `__call__()` with ANONYMOUS caller on outer node → ERROR + "S-1 trust gate denied" | PASS |

## Proof-of-Boundary Tests (Mandatory)

| PB-ID | Boundary | Test | Expected Result | Result |
|-------|----------|------|----------------|--------|
| PB-1 | BaseNode → EventEmitter | `emit_trace_event()` fires on every invocation path | No silent failures | PASS |
| PB-2 | State serialization | Post-invoke State is primitives only | No Pydantic/dataclass — `test_state_safety.py` | PASS |
| PB-3 | Deterministic tool → inventory | `LotMatchNode` calls `src/services/lot_matcher.py` against inventory rows | Real deterministic classification | PASS |
| PB-4 | Import isolation | No Level 0 imports | AST scan: 0 violations — `test_import_isolation.py` | PASS |
| PB-5 | Checkpoint safety | No JWT/Pydantic in checkpoint | Inspection pass — `test_state_safety.py` | PASS |
| PB-6 | Invoke execution order | `__call__()`: S-1 → S-4 `node_start` → S-2 → `execute()` → S-3 → S-4 `node_complete` for every `src/nodes/` class | `test_pb_invoke_order.py` | PASS |
| PB-7 | HITL interrupt propagation | `hitl.enabled` not set for this template | Auto-waived — non-HITL (`test_pb7_hitl_interrupt_propagation.py` auto-skips) | Auto-waived |

## Business Logic Tests

| TC-ID | Test | Input | Expected Result | Result |
|-------|------|-------|----------------|--------|
| BL-01 | Exact lot+location match | `lot_numbers=[ABC123]`, inventory row exact match, `parse_confidence>=0.7` | `match_result.status == "exact"`, 1 grounded claim, `action_rule_id == quarantine_review` | PASS |
| BL-02 | No inventory match | `lot_numbers=[ZZZ999]`, no matching row | `match_result.status == "no_match"`, `escalation_packet.claims == []` | PASS |
| BL-03 | Sub-threshold parse confidence forces `possible` | `parse_confidence < 0.7` | `match_result.status == "possible"`, `confidence_basis == "sub_threshold_parse_confidence"` | PASS |
| BL-04 | Malformed lot grammar lowers `parse_confidence` | Lot number fails `^[A-Z0-9]{3,20}(-[A-Z0-9]{3,20})?$` | `parse_confidence < 0.7` | PASS |
| BL-05 | OutputValidate rejects ungrounded claim | Claim missing `inventory_record_ids` | Whole package rejected (ERROR) | PASS |
| BL-06 | OutputValidate rejects unapproved `action_rule_id` | Claim references an id outside the approved set | Whole package rejected (ERROR) | PASS |
| BL-07 | End-to-end exact match via `Graph().invoke()` | JSON envelope `{recall_text, inventory_rows}` with exact match | `result.status == "success"`, `escalation_packet.match_status == "exact"` | PASS |

## Test Execution Summary
- Execution date: 2026-07-18
- Total tests: unit (input_validate 6, recall_parse 4, lot_match 4, escalation_render 3,
  output_validate 8, framework_compliance ~18) + integration (3) + proof_of_boundary (import
  isolation, state safety, invoke order, PB-7 auto-skip)
- Pass: local run (see MR CI) / Fail: 0 / Skip: PB-7 (non-HITL, expected)
- Coverage: every node ≥1 success + ≥1 error/edge path; full graph ≥1 integration compile+invoke
