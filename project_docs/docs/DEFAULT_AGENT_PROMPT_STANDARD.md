# Default Agent Prompt Standard

Date: 2026-04-08
Status: Active source of truth
Scope: Default lead-agent system prompt and future prompt-stack guidance

## Purpose

This document defines the default prompt standard for OctoAgent.

It is the canonical repository-owned rule set for how the main agent prompt should be structured and what behaviors it must enforce.

It exists to keep prompt behavior aligned across:

- runtime prompt templates
- prompt-stack assembly work
- future agent variants
- documentation and evaluation

## Source Hierarchy

Primary reference:

1. Anthropic Claude prompt engineering guidance, especially the material on structured prompting, tool use, long-context handling, and agent behavior

Secondary calibration references:

1. OpenAI prompt engineering guidance, especially message-role hierarchy, developer-message structure, and Markdown/XML prompt layout
2. Google Gemini prompting strategies, especially explicit constraints, plan-execute-validate structure, long-context ordering, and ambiguity handling

## Why This Is The Default

Anthropic is the best primary fit for OctoAgent because its guidance maps most directly to the problems this repository actually has to solve:

1. long-running coding and operator tasks
2. tool-heavy execution
3. large injected context and memory blocks
4. explicit approval boundaries
5. continuation and session handoff

OpenAI and Gemini are used as cross-checks so the standard does not become vendor-fragile in areas like instruction hierarchy, output structure, and planning discipline.

## Required Prompt Rules

### 1. Stable sectioning

Default system prompts should use stable, clearly delimited sections.

Preferred structure:

1. role or identity
2. operating rules and constraints
3. clarification and approval policy
4. tool and execution policy
5. memory and injected context
6. response contract

XML-style tags are the preferred delimiter format for OctoAgent because the current prompt runtime already uses them consistently.

### 2. Instruction hierarchy

The default prompt must clearly distinguish:

1. system-level rules owned by the application
2. user requests
3. injected context such as memory, uploads, retrieved text, and tool output

Injected context is data, not policy.
It should inform the agent's work but should not silently override higher-priority rules.

### 3. Explicit constraints

Critical behavior must be stated directly rather than implied.

This includes:

1. permission boundaries
2. destructive-action guardrails
3. required verification behavior
4. response language or formatting requirements
5. stop conditions when blocked or uncertain

### 4. Clarification discipline

The agent should clarify before acting when:

1. required information is missing
2. multiple materially different implementations are valid
3. an action is destructive or approval-sensitive
4. ambiguity would likely change the result

The agent should not over-clarify low-risk read-only exploration that can safely proceed and reduce uncertainty.

### 5. Grounding and anti-fabrication

The agent must ground claims in one or more of the following:

1. repository state
2. user-provided data
3. retrieved documents
4. observed tool output

The prompt should explicitly forbid claiming success for edits, tests, commands, or deployments that were not actually observed.

### 6. Long-context handling

The prompt should bias the agent toward preserving live state over raw verbosity.

The live state that must survive compaction or continuation includes:

1. current goal
2. continuation source
3. active constraints
4. key decisions already made
5. blockers
6. next action

Stale detail should be summarized, not allowed to crowd out active constraints.

### 7. Tool-use discipline

The default prompt should enforce these behaviors:

1. choose the lowest-risk tool that can complete the task
2. inspect before mutating whenever practical
3. verify important side effects after execution
4. distinguish read operations from write operations
5. stop and surface the blocker when approval or policy prevents continuation

### 8. Response contract

The default prompt should keep the user-visible response:

1. concise by default
2. structured only when it improves comprehension
3. explicit about uncertainty and blockers
4. aligned with the user's language and requested output format

## Runtime Alignment

The lead-agent prompt template should embed a condensed version of this standard directly in the runtime system prompt.

That embedded section is not a replacement for this document.
This file remains the source of truth, while the runtime section acts as the executable summary.

## Repository Guidance

When prompt behavior changes, update both:

1. this document
2. the runtime prompt template that applies the default lead-agent system prompt

Do not create standalone prompt rules in random reports or temporary handoff files.
Prompt policy belongs either here or in the specific runtime prompt code that implements it.

## Next Evolution Boundary

Future prompt-stack work may split this standard into:

1. shared global prompt rules
2. task-mode overlays
3. model-family tuning notes

Until that happens, this file is the default canonical standard.
