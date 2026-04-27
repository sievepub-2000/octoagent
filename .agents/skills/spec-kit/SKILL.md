---
name: spec-kit
description: 'Specification-driven development kit. Generates formal specs, BDD scenarios, acceptance criteria, and API contracts from requirements. USE FOR: writing specs, creating test plans, BDD/Given-When-Then scenarios, acceptance criteria, contract testing, spec-first API design, feature specifications, definition of done checklists. DO NOT USE FOR: one-off tasks without a spec, hotfixes, exploratory work without clear requirements.'
license: MIT
metadata:
  author: custom
  version: "1.0"
---

# Spec-Kit: Specification-Driven Development

A structured approach to writing clear, executable specifications before implementation. Covers feature specs, API contracts, BDD scenarios, and acceptance criteria.

## When to Use This Skill

- Writing a formal feature specification from requirements
- Generating BDD (Behavior-Driven Development) scenarios (Given/When/Then)
- Defining API contracts (request/response schemas, error codes, edge cases)
- Creating acceptance criteria with a clear Definition of Done
- Producing test plans from specs
- Auditing existing code against a specification

---

## Core Principles

1. **Spec before code**: Write the spec first. Implementation follows the spec, not the other way around.
2. **Executable specs**: Every scenario should map 1:1 to a test case.
3. **Unambiguous language**: Use precise verbs (MUST, SHOULD, MUST NOT per RFC 2119).
4. **Edge cases are citizens**: Happy path is 20% of the spec; edge cases are 80%.
5. **Machine-readable**: Prefer YAML/Markdown tables over prose for structured data.

---

## Specification Templates

### Feature Specification

```markdown
## Feature: <Name>

**Goal**: One sentence describing the business value.
**Scope**: What's in and what's explicitly out of scope.
**Owner**: Team/person responsible.
**Priority**: P0 / P1 / P2

### Acceptance Criteria

| ID   | Criterion                          | Test Method  |
|------|------------------------------------|--------------|
| AC-1 | <condition that MUST be true>      | automated    |
| AC-2 | <condition that SHOULD be true>    | manual       |

### BDD Scenarios

#### Scenario 1: <Happy Path>
Given <initial state>
When  <action taken>
Then  <expected outcome>

#### Scenario 2: <Error Case>
Given <initial state with error condition>
When  <action taken>
Then  <error is surfaced with specific message/code>

### Definition of Done
- [ ] All AC marked with `automated` have passing tests
- [ ] Edge cases in Scenario 2+ are covered
- [ ] API docs updated
- [ ] No new regressions
```

### API Contract

```yaml
endpoint: POST /api/resource
description: One-line description
request:
  headers:
    Authorization: Bearer <token>  # REQUIRED
    Content-Type: application/json
  body:
    field_name:
      type: string
      required: true
      constraints: "max 255 chars, no HTML"
response:
  200:
    description: Success
    body: { id: uuid, created_at: iso8601 }
  400:
    description: Validation error
    body: { error: string, field: string }
  401:
    description: Unauthorized
errors:
  - code: FIELD_TOO_LONG
    trigger: field_name > 255 chars
    http_status: 400
```

---

## Agent Workflow

### When asked to write a spec:
1. **Clarify the goal** — Ask 3 targeted questions max if requirements are ambiguous.
2. **Identify entities** — List all data models/actors involved.
3. **Write happy path first** — One primary scenario per feature.
4. **Enumerate error paths** — What can go wrong? Network, auth, validation, concurrency.
5. **Define measurable AC** — Each criterion must be testable.
6. **Produce test skeleton** — Generate test file stubs from scenarios.

### When auditing code against spec:
1. Map each AC to a code path.
2. Flag any AC with no corresponding test.
3. Flag any code path not covered by a scenario (potential over-engineering or hidden feature).
4. Report coverage as `X / Y acceptance criteria verified`.

---

## Quality Gates

A spec is complete when:
- [ ] Every "MUST" in requirements maps to at least one AC
- [ ] Every AC has a testable outcome (not "works correctly" — specify exact behavior)
- [ ] Error paths have specific error codes/messages defined
- [ ] Performance requirements are numeric (e.g., "< 200ms p99", not "fast")
- [ ] Security requirements are explicit (auth, authz, input validation)
