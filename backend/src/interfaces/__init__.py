"""External interface surface (Python SDK, embedded client, Studio, Research, Distributed exec).

Per ``project_docs/docs/MODULE_OWNERS.md`` (Phase 7 physical merge, 2026-05-26)
this package collects the eight previously top-level modules that surface the
gateway / runtime to non-HTTP clients. Inner subpackages preserve their public
APIs — direct imports continue to work via these stable paths:

* :mod:`src.interfaces.embedded` — in-process Python client (former ``src.client*``)
* :mod:`src.interfaces.python_sdk` — thin HTTP/WS SDK (former ``src.interfaces.python_sdk``)
* :mod:`src.interfaces.contracts` — shared dataclasses + dispatcher (former ``src.interfaces.contracts``)
* :mod:`src.interfaces.studio` — LangStudio runtime bridge (former ``src.interfaces.studio``)
* :mod:`src.interfaces.research` — research runtime service (former ``src.interfaces.research``)
* :mod:`src.interfaces.distributed` — multi-host execution proxy (former ``src.interfaces.distributed``)
"""
__all__: list[str] = []
