
import json
import os
from datetime import datetime
from typing import Dict, Any, List, Optional


class ToolExecutionError(Exception):
    """Raised when an agent tool fails to execute."""
    pass


# Predefined Support Policies Knowledge Base
SUPPORT_POLICIES: Dict[str, Dict[str, Any]] = {
    "Billing": {
        "policy_id": "POL-BIL-01",
        "department": "Billing & Revenue Operations",
        "sla_high": "1 hour (Immediate Escalation)",
        "sla_medium": "8 business hours",
        "sla_low": "24 business hours",
        "priority_criteria": {
            "High": "Duplicate charges, unauthorized deductions, paid subscription inaccessible after payment, or failed enterprise wire transfers.",
            "Medium": "Refund status inquiries, invoice tax/GST corrections, promo code issues, or plan downgrade requests.",
            "Low": "General pricing questions, upcoming renewal date checks, or receipt copy requests.",
        },
        "standard_actions": {
            "duplicate_charge_no_access": "Escalate for payment verification",
            "duplicate_charge": "Escalate to Billing Specialist for duplicate charge audit and immediate refund",
            "refund_request": "Verify refund eligibility under 14-day policy and queue billing review",
            "invoice_update": "Route to Billing Operations for invoice regeneration",
            "default": "Route to Billing Support queue for transaction verification",
        },
        "auto_escalate_triggers": [
            "deducted twice",
            "charged twice",
            "double charged",
            "duplicate charge",
            "cannot access my purchased subscription",
            "paid but no access",
            "unauthorized charge",
            "fraud",
        ],
    },
    "Account Access": {
        "policy_id": "POL-ACC-02",
        "department": "Identity & Access Management (IAM)",
        "sla_high": "30 minutes (Security / Lockout Escalation)",
        "sla_medium": "4 business hours",
        "sla_low": "24 business hours",
        "priority_criteria": {
            "High": "Suspected account compromise/unauthorized login, complete lockout of active account, or broken 2FA/SSO blocking team access.",
            "Medium": "Password reset email not arriving, single-user 2FA device transfer, or OAuth link error.",
            "Low": "Username change request, profile email update, or general question about multi-factor authentication setup.",
        },
        "standard_actions": {
            "compromised": "Escalate immediately to Security Operations and freeze session tokens",
            "locked_out": "Escalate to IAM Tier-2 for identity verification and manual account unlock",
            "reset_issue": "Trigger manual password reset link and verify email delivery logs",
            "default": "Provide self-service account recovery guide and verify login status",
        },
        "auto_escalate_triggers": [
            "hacked",
            "unauthorized login",
            "compromised",
            "locked out",
            "2fa not working",
            "cannot login",
            "can't log in",
        ],
    },
    "Technical": {
        "policy_id": "POL-TECH-03",
        "department": "Product Engineering & Tier-2 Support",
        "sla_high": "2 hours (Incident Escalation)",
        "sla_medium": "12 business hours",
        "sla_low": "48 business hours",
        "priority_criteria": {
            "High": "Production outage, live client demo failure, app/website not working with client, 500 errors, or crash blocking core workflows.",
            "Medium": "Non-blocking bug, slow dashboard loading, webhook retry delay, or CSV export formatting glitch.",
            "Low": "Minor UI alignment issue, browser compatibility question, or non-critical warning log.",
        },
        "standard_actions": {
            "outage_or_500": "Escalate to On-Call Site Reliability Engineering (SRE) with error logs",
            "bug_or_crash": "Assign to Tier-2 Technical Support to reproduce bug and collect diagnostic logs",
            "performance": "Run telemetry diagnostics and provide performance optimization steps",
            "default": "Route to Technical Support queue with troubleshooting checklist",
        },
        "auto_escalate_triggers": [
            "production down",
            "outage",
            "data loss",
            "500 internal server error",
            "crashing continuously",
            "all users affected",
            "in demo",
            "in a demo",
            "live demo",
            "client demo",
            "with the client",
            "with a client",
            "with client",
            "website is not working",
            "app is not working",
            "site is down",
            "app is down",
        ],
    },
    "General": {
        "policy_id": "POL-GEN-04",
        "department": "Customer Success & Product Feedback",
        "sla_high": "4 hours (Urgent Escalation / Ambiguous Triage)",
        "sla_medium": "24 business hours",
        "sla_low": "72 business hours",
        "priority_criteria": {
            "High": "Ambiguous request with urgent customer distress or executive/legal escalation requiring human triage.",
            "Medium": "Partnership inquiry, bulk enterprise onboarding question, or compliance documentation request.",
            "Low": "Feature requests (e.g., dark mode, integrations), general product questions, or documentation feedback.",
        },
        "standard_actions": {
            "feature_request": "Log feature request on Product Roadmap and send acknowledgement to customer",
            "ambiguous": "Escalate to human triage specialist for clarification and customer follow-up",
            "how_to": "Send relevant knowledge base documentation link and mark as answered",
            "default": "Route to Customer Success queue for standard response",
        },
        "auto_escalate_triggers": [
            "legal",
            "gdpr violation",
            "urgent help needed",
        ],
    },
}

PRIORITY_WEIGHT = {
    "High": 3,
    "Medium": 2,
    "Low": 1,
}


class TicketStore:
    """Simulated database for storing, retrieving, sorting, and resolving tickets."""

    def __init__(self, storage_path: Optional[str] = None):
        self.storage_path = storage_path
        self._tickets: List[Dict[str, Any]] = []
        self._counter = 1000
        if self.storage_path and os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, list):
                        self._tickets = loaded
                        self._counter = 1000 + len(self._tickets)
            except Exception:
                self._tickets = []

    def add_ticket(self, ticket_record: Dict[str, Any]) -> Dict[str, Any]:
        self._counter += 1
        ticket_id = f"TKT-{self._counter}"
        now_dt = datetime.now()
        created_at_str = ticket_record.get("created_at") or now_dt.strftime("%Y-%m-%d %H:%M:%S")
        record = {
            "ticket_id": ticket_id,
            "created_at": created_at_str,
            "status": "Escalated" if ticket_record.get("escalate") else "Open",
            "resolved_at": None,
            **ticket_record,
        }
        self._tickets.append(record)
        self._sort_tickets()
        if self.storage_path:
            try:
                with open(self.storage_path, "w", encoding="utf-8") as f:
                    json.dump(self._tickets, f, indent=2)
            except Exception as exc:
                raise ToolExecutionError(f"Failed to persist ticket to disk: {exc}") from exc
        return record

    def _sort_tickets(self) -> None:
        """Always keeps High priority requests first, then Medium, then Low."""
        self._tickets.sort(
            key=lambda t: (
                PRIORITY_WEIGHT.get(t.get("priority", "Low"), 0),
                t.get("created_at", "")
            ),
            reverse=True
        )

    def resolve_ticket(self, ticket_id: str) -> Optional[Dict[str, Any]]:
        """Marks a ticket as Resolved and records timestamp."""
        for t in self._tickets:
            if t.get("ticket_id") == ticket_id:
                t["status"] = "Resolved"
                t["resolved_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if self.storage_path:
                    try:
                        with open(self.storage_path, "w", encoding="utf-8") as f:
                            json.dump(self._tickets, f, indent=2)
                    except Exception:
                        pass
                return t
        return None

    def list_tickets(self) -> List[Dict[str, Any]]:
        self._sort_tickets()
        return list(self._tickets)

    def get_stats(self) -> Dict[str, int]:
        total = len(self._tickets)
        resolved = sum(1 for t in self._tickets if t.get("status") == "Resolved")
        pending = total - resolved
        high = sum(1 for t in self._tickets if t.get("priority") == "High")
        medium = sum(1 for t in self._tickets if t.get("priority") == "Medium")
        low = sum(1 for t in self._tickets if t.get("priority") == "Low")
        return {
            "total_done": total,
            "pending": pending,
            "resolved": resolved,
            "high": high,
            "medium": medium,
            "low": low
        }

    def clear(self) -> None:
        self._tickets.clear()
        self._counter = 1000


# Default singleton store instance
DEFAULT_STORE = TicketStore()


def lookup_support_policy(
    category: str,
    simulate_failure: bool = False,
) -> Dict[str, Any]:
    """
    Tool 1: Looks up predefined support policy, SLA rules, and escalation triggers for a category.
    """
    if simulate_failure:
        raise ToolExecutionError("Policy Service Unavailable: Connection to Policy Knowledge Base timed out (503).")

    normalized = category.strip() if isinstance(category, str) else "General"
    policy = SUPPORT_POLICIES.get(normalized)
    if not policy:
        policy = SUPPORT_POLICIES["General"]
        return {
            "status": "fallback",
            "matched_category": "General",
            "policy": policy,
            "note": f"Category '{normalized}' not found in policy table; returned General policy.",
        }

    return {
        "status": "ok",
        "matched_category": normalized,
        "policy": policy,
    }


def create_and_store_ticket(
    request_text: str,
    category: str,
    priority: str,
    suggested_action: str,
    reason: str,
    escalate: bool = False,
    policy_id: str = "POL-GEN-04",
    sla_target: str = "24 business hours",
    customer_id: str = "CUST-ANON",
    created_at: Optional[str] = None,
    store: Optional[TicketStore] = None,
    simulate_failure: bool = False,
) -> Dict[str, Any]:
    """
    Tool 2: Creates and stores a simulated ticket in the ticket database.
    Tickets are sorted High -> Medium -> Low priority automatically.
    """
    if simulate_failure:
        raise ToolExecutionError("Ticket Database Write Error: Simulated storage outage (DB_LOCK_TIMEOUT).")

    target_store = store or DEFAULT_STORE
    payload = {
        "customer_id": customer_id,
        "request_text": request_text,
        "category": category,
        "priority": priority,
        "suggested_action": suggested_action,
        "reason": reason,
        "escalate": escalate,
        "policy_id": policy_id,
        "sla_target": sla_target,
        "created_at": created_at,
    }
    saved = target_store.add_ticket(payload)
    return {
        "status": "stored",
        "ticket": saved,
    }
