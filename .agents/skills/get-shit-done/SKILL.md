---
name: get-shit-done
description: 'Pragmatic, no-nonsense coding discipline. Cuts through analysis paralysis, scope creep, and over-engineering. USE FOR: when stuck, when a task is stalling, when scope keeps growing, when you need to ship, when perfection is blocking progress. DO NOT USE FOR: greenfield architecture decisions, security-critical systems where shortcuts are dangerous, team-wide standards changes.'
license: MIT
metadata:
  author: custom
  version: "1.0"
---

# Get-Shit-Done: Pragmatic Execution Discipline

A set of rules and heuristics to cut through paralysis and ship working software. Inspired by pragmatic engineering culture — done is better than perfect, but not at the cost of correctness.

## Core Rules

### Rule 1: Ship the Smallest Thing That Works
- Default to the smallest scope that satisfies the **stated requirement**, not the imagined future requirements.
- If in doubt, cut the feature. If the feature is missing, add it later.
- **Red flag**: If a task estimates 3+ days, it needs to be split.

### Rule 2: Two Hours Rule
- If you've been stuck on the same problem for more than 2 hours, you MUST:
  1. Write down exactly what you've tried and why it failed.
  2. Ask for help OR change approach completely.
  3. Never keep retrying the same failed approach expecting different results.

### Rule 3: 80% Now, 20% Later
- Write code that handles the happy path + the top 3 error cases.
- Document the remaining edge cases in a `// TODO(gsd):` comment.
- Ship. Come back for the 20%.

### Rule 4: No Rabbit Holes
- **Forbidden actions** while executing a task:
  - Refactoring code unrelated to the task
  - "While I'm here" changes
  - Upgrading dependencies unless directly required
  - Re-architecting because you spotted a design smell
- **Allowed**: Leave a `// FIXME:` comment and move on.

### Rule 5: Done Means Done
A task is done when:
- [ ] The feature works as specified (not "mostly works")
- [ ] It doesn't break existing functionality
- [ ] A human can use it without reading source code
- [ ] The diff is reviewable (< 400 lines changed per PR)

Not done:
- ❌ "It works on my machine"
- ❌ "I'll write tests later"
- ❌ "The happy path works"

---

## Anti-Patterns to Eliminate

| Anti-Pattern | Signal | Fix |
|---|---|---|
| Analysis Paralysis | Been researching for > 1h without writing code | Time-box to 30min, then code |
| Scope Creep | Task keeps growing with "while I'm here..." | Freeze scope, create new issues |
| Perfectionism | Rewriting the same function 3+ times | Ship v1, iterate |
| Gold Plating | Adding features no one asked for | Cut it unless in requirements |
| Yak Shaving | Fixing tool X to fix tool Y to fix the actual task | Work around X, file a ticket |
| Premature Optimization | Optimizing before profiling shows it's slow | Profile first, optimize second |

---

## When You're Stuck: Decision Tree

```
Stuck for > 30min?
├── YES: Do you understand the problem?
│   ├── NO  → Restate the problem in 2 sentences. If you can't, ask for clarification.
│   └── YES → Have you tried a different approach?
│       ├── NO  → Try the dumbest, most direct approach first.
│       └── YES → Document what failed. Ask for help. Don't repeat.
└── NO → Keep going.
```

---

## The GSD Commit Protocol

Every commit should answer: **"What did this change, and why?"**

```
feat: add user login endpoint [closes #42]

- POST /api/auth/login with email+password
- Returns JWT on success, 401 on bad creds
- Skipping rate limiting for now (TODO #43)
```

**Forbidden commit messages:**
- `fix stuff`
- `wip`
- `updates`
- `asdf`

---

## Daily Execution Pattern

1. **Morning**: Pick 1 primary task. Write it as one sentence.  
2. **Execute**: Close all tabs except what's needed. Minimize context switches.  
3. **Time-box**: Set a 90-min timer. If not done at end, split the task smaller.  
4. **Checkpoint**: Can you demo it? If yes → PR. If no → what's blocking?  
5. **EOD**: Either shipped or has a clear blocker documented.
