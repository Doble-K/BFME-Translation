---
description: Show aggregate translation progress and active worker leases.
agent: translator
---

Run:

```bash
python3 tools/localization/agent_batch.py status \
  --project config/project.json \
  --mode incomplete \
  --json
```

Summarize counts and active workers only. Do not inspect any catalog or batch.
