# Validation, Approval, and Promotion

AI output is not production authority.

Jarvis may produce:

- recommendations;
- YAML;
- shell scripts;
- Python;
- configuration changes;
- media decisions;
- reports;
- escalation packets.

Before anything progresses toward production, deterministic validation should run wherever possible.

Examples:

- YAML syntax validation;
- Home Assistant configuration checks;
- schema validation;
- Python syntax/lint/tests;
- shellcheck;
- Docker Compose validation;
- SQL checks;
- duplicate/collision protection;
- ffprobe validation;
- git diff review.

## Promotion path

```text
ANALYSIS
   ↓
PROPOSAL
   ↓
DETERMINISTIC VALIDATION
   ↓
REMOTE / LOCAL HUMAN REVIEW
   ↓
APPROVAL
   ↓
CONTROLLED IMPLEMENTATION
   ↓
RUNTIME VERIFICATION
```

`rdp-scripts/Jarvis` is intentionally suited to the proposal and remote-review stages.

A Git commit in that results repository does not automatically mean the live environment changed.
