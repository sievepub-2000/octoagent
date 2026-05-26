# Contributing to OctoAgent

Thanks for considering a contribution. Before opening a pull request,
please read this entire document — by submitting a PR you agree to the
**Contributor License Agreement (CLA)** in section 4 below.

## 1. Quick start

```bash
git clone git@github.com:sievepub-2000/octoagent.git
cd octoagent
./scripts/install-octoagent.sh        # bootstraps venv + pnpm + runtime dirs
./scripts/octoagent configure         # interactive model & provider setup
make smoke-chat-regression            # quick browser-level smoke
```

The canonical development handbook is
[`project_docs/imported/root_files/CONTRIBUTING.md`](project_docs/imported/root_files/CONTRIBUTING.md);
backend-specific notes live in
[`project_docs/backend/CONTRIBUTING.md`](project_docs/backend/CONTRIBUTING.md).

## 2. Code style & checks

Before opening a PR:

- `cd backend && .venv/bin/ruff check src tests`
- `cd backend && .venv/bin/python scripts/check_topology_freeze.py`
- `cd backend && .venv/bin/pytest`
- `cd frontend && pnpm lint && pnpm typecheck && pnpm build`

CI re-runs all of the above plus `license-check`, `import-linter`,
`live-validations`, and `chat-regression`. A red CI is a blocker.

## 3. Tampering with the About module

`backend/src/governance/about.py` is integrity-protected. If you
*legitimately* change the contact email or About body, you MUST run:

```bash
python scripts/dev_tools/refresh_about_fingerprint.py
```

…and explain the rationale in your PR description. PRs that touch the
About body without resealing the fingerprint, or that remove the About
panel from the Settings navigation, will be closed without merge as a
license violation (see LICENSE, Addendum A).

## 4. Contributor License Agreement (CLA)

By submitting a contribution (code, documentation, translations, tests,
issue triage, design assets, or any other material that is incorporated
into the project), you agree to the following terms. This CLA is
intentionally short; if anything is unclear, raise it in the PR before
merge.

### 4.1 Grant of rights

You hereby grant to OctoSys (and to recipients of the project) a
perpetual, worldwide, non-exclusive, royalty-free, irrevocable license
to reproduce, prepare derivative works of, publicly display, publicly
perform, sublicense, and distribute your contribution and such
derivative works.

### 4.2 Dual-licensing acceptance

You acknowledge that the project is distributed under the dual-license
framework in [`LICENSE`](LICENSE) (SSPL v1 + addenda for community use,
commercial license available from zillafan80@gmail.com). You agree that
OctoSys may distribute your contribution under either track and that
you will not later assert any claim that would prevent such
dual-licensing — including under any patent you control. The Patent
Retaliation Clause (Addendum B) applies to you as well as to downstream
users.

### 4.3 Representation of originality

You represent that:

(a) the contribution is your original work, or you have the right to
    submit it on behalf of the copyright owner;
(b) your contribution does not knowingly include any third-party code
    or content that is incompatible with the project's license;
(c) if your employer has rights to intellectual property you create,
    you have obtained their permission to make the contribution, or
    your employer has waived such rights for OctoAgent contributions.

### 4.4 Sign-off

Add a `Signed-off-by: Your Name <your-email>` trailer to each commit
(`git commit -s`). This certifies the Developer Certificate of Origin
v1.1 (https://developercertificate.org/) as well as section 4 above.

## 5. Reporting security issues

Do NOT open public issues for security problems. Email
**zillafan80@gmail.com** with subject `[octoagent-security]` and we will
respond within five business days. Coordinated disclosure is preferred.

## 6. Commercial inquiries

For licensing that goes beyond SSPL v1 (managed-service offerings,
embedded redistribution, OEM, proprietary integration, removal of the
About panel obligations, etc.), open an issue using the
[`Commercial inquiry`](.github/ISSUE_TEMPLATE/commercial_inquiry.md)
template or email zillafan80@gmail.com directly.
