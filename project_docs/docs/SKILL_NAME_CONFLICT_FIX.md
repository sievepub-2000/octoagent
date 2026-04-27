# Skill Name Conflict Fix

**Date**: 2026-02-10
**Status**: Historical design note. The conflict was identified and analyzed; this document records the intended fix path in English.

## Problem

A name collision could happen when a public skill and a custom skill shared the same skill name while having different content.

That caused three classes of risk:

1. Opening one skill could also open another skill with the same name.
2. Closing one skill could also close another skill with the same name.
3. Both skills could share the same configuration key and pollute each other's state.

## Root Cause

- Skill state used only `skill_name` as the configuration key.
- Same-name skills from different categories could not be distinguished.
- Duplicate detection did not operate at the category level.

## Proposed Fix Strategy

1. Use a composite key in the form `{category}:{name}`.
2. Keep backward compatibility for existing config written with the old key format.
3. Add duplicate detection inside each category during skill loading.
4. Allow API routes to accept an optional `category` query parameter.

## Implementation Areas

### Backend configuration layer

- Add a helper that builds the composite key.
- Update skill-enabled lookups to prefer the composite key.
- Preserve fallback compatibility for old config.

### Backend skill loader

- Detect duplicate names inside each category.
- Raise a clear error with the relevant paths when a duplicate is found.

### Skills API routes

- Add an optional `category` selector.
- Use a shared skill lookup helper.
- Return a clear error if multiple matches exist and no category is given.

### Front-end API and hooks

- Pass `category` when enabling or configuring a skill.
- Use composite React keys for same-name skill rendering.

## Migration Note

The intended migration path is soft migration, not a breaking rewrite:

- old config stays readable
- new writes use the composite key
- same-name conflicts become explicit and diagnosable
