---
type: llm
focus: trace
weight: 1
---

answer.md explains that a yield inside an on_llm_request hook makes AstrBot skip the hook (hooks must be plain coroutines)
