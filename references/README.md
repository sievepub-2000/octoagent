# Reference Repositories

This directory is reserved for local-only synchronization of third-party reference repositories used for architecture study.

Tracked content:

- this `README.md`

Ignored local content:

- `references/_clones/Claude-Code-Leak`
- `references/_clones/claude-code-reverse`
- `references/_clones/claude-code-sourcemap`
- `references/_clones/claude-code-source-code`

Usage:

```bash
make sync-references
```

The synchronized reference sources are used for study and comparison. They are not part of OctoAgent's shipped product code and must not be copied directly into the repository-owned runtime without legal and technical review.
