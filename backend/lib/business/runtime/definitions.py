"""Stable workflow contracts shared by producers and workers."""

OPERATOR_WORKFLOW_STEPS = [
    {"step_key": "analyst", "handler": "operator.analyst"},
    {"step_key": "strategist", "handler": "operator.strategist"},
    {"step_key": "researcher", "handler": "operator.researcher"},
    {"step_key": "creator", "handler": "operator.creator"},
    {"step_key": "packager", "handler": "operator.packager"},
    {"step_key": "finalize", "handler": "operator.finalize"},
]

INITIATIVE_EXECUTION_STEPS = [
    {"step_key": "execute_approved_scope", "handler": "initiative.execute"},
]
