# OctoAgent architecture

Version 20260721.1.0 has two public application Modules.

```text
WebUI
  └─ App Server (unprivileged, one process and one port)
       ├─ Agent Runtime
       │    ├─ LangGraph protocol and streaming
       │    ├─ model turns and continuation
       │    └─ Project / Task / Run / RunEvent data
       └─ Harness
            ├─ dynamic capability scan and private registry
            ├─ permission enforcement and dispatch
            ├─ workspace / shell / browser / MCP implementations
            ├─ traces and artifact ownership
            └─ Markdown memory + pgvector retrieval
                 └─ System Executor (isolated host-root boundary)
```

Agent Runtime decides what to do. Harness is the only Interface through which
capabilities are discovered and executed. The model does not call a second
Tools Hub, Brain, QueryEngine, or workflow service. LangGraph is an internal
protocol/runtime library hosted inside App Server, not a second control plane.

System Executor is deliberately a separate container because it owns the only
Docker socket and host-root execution path. App Server and Frontend run as
unprivileged users and cannot acquire system permission without server-side
Harness enforcement.

Memory source files live at `runtime/memory/<thread>/`. Every completed run
first writes an atomic `.raw.md` transcript and `.memory.md` extraction.
PostgreSQL pgvector is a derived HNSW retrieval index. Harness startup scans the
Markdown source and repairs missing index rows, so a database index failure
cannot erase the original memory.
