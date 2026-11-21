"""
integrations.py — External execution dispatcher.

Supports:
  1. GitHub Issues REST API  (GITHUB_TOKEN + GITHUB_REPO env vars)
  2. Generic Slack/Discord Webhook  (WEBHOOK_URL env var)
  3. Local receipt logger fallback (when no credentials are configured)

All dispatchers return a structured ExecutionReceipt dict that is stored
in execution_tasks.external_execution_receipt_json.
"""
from __future__ import annotations

import datetime
import json
import os
import logging
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
GITHUB_TOKEN: str = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO: str = os.getenv("GITHUB_REPO", "")  # "owner/repo"
WEBHOOK_URL: str = os.getenv("WEBHOOK_URL", "")

GITHUB_API_BASE = "https://api.github.com"
REQUEST_TIMEOUT = 10  # seconds


# ── Receipt builder ───────────────────────────────────────────────────────────
def _make_receipt(
    channel: str,
    success: bool,
    external_id: Optional[str] = None,
    external_url: Optional[str] = None,
    payload: Optional[dict] = None,
    error: Optional[str] = None,
) -> dict:
    return {
        "channel": channel,
        "success": success,
        "external_id": external_id,
        "external_url": external_url,
        "payload_sent": payload,
        "error": error,
        "dispatched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


# ── GitHub Issues ─────────────────────────────────────────────────────────────
async def _dispatch_github_issue(task: dict) -> dict:
    """Create a GitHub Issue for an approved action item."""
    owner_repo = GITHUB_REPO.strip()
    if not owner_repo or "/" not in owner_repo:
        return _make_receipt(
            "github",
            False,
            error="GITHUB_REPO not configured or invalid (expected 'owner/repo')",
        )

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    deadline_line = (
        f"\n\n**Deadline:** {task.get('deadline_iso', 'TBD')}"
        if task.get("deadline_iso")
        else ""
    )
    assignee_line = (
        f"\n**Owner:** {task.get('owner', 'Unassigned')}"
        if task.get("owner")
        else ""
    )
    quote_line = (
        f"\n\n> *Meeting Quote:* \"{task.get('verbatim_quote', '')}\"" 
        if task.get("verbatim_quote")
        else ""
    )

    body = (
        f"{task.get('description', '')}"
        f"{deadline_line}"
        f"{assignee_line}"
        f"{quote_line}"
        f"\n\n---\n*Auto-created by Meeting-to-Execution Agent*"
    )

    payload = {
        "title": f"[Meeting Action] {task.get('title', 'Untitled')}",
        "body": body,
        "labels": ["meeting-action", f"priority:{task.get('priority', 'medium').lower()}"],
    }

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.post(
                f"{GITHUB_API_BASE}/repos/{owner_repo}/issues",
                headers=headers,
                json=payload,
            )
            if resp.status_code == 201:
                data = resp.json()
                return _make_receipt(
                    "github",
                    True,
                    external_id=str(data.get("number")),
                    external_url=data.get("html_url"),
                    payload=payload,
                )
            else:
                return _make_receipt(
                    "github",
                    False,
                    payload=payload,
                    error=f"GitHub API returned {resp.status_code}: {resp.text[:300]}",
                )
    except Exception as exc:
        logger.error("GitHub dispatch error: %s", exc)
        return _make_receipt("github", False, payload=payload, error=str(exc))


# ── Generic Webhook (Slack / Discord / Custom) ────────────────────────────────
async def _dispatch_webhook(task: dict) -> dict:
    """POST a notification to the configured generic webhook URL."""
    url = WEBHOOK_URL.strip()
    if not url:
        return _make_receipt(
            "webhook", False, error="WEBHOOK_URL not configured"
        )

    # Slack-compatible block payload (also works for Discord with attachments)
    payload: dict = {
        "text": f"✅ *New Task Approved:* {task.get('title', 'Untitled')}",
        "attachments": [
            {
                "color": "#36a64f",
                "fields": [
                    {"title": "Owner", "value": task.get("owner") or "Unassigned", "short": True},
                    {"title": "Priority", "value": task.get("priority", "MEDIUM"), "short": True},
                    {"title": "Deadline", "value": task.get("deadline_iso") or "TBD", "short": True},
                    {"title": "Description", "value": task.get("description", "")[:300], "short": False},
                ],
                "footer": "Meeting-to-Execution Agent",
            }
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code in (200, 201, 204):
                return _make_receipt("webhook", True, payload=payload)
            else:
                return _make_receipt(
                    "webhook",
                    False,
                    payload=payload,
                    error=f"Webhook returned {resp.status_code}: {resp.text[:200]}",
                )
    except Exception as exc:
        logger.error("Webhook dispatch error: %s", exc)
        return _make_receipt("webhook", False, payload=payload, error=str(exc))


# ── Local logger fallback ─────────────────────────────────────────────────────
def _dispatch_local_log(task: dict) -> dict:
    """Persist an execution receipt to local log when no external tokens exist."""
    receipt = _make_receipt(
        "local_log",
        True,
        external_id=f"local-{task.get('id', 'unknown')}",
        payload=task,
    )
    logger.info(
        "[LOCAL EXECUTION LOG] Task approved: %s | Owner: %s | Deadline: %s",
        task.get("title"),
        task.get("owner", "Unassigned"),
        task.get("deadline_iso", "TBD"),
    )
    return receipt


# ── Public Dispatcher ─────────────────────────────────────────────────────────
async def dispatch_execution(task: dict) -> dict[str, Any]:
    """
    Main entry point.  Tries GitHub → Webhook → local log in order.

    Parameters
    ----------
    task : dict
        Must contain at minimum: title, description, owner, deadline_iso,
        priority, verbatim_quote, id.

    Returns
    -------
    dict
        Combined receipt with keys from each attempted channel.
    """
    receipts: dict[str, Any] = {}

    if GITHUB_TOKEN and GITHUB_REPO:
        receipts["github"] = await _dispatch_github_issue(task)
        logger.info("GitHub dispatch: success=%s", receipts["github"]["success"])

    if WEBHOOK_URL:
        receipts["webhook"] = await _dispatch_webhook(task)
        logger.info("Webhook dispatch: success=%s", receipts["webhook"]["success"])

    if not receipts:
        # Neither GitHub nor webhook configured — use local logger
        receipts["local_log"] = _dispatch_local_log(task)

    return receipts


# ── Health check helpers ──────────────────────────────────────────────────────
def github_status() -> str:
    if GITHUB_TOKEN and GITHUB_REPO:
        return f"configured ({GITHUB_REPO})"
    return "not_configured"


def webhook_status() -> str:
    if WEBHOOK_URL:
        domain = WEBHOOK_URL.split("/")[2] if "//" in WEBHOOK_URL else WEBHOOK_URL[:30]
        return f"configured ({domain})"
    return "not_configured"
