# Template Design Specification

## Position in AgentCore Architecture

- **Agent Class**: `HcrC2079RecallLotMatchEscalationAgent` (`src/graph/graph.py`)
- **L1 Base**: AgentBaseGraph (Cat 2 outer graph) — L1 direct, no L2 class
- **Three-Layer Separation**:
  - State: flat TypedDict composition (no Pydantic — msgpack incompatible), `src/schemas/state.py`
  - Node: L1 inheritance (Template Method: `execute(self, state: dict) -> dict` override only)
  - Graph: composition — outer `AgentBaseGraph` (`register_nodes()`), inner `BaseGraph`
    (`RecallLotMatchWorkflowGraph`) wrapped by `RecallLotMatchGraphNode` (`main` slot)

## Architecture Overview

Cat 2 (multi-step pipeline for a specific job-to-be-done). Scope: parse an incoming authorized recall notice, match
against read-only lot/location inventory, produce exact/possible/no-match
evidence + a structured escalation packet. Out of scope: physically
quarantining stock, directing clinical care, formally closing a recall.

### Node Configuration (outer backbone)

| Node | Responsibility | Input State | Output State | Inherits/Overrides |
|------|---------------|-------------|--------------|-------------------|
| initialize | schema_version, session_id, trust_level | — | — | InitializeNode (default) |
| pre_process | **InputValidateNode** — S-1 (VERIFIED_EXTERNAL) + S-2 credential/identifier scan; parse JSON envelope `{recall_text, inventory_rows}` | `user_input` | `recall_text`, `inventory_rows`, `validated_input` | `FunctionNode` |
| main | **RecallLotMatchGraphNode** (`GraphNode`) — dispatches to inner subgraph | `validated_input` | `parsed_criteria`, `match_result`, `escalation_packet` | `GraphNode` |
| post_process | **OutputValidateNode** — S-3 whole-package validation (claim grounding + credential re-scan) | `escalation_packet` | `result`, `formatted_output` | `FunctionNode` |
| finalize | response_metadata, total_time_ms | — | — | FinalizeNode (default) |

### Inner subgraph (`src/graph/recall_lot_match_workflow_graph.py` — `RecallLotMatchWorkflowGraph`, `BaseGraph`)

| Inner node | Responsibility | Output |
|---|---|---|
| `recall_parse` (**RecallParseNode**, LLM; deterministic fallback when no LLM is configured) | Normalize free-text recall notice into `lot_numbers[]`, `product_id`, `location_scope`, deterministic `parse_confidence`, `parse_method` (`llm` / `deterministic_fallback`). The fallback extracts only lot numbers that follow a "lot" keyword and match the lot grammar; it leaves location and product empty, so confidence stays below 0.7 and the match can only resolve to `possible` | `parsed_criteria` |
| `lot_match` (**LotMatchNode**, `FunctionNode` wrapping `src/services/lot_matcher.py`) | Deterministic exact/possible/no_match classification against inventory | `match_result` |
| `escalation_render` (**EscalationRenderNode**, LLM) | Assemble structured claims grounded in `parsed_criteria`/`match_result`/inventory, bound to a pre-approved `action_rule_id` | `escalation_packet` |

### Data Flow

```
START → initialize → pre_process(InputValidate) → main(GraphNode) → {route} → post_process(OutputValidate) → finalize → END
                                                                        ↓ (retry)
                                                                  pre_process
                        │
                        ▼ (inside GraphNode.execute())
        INNER: START → recall_parse → lot_match → escalation_render → END
```

### Deterministic status-rule contract (locked — `src/services/lot_matcher.py`)

`parse_confidence < 0.7` → `possible`; malformed/missing lot number(s) → `possible`;
>1 distinct matching location code → `possible`; candidate count > 20 → `possible`;
exact key match (`lot_number` + `location_id`), `parse_confidence >= 0.7`, unambiguous
location → `exact`; zero candidates with no ambiguity/malformed condition → `no_match`;
any condition not explicitly enumerated → `possible` (fail-safe, never silently
collapses to `no_match`).

### State Definition

| Field | Type | Purpose | Required |
|-------|------|---------|----------|
| `recall_text` | `NotRequired[str]` | Raw recall notice text (post S-2 scan) | No |
| `inventory_rows` | `NotRequired[list[dict]]` | Read-only lot/location inventory rows | No |
| `parsed_criteria` | `NotRequired[dict]` | `{lot_numbers, product_id, location_scope, parse_confidence}` | No |
| `match_result` | `NotRequired[dict]` | `{status, matched_records, confidence_basis, status_reason}` | No |
| `escalation_packet` | `NotRequired[dict]` | `{summary, claims, recommended_action, match_status}` | No |

**State Constraints (mandatory):**
- Flat TypedDict only (primitives + JSON-serializable types)
- No JWT, API keys, credentials in State (checkpoint DB leakage)
- InvocationContext via `config["configurable"]` only (not in State)
- No Pydantic models, dataclass, arbitrary Python objects (msgpack incompatible)

## Framework Utilization

### Shared Components Used
- [x] InvocationContext (correlation_id, session_id, permissions, credential handle)
- [ ] ConnectionPolicy (retry/timeout strategy) — default `max_retry: 3` from `config/agent.yaml`
- [x] SecurityViolationError semantics via ERROR-status returns (no raise — see below)
- [x] S-2: `_extra_security_gate_input()` on `InputValidateNode` — credential-pattern +
      facility/patient-identifier regex scan on `user_input`
- [x] S-3: `_extra_security_gate_output()` on `OutputValidateNode` — credential-pattern
      re-scan on the node's own `formatted_output`; claim-grounding validation is business
      logic inside `execute()` (returns ERROR dict, never raises)
- [x] S-4: `emit_trace_event()` — every node (outer + inner + `GraphNode` hooks
      `extract_input()`/`merge_output()`) emits ≥1 domain event

> **S-2/S-3 gate behaviour by node type (ADR-017):**
> - `FunctionNode` subclass (all 5 domain nodes here) → framework `@final` gate always
>   runs automatically; extended via `_extra_security_gate_input()` / `_extra_security_gate_output()`
> - `GraphNode` (`RecallLotMatchGraphNode`) → deliberate no-op (inner subgraph nodes already
>   run their own S-2/S-3 gates); S-4 audit is emitted via `extract_input()`/`merge_output()` hooks

### Composition Pattern

- **Pattern**: `GraphNode` (subgraph) — Cat 2 outer/inner split
- **Composition target**: `src/graph/recall_lot_match_workflow_graph.py` (`RecallLotMatchWorkflowGraph`)
- **Error propagation strategy**: `propagate` (`RecallLotMatchGraphNode.error_strategy`) — inner
  subgraph errors surface as `SubgraphError`, fail-fast

## Import Isolation Confirmation
- [x] Template does not import agenticstar-platform SDK (Level 0)
- [x] Import targets: framework/ and shared/ only (no agents/base/ required)

## Security & Secrets

No external LLM/DB credential is required for the deterministic `lot_matcher` service
(pure function, no I/O). `RecallParseNode`/`EscalationRenderNode` accept an `llm` client
injected via constructor at the entry point; secret provisioning (if the LLM client
requires an API key) follows `ctx.secrets.require()` / `bound_secrets()` per
`config/agent.yaml requires.secrets` — none declared for the current LLM-agnostic design
(the LLM client instance itself owns its own credential handling upstream).

The standalone entry point (`src/api/server.py`) reads an optional `ANTHROPIC_API_KEY` with
`.get()` (never `.require()`): when the key is absent the graph is built with `llm=None` and
`RecallParseNode` uses its deterministic lot-number fallback.

Facility-specific escalation-rule configuration (routing, recommended-action wording) is
a customer-provided input at onboarding — the
engineering-default `src/services/escalation_rules.py` ids/wording are placeholders to be
replaced per facility.

## Design Decision Record

| Decision | Option A | Option B | Chosen | Rationale |
|----------|----------|----------|--------|-----------|
| L1 base type | AgentBaseGraph | AutonomousBaseGraph | **AgentBaseGraph** | Fixed multi-step pipeline (parse→match→render→validate), no autonomous reasoning loop needed |
| Composition pattern | Flat Cat 1-style 3-node | GraphNode + inner subgraph | **GraphNode + inner subgraph** | Cat 2 requires outer/inner split (`gate-composition`); domain workflow has 3 distinct reasoning/deterministic steps |
| Lot matcher location | `src/nodes/` graph node | `src/services/` pure function | **`src/services/lot_matcher.py`** | Agent-vs-Tool boundary (§2): deterministic matching is a Tool-equivalent helper, not a graph node in its own right |
| Trust level (outer) | ANONYMOUS | VERIFIED_EXTERNAL | **VERIFIED_EXTERNAL** | Matches `config/agent.yaml` agent default; outer boundary receives input from hospital operations systems |
| Trust level (inner) | INTERNAL | ANONYMOUS | **ANONYMOUS** | Trust authenticated once at outer backbone; inner nodes requiring INTERNAL would be unreachable privilege-escalation |
