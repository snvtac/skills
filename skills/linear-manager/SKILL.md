---
name: linear-manager
description: Manage Linear tickets/comments via direct HTTP GraphQL with `python3 scripts/linear_manager.py` and token env vars only (no Linear MCP). Supports create/read/update tickets and sub-tickets, workflow status changes, cycle/label updates, and comment read/create/thread reply.
---

# Linear Manager

## Overview
Use this skill for Linear operations through `https://api.linear.app/graphql` only.
Execution entrypoint is `python3 scripts/linear_manager.py`.

## Capability Scope
- Read:
`list`, `get`, `states`, `children`, `comments`
- Write:
`create`, `update`, `comment`
- Sub-ticket:
`create --parent <ISSUE_REF>`
- Status management:
`update --state <name>` or `update --state-id <uuid>`
- Cycle/label management:
`update --cycle-id|--cycle-name|--cycle-number`
`update --set-labels|--add-labels|--remove-labels`
`update --set-label-ids|--add-label-ids|--remove-label-ids`

## Hard Constraints
- Always operate via HTTP script: `python3 scripts/linear_manager.py`.
- Never use Linear MCP tools (`mcp__linear__*`) in this skill.
- If token is missing or HTTP fails, return an error with short suggestions only.
- Do not fallback to Linear MCP under any failure mode.

## Token Policy
Default env var is `LINEAR_API_TOKEN`.

Check token:
```bash
echo "$LINEAR_API_TOKEN"
```

If missing, stop and provide suggestions only:
```bash
export LINEAR_API_TOKEN='lin_api_xxx'
```

Use non-default env var:
```bash
python3 scripts/linear_manager.py --token-env <ENV_NAME> ...
```

## Write Safety Policy (Default Dry-Run)
`create`, `update`, `comment` are dry-run by default.
To perform real write, caller must pass `--execute`.

Recommended two-step workflow:
1. Run dry-run first and inspect payload.
2. Run the same command with `--execute` to apply.

Example:
```bash
python3 scripts/linear_manager.py --pretty update --id ENG-123 --state "In Progress"
python3 scripts/linear_manager.py --pretty update --id ENG-123 --state "In Progress" --execute
```

## Command Reference
Run from skill folder:

```bash
python3 scripts/linear_manager.py --pretty list --limit 20
```

```bash
python3 scripts/linear_manager.py --pretty get --id ENG-123 --include-children --comments-limit 20
```

```bash
python3 scripts/linear_manager.py --pretty create \
  --team-key ENG \
  --title "Issue title"
```

```bash
python3 scripts/linear_manager.py --pretty create \
  --team-key ENG \
  --title "Issue title" \
  --description "Issue description" \
  --execute
```

```bash
python3 scripts/linear_manager.py --pretty create \
  --team-key ENG \
  --title "Sub-ticket title" \
  --parent ENG-123 \
  --execute
```

```bash
python3 scripts/linear_manager.py --pretty update \
  --id ENG-123 \
  --cycle-name "Cycle 25" \
  --add-labels "TEST,bug bash"
```

```bash
python3 scripts/linear_manager.py --pretty update \
  --id ENG-123 \
  --cycle-name "Cycle 25" \
  --add-labels "TEST,bug bash" \
  --execute
```

```bash
python3 scripts/linear_manager.py --pretty update \
  --id ENG-123 \
  --description-file /tmp/issue-desc.md \
  --execute
```

```bash
python3 scripts/linear_manager.py --pretty states --team-key ENG
```

```bash
python3 scripts/linear_manager.py --pretty children --id ENG-123 --limit 50
```

```bash
python3 scripts/linear_manager.py --pretty comments --id ENG-123 --limit 20
```

```bash
python3 scripts/linear_manager.py --pretty comment \
  --id ENG-123 \
  --body "Progress update"
```

```bash
python3 scripts/linear_manager.py --pretty comment \
  --id ENG-123 \
  --body "Progress update" \
  --execute
```

```bash
python3 scripts/linear_manager.py --pretty comment \
  --id ENG-123 \
  --parent-comment-id <COMMENT_UUID> \
  --body "Thread reply" \
  --execute
```

## Output And Exit Codes
- Exit code `0`:
success
- Exit code `1`:
validation/API error
- Exit code `2`:
missing token env var

## Operational Notes
- Prefer `--pretty` for readable JSON.
- `--id` and `--parent` accept both UUID and identifier (`TEAM-123`).
- For large markdown, use `--description-file` or `--body-file`.
- Use `--body-stdin` for piping comment content.

## Validation
Ensure no MCP call is introduced in executable script:
```bash
rg -n "mcp__linear__" skills/linear-manager/scripts/linear_manager.py
```
Expected result: no matches (exit code `1`).

## Resources
- Script entrypoint: `scripts/linear_manager.py`
- Test cases: `scripts/linear_manager_test_cases.md`
- GraphQL reference: `references/graphql-operations.md`
