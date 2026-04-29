#!/usr/bin/env python3
"""Deploy n8n workflow from JSON definition.

Usage:
    python scripts/deploy_n8n_workflow.py <workflow_json_path>

Environment variables:
    N8N_BASE_URL: Base URL of n8n instance (e.g., https://n8n.draiwing.com)
    N8N_API_KEY: n8n API key
    N8N_WORKFLOW_ID: (optional) Specific workflow ID to update
    VERCEL_API_SECRET: Secret for Vercel API auth (stored in n8n credentials)
    VERCEL_API_URL: Base URL of the Vercel deployment (e.g., https://trading-champs.vercel.app)
"""

import json
import os
import sys
from pathlib import Path

import requests

N8N_BASE_URL = os.environ.get("N8N_BASE_URL", "").rstrip("/")
N8N_API_KEY = os.environ.get("N8N_API_KEY", "")
WORKFLOW_ID_ENV = os.environ.get("N8N_WORKFLOW_ID", "")
VERCEL_API_URL = os.environ.get("VERCEL_API_URL", "")
VERCEL_API_SECRET = os.environ.get("VERCEL_API_SECRET", "")


def get_headers() -> dict:
    return {
        "X-N8N-API-KEY": N8N_API_KEY,
        "Content-Type": "application/json",
    }


def get_api_url(path: str) -> str:
    return f"{N8N_BASE_URL}/api/v1{path}"


def list_workflows() -> list[dict]:
    """List all workflows."""
    response = requests.get(
        get_api_url("/workflows"),
        headers=get_headers(),
        params={"limit": 100},
    )
    response.raise_for_status()
    return response.json().get("data", [])


def get_workflow_by_name(name: str, workflows: list[dict]) -> dict | None:
    """Find workflow by name."""
    return next((w for w in workflows if w["name"] == name), None)


def create_workflow(workflow_data: dict) -> dict:
    """Create a new workflow."""
    # Only send fields that the create API accepts
    # Note: 'active' is returned by GET but causes 400 on POST/PATCH
    allowed_fields = ("name", "description", "nodes", "connections", "settings")
    data = {k: v for k, v in workflow_data.items() if k in allowed_fields}
    # Use data= with pre-serialized JSON to avoid requests library adding extra properties
    response = requests.post(
        get_api_url("/workflows"),
        headers=get_headers(),
        data=json.dumps(data),
    )
    response.raise_for_status()
    return response.json()


def update_workflow(workflow_id: str, workflow_data: dict) -> dict:
    """Update an existing workflow."""
    # Only send fields that the PUT API accepts
    # Note: 'active' and 'description' are returned by GET but cause 400 on PUT
    allowed_fields = ("name", "nodes", "connections", "settings")
    data = {k: v for k, v in workflow_data.items() if k in allowed_fields}
    # Use data= with pre-serialized JSON to avoid requests library adding extra properties
    response = requests.put(
        get_api_url(f"/workflows/{workflow_id}"),
        headers=get_headers(),
        data=json.dumps(data),
    )
    response.raise_for_status()
    return response.json()


def activate_workflow(workflow_id: str) -> None:
    """Activate a workflow."""
    response = requests.post(
        get_api_url(f"/workflows/{workflow_id}/activate"),
        headers=get_headers(),
    )
    response.raise_for_status()


def deactivate_workflow(workflow_id: str) -> None:
    """Deactivate a workflow."""
    response = requests.post(
        get_api_url(f"/workflows/{workflow_id}/deactivate"),
        headers=get_headers(),
    )
    response.raise_for_status()


def deploy_workflow(workflow_json_path: str) -> dict:
    """Deploy (create or update) a workflow from JSON file."""
    # Load workflow definition
    with open(workflow_json_path, "r") as f:
        workflow_data = json.load(f)

    # Substitute placeholders with actual values
    workflow_json = json.dumps(workflow_data)
    if VERCEL_API_URL:
        workflow_json = workflow_json.replace("{{VERCEL_API_URL}}", VERCEL_API_URL)
    if VERCEL_API_SECRET:
        workflow_json = workflow_json.replace("{{VERCEL_API_SECRET}}", VERCEL_API_SECRET)
    workflow_data = json.loads(workflow_json)

    workflow_name = workflow_data.get("name", "")
    if not workflow_name:
        raise ValueError("Workflow JSON must have a 'name' field")

    # Check if workflow exists
    existing = None
    if WORKFLOW_ID_ENV:
        existing = {"id": WORKFLOW_ID_ENV}
    else:
        workflows = list_workflows()
        existing = get_workflow_by_name(workflow_name, workflows)

    if existing:
        print(f"Updating existing workflow: {workflow_name} (ID: {existing['id']})")
        result = update_workflow(existing["id"], workflow_data)
        action = "updated"
    else:
        print(f"Creating new workflow: {workflow_name}")
        result = create_workflow(workflow_data)
        action = "created"

    workflow_id = result["id"]

    # Activate/deactivate based on the 'active' field in JSON
    is_active = workflow_data.get("active", False)
    try:
        if is_active:
            activate_workflow(workflow_id)
            print(f"Activated workflow {workflow_id}")
        else:
            deactivate_workflow(workflow_id)
            print(f"Deactivated workflow {workflow_id}")
    except requests.exceptions.HTTPError as e:
        print(f"Warning: Could not toggle activation state: {e}")

    print(f"Workflow {action} successfully: {workflow_id}")
    return result


def main():
    if len(sys.argv) < 2:
        print("Usage: deploy_n8n_workflow.py <workflow_json_path>")
        sys.exit(1)

    if not N8N_BASE_URL:
        print("Error: N8N_BASE_URL environment variable is required")
        sys.exit(1)

    if not N8N_API_KEY:
        print("Error: N8N_API_KEY environment variable is required")
        sys.exit(1)

    workflow_json_path = sys.argv[1]
    if not Path(workflow_json_path).is_absolute():
        # Resolve relative to project root
        project_root = Path(__file__).parent.parent
        workflow_json_path = str(project_root / workflow_json_path)

    try:
        result = deploy_workflow(workflow_json_path)
        print(f"\nDeployed workflow ID: {result['id']}")
        print(f"Name: {result['name']}")
        print(f"Active: {result.get('active', False)}")
    except requests.exceptions.HTTPError as e:
        print(f"HTTP Error: {e}")
        print(f"Response: {e.response.text}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
