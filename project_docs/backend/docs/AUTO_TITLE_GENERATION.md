# Auto Title Generation

This document explains the title-generation behavior used for OctopusAgent threads.

## Purpose

The title generator creates a concise, human-readable thread title from the early conversation context so that users can identify threads quickly in the UI.

## Design Goals

- generate short, useful titles
- avoid generic filler such as "New Chat"
- stay aligned with the user's actual task
- work safely when the model is unavailable

## Expected Behavior

- Title generation runs after enough conversation context exists.
- The generated title should summarize the user's intent, not the assistant's answer.
- When title generation is unavailable, the system should fall back gracefully.

## Implementation Notes

The title path should remain lightweight and should not block the main conversation flow.
