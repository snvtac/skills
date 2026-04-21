# Linear GraphQL Operations

## Endpoint
- `https://api.linear.app/graphql`

## Auth
- HTTP header: `Authorization: <LINEAR_API_TOKEN>`
- Token source: environment variable (default `LINEAR_API_TOKEN`)

## Transport Policy
- This skill is HTTP-only.
- Do not use Linear MCP tools (`mcp__linear__*`).
- Do not fallback to MCP when token/network/API errors happen.

## Implemented Operations

### 1) List issues
```graphql
query ListIssues($first: Int!) {
  issues(first: $first) {
    nodes {
      id
      identifier
      title
      team {
        id
        key
        name
      }
      state {
        id
        name
        type
      }
      priority
      url
      updatedAt
      createdAt
    }
  }
}
```

### 2) Get issue
```graphql
query GetIssue($id: String!) {
  issue(id: $id) {
    id
    identifier
    title
    description
    state {
      id
      name
      type
    }
    priority
    assignee {
      id
      name
      email
    }
    creator {
      id
      name
      email
    }
    team {
      id
      key
      name
    }
    cycle {
      id
      number
      name
      startsAt
      endsAt
    }
    labels {
      nodes {
        id
        name
        color
      }
    }
    parent {
      id
      identifier
      title
      url
    }
    url
    createdAt
    updatedAt
  }
}
```

### 3) Resolve issue reference (UUID or TEAM-123)
`--id`/`--parent` accepts both UUID and identifier.

If input is UUID:
```graphql
query ResolveIssueById($id: String!) {
  issue(id: $id) {
    id
    identifier
    title
    url
    team {
      id
      key
      name
    }
  }
}
```

If input is TEAM-123:
```graphql
query ResolveIssueByIdentifier($team: String!, $number: Float!) {
  issues(filter: { team: { key: { eq: $team } }, number: { eq: $number } }, first: 1) {
    nodes {
      id
      identifier
      title
      url
      team {
        id
        key
        name
      }
    }
  }
}
```

### 4) Create issue / sub-issue
```graphql
mutation CreateIssue($input: IssueCreateInput!) {
  issueCreate(input: $input) {
    success
    issue {
      id
      identifier
      title
      url
      createdAt
      parent {
        id
        identifier
      }
    }
  }
}
```

Input fields used:
- `teamId` (required)
- `title` (required)
- `parentId` (optional, used for sub-ticket creation)
- `description` (optional)
- `priority` (optional)
- `assigneeId` (optional)

### 5) Update issue (status + fields)
```graphql
mutation UpdateIssue($id: String!, $input: IssueUpdateInput!) {
  issueUpdate(id: $id, input: $input) {
    success
    issue {
      id
      identifier
      title
      url
      updatedAt
      team {
        id
        key
        name
      }
      state {
        id
        name
        type
      }
    }
  }
}
```

Input fields used:
- `title` (optional)
- `description` (optional)
- `priority` (optional)
- `teamId` (optional; used to move an issue to another team)
- `assigneeId` (optional)
- `stateId` (optional; resolved from `--state` by querying team states)
- `cycleId` (optional; direct id or resolved from `--cycle-name`/`--cycle-number`)
- `labelIds` (optional; replace all labels)
- `addedLabelIds` (optional; add labels incrementally)
- `removedLabelIds` (optional; remove labels incrementally)

CLI behavior:
- `update --team-key|--team-id` resolves destination team and sends `teamId`.
- Cross-team moves are rejected when combined with `state`, `cycle`, or label mutation selectors in the same command.

### 6) Delete issue
```graphql
mutation DeleteIssue($id: String!) {
  issueDelete(id: $id) {
    success
    issue: entity {
      id
      identifier
      title
      url
      team {
        id
        key
        name
      }
    }
  }
}
```

CLI behavior:
- `delete` accepts either UUID or `TEAM-123` and resolves the issue before dry-run or execute.
- Real delete requires both `--execute` and `--confirm-delete <RESOLVED_IDENTIFIER>`.
- The confirmation requirement is enforced in the CLI before the GraphQL mutation is sent.
- Linear's payload type is `IssueArchivePayload`; the CLI aliases `entity` to `issue` to keep response shape consistent with other commands.

### 7) List team states
```graphql
query TeamStates($id: String!) {
  team(id: $id) {
    id
    key
    name
    states {
      nodes {
        id
        name
        type
      }
    }
  }
}
```

### 8) List child issues
```graphql
query GetIssueChildren($id: String!, $first: Int!) {
  issue(id: $id) {
    id
    identifier
    children(first: $first) {
      nodes {
        id
        identifier
        title
        url
        state {
          id
          name
          type
        }
        assignee {
          id
          name
        }
      }
    }
  }
}
```

### 9) List comments
```graphql
query GetIssueComments($id: String!, $first: Int!) {
  issue(id: $id) {
    id
    identifier
    comments(first: $first) {
      nodes {
        id
        body
        url
        createdAt
        updatedAt
        user {
          id
          name
          email
        }
      }
    }
  }
}
```

### 10) Create comment
```graphql
mutation CreateComment($input: CommentCreateInput!) {
  commentCreate(input: $input) {
    success
    comment {
      id
      body
      url
      createdAt
      updatedAt
    }
  }
}
```

Input fields used:
- `issueId` (required)
- `body` (required)
- `parentId` (optional, for threaded reply)

## Error Handling Behavior
- Missing token: return a clear error with short optional suggestions.
- API returns `errors`: raise command failure with GraphQL payload.
- HTTP/network failure: return clear CLI error message.
- Not found issues/teams/states: return explicit object-specific error.
- Write operations (`create`, `update`, `delete`, `comment`) support `--dry-run` to inspect payload before mutation.
