# Packet Result Template

Replace the packet's placeholder with at most eight lines:

```text
Status: done | blocked_external
Changed: path: symbols, or none
Behavior: one sentence
Tests: exact command -> result
Risks: none, or one concise residual risk
Next: packet number, or exact blocker
```

Do not paste diffs, logs, stack traces, or full test output. For a blocker, include
only the first relevant error and its file/line.
