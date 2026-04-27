---
name: awesome-design-md
description: Default design-governance skill for UI, frontend, landing page, dashboard, component, HTML/CSS, React, Vue, and design-system work. Use when the task involves visual design, UX polish, interface review, or converting product intent into a high-quality screen.
license: MIT
---

# Awesome Design MD

This is OctoAgent's default design-governance skill for interface work.

## Use This Skill When

- Building or redesigning a page, component, dashboard, form, or application surface
- Polishing frontend code that works but looks generic or inconsistent
- Reviewing UI quality, accessibility, hierarchy, or interaction clarity
- Translating vague product intent into a concrete visual direction

## Core Design Standard

1. Pick a visual direction before editing code.
2. Avoid generic AI aesthetics and overused defaults.
3. Use typography, spacing, color, and motion as one coherent system.
4. Keep accessibility, responsiveness, and implementation realism intact.
5. Preserve an existing design system when one already exists.

## Execution Workflow

### 1. Define Direction

State briefly:
- interface type
- audience
- primary action
- visual tone
- constraints from the existing product or stack

### 2. Establish the System

Before large edits, decide:
- typography pair or typographic hierarchy
- core palette and contrast model
- spacing rhythm
- radius and shadow style
- motion principles

### 3. Implement the Smallest Complete Slice

- Prefer one coherent screen or one finished component over scattered partial polish.
- Reuse existing primitives where possible.
- Add tokens or variables instead of repeating raw values.

### 4. Review Against the Standard

Check for:
- clear hierarchy
- consistent spacing
- obvious interaction states
- responsive safety
- accessible contrast and focus handling
- absence of generic boilerplate patterns

## Review Mode

If the user asks for a design review, prioritize findings in this order:
- visual hierarchy issues
- inconsistent tokens or spacing
- accessibility regressions
- weak interaction feedback
- mobile/responsive breakage
- design drift from the existing product language

## Anti-Patterns

- default font stacks with no intent
- purple-gradient hero sections unless explicitly requested
- ornamental motion with no UX value
- adding new components where existing ones can be refined
- redesigning the whole product when only one surface needs work