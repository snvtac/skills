# Skills

A curated collection of agent skills — reusable, self-contained modules that extend AI coding assistants with specialized capabilities and domain knowledge.

## Repository Structure

```
skills/
└── <skill-name>/
    ├── SKILL.md              # Skill definition & instructions
    ├── agents/               # Agent platform configs
    │   └── openai.yaml
    ├── references/           # Domain-specific reference docs
    └── scripts/              # Executable entrypoints & tests
```

## Available Skills

| Skill | Description |
|-------|-------------|
| [linear-manager](skills/linear-manager/SKILL.md) | HTTP-only Linear issue manager — create/read/update tickets, sub-tickets, workflow status, cycles, labels, and comments via direct GraphQL. No Linear MCP dependency. |

## Quick Start

### linear-manager

Manage Linear issues through the GraphQL API with a single Python script.

```bash
# Set your Linear API token
export LINEAR_API_TOKEN="lin_api_..."

# List issues for a team
python3 skills/linear-manager/scripts/linear_manager.py list --team ENG

# Get issue details
python3 skills/linear-manager/scripts/linear_manager.py get ENG-123

# Create an issue (dry-run by default)
python3 skills/linear-manager/scripts/linear_manager.py create --team ENG --title "Fix login bug"

# Execute for real (pass --execute)
python3 skills/linear-manager/scripts/linear_manager.py create --team ENG --title "Fix login bug" --execute
```

Write commands (`create`, `update`, `comment`) are **dry-run by default** — pass `--execute` to apply mutations.

## Skill Anatomy

Each skill follows a standard layout:

- **`SKILL.md`** — The primary instruction file. Defines the skill's name, description, capabilities, constraints, and command reference. AI agents read this to understand how to use the skill.
- **`agents/`** — Platform-specific agent configurations (e.g., `openai.yaml` for OpenAI-compatible agents).
- **`references/`** — Supplementary domain docs (API schemas, GraphQL operations, etc.) that the skill can reference.
- **`scripts/`** — Executable code and test case documentation.

## License

[MIT](LICENSE)
