#!/usr/bin/env python3
"""Linear issue helper via Linear GraphQL API."""

import argparse
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple
from urllib import error, request

LINEAR_GRAPHQL_URL = "https://api.linear.app/graphql"
DEFAULT_TOKEN_ENV = "LINEAR_API_TOKEN"

ISSUE_IDENTIFIER_RE = re.compile(r"^(?P<team>[A-Za-z][A-Za-z0-9]+)-(?P<number>\d+)$")
UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

PRIORITY_MAP = {
    "none": 0,
    "urgent": 1,
    "high": 2,
    "medium": 3,
    "low": 4,
}


class LinearAPIError(Exception):
    """Raised when the Linear API returns an error response."""


def print_missing_token_guidance(token_env: str) -> None:
    message = f"""
Missing environment variable: {token_env}

Suggested next steps (you decide):
- Set token for current shell:
  export {token_env}='lin_api_xxx'
- Or set another env var and pass:
  --token-env <ENV_NAME>
- Or stop here and configure token later.
""".strip()
    print(message, file=sys.stderr)


def post_graphql(token: str, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    req = request.Request(
        LINEAR_GRAPHQL_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": token,
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=30) as response:
            body = response.read().decode("utf-8")
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        raise LinearAPIError(f"HTTP {exc.code}: {body}") from exc
    except error.URLError as exc:
        raise LinearAPIError(f"Network error: {exc}") from exc

    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise LinearAPIError(f"Invalid JSON response: {body}") from exc

    errors_payload = data.get("errors")
    if errors_payload:
        raise LinearAPIError(json.dumps(errors_payload, ensure_ascii=False))

    return data.get("data", {})


def normalize_priority(raw: str) -> int:
    value = raw.strip().lower()
    if not value:
        raise LinearAPIError("Priority must not be empty.")
    if value.isdigit():
        parsed = int(value)
        if parsed < 0 or parsed > 4:
            raise LinearAPIError("Priority number must be in 0..4.")
        return parsed
    if value not in PRIORITY_MAP:
        raise LinearAPIError("Priority must be one of: none, urgent, high, medium, low, or 0..4.")
    return PRIORITY_MAP[value]


def parse_csv_values(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def dedupe_preserve_order(values: List[str]) -> List[str]:
    seen = set()
    output: List[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def parse_issue_identifier(issue_identifier: str) -> Tuple[str, int]:
    match = ISSUE_IDENTIFIER_RE.match(issue_identifier.strip())
    if not match:
        raise LinearAPIError(
            f"Invalid issue identifier: {issue_identifier}. Expected format like TEAM-123."
        )
    return match.group("team").upper(), int(match.group("number"))


def issue_summary(issue: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": issue.get("id"),
        "identifier": issue.get("identifier"),
        "title": issue.get("title"),
        "url": issue.get("url"),
        "team": issue.get("team"),
    }


def resolve_issue_ref(token: str, issue_id_or_identifier: str) -> Dict[str, Any]:
    issue_ref = issue_id_or_identifier.strip()
    if not issue_ref:
        raise LinearAPIError("Issue id/identifier must not be empty.")

    if UUID_RE.match(issue_ref):
        query = """
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
        """
        data = post_graphql(token, query, {"id": issue_ref})
        issue = data.get("issue")
        if not issue:
            raise LinearAPIError(f"Issue not found: {issue_ref}")
        return issue

    team_key, number = parse_issue_identifier(issue_ref)
    query = """
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
    """
    data = post_graphql(token, query, {"team": team_key, "number": float(number)})
    nodes = ((data.get("issues") or {}).get("nodes")) or []
    if not nodes:
        raise LinearAPIError(f"Issue not found: {team_key}-{number}")
    return nodes[0]


def resolve_team_ref(token: str, team_id: Optional[str], team_key: Optional[str]) -> Dict[str, Any]:
    if team_id:
        query = """
        query ResolveTeamById($id: String!) {
          team(id: $id) {
            id
            key
            name
          }
        }
        """
        data = post_graphql(token, query, {"id": team_id.strip()})
        team = data.get("team")
        if not team:
            raise LinearAPIError(f"Team not found by id: {team_id}")
        return team

    if not team_key:
        raise LinearAPIError("Either --team-id or --team-key is required.")

    query = """
    query ResolveTeamByKey($key: String!) {
      teams(filter: { key: { eq: $key } }, first: 1) {
        nodes {
          id
          key
          name
        }
      }
    }
    """
    data = post_graphql(token, query, {"key": team_key.strip().upper()})
    nodes = ((data.get("teams") or {}).get("nodes")) or []
    if not nodes:
        raise LinearAPIError(f"Team not found by key: {team_key}")
    return nodes[0]


def resolve_team_id(token: str, team_id: Optional[str], team_key: Optional[str]) -> str:
    return str(resolve_team_ref(token, team_id, team_key)["id"]).strip()


def get_issue_team_id(token: str, issue_id: str) -> str:
    query = """
    query GetIssueTeam($id: String!) {
      issue(id: $id) {
        id
        team {
          id
          key
          name
        }
      }
    }
    """
    data = post_graphql(token, query, {"id": issue_id})
    issue = data.get("issue")
    if not issue:
        raise LinearAPIError(f"Issue not found: {issue_id}")
    team = issue.get("team") or {}
    team_id = (team.get("id") or "").strip()
    if not team_id:
        raise LinearAPIError(f"Team id not found for issue: {issue_id}")
    return team_id


def list_team_states(token: str, team_id: str) -> List[Dict[str, Any]]:
    query = """
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
    """
    data = post_graphql(token, query, {"id": team_id})
    team = data.get("team")
    if not team:
        raise LinearAPIError(f"Team not found: {team_id}")
    return ((team.get("states") or {}).get("nodes")) or []


def resolve_state_id(token: str, issue_id: str, state_name: str) -> str:
    team_id = get_issue_team_id(token, issue_id)
    states = list_team_states(token, team_id)
    wanted = state_name.strip().lower()
    for state in states:
        state_label = str(state.get("name") or "").strip()
        if state_label.lower() == wanted:
            state_id = (state.get("id") or "").strip()
            if state_id:
                return state_id

    available = ", ".join(
        str(state.get("name") or "").strip() for state in states if state.get("name")
    )
    raise LinearAPIError(f"State not found: {state_name}. Available states: {available}")


def list_team_cycles(token: str, team_id: str) -> List[Dict[str, Any]]:
    query = """
    query TeamCycles($teamId: ID!, $first: Int!) {
      cycles(filter: { team: { id: { eq: $teamId } } }, first: $first) {
        nodes {
          id
          number
          name
          startsAt
          endsAt
        }
      }
    }
    """
    data = post_graphql(token, query, {"teamId": team_id, "first": 100})
    return ((data.get("cycles") or {}).get("nodes")) or []


def resolve_cycle_id(
    token: str,
    team_id: str,
    cycle_id: Optional[str],
    cycle_name: Optional[str],
    cycle_number: Optional[int],
) -> Optional[str]:
    if cycle_id:
        return cycle_id.strip()
    if cycle_name is None and cycle_number is None:
        return None

    cycles = list_team_cycles(token, team_id)
    if cycle_name is not None:
        wanted = cycle_name.strip().lower()
        for cycle in cycles:
            name = str(cycle.get("name") or "").strip()
            if name.lower() == wanted:
                return str(cycle.get("id") or "").strip()
        available = ", ".join(str(c.get("name") or "").strip() for c in cycles if c.get("name"))
        raise LinearAPIError(f"Cycle not found by name: {cycle_name}. Available cycles: {available}")

    for cycle in cycles:
        if int(cycle.get("number") or -1) == int(cycle_number):
            return str(cycle.get("id") or "").strip()
    available_numbers = ", ".join(str(c.get("number")) for c in cycles if c.get("number") is not None)
    raise LinearAPIError(
        f"Cycle not found by number: {cycle_number}. Available cycle numbers: {available_numbers}"
    )


def list_team_labels(token: str, team_id: str) -> List[Dict[str, Any]]:
    query = """
    query TeamIssueLabels($teamId: ID!, $first: Int!) {
      issueLabels(filter: { team: { id: { eq: $teamId } } }, first: $first) {
        nodes {
          id
          name
          color
        }
      }
    }
    """
    data = post_graphql(token, query, {"teamId": team_id, "first": 250})
    return ((data.get("issueLabels") or {}).get("nodes")) or []


def resolve_label_ids_by_names(token: str, team_id: str, names: List[str]) -> List[str]:
    if not names:
        return []
    labels = list_team_labels(token, team_id)
    label_by_name: Dict[str, str] = {}
    for label in labels:
        name = str(label.get("name") or "").strip()
        if not name:
            continue
        label_by_name[name.lower()] = str(label.get("id") or "").strip()

    missing: List[str] = []
    resolved_ids: List[str] = []
    for name in names:
        key = name.strip().lower()
        label_id = label_by_name.get(key)
        if not label_id:
            missing.append(name)
            continue
        resolved_ids.append(label_id)

    if missing:
        available = ", ".join(sorted(label_by_name.keys()))
        raise LinearAPIError(
            f"Label(s) not found: {', '.join(missing)}. Available labels: {available}"
        )
    return dedupe_preserve_order(resolved_ids)


def get_viewer_id(token: str) -> str:
    data = post_graphql(token, "query ViewerId { viewer { id } }")
    viewer = data.get("viewer") or {}
    viewer_id = (viewer.get("id") or "").strip()
    if not viewer_id:
        raise LinearAPIError("Cannot resolve viewer id.")
    return viewer_id


def load_text_from_args(value: Optional[str], value_file: Optional[str], use_stdin: bool, kind: str) -> str:
    if value_file:
        try:
            with open(value_file, "r", encoding="utf-8") as handle:
                return handle.read()
        except OSError as exc:
            raise LinearAPIError(f"Failed reading {kind} file '{value_file}': {exc}") from exc
    if value is not None:
        return value
    if use_stdin:
        return sys.stdin.read()
    raise LinearAPIError(f"Missing {kind}. Use --{kind}, --{kind}-file, or --{kind}-stdin.")


def has_team_scoped_update_args(args: argparse.Namespace) -> bool:
    return any(
        (
            args.state is not None,
            args.state_id is not None,
            args.cycle_id is not None,
            args.cycle_name is not None,
            args.cycle_number is not None,
            args.set_label_ids is not None,
            args.set_labels is not None,
            args.add_label_ids is not None,
            args.add_labels is not None,
            args.remove_label_ids is not None,
            args.remove_labels is not None,
        )
    )


def cmd_list_issues(token: str, args: argparse.Namespace) -> Dict[str, Any]:
    if args.limit < 1:
        raise LinearAPIError("--limit must be >= 1")

    if args.team_key:
        team_id = resolve_team_id(token, None, args.team_key)
        query = """
        query ListIssuesByTeam($first: Int!, $teamId: ID!) {
          issues(first: $first, filter: { team: { id: { eq: $teamId } } }) {
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
        """
        return post_graphql(token, query, {"first": args.limit, "teamId": team_id})

    query = """
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
    """
    return post_graphql(token, query, {"first": args.limit})


def fetch_issue_children(token: str, issue_id: str, limit: int) -> Dict[str, Any]:
    query = """
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
    """
    return post_graphql(token, query, {"id": issue_id, "first": limit})


def fetch_issue_comments(token: str, issue_id: str, limit: int) -> Dict[str, Any]:
    query = """
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
    """
    return post_graphql(token, query, {"id": issue_id, "first": limit})


def cmd_get_issue(token: str, args: argparse.Namespace) -> Dict[str, Any]:
    issue_ref = resolve_issue_ref(token, args.id)
    query = """
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
    """
    data = post_graphql(token, query, {"id": issue_ref["id"]})
    issue = data.get("issue")
    if not issue:
        raise LinearAPIError(f"Issue not found: {args.id}")

    if args.include_children:
        children = fetch_issue_children(token, issue_ref["id"], args.children_limit)
        issue["children"] = ((children.get("issue") or {}).get("children")) or {"nodes": []}

    if args.comments_limit > 0:
        comments = fetch_issue_comments(token, issue_ref["id"], args.comments_limit)
        issue["comments"] = ((comments.get("issue") or {}).get("comments")) or {"nodes": []}

    return {"issue": issue}


def cmd_create_issue(token: str, args: argparse.Namespace) -> Dict[str, Any]:
    team_id = resolve_team_id(token, args.team_id, args.team_key)
    description = None
    if args.description_file:
        description = load_text_from_args(None, args.description_file, False, "description")
    elif args.description is not None:
        description = args.description

    issue_input: Dict[str, Any] = {
        "teamId": team_id,
        "title": args.title,
    }
    if description is not None:
        issue_input["description"] = description
    if args.priority is not None:
        issue_input["priority"] = normalize_priority(args.priority)
    if args.assignee_id:
        issue_input["assigneeId"] = args.assignee_id
    if args.parent:
        parent = resolve_issue_ref(token, args.parent)
        issue_input["parentId"] = parent["id"]

    should_execute = bool(getattr(args, "execute", False))
    if not should_execute:
        return {"dryRun": True, "execute": False, "input": issue_input}

    query = """
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
    """
    data = post_graphql(token, query, {"input": issue_input})
    result = data.get("issueCreate") or {}
    if not result.get("success"):
        raise LinearAPIError(f"issueCreate failed: {json.dumps(result, ensure_ascii=False)}")
    return data


def cmd_update_issue(token: str, args: argparse.Namespace) -> Dict[str, Any]:
    issue = resolve_issue_ref(token, args.id)
    issue_input: Dict[str, Any] = {}
    issue_team_id: Optional[str] = None
    current_team = issue.get("team") or {}
    current_team_id = str(current_team.get("id") or "").strip()
    target_team: Optional[Dict[str, Any]] = None
    target_team_id = ""

    if args.team_id or args.team_key:
        target_team = resolve_team_ref(token, args.team_id, args.team_key)
        target_team_id = str(target_team.get("id") or "").strip()
        if not target_team_id:
            raise LinearAPIError("Resolved target team is missing an id.")
        if current_team_id and target_team_id != current_team_id and has_team_scoped_update_args(args):
            raise LinearAPIError(
                "Cannot combine a team move with state, cycle, or label updates. "
                "Move the ticket first, then update destination-team state/cycle/labels in a separate command."
            )
        if target_team_id != current_team_id:
            issue_input["teamId"] = target_team_id

    if args.title is not None:
        issue_input["title"] = args.title

    if args.description_file:
        issue_input["description"] = load_text_from_args(
            None, args.description_file, False, "description"
        )
    elif args.description is not None:
        issue_input["description"] = args.description

    if args.priority is not None:
        issue_input["priority"] = normalize_priority(args.priority)

    if args.state_id:
        issue_input["stateId"] = args.state_id
    elif args.state:
        issue_input["stateId"] = resolve_state_id(token, issue["id"], args.state)

    if args.cycle_id and (args.cycle_name is not None or args.cycle_number is not None):
        raise LinearAPIError("Use only one cycle selector: --cycle-id OR --cycle-name OR --cycle-number.")
    if args.cycle_name is not None and args.cycle_number is not None:
        raise LinearAPIError("Use only one cycle selector: --cycle-name OR --cycle-number.")

    if args.cycle_id or args.cycle_name is not None or args.cycle_number is not None:
        issue_team_id = issue_team_id or get_issue_team_id(token, issue["id"])
        cycle_id = resolve_cycle_id(
            token,
            issue_team_id,
            args.cycle_id,
            args.cycle_name,
            args.cycle_number,
        )
        if cycle_id:
            issue_input["cycleId"] = cycle_id

    set_label_ids = dedupe_preserve_order(parse_csv_values(args.set_label_ids))
    add_label_ids = dedupe_preserve_order(parse_csv_values(args.add_label_ids))
    remove_label_ids = dedupe_preserve_order(parse_csv_values(args.remove_label_ids))
    set_label_names = parse_csv_values(args.set_labels)
    add_label_names = parse_csv_values(args.add_labels)
    remove_label_names = parse_csv_values(args.remove_labels)

    if (set_label_ids or set_label_names) and (
        add_label_ids or remove_label_ids or add_label_names or remove_label_names
    ):
        raise LinearAPIError(
            "Do not mix set-labels with add/remove labels. Use either set OR add/remove."
        )

    if set_label_names or add_label_names or remove_label_names:
        issue_team_id = issue_team_id or get_issue_team_id(token, issue["id"])

    if set_label_names:
        set_label_ids.extend(resolve_label_ids_by_names(token, issue_team_id or "", set_label_names))
    if add_label_names:
        add_label_ids.extend(resolve_label_ids_by_names(token, issue_team_id or "", add_label_names))
    if remove_label_names:
        remove_label_ids.extend(
            resolve_label_ids_by_names(token, issue_team_id or "", remove_label_names)
        )

    set_label_ids = dedupe_preserve_order(set_label_ids)
    add_label_ids = dedupe_preserve_order(add_label_ids)
    remove_label_ids = dedupe_preserve_order(remove_label_ids)

    if set_label_ids:
        issue_input["labelIds"] = set_label_ids
    else:
        if add_label_ids:
            issue_input["addedLabelIds"] = add_label_ids
        if remove_label_ids:
            issue_input["removedLabelIds"] = remove_label_ids

    if args.assignee_viewer:
        issue_input["assigneeId"] = get_viewer_id(token)
    elif args.assignee_id:
        issue_input["assigneeId"] = args.assignee_id

    if not issue_input:
        raise LinearAPIError(
            "No update fields provided. Use at least one of --title, --description, --description-file, --priority, --state, --state-id, --cycle-id, --cycle-name, --cycle-number, --set-label-ids, --set-labels, --add-label-ids, --add-labels, --remove-label-ids, --remove-labels, --assignee-id, --assignee-viewer."
        )

    should_execute = bool(getattr(args, "execute", False))
    if not should_execute:
        result: Dict[str, Any] = {
            "dryRun": True,
            "execute": False,
            "issue": issue_summary(issue),
            "input": issue_input,
        }
        if target_team:
            result["targetTeam"] = target_team
        return result

    query = """
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
    """
    data = post_graphql(token, query, {"id": issue["id"], "input": issue_input})
    result = data.get("issueUpdate") or {}
    if not result.get("success"):
        raise LinearAPIError(f"issueUpdate failed: {json.dumps(result, ensure_ascii=False)}")
    return data


def cmd_delete_issue(token: str, args: argparse.Namespace) -> Dict[str, Any]:
    issue = resolve_issue_ref(token, args.id)
    expected_confirmation = str(issue.get("identifier") or "").strip()
    if not expected_confirmation:
        raise LinearAPIError("Resolved issue is missing an identifier required for delete confirmation.")

    should_execute = bool(getattr(args, "execute", False))
    if not should_execute:
        return {
            "dryRun": True,
            "execute": False,
            "issue": issue_summary(issue),
            "expectedConfirmation": expected_confirmation,
        }

    provided_confirmation = (args.confirm_delete or "").strip()
    if not provided_confirmation:
        raise LinearAPIError(
            "Delete requires explicit user-confirmed consent. Re-run with "
            f"--confirm-delete {expected_confirmation} and --execute."
        )
    if provided_confirmation != expected_confirmation:
        raise LinearAPIError(
            f"Delete confirmation mismatch. Expected --confirm-delete {expected_confirmation}."
        )

    query = """
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
    """
    data = post_graphql(token, query, {"id": issue["id"]})
    result = data.get("issueDelete") or {}
    if not result.get("success"):
        raise LinearAPIError(f"issueDelete failed: {json.dumps(result, ensure_ascii=False)}")
    return data


def cmd_list_states(token: str, args: argparse.Namespace) -> Dict[str, Any]:
    team_id = resolve_team_id(token, args.team_id, args.team_key)
    query = """
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
    """
    return post_graphql(token, query, {"id": team_id})


def cmd_list_children(token: str, args: argparse.Namespace) -> Dict[str, Any]:
    if args.limit < 1:
        raise LinearAPIError("--limit must be >= 1")
    issue_ref = resolve_issue_ref(token, args.id)
    return fetch_issue_children(token, issue_ref["id"], args.limit)


def cmd_list_comments(token: str, args: argparse.Namespace) -> Dict[str, Any]:
    if args.limit < 1:
        raise LinearAPIError("--limit must be >= 1")
    issue_ref = resolve_issue_ref(token, args.id)
    return fetch_issue_comments(token, issue_ref["id"], args.limit)


def cmd_create_comment(token: str, args: argparse.Namespace) -> Dict[str, Any]:
    issue_ref = resolve_issue_ref(token, args.id)
    body = load_text_from_args(args.body, args.body_file, args.body_stdin, "body")
    comment_input: Dict[str, Any] = {"issueId": issue_ref["id"], "body": body}
    if args.parent_comment_id:
        comment_input["parentId"] = args.parent_comment_id

    should_execute = bool(getattr(args, "execute", False))
    if not should_execute:
        return {
            "dryRun": True,
            "execute": False,
            "issue": {
                "id": issue_ref["id"],
                "identifier": issue_ref.get("identifier"),
                "title": issue_ref.get("title"),
                "url": issue_ref.get("url"),
            },
            "bodyLength": len(body),
            "parentCommentId": args.parent_comment_id,
        }

    query = """
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
    """
    data = post_graphql(token, query, {"input": comment_input})
    result = data.get("commentCreate") or {}
    if not result.get("success"):
        raise LinearAPIError(f"commentCreate failed: {json.dumps(result, ensure_ascii=False)}")
    return data


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read/create/update/delete/comment Linear issues via Linear GraphQL API.",
    )
    parser.add_argument(
        "--token-env",
        default=DEFAULT_TOKEN_ENV,
        help=f"Environment variable for token (default: {DEFAULT_TOKEN_ENV})",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List latest issues.")
    list_parser.add_argument("--limit", type=int, default=20, help="Number of issues to fetch.")
    list_parser.add_argument("--team-key", help="Optional team key filter (e.g. ENG).")

    get_parser = subparsers.add_parser("get", help="Get issue details by UUID or identifier.")
    get_parser.add_argument("--id", required=True, help="Issue UUID or identifier (e.g. ABC-123).")
    get_parser.add_argument(
        "--include-children",
        action="store_true",
        help="Include child issues in output.",
    )
    get_parser.add_argument(
        "--children-limit",
        type=int,
        default=50,
        help="Max children when --include-children is enabled.",
    )
    get_parser.add_argument(
        "--comments-limit",
        type=int,
        default=0,
        help="Include latest N comments when > 0.",
    )

    create_parser = subparsers.add_parser("create", help="Create a new issue or sub-issue.")
    team_group = create_parser.add_mutually_exclusive_group(required=True)
    team_group.add_argument("--team-id", help="Linear team id (UUID).")
    team_group.add_argument("--team-key", help="Linear team key (e.g. ENG).")
    create_parser.add_argument("--title", required=True, help="Issue title.")
    create_parser.add_argument("--description", help="Issue description in markdown.")
    create_parser.add_argument("--description-file", help="Path to description markdown file.")
    create_parser.add_argument(
        "--priority",
        help="Issue priority: none, urgent, high, medium, low, or 0..4.",
    )
    create_parser.add_argument("--assignee-id", help="Assignee user id (UUID).")
    create_parser.add_argument(
        "--parent",
        help="Parent issue UUID or identifier (e.g. ENG-123) to create a sub-issue.",
    )
    create_mode = create_parser.add_mutually_exclusive_group()
    create_mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview payload only (default behavior).",
    )
    create_mode.add_argument(
        "--execute",
        action="store_true",
        help="Apply write to Linear. Without this flag, create runs in dry-run mode.",
    )

    update_parser = subparsers.add_parser("update", help="Update issue fields and workflow state.")
    update_parser.add_argument("--id", required=True, help="Issue UUID or identifier.")
    update_team_group = update_parser.add_mutually_exclusive_group()
    update_team_group.add_argument("--team-id", help="Destination team id (UUID).")
    update_team_group.add_argument("--team-key", help="Destination team key (e.g. ENG).")
    update_parser.add_argument("--title", help="New issue title.")
    update_parser.add_argument("--description", help="New issue description in markdown.")
    update_parser.add_argument("--description-file", help="Path to description markdown file.")
    update_parser.add_argument(
        "--priority",
        help="Issue priority: none, urgent, high, medium, low, or 0..4.",
    )
    update_parser.add_argument("--state", help="Workflow state name (case-insensitive).")
    update_parser.add_argument("--state-id", help="Workflow state id (UUID).")
    update_parser.add_argument("--cycle-id", help="Cycle id (UUID).")
    update_parser.add_argument("--cycle-name", help="Cycle name (case-insensitive exact match).")
    update_parser.add_argument("--cycle-number", type=int, help="Cycle number (e.g. 63).")
    update_parser.add_argument(
        "--set-label-ids",
        help="Replace labels with comma-separated label IDs.",
    )
    update_parser.add_argument(
        "--set-labels",
        help="Replace labels with comma-separated label names.",
    )
    update_parser.add_argument(
        "--add-label-ids",
        help="Add comma-separated label IDs.",
    )
    update_parser.add_argument(
        "--add-labels",
        help="Add comma-separated label names.",
    )
    update_parser.add_argument(
        "--remove-label-ids",
        help="Remove comma-separated label IDs.",
    )
    update_parser.add_argument(
        "--remove-labels",
        help="Remove comma-separated label names.",
    )
    update_parser.add_argument("--assignee-id", help="Assignee user id (UUID).")
    update_parser.add_argument(
        "--assignee-viewer",
        action="store_true",
        help="Assign issue to the current API viewer.",
    )
    update_mode = update_parser.add_mutually_exclusive_group()
    update_mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview payload only (default behavior).",
    )
    update_mode.add_argument(
        "--execute",
        action="store_true",
        help="Apply write to Linear. Without this flag, update runs in dry-run mode.",
    )

    delete_parser = subparsers.add_parser("delete", help="Delete an issue with explicit confirmation.")
    delete_parser.add_argument("--id", required=True, help="Issue UUID or identifier.")
    delete_parser.add_argument(
        "--confirm-delete",
        help="Required with --execute. Must exactly match the resolved issue identifier.",
    )
    delete_mode = delete_parser.add_mutually_exclusive_group()
    delete_mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview target issue and required confirmation only (default behavior).",
    )
    delete_mode.add_argument(
        "--execute",
        action="store_true",
        help="Apply delete to Linear. Requires --confirm-delete <IDENTIFIER>.",
    )

    states_parser = subparsers.add_parser("states", help="List workflow states for a team.")
    states_group = states_parser.add_mutually_exclusive_group(required=True)
    states_group.add_argument("--team-id", help="Linear team id (UUID).")
    states_group.add_argument("--team-key", help="Linear team key (e.g. ENG).")

    children_parser = subparsers.add_parser("children", help="List child issues of an issue.")
    children_parser.add_argument("--id", required=True, help="Issue UUID or identifier.")
    children_parser.add_argument("--limit", type=int, default=50, help="Number of child issues to fetch.")

    comments_parser = subparsers.add_parser("comments", help="List comments for an issue.")
    comments_parser.add_argument("--id", required=True, help="Issue UUID or identifier.")
    comments_parser.add_argument("--limit", type=int, default=20, help="Number of comments to fetch.")

    comment_parser = subparsers.add_parser("comment", help="Create a comment on an issue.")
    comment_parser.add_argument(
        "--id",
        "--issue-id",
        dest="id",
        required=True,
        help="Issue UUID or identifier.",
    )
    comment_parser.add_argument("--body", help="Comment body in markdown.")
    comment_parser.add_argument("--body-file", help="Path to markdown file for comment body.")
    comment_parser.add_argument(
        "--parent-comment-id",
        help="Parent comment id for threaded reply.",
    )
    comment_parser.add_argument(
        "--body-stdin",
        action="store_true",
        help="Read comment body from stdin.",
    )
    comment_mode = comment_parser.add_mutually_exclusive_group()
    comment_mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview payload only (default behavior).",
    )
    comment_mode.add_argument(
        "--execute",
        action="store_true",
        help="Apply write to Linear. Without this flag, comment runs in dry-run mode.",
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    token = os.getenv(args.token_env, "").strip()
    if not token:
        print_missing_token_guidance(args.token_env)
        return 2

    try:
        if args.command == "list":
            result = cmd_list_issues(token, args)
        elif args.command == "get":
            result = cmd_get_issue(token, args)
        elif args.command == "create":
            result = cmd_create_issue(token, args)
        elif args.command == "update":
            result = cmd_update_issue(token, args)
        elif args.command == "delete":
            result = cmd_delete_issue(token, args)
        elif args.command == "states":
            result = cmd_list_states(token, args)
        elif args.command == "children":
            result = cmd_list_children(token, args)
        elif args.command == "comments":
            result = cmd_list_comments(token, args)
        elif args.command == "comment":
            result = cmd_create_comment(token, args)
        else:
            parser.error(f"Unknown command: {args.command}")
            return 1
    except LinearAPIError as exc:
        print(f"Linear API error: {exc}", file=sys.stderr)
        return 1

    if args.pretty:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
