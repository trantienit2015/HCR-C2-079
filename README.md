# HCR-C2-079 — Healthcare Facility Sterile-Supply Recall Lot Match Escalation Agent

> **Category**: Cat 2 (orchestrates multiple steps to accomplish a specific use case)
> **Industry**: HCR

## Overview

This agent helps a healthcare facility respond to a sterile-supply recall notice. The caller
sends one JSON document in the `input` string: `recall_text` (the free-text recall notice) and
`inventory_rows` (a read-only list of `{lot_number, location_id}` records from the facility's
stock system). The agent then runs a fixed five-step pipeline:

1. **Input validation** parses the JSON envelope and rejects input that contains credential-like
   strings or patient identifiers (`patient_id`, `MRN`).
2. **Recall parsing** turns the notice into structured criteria (lot numbers, product id, affected
   location) with a deterministic `parse_confidence` score. When an LLM client is configured, the
   model does the extraction. When no LLM is configured, a deterministic keyword fallback extracts
   only the lot numbers that follow a "lot" keyword. It never guesses the location or product, so
   its confidence always stays below the exact-match threshold. The method used is recorded as
   `parse_method` (`llm` or `deterministic_fallback`).
3. **Lot matching** applies fixed rules to compare the criteria with the inventory and classify the
   result as `exact`, `possible` or `no_match`. Low confidence, malformed lots, ambiguous locations
   and too many candidates all resolve to `possible`.
4. **Escalation rendering** builds a packet of claims. Each claim is tied to the parsed criteria,
   the match result and the inventory records, plus an action rule from a closed, pre-approved
   set: quarantine review, compliance notification, or no action.
5. **Output validation** rejects the whole packet if any claim is ungrounded, or if a match that
   needs escalation has no claims.

The agent only produces a recommendation for human review. It never quarantines stock, closes a
recall or directs clinical care. The action-rule wording in `src/services/escalation_rules.py` is
an engineering default that each facility is expected to replace with its own approved rules.

This is an agent template built with the **AGENTIC STAR** development platform and the
**AgentCore Framework**. It is intended to be taken as a starting point: fork it, adapt it to
your own data and policies, and run it inside your own AGENTIC STAR deployment.

## Requirements

**This template does not run standalone.** It requires:

| Requirement | Notes |
|---|---|
| **AGENTIC STAR platform** | The agent connects to the platform at start-up. Without it, start-up fails immediately (see *Behaviour without the platform* below). Deployment guides and API documentation: [AGENTIC STAR Developers](https://developers.fd.agenticstar.tm.softbank.jp/) |
| **AgentCore Framework** (`agenticstar-agentcore`) | Installed from PyPI as a dependency. |
| Python | 3.11 or later |

```bash
pip install -e .
```

### Behaviour without the platform

The framework is designed to run **only** on AGENTIC STAR. There is no fallback or degraded
mode. If the platform is unreachable or the SDK version does not match, the agent raises
`PlatformRequired` during graph compile / start-up preflight rather than starting in a partially
working state. This is intentional — a half-running agent is worse than one that refuses to start.

## Quick Start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest tests/ -v
```

Tests run without a platform connection. Running the agent itself does not.

## Project Structure

```
src/          agent implementation (nodes, services, schemas)
tests/        unit, integration and boundary tests
config/       agent configuration
docs/         design and test specification
```

See `docs/02_design.md` for the design and `docs/03_test_spec.md` for the test specification.

## Customising

1. Adjust `config/` for your own environment and policies.
2. Replace the knowledge sources and sample data with your own.
3. Review the node implementations under `src/nodes/` for domain-specific logic.
4. Re-run the test suite.

## License

MIT — see [LICENSE](LICENSE).

## Status of this repository

This template is published **as is**, by its individual author, under the MIT license. It carries
**no warranty and no support commitment**, and no organisation stands behind its behaviour or
fitness for any purpose. Issues and pull requests may or may not receive a response; that is at
the sole discretion of the repository owner.
