"""AgentCore Platform v1.0"""

# Pre-approved facility escalation-rule set. Customer-configured per hospital
# at onboarding (docs/02_design.md §Dependencies); the ids/wording below are
# engineering-default placeholders. EscalationRenderNode may only reference
# action_rule_id values from this closed set — never invented free-form
# wording — and OutputValidateNode rejects the whole package if a claim
# references an id outside this set.

APPROVED_ACTION_RULE_IDS = {"quarantine_review", "compliance_notify", "no_action_required"}

ACTION_WORDING = {
    "quarantine_review": "Escalate to sterile-processing lead for physical quarantine review.",
    "compliance_notify": "Notify compliance officer for recall sign-off review.",
    "no_action_required": "No further action required — no matching inventory found.",
}

ACTION_RULE_BY_MATCH_STATUS = {
    "exact": "quarantine_review",
    "possible": "compliance_notify",
    "no_match": "no_action_required",
}
