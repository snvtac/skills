---
name: task-summary
description: Analyze unstructured content and create structured Linear tickets (single or parent + sub-tickets). Default team CF. Delegates to linear-manager skill.
---

# Task Summary

## Overview

This skill analyzes unstructured input (meeting notes, ideas, project briefs, conversations, etc.) and produces structured Linear tickets. It delegates all Linear operations to the `linear-manager` skill.

## Default Configuration

- **Team key**: `CF`
- The user can override the team key by specifying a different one in their request.

## Ticket Description Template

Use the following sections as `##` headers in the ticket description. **Only include sections that have meaningful content — omit any section that is empty or not applicable.**

```markdown
## Overview
Brief summary of the ticket (1-3 sentences).

## Context
Background information and motivation for this work.

## Goal
What we want to achieve — the desired outcome.

## Scope
What is in scope and what is out of scope.

## Task
- [ ] Specific actionable task 1
- [ ] Specific actionable task 2

## Technical Implementation
Technical approach, architecture decisions, or implementation details.

## Success Metrics
- How to measure whether this work is successful

## Dependencies
- What this work depends on (other tickets, external services, team availability, etc.)
```

### Formatting Rules

- Use `##` (H2) for section headers — not H1, which conflicts with Linear's title rendering.
- **Task** section uses markdown checklist syntax (`- [ ]`).
- **Dependencies** and **Success Metrics** use bullet lists.
- **Scope** should distinguish "In scope" vs "Out of scope" when both are clear.
- **Overview** should be concise: 1-3 sentences maximum.
- If a section has no relevant content from the user's input, **omit it entirely** — do not include an empty heading.

## Workflow

### Step 1: Analyze Input

1. Read the user's input. This can be freeform text, bullet points, meeting notes, a pasted document, or anything else.
2. Determine the ticket mode:
   - **Single ticket (default)**: Use this unless the user explicitly asks for multiple tickets or the input contains clearly enumerated independent deliverables.
   - **Batch mode (parent + sub-tickets)**: Only use when the user explicitly requests it, or the input already lists distinct, independent deliverables (e.g., numbered items that each represent separate work).

   Batch mode triggers (must meet at least one):
   - User explicitly asks to "break down", "split", or "create multiple tickets"
   - Input contains a clearly enumerated list of independent deliverables (e.g., "1) do X, 2) do Y, 3) do Z" where each is a separate work stream)

   **Do NOT enter batch mode** just because the input is long or complex. A long description of a single initiative is still a single ticket.

3. Extract and map content into the template sections.

### Step 2: Present Draft

Present the structured ticket draft(s) to the user:

**For single ticket:**
- Show the title and full structured description.

**For batch mode:**
- Show the parent ticket title and description.
- Show each sub-ticket title and description.

The user can then:
- Ask for changes → adjust and present again.
- Say "create" / "execute" / confirm → proceed to Step 3.
- Continue the conversation → the draft is available for reference.

Do **not** block or force an explicit confirmation prompt. Present the draft and let the user drive the next action.

### Step 3: Create Tickets

When the user asks to create, delegate to the `linear-manager` skill. This skill does **not** call Linear APIs or scripts directly — it tells `linear-manager` what to do and lets that skill handle execution details, dry-run policy, and error handling.

**Single ticket:**
- Delegate to `linear-manager`: create a ticket with the team key (`CF` or user-specified), title, and description from the draft.

**Batch mode:**
1. Delegate to `linear-manager`: create the parent ticket with the team key, title, and description.
2. Get the parent ticket identifier (e.g., `CF-456`) from the result.
3. For each sub-ticket, delegate to `linear-manager`: create a ticket with the team key, title, description, and parent set to the parent identifier.

### Step 4: Report Results

After creation, report:
- Ticket identifier (e.g., `CF-123`)
- URL for each created ticket

For batch mode, present a summary:
```
Created tickets:
- CF-456: Parent ticket title (parent) — <url>
  - CF-457: Sub-ticket 1 — <url>
  - CF-458: Sub-ticket 2 — <url>
```

## Batch Mode: Parent Ticket Description

The parent ticket gets a high-level description:
- **Overview** summarizing the entire initiative
- **Context** and **Goal** if applicable
- **Scope** covering overall scope
- Other sections as applicable to the overall initiative

Do **not** put a sub-ticket tracking checklist in the parent description. Linear's native parent-child relationship handles the hierarchy — duplicating it in the description creates drift.

Each sub-ticket gets its own focused description scoped to its specific piece of work.

## Title Conventions

- Start with an action verb (e.g., "Implement", "Design", "Set up", "Investigate", "Migrate")
- Keep under 80 characters
- Be specific enough to understand without reading the description
- For parent tickets: use a noun phrase describing the initiative (e.g., "Authentication System Overhaul")
- For sub-tickets: use action verbs scoped to the specific task

## Constraints

### Capability Boundary
- This skill **only** analyzes content and structures tickets. It does **not** interact with Linear directly.
- All Linear operations (create, update, read) are delegated to the `linear-manager` skill. Respect `linear-manager`'s own execution policies (dry-run, token handling, error behavior) — do not bypass or reimplement them.
- Never use Linear MCP tools (`mcp__linear__*`) or call Linear APIs directly.

### Behavior
- Present draft ticket(s) before creating, but do not force an explicit confirmation — let the user drive the next action.
- Never fabricate content. If the user's input is too vague to produce a meaningful ticket, ask clarifying questions.
- When delegating to `linear-manager`, always provide the team key (default `CF`) for every ticket creation — including sub-tickets.

## Batch Mode: Failure Handling

If creating tickets in batch mode and a failure occurs mid-way:
1. **Stop** creating further tickets.
2. **Report** which tickets were successfully created (with identifiers and URLs) and which failed (with the error).
3. Let the user decide whether to retry the failed ticket(s) or proceed as-is.

## Examples

### Example 1: Single Ticket

**User input:**
> We need to add rate limiting to our API gateway. Currently there's no protection against abuse and we've seen some spikes from automated clients.

**Output ticket:**

**Title:** Implement rate limiting for API gateway

**Description:**
```markdown
## Overview
Add rate limiting to the API gateway to protect against abuse from automated clients.

## Context
The API gateway currently has no rate limiting. Recent traffic spikes from automated clients indicate a need for abuse protection.

## Goal
Prevent API abuse by enforcing request rate limits per client.

## Task
- [ ] Research rate limiting strategies (token bucket, sliding window, etc.)
- [ ] Implement rate limiting middleware
- [ ] Configure limits per endpoint/client tier
- [ ] Add monitoring and alerting for rate limit hits
- [ ] Update API documentation with rate limit details

## Success Metrics
- Automated abuse traffic reduced to acceptable levels
- No impact on legitimate user traffic
```

### Example 2: Batch Mode

**User input:**
> We're launching a new onboarding flow. Need to: 1) design the UI mockups, 2) build the backend API for user progress tracking, 3) implement the frontend components, 4) write E2E tests.

**Output:**

**Parent ticket — "New User Onboarding Flow"**

Description contains Overview, Context, Goal, and Scope for the overall initiative. No sub-ticket checklist — Linear's parent-child hierarchy handles tracking.

**Sub-tickets (each as a child of the parent):**
1. "Design UI mockups for onboarding flow"
2. "Build backend API for onboarding progress tracking"
3. "Implement frontend onboarding components"
4. "Write E2E tests for onboarding flow"

Each sub-ticket has its own focused description with applicable template sections. All created with the same team key (`CF`).

### Example 3: Minimal Input

**User input:**
> fix login bug on mobile

**Output ticket draft:**

**Title:** Fix login bug on mobile

**Description:**
```markdown
## Overview
Fix a login bug occurring on mobile platform.

## Task
- [ ] Reproduce the login bug on mobile
- [ ] Identify root cause
- [ ] Implement fix
- [ ] Verify fix on mobile
```

If the input is extremely vague (e.g., just a single ambiguous word), ask one focused clarifying question — but prefer producing a reasonable draft over blocking on questions.
