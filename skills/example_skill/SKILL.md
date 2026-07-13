# Example Skill

## Purpose
Verify that the skill registry, executor, and tool registry work.

## When to use
Use when the user asks to test skill calling, run a demo skill, or echo a test
message.

## Available tools
- echo

## Workflow
1. Normalize the message.
2. Call the `echo` diagnostic tool.
3. Return the echoed text and simple metadata.

## Rules
- Do not call external APIs.
- Return deterministic structured output.
