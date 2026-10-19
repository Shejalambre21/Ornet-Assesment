import json
import os
import re
import ssl
import urllib.request
import urllib.error
from datetime import datetime
from typing import Dict, Any, Optional, List

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

try:
    import requests as http_requests
except ImportError:
    http_requests = None

from validators import (
    validate_ticket_input,
    is_ambiguous_request,
    validate_and_parse_llm_response,
)
from tools import (
    lookup_support_policy,
    create_and_store_ticket,
    ToolExecutionError,
    TicketStore,
    DEFAULT_STORE,
)

DEFAULT_XKIRO_API_KEY = "sk-xt-6f4481477e22cf4ec1a643e1f7c3a7797c9ce64bafabf72b"
DEFAULT_XKIRO_MODEL = "qwen/qwen3.5-plus:free"
DEFAULT_XKIRO_BASE_URL = "https://api.xkiro.com/v1"

SYSTEM_PROMPT = """You are an AI Support Ticket Triage Agent.
Analyze the incoming customer support request description and return ONLY a valid JSON object matching this exact schema (no markdown fences, no extra text):
{
  "category": "Billing" | "Technical" | "Account Access" | "General",
  "priority": "Low" | "Medium" | "High",
  "suggested_action": "Clear, specific next step for support operations",
  "reason": "Brief 1-sentence reason explaining the category, priority, and action generated specifically for this ticket",
  "escalate": true | false,
  "confidence": 0.0 to 1.0
}

Priority Criteria:
- High: Duplicate charges, payment deducted without subscription access, unauthorized charges, account lockout/compromise, production outage, live client demo failure, or severe data loss.
- Medium: Functional bugs with workarounds, refund status checks, invoice adjustments, password reset email delays, or slow performance.
- Low: Feature requests, general 'how-to' inquiries, pricing questions, or minor cosmetic UI feedback.

Escalation Rule:
- Always set "escalate": true for High priority issues OR when the request is ambiguous/unclear.
- Never guess or fabricate unsupported actions for vague requests; escalate to a human triage specialist.
"""

PLACEHOLDER_KEYS = {"your_xkiro_api_key_here", "your_api_key_here", ""}


def load_env_file(filepath: Optional[str] = None) -> None:
    """
    Loads key-value pairs from .env file(s) into os.environ.
    Handles UTF-8 with BOM, UTF-16 (Windows Notepad/PowerShell), and multiple candidate paths.
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    cwd_dir = os.getcwd()
    parent_dir = os.path.dirname(base_dir)

    candidate_paths: List[str] = []
    if filepath:
        candidate_paths.append(filepath)
    for d in (base_dir, cwd_dir, parent_dir):
        for fname in (".env", ".env.txt", ".env.local"):
            p = os.path.join(d, fname)
            if p not in candidate_paths:
                candidate_paths.append(p)

    for path in candidate_paths:
        if not os.path.exists(path) or not os.path.isfile(path):
            continue
        content = None
        for enc in ("utf-8-sig", "utf-16", "utf-8", "latin-1"):
            try:
                with open(path, "r", encoding=enc) as f:
                    content = f.read()
                if content and "=" in content:
                    break
            except Exception:
                continue
        if not content:
            continue

        for raw_line in content.splitlines():
            line = raw_line.lstrip("\ufeff").strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.lower().startswith("export "):
                line = line[7:].strip()
            k, v = line.split("=", 1)
            k = k.lstrip("\ufeff").strip()
            v = v.strip().strip("\"'")
            if k and v and v not in PLACEHOLDER_KEYS:
                os.environ[k] = v

    # Ensure both XKIRO_API_KEY and OPENAI_API_KEY are populated
    resolved_key = (
        os.environ.get("XKIRO_API_KEY", "").strip()
        or os.environ.get("OPENAI_API_KEY", "").strip()
        or os.environ.get("LLM_API_KEY", "").strip()
        or DEFAULT_XKIRO_API_KEY
    )
    if resolved_key and resolved_key not in PLACEHOLDER_KEYS:
        os.environ["XKIRO_API_KEY"] = resolved_key
        os.environ["OPENAI_API_KEY"] = resolved_key


def normalize_chat_completions_url(base_url: str) -> str:
    """
    Ensures an OpenAI-compatible base URL (e.g. https://api.xkiro.com/v1)
    points to the /chat/completions endpoint when using raw HTTP requests.
    """
    cleaned = (base_url or DEFAULT_XKIRO_BASE_URL).strip().rstrip("/")
    if cleaned.endswith("/chat/completions"):
        return cleaned
    if cleaned.endswith("/v1"):
        return f"{cleaned}/chat/completions"
    return f"{cleaned}/v1/chat/completions"


def normalize_sdk_base_url(base_url: str) -> str:
    """
    Ensures base_url passed to OpenAI(base_url=...) ends with /v1
    (not /chat/completions, since OpenAI SDK appends /chat/completions itself).
    """
    cleaned = (base_url or DEFAULT_XKIRO_BASE_URL).strip().rstrip("/")
    if cleaned.endswith("/chat/completions"):
        cleaned = cleaned[: -len("/chat/completions")].rstrip("/")
    if not cleaned.endswith("/v1"):
        cleaned = f"{cleaned}/v1"
    return cleaned


class SupportTicketTriageAgent:
    """
    AI Agent that validates, classifies, prioritizes, looks up policy rules,
    and stores triaged support requests with full observability and fault tolerance.
    Uses the configured LLM via OpenAI client first and only falls back to the
    built-in interpreter if the LLM fails to generate a response.
    """

    def __init__(
        self,
        ticket_store: Optional[TicketStore] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        load_env_file()
        self.store = ticket_store or DEFAULT_STORE

        raw_key = (
            api_key
            or os.environ.get("XKIRO_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or os.environ.get("LLM_API_KEY")
            or DEFAULT_XKIRO_API_KEY
        )
        if raw_key and raw_key.strip() in PLACEHOLDER_KEYS:
            raw_key = DEFAULT_XKIRO_API_KEY
        self.api_key = raw_key.strip() if raw_key else DEFAULT_XKIRO_API_KEY
        os.environ["OPENAI_API_KEY"] = self.api_key
        os.environ["XKIRO_API_KEY"] = self.api_key

        self.model = (
            model
            or os.environ.get("XKIRO_MODEL")
            or os.environ.get("LLM_MODEL")
            or DEFAULT_XKIRO_MODEL
        ).strip()
        self.base_url = normalize_sdk_base_url(
            base_url
            or os.environ.get("XKIRO_BASE_URL")
            or os.environ.get("LLM_BASE_URL")
            or DEFAULT_XKIRO_BASE_URL
        )
        self.gemini_api_key = (os.environ.get("GEMINI_API_KEY") or "").strip() or None

    @property
    def xkiro_api_key(self) -> Optional[str]:
        return self.api_key

    @xkiro_api_key.setter
    def xkiro_api_key(self, value: Optional[str]) -> None:
        if value and value.strip() not in PLACEHOLDER_KEYS:
            self.api_key = value.strip()
            os.environ["OPENAI_API_KEY"] = self.api_key
            os.environ["XKIRO_API_KEY"] = self.api_key

    @property
    def xkiro_model(self) -> str:
        return self.model

    @xkiro_model.setter
    def xkiro_model(self, value: str) -> None:
        if value and value.strip():
            self.model = value.strip()

    @property
    def xkiro_base_url(self) -> str:
        return self.base_url

    @xkiro_base_url.setter
    def xkiro_base_url(self, value: str) -> None:
        if value and value.strip():
            self.base_url = normalize_sdk_base_url(value.strip())

    def _refresh_env_credentials(self) -> None:
        """Ensures API key and base_url are always populated before calling the LLM."""
        load_env_file()
        if not self.api_key or self.api_key in PLACEHOLDER_KEYS:
            env_key = (
                os.environ.get("XKIRO_API_KEY")
                or os.environ.get("OPENAI_API_KEY")
                or os.environ.get("LLM_API_KEY")
                or DEFAULT_XKIRO_API_KEY
            )
            self.api_key = env_key.strip()
        os.environ["OPENAI_API_KEY"] = self.api_key
        os.environ["XKIRO_API_KEY"] = self.api_key
        self.base_url = normalize_sdk_base_url(self.base_url)

    def _coerce_raw_llm_to_json_str(self, raw_text: str, request_text: str) -> str:
        """
        Self-contained parser that converts raw LLM output (even with <think> blocks,
        markdown fences, capitalized keys, or plain-text lines) into a clean JSON string
        so that a valid LLM response is never rejected by validators.py.
        """
        cleaned = str(raw_text).strip()
        # Strip closed <think>...</think> blocks
        cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL | re.IGNORECASE).strip()
        # If there is an unclosed </think>, keep everything after it
        if "</think>" in cleaned.lower():
            idx = cleaned.lower().rfind("</think>")
            cleaned = cleaned[idx + len("</think>") :].strip()

        # Strip markdown fences
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()

        parsed_dict: Optional[Dict[str, Any]] = None

        # 1. Try direct JSON parse or balanced {...} extraction
        for candidate in (
            cleaned,
            cleaned[cleaned.find("{") : cleaned.rfind("}") + 1]
            if ("{" in cleaned and "}" in cleaned and cleaned.rfind("}") > cleaned.find("{"))
            else "",
        ):
            if not candidate:
                continue
            for attempt in (candidate, re.sub(r",\s*}", "}", candidate)):
                try:
                    obj = json.loads(attempt)
                    if isinstance(obj, dict):
                        parsed_dict = obj
                        break
                except Exception:
                    continue
            if parsed_dict is not None:
                break

        # 2. If the LLM returned key-value lines (e.g. "Category: Billing\nPriority: High...")
        if parsed_dict is None:
            cat_match = re.search(r"category\s*[:\-]\s*([^\n\r]+)", cleaned, re.IGNORECASE)
            pri_match = re.search(r"priority\s*[:\-]\s*([^\n\r]+)", cleaned, re.IGNORECASE)
            act_match = re.search(r"(?:suggested[_\s]*action|action)\s*[:\-]\s*([^\n\r]+)", cleaned, re.IGNORECASE)
            rea_match = re.search(r"reason\s*[:\-]\s*([^\n\r]+)", cleaned, re.IGNORECASE)
            if cat_match or pri_match or act_match or rea_match:
                parsed_dict = {
                    "category": cat_match.group(1).strip(" *\"',") if cat_match else "General",
                    "priority": pri_match.group(1).strip(" *\"',") if pri_match else "Medium",
                    "suggested_action": act_match.group(1).strip(" *\"',") if act_match else "Review and respond to customer request",
                    "reason": rea_match.group(1).strip(" *\"',") if rea_match else cleaned[:250],
                    "escalate": False,
                    "confidence": 0.9,
                }

        # 3. Normalize dictionary keys case-insensitively
        if isinstance(parsed_dict, dict):
            lower_map = {str(k).strip().lower().replace(" ", "_"): v for k, v in parsed_dict.items()}
            category = str(
                lower_map.get("category")
                or lower_map.get("ticket_category")
                or "General"
            ).strip()
            priority = str(
                lower_map.get("priority")
                or lower_map.get("urgency")
                or "Medium"
            ).strip()
            suggested_action = str(
                lower_map.get("suggested_action")
                or lower_map.get("suggestedaction")
                or lower_map.get("action")
                or lower_map.get("next_step")
                or "Review support request and follow up with customer"
            ).strip()
            reason = str(
                lower_map.get("reason")
                or lower_map.get("explanation")
                or lower_map.get("rationale")
                or lower_map.get("summary")
                or cleaned[:250]
            ).strip()
            raw_esc = lower_map.get("escalate", str(priority).strip().lower() in ("high", "critical", "urgent"))
            if isinstance(raw_esc, str):
                escalate = raw_esc.strip().lower() in ("true", "1", "yes")
            else:
                escalate = bool(raw_esc)
            try:
                confidence = float(lower_map.get("confidence", 0.92))
            except Exception:
                confidence = 0.92

            return json.dumps({
                "category": category,
                "priority": priority,
                "suggested_action": suggested_action,
                "reason": reason,
                "escalate": escalate,
                "confidence": confidence,
            })

        raise ValueError(f"Could not extract structured fields from LLM output: {cleaned[:200]}")

    def _call_env_llm(self, request_text: str) -> str:
        """
        Calls the configured LLM using the exact OpenAI SDK pattern:
            from openai import OpenAI
            client = OpenAI(base_url="https://api.xkiro.com/v1", api_key=self.api_key)
            response = client.chat.completions.create(
                model="qwen/qwen3.5-plus:free",
                messages=[{"role": "user", "content": ...}],
            )
            return response.choices[0].message.content
        Includes automatic fallback to `requests` / `urllib` if `openai` is not installed.
        """
        self._refresh_env_credentials()
        if not self.api_key:
            raise RuntimeError("No API key configured.")

        user_prompt = f"{SYSTEM_PROMPT}\n\nSupport Request:\n{request_text}"
        messages = [{"role": "user", "content": user_prompt}]
        transport_errors: List[str] = []

        # 1. Primary: Official OpenAI Python SDK (matches user's exact snippet)
        if OpenAI is not None:
            try:
                client = OpenAI(
                    base_url=self.base_url,
                    api_key=self.api_key,
                )
                response = client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                )
                msg = response.choices[0].message
                content = getattr(msg, "content", None)
                if not content:
                    content = getattr(msg, "reasoning_content", None) or getattr(msg, "reasoning", None)
                if content and str(content).strip():
                    print(f"[LLM] Connected via OpenAI SDK ({self.model})")
                    return self._coerce_raw_llm_to_json_str(str(content), request_text)
                transport_errors.append("OpenAI SDK returned empty message content")
            except Exception as sdk_exc:
                transport_errors.append(f"OpenAI SDK error: {sdk_exc}")

        # 2. Secondary HTTP Transport: `requests` library (if installed)
        endpoint_url = normalize_chat_completions_url(self.base_url)
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }
        payload = {
            "model": self.model,
            "messages": messages,
        }

        if http_requests is not None:
            try:
                resp = http_requests.post(
                    endpoint_url,
                    headers=headers,
                    json=payload,
                    timeout=30,
                )
                if resp.status_code >= 400:
                    raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")
                body = resp.json()
                msg = body["choices"][0]["message"]
                content = msg.get("content") or msg.get("reasoning_content") or msg.get("reasoning")
                if content and str(content).strip():
                    print(f"[LLM] Connected via requests ({self.model})")
                    return self._coerce_raw_llm_to_json_str(str(content), request_text)
            except Exception as req_exc:
                transport_errors.append(f"requests error: {req_exc}")

        # 3. Tertiary HTTP Transport: `urllib.request` (with SSL fallback for Windows/macOS cert issues)
        for use_unverified_ssl in (False, True):
            try:
                req = urllib.request.Request(
                    endpoint_url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers=headers,
                    method="POST",
                )
                ctx = ssl._create_unverified_context() if use_unverified_ssl else None
                with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                    msg = body["choices"][0]["message"]
                    content = msg.get("content") or msg.get("reasoning_content") or msg.get("reasoning")
                    if content and str(content).strip():
                        print(f"[LLM] Connected via urllib ({self.model})")
                        return self._coerce_raw_llm_to_json_str(str(content), request_text)
            except urllib.error.HTTPError as http_err:
                err_body = ""
                try:
                    err_body = http_err.read().decode("utf-8", errors="replace")
                except Exception:
                    pass
                transport_errors.append(f"HTTP {http_err.code}: {err_body or http_err.reason}")
                break
            except urllib.error.URLError as url_err:
                if not use_unverified_ssl and "CERTIFICATE_VERIFY_FAILED" in str(url_err):
                    continue
                transport_errors.append(f"URLError: {url_err}")
                break
            except Exception as exc:
                transport_errors.append(f"urllib error: {exc}")
                break

        raise RuntimeError(" | ".join(transport_errors) if transport_errors else "Unknown LLM connection failure")

    def _call_gemini_llm(self, request_text: str) -> str:
        """Calls Gemini API if GEMINI_API_KEY is configured."""
        self._refresh_env_credentials()
        if not self.gemini_api_key:
            raise RuntimeError("No GEMINI_API_KEY configured.")

        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.5-flash:generateContent?key={self.gemini_api_key}"
        )
        payload = {
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"parts": [{"text": f"Support Request:\n{request_text}"}]}],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
            },
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (compatible; SupportTicketTriageAgent/1.0)",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            raw_text = body["candidates"][0]["content"]["parts"][0]["text"]
            return self._coerce_raw_llm_to_json_str(raw_text, request_text)

    def _call_external_llm(self, request_text: str) -> Optional[str]:
        """Calls the primary configured LLM or secondary Gemini LLM."""
        self._refresh_env_credentials()
        if self.api_key:
            return self._call_env_llm(request_text)
        if self.gemini_api_key:
            return self._call_gemini_llm(request_text)
        return None

    def _built_in_llm_interpreter(self, request_text: str) -> str:
        """
        Offline fallback interpreter used ONLY when external LLM generation fails
        or when no LLM API key is configured.
        """
        lower = request_text.lower().strip()

        if (
            ("deducted twice" in lower or "charged twice" in lower or "double charge" in lower or "duplicate charge" in lower)
            and ("subscription" in lower or "access" in lower)
        ):
            return json.dumps({
                "category": "Billing",
                "priority": "High",
                "suggested_action": "Escalate for payment verification",
                "reason": "The customer reports a duplicate charge and loss of access to a purchased subscription.",
                "escalate": True,
                "confidence": 0.98,
            })

        is_live_client_demo = any(ctx in lower for ctx in [
            "in demo", "in a demo", "live demo", "client demo",
            "with the client", "with a client", "with client",
            "client meeting", "customer meeting", "presentation", "sales pitch"
        ])
        is_technical_outage = any(fail in lower for fail in [
            "not working", "website is not working", "app is not working", "site is not working",
            "down", "broken", "crash", "crashing", "fails", "failing", "error", "unresponsive", "won't load", "cannot open"
        ])
        if is_live_client_demo and is_technical_outage:
            return json.dumps({
                "category": "Technical",
                "priority": "High",
                "suggested_action": "Escalate immediately to Emergency Technical Support / On-Call SRE for live client demo recovery",
                "reason": "Critical operational issue: Application or website is failing during an active client presentation or live demo.",
                "escalate": True,
                "confidence": 0.98,
            })

        ambiguous, ambig_reason = is_ambiguous_request(request_text)
        if ambiguous:
            return json.dumps({
                "category": "General",
                "priority": "High" if ("urgent" in lower or "emergency" in lower or "immediately" in lower) else "Medium",
                "suggested_action": "Escalate to human triage specialist for clarification",
                "reason": f"Ambiguous request escalated rather than making an unsupported decision: {ambig_reason}",
                "escalate": True,
                "confidence": 0.42,
            })

        billing_kw = [
            "payment", "deducted", "charged", "charge", "invoice", "refund",
            "billing", "subscription", "credit card", "debit", "receipt", "overcharged", "plan", "renewal", "gst"
        ]
        account_kw = [
            "login", "log in", "sign in", "signin", "password", "locked out", "locked",
            "2fa", "two-factor", "otp", "authentication", "hacked", "compromised",
            "unauthorized access", "unauthorized login", "reset link", "recovery email", "credentials"
        ]
        technical_kw = [
            "crash", "crashing", "bug", "error", "500", "404", "exception", "api",
            "outage", "is down", "system down", "slow", "latency", "upload", "export", "csv", "sync",
            "webhook", "integration", "broken", "freezing", "glitch", "database", "timeout",
            "website", "app", "application", "platform", "portal", "not working", "is not working", "down"
        ]
        general_kw = [
            "feature request", "suggest", "dark mode", "how do i", "how to",
            "documentation", "question", "inquiry", "business hours", "request demo", "product tour",
            "roadmap", "feedback", "would love", "add support", "keyboard shortcuts"
        ]

        scores = {
            "Billing": sum(2 if kw in lower else 0 for kw in billing_kw),
            "Account Access": sum(2 if kw in lower else 0 for kw in account_kw),
            "Technical": sum(2 if kw in lower else 0 for kw in technical_kw),
            "General": sum(2 if kw in lower else 0 for kw in general_kw),
        }

        if any(w in lower for w in ["deducted", "charged", "refund", "invoice", "payment"]):
            scores["Billing"] += 3
        if any(w in lower for w in ["password", "login", "log in", "locked out", "2fa", "hacked"]):
            scores["Account Access"] += 3
        if any(w in lower for w in ["500", "crash", "bug", "api", "outage", "error", "csv", "timeout"]):
            scores["Technical"] += 3
        if any(w in lower for w in ["feature request", "dark mode", "would be great if", "how to"]):
            scores["General"] += 3

        best_category = max(scores, key=scores.get)
        max_score = scores[best_category]

        if max_score == 0:
            return json.dumps({
                "category": "General",
                "priority": "Medium",
                "suggested_action": "Escalate to human triage specialist for clarification",
                "reason": "The request does not clearly match standard support categories and requires human review.",
                "escalate": True,
                "confidence": 0.50,
            })

        if best_category == "Billing":
            if any(k in lower for k in ["twice", "double", "duplicate", "unauthorized", "fraud", "paid but", "cannot access", "can't access", "stolen"]):
                priority = "High"
                action = "Escalate for payment verification"
                reason = "The customer reports a critical billing discrepancy (duplicate/unauthorized charge or paid access failure) requiring immediate verification."
                escalate = True
                conf = 0.95
            elif any(k in lower for k in ["refund", "invoice", "wrong amount", "cancel", "tax", "gst", "discount", "receipt"]):
                priority = "Medium"
                action = "Route to Billing Operations for invoice/refund review"
                reason = "The customer is requesting a standard billing adjustment, invoice update, or refund status review."
                escalate = False
                conf = 0.89
            else:
                priority = "Low"
                action = "Send billing FAQ and schedule standard billing follow-up"
                reason = "The customer has a general, non-urgent billing or pricing inquiry."
                escalate = False
                conf = 0.85

        elif best_category == "Account Access":
            if any(k in lower for k in ["hacked", "compromised", "unauthorized", "locked out", "blocked", "urgent", "entire team", "production account"]):
                priority = "High"
                action = "Escalate to IAM Security Tier-2 for identity verification and account unlock"
                reason = "The customer is locked out of their account or reports potential unauthorized access requiring urgent security escalation."
                escalate = True
                conf = 0.94
            elif any(k in lower for k in ["password", "reset", "2fa", "otp", "login failure", "cannot log in", "can't log in", "failed login", "recovery email"]):
                priority = "Medium"
                action = "Verify email delivery logs and send manual password/2FA recovery link"
                reason = "The customer is experiencing a login or password reset issue that requires authentication recovery assistance."
                escalate = False
                conf = 0.90
            else:
                priority = "Low"
                action = "Provide self-service account profile management instructions"
                reason = "The customer is asking a routine account settings or profile question."
                escalate = False
                conf = 0.84

        elif best_category == "Technical":
            if is_live_client_demo or any(k in lower for k in ["outage", "is down", "system down", "production down", "500", "data loss", "corrupted", "all users", "crashing", "urgent", "critical", "website is not working", "app is not working", "in demo", "with the client"]):
                priority = "High"
                action = "Escalate immediately to On-Call Engineering (SRE) with incident diagnostics"
                reason = "The customer reports a severe technical failure or production service disruption impacting core operations."
                escalate = True
                conf = 0.95
            elif any(k in lower for k in ["bug", "error", "slow", "export", "upload", "sync", "webhook", "not loading", "glitch", "fails", "timeout", "csv"]):
                priority = "Medium"
                action = "Assign to Tier-2 Technical Support to reproduce issue and inspect error logs"
                reason = "The customer describes a functional software bug or performance degradation affecting a specific feature."
                escalate = False
                conf = 0.88
            else:
                priority = "Low"
                action = "Share technical troubleshooting documentation and log minor UI feedback"
                reason = "The customer reports a minor technical question or cosmetic issue with minimal workflow impact."
                escalate = False
                conf = 0.83

        else:
            if any(k in lower for k in ["urgent", "immediately", "legal", "breach", "escalate", "unacceptable"]):
                priority = "High"
                action = "Escalate to Customer Success Manager for priority human review"
                reason = "The customer inquiry contains urgent escalation indicators requiring immediate human review."
                escalate = True
                conf = 0.86
            elif any(k in lower for k in ["feature request", "dark mode", "suggest", "would love", "add", "roadmap", "enhancement"]):
                priority = "Low"
                action = "Log feature request for the Product Team and send thank-you confirmation"
                reason = "The customer is submitting a product feature request or enhancement suggestion with no active service issue."
                escalate = False
                conf = 0.93
            else:
                priority = "Low"
                action = "Provide relevant Knowledge Base documentation and answer general inquiry"
                reason = "The customer is asking a general informational question with no system or billing impact."
                escalate = False
                conf = 0.87

        return json.dumps({
            "category": best_category,
            "priority": priority,
            "suggested_action": action,
            "reason": reason,
            "escalate": escalate,
            "confidence": conf,
        })

    def triage_ticket(
        self,
        request_text: Any,
        customer_id: str = "CUST-1042",
        created_at: Optional[str] = None,
        simulate_malformed_llm: bool = False,
        simulate_policy_tool_failure: bool = False,
        simulate_storage_tool_failure: bool = False,
    ) -> Dict[str, Any]:
        """
        End-to-end execution of the Support Ticket Triage Agent.
        Always attempts generation with the user's configured LLM first, and only
        falls back to the built-in interpreter if the LLM fails to generate.
        """
        trace: List[Dict[str, Any]] = []
        warnings: List[str] = []
        gen_timestamp = created_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Step 1: Input Validation
        is_valid, cleaned_or_err, err_code = validate_ticket_input(request_text)
        if not is_valid:
            trace.append({
                "step": "1. Input Validation",
                "status": "error",
                "detail": f"[{err_code}] {cleaned_or_err}",
            })
            return {
                "success": False,
                "error_code": err_code,
                "error_message": cleaned_or_err,
                "category": None,
                "priority": None,
                "suggested_action": "Reject empty/invalid input and prompt user for details",
                "reason": cleaned_or_err,
                "escalate": False,
                "created_at": gen_timestamp,
                "warnings": warnings,
                "trace": trace,
            }

        cleaned_text = cleaned_or_err
        trace.append({
            "step": "1. Input Validation",
            "status": "ok",
            "detail": f"Validated input string ({len(cleaned_text)} chars) with timestamp {gen_timestamp}.",
        })

        # Step 2: LLM Interpretation & Structured Output Validation
        self._refresh_env_credentials()
        parsed_llm: Optional[Dict[str, Any]] = None
        engine_used = f"Configured LLM ({self.model})"
        used_fallback = False

        if simulate_malformed_llm:
            try:
                raw_llm_output = "{not_valid_json: 'broken_llm_output', missing_fields: true"
                parsed_llm, _ = validate_and_parse_llm_response(raw_llm_output)
            except Exception as llm_exc:
                used_fallback = True
                engine_used = "Fallback Interpreter (Simulated Malformed LLM)"
                warn_msg = f"LLM output validation failed ({llm_exc}); fell back to built-in interpreter."
                warnings.append(warn_msg)
                fallback_raw = self._built_in_llm_interpreter(cleaned_text)
                parsed_llm, _ = validate_and_parse_llm_response(fallback_raw)
                trace.append({
                    "step": "2. LLM Structured Interpretation",
                    "status": "fallback",
                    "detail": f"[{engine_used}] {warn_msg}",
                    "raw_output": parsed_llm,
                })
        else:
            llm_errors: List[str] = []

            # 1. Primary: Call user's configured LLM (OpenAI SDK -> requests -> urllib)
            if self.api_key:
                try:
                    raw_llm_output = self._call_env_llm(cleaned_text)
                    parsed_llm, parse_warn = validate_and_parse_llm_response(raw_llm_output)
                    engine_used = f"Configured LLM ({self.model})"
                    if parse_warn:
                        warnings.append(parse_warn)
                    trace.append({
                        "step": "2. LLM Structured Interpretation",
                        "status": "ok" if not parse_warn else "warning",
                        "detail": (
                            f"[{engine_used}] Category='{parsed_llm['category']}', "
                            f"Priority='{parsed_llm['priority']}' (Confidence: {int(parsed_llm['confidence']*100)}%)."
                        ),
                        "raw_output": parsed_llm,
                    })
                except Exception as env_llm_exc:
                    print(f"[LLM WARNING] Primary LLM failed: {env_llm_exc}")
                    llm_errors.append(f"Configured LLM ({self.model}) failed: {env_llm_exc}")

            # 2. Secondary: Try Gemini LLM if configured and primary failed
            if parsed_llm is None and self.gemini_api_key:
                try:
                    raw_llm_output = self._call_gemini_llm(cleaned_text)
                    parsed_llm, parse_warn = validate_and_parse_llm_response(raw_llm_output)
                    engine_used = "Gemini LLM (gemini-2.5-flash)"
                    if parse_warn:
                        warnings.append(parse_warn)
                    trace.append({
                        "step": "2. LLM Structured Interpretation",
                        "status": "ok" if not parse_warn else "warning",
                        "detail": (
                            f"[{engine_used}] Category='{parsed_llm['category']}', "
                            f"Priority='{parsed_llm['priority']}' (Confidence: {int(parsed_llm['confidence']*100)}%)."
                        ),
                        "raw_output": parsed_llm,
                    })
                except Exception as gemini_exc:
                    llm_errors.append(f"Gemini LLM failed: {gemini_exc}")

            # 3. Last Resort Fallback: Only run built-in interpreter if LLM failed
            if parsed_llm is None:
                used_fallback = True
                if llm_errors:
                    err_summary = " | ".join(llm_errors)
                    warn_msg = f"LLM generation failed ({err_summary}); used built-in fallback interpreter."
                    engine_used = "Fallback Interpreter (LLM Failed)"
                else:
                    warn_msg = "No external LLM API key configured; used built-in fallback interpreter."
                    engine_used = "Fallback Interpreter (No API Key)"

                warnings.append(warn_msg)
                fallback_raw = self._built_in_llm_interpreter(cleaned_text)
                parsed_llm, _ = validate_and_parse_llm_response(fallback_raw)
                trace.append({
                    "step": "2. LLM Structured Interpretation",
                    "status": "fallback",
                    "detail": (
                        f"[{engine_used}] {warn_msg} -> Category='{parsed_llm['category']}', "
                        f"Priority='{parsed_llm['priority']}'."
                    ),
                    "raw_output": parsed_llm,
                })

        category = parsed_llm["category"]
        priority = parsed_llm["priority"]
        suggested_action = parsed_llm["suggested_action"]
        reason = parsed_llm["reason"]
        escalate = bool(parsed_llm["escalate"])

        # Step 3: Tool 1 - Lookup Predefined Support Policies
        policy_id = "POL-FALLBACK"
        sla_target = "4 business hours (Fallback SLA)"
        try:
            policy_res = lookup_support_policy(
                category=category,
                simulate_failure=simulate_policy_tool_failure,
            )
            policy_data = policy_res["policy"]
            policy_id = policy_data["policy_id"]
            sla_key = f"sla_{priority.lower()}"
            sla_target = policy_data.get(sla_key, "24 business hours")

            lower_req = cleaned_text.lower()
            matched_triggers = [
                trig for trig in policy_data.get("auto_escalate_triggers", [])
                if trig in lower_req
            ]
            if matched_triggers and priority != "High":
                priority = "High"
                escalate = True
                sla_target = policy_data.get("sla_high", "1 hour")

            trace.append({
                "step": "3. Tool Call: lookup_support_policy",
                "status": "ok",
                "detail": f"Loaded Policy {policy_id} ({policy_data['department']}) | Target SLA: {sla_target}",
                "tool_output": {
                    "policy_id": policy_id,
                    "department": policy_data["department"],
                    "sla_target": sla_target,
                    "matched_triggers": matched_triggers,
                },
            })
        except ToolExecutionError as tool1_exc:
            warn_msg = f"Tool 'lookup_support_policy' failed ({tool1_exc}). Applied safe fallback SLA policy."
            warnings.append(warn_msg)
            trace.append({
                "step": "3. Tool Call: lookup_support_policy",
                "status": "fallback",
                "detail": warn_msg,
            })

        # Step 4: Tool 2 - Create and Store Simulated Ticket (Sorted High -> Medium -> Low)
        ticket_record = None
        try:
            store_res = create_and_store_ticket(
                request_text=cleaned_text,
                category=category,
                priority=priority,
                suggested_action=suggested_action,
                reason=reason,
                escalate=escalate,
                policy_id=policy_id,
                sla_target=sla_target,
                customer_id=customer_id,
                created_at=gen_timestamp,
                store=self.store,
                simulate_failure=simulate_storage_tool_failure,
            )
            ticket_record = store_res["ticket"]
            trace.append({
                "step": "4. Tool Call: create_and_store_ticket",
                "status": "ok",
                "detail": f"Created Ticket {ticket_record['ticket_id']} with priority {priority} (Sorted High->Med->Low in store).",
                "tool_output": ticket_record,
            })
        except ToolExecutionError as tool2_exc:
            warn_msg = f"Tool 'create_and_store_ticket' failed ({tool2_exc}). Queued ticket in volatile fallback buffer."
            warnings.append(warn_msg)
            ticket_record = {
                "ticket_id": "TKT-TEMP-FALLBACK",
                "created_at": gen_timestamp,
                "status": "Escalated (Storage Retry Pending)" if escalate else "Open (Storage Retry Pending)",
                "policy_id": policy_id,
                "sla_target": sla_target,
            }
            trace.append({
                "step": "4. Tool Call: create_and_store_ticket",
                "status": "fallback",
                "detail": warn_msg,
                "tool_output": ticket_record,
            })

        return {
            "success": True,
            "ticket_id": ticket_record["ticket_id"],
            "created_at": gen_timestamp,
            "status": ticket_record["status"],
            "category": category,
            "priority": priority,
            "suggested_action": suggested_action,
            "reason": reason,
            "escalate": escalate,
            "confidence": parsed_llm.get("confidence", 0.9),
            "engine_used": engine_used,
            "used_fallback": used_fallback,
            "policy_id": policy_id,
            "sla_target": sla_target,
            "warnings": warnings,
            "trace": trace,
            "formatted_text": (
                f"Category: {category}\n"
                f"Priority: {priority}\n"
                f"Suggested Action: {suggested_action}\n"
                f"Reason: {reason}"
            ),
        }