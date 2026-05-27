# OctoAgent Commercial License FAQ

> OctoAgent is dual-licensed:
> - **SSPL v1** (the public source license — see [`LICENSE`](../LICENSE)).
> - **Commercial license** (a separate, paid agreement — contact
>   **zillafan80@gmail.com**).
>
> The Bytedance-derived portion remains under **MIT** — see
> [`NOTICE.md`](../NOTICE.md) for the file-level attribution.

This FAQ exists because SSPL is widely misread as "free for anything,
since it's open source". It is not. The summary below is non-binding;
[`LICENSE`](../LICENSE) is the authoritative document and supersedes
any wording here.

---

## TL;DR — when do I need a commercial license?

**Only the following uses are free under SSPL v1:**

1. **Personal, non-commercial** use on hardware you personally own and
   control, with no third-party users.
2. **Bona-fide academic research and teaching** that publishes results
   under a permissive license and does not bill users for access.
3. **Internal evaluation** for up to 30 days while you decide whether
   to buy a commercial license.

**Every other use case requires a commercial license**, including but
not limited to:

| Scenario | Commercial license required? |
| --- | --- |
| Running OctoAgent for paying customers as a SaaS | **Yes** |
| Bundling OctoAgent into a product you sell or license | **Yes** |
| Running OctoAgent inside a for-profit company for internal staff | **Yes** |
| Hosting OctoAgent for a client as a managed service | **Yes** |
| Running OctoAgent on a client's hardware as part of a paid engagement | **Yes** |
| Forking and publishing a commercial derivative | **Yes** |
| Personal hobby use on your own laptop, no users but you | No |
| University research that publishes findings under MIT/CC-BY | No |

If you are unsure which side of the line your use sits on, **assume a
commercial license is required and ask first**: `zillafan80@gmail.com`.

---

## Why SSPL?

SSPL was chosen because OctoAgent ships as a *service-shaped* product —
it has a backend, a frontend, a multi-tenant gateway, sandboxing, and
plug-ins. Permissive licenses (MIT/Apache) would let a cloud vendor
operate the project as a managed service without contributing
improvements back. SSPL closes that loophole by requiring that anyone
who offers OctoAgent's functionality "as a service" to third parties
also publish the source of the *entire service stack* used to deliver
it — load balancers, monitoring, deployment automation, the lot.

For most operators, complying with SSPL §13 in full is impractical, so
the commercial license is the pragmatic path.

---

## What does a commercial license get you?

* Permission to operate OctoAgent for third parties without SSPL §13.
* Permission to embed OctoAgent in proprietary products.
* Optional support, hardening guidance, and roadmap input (per the
  signed agreement).
* Indemnification terms can be negotiated for enterprise customers.

The commercial license is **separate** from the OSS license; you
continue to receive the public source releases under SSPL.

---

## What about the MIT-licensed Bytedance-derived files?

A subset of files under `backend/src/` originated in Bytedance's
agent-sandbox project and remain under **MIT**. See
[`NOTICE.md`](../NOTICE.md) for the file list. You are free to use,
modify, and redistribute *those specific files* under MIT regardless of
the rest of OctoAgent's licensing. The MIT carve-out does **not**
extend to the project as a whole.

---

## Contributor License Agreement

Every contributor implicitly agrees to the CLA in
[`CONTRIBUTING.md`](../CONTRIBUTING.md) §4 when opening a pull request.
The CLA grants the project maintainers the right to re-license
contributions under the commercial license. This is standard practice
for dual-licensed projects.

---

## Reporting suspected non-compliance

If you notice OctoAgent being operated commercially without (to your
knowledge) a license, email **zillafan80@gmail.com** with the URL and
any public evidence. We follow up privately — please do not file public
issues that name suspected operators.

---

## Contact

| Channel | When to use |
| --- | --- |
| `zillafan80@gmail.com` | All commercial licensing inquiries (Chinese / English / 日本語 OK). |
| GitHub issue (`commercial_inquiry` template) | Public, non-confidential questions about licensing terms. |
| GitHub issue (`bug_report` template) | Bugs in the OSS release. |

Average first-reply window: 2 business days.
