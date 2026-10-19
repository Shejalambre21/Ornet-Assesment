"""
validators.py - Input and Output Validation Module for AI Support Ticket Triage Agent.
Handles Requirement 8: Empty inputs, invalid lengths, gibberish/ambiguous detection,
and unexpected/malformed LLM responses (including <think> tags and markdown blocks).
"""

import json
import re
from typing import Dict, Any, Tuple, Optional

VALID_CATEGORIES = {"Billing", "Technical", "Account Access", "General"}
VALID_PRIORITIES = {"Low", "Medium", "High"}

MIN_INPUT_LENGTH = 5
MAX_INPUT_LENGTH = 2000


class ValidationError(Exception):
    """Custom exception raised when ticket input validation fails."""
    def __init__(self, message: str, code: str = "INVALID_INPUT"):
        super().__init__(message)
        self.message = message
        self.code = code


def validate_ticket_input(raw_input: Any) -> Tuple[bool, str, Optional[str]]:
    """
    Validates incoming support request string.
    Returns:
        (is_valid, cleaned_text_or_error_message, error_code)
    """
    if raw_input is None:
        return False, "Support request cannot be None. Please provide a valid description.", "EMPTY_INPUT"

    if not isinstance(raw_input, str):
        return False, f"Expected text string input, received {type(raw_input).__name__}.", "INVALID_TYPE"

    cleaned = raw_input.strip()
    if not cleaned:
        return False, "Support request is empty or contains only whitespace. Please describe your issue.", "EMPTY_INPUT"

    if len(cleaned) < MIN_INPUT_LENGTH:
        return (
            False,
            f"Support request is too short ({len(cleaned)} chars). Minimum required is {MIN_INPUT_LENGTH} characters.",
            "INPUT_TOO_SHORT",
        )

    if len(cleaned) > MAX_INPUT_LENGTH:
        return (
            False,
            f"Support request exceeds maximum length of {MAX_INPUT_LENGTH} characters ({len(cleaned)} provided).",
            "INPUT_TOO_LONG",
        )

    alpha_count = sum(1 for c in cleaned if c.isalpha())
    if alpha_count < 3:
        return (
            False,
            "Support request must contain descriptive words, not only numbers or symbols.",
            "NON_DESCRIPTIVE_INPUT",
        )

    return True, cleaned, None


def is_ambiguous_request(text: str) -> Tuple[bool, str]:
    """
    Checks if a valid input string is too vague or ambiguous to classify safely
    (Requirement 7: Escalate urgent or ambiguous cases rather than making unsupported decisions).
    """
    words = re.findall(r"[a-zA-Z']+", text.lower())
    if len(words) < 3:
        return True, "Request contains fewer than 3 words and lacks sufficient context to diagnose."

    vague_patterns = [
        r"^(help|urgent|hello|hi|hey|please help|it is broken|not working|doesn't work|something is wrong|issue|problem|error|fix it)[.!?\s]*$",
        r"^(i need help with my account or maybe billing or something)[.!?\s]*$",
    ]
    normalized = text.strip().lower()
    for pat in vague_patterns:
        if re.match(pat, normalized):
            return True, "The customer states a generic problem without specifying the affected feature, error, or service."

    domain_keywords = {
        "payment", "charged", "deducted", "invoice", "refund", "billing", "subscription", "card", "price", "plan",
        "crash", "bug", "error", "slow", "api", "app", "website", "screen", "upload", "download", "sync", "integration",
        "login", "password", "locked", "2fa", "otp", "sign in", "signin", "access", "account", "username", "reset",
        "feature", "dark mode", "export", "question", "how to", "inquire", "inquiry", "hours", "pricing", "demo", "documentation"
    }
    has_keyword = any(kw in normalized for kw in domain_keywords)
    if not has_keyword and len(words) <= 6:
        return True, "No recognizable product, billing, technical, or account context was found in the brief message."

    return False, ""


def _extract_json_dict(raw_text: str) -> Dict[str, Any]:
    """
    Parses a JSON object from LLM text output, stripping <think>...</think> reasoning
    tags, markdown code fences, or surrounding prose if present.
    """
    cleaned = raw_text.strip()
    # Remove <think>...</think> blocks emitted by reasoning models (e.g. Qwen)
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL | re.IGNORECASE).strip()

    # Strip markdown code fences if present
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned).strip()

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # Fallback: locate the first balanced JSON object {...} in the text
    start_idx = cleaned.find("{")
    end_idx = cleaned.rfind("}")
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        candidate = cleaned[start_idx : end_idx + 1]
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError as exc:
            raise ValueError(f"Unexpected model response: Malformed JSON ({exc.msg}).") from exc

    raise ValueError("Unexpected model response: Malformed JSON.")


def validate_and_parse_llm_response(raw_response: Any) -> Tuple[Dict[str, Any], Optional[str]]:
    """
    Validates and normalizes structured output from the LLM.
    Handles Requirement 8: Unexpected model responses (malformed JSON, missing keys, invalid enums).
    Returns:
        (normalized_dict, warning_message_if_repaired)
    """
    warning = None

    if raw_response is None:
        raise ValueError("Model returned an empty (None) response.")

    if isinstance(raw_response, str):
        data = _extract_json_dict(raw_response)
    elif isinstance(raw_response, dict):
        data = dict(raw_response)
    else:
        raise ValueError(f"Unexpected model response type: {type(raw_response).__name__}")

    required_keys = ["category", "priority", "suggested_action", "reason"]
    missing_keys = [k for k in required_keys if k not in data or not str(data.get(k, "")).strip()]
    if missing_keys:
        raise ValueError(f"Model response missing required structured fields: {', '.join(missing_keys)}")

    # Validate & normalize Category
    category = str(data["category"]).strip()
    category_map = {
        "billing": "Billing",
        "payment": "Billing",
        "technical": "Technical",
        "tech": "Technical",
        "bug": "Technical",
        "account access": "Account Access",
        "account": "Account Access",
        "login": "Account Access",
        "auth": "Account Access",
        "general": "General",
        "inquiry": "General",
        "feature request": "General",
    }
    if category not in VALID_CATEGORIES:
        mapped_cat = category_map.get(category.lower())
        if mapped_cat:
            warning = f"Normalized non-standard category '{category}' to '{mapped_cat}'."
            category = mapped_cat
        else:
            warning = f"Unknown category '{category}' returned by model; defaulted to 'General' with escalation."
            category = "General"
            data["escalate"] = True

    # Validate & normalize Priority
    priority = str(data["priority"]).strip().capitalize()
    priority_map = {
        "Critical": "High",
        "Urgent": "High",
        "High": "High",
        "Medium": "Medium",
        "Moderate": "Medium",
        "Normal": "Medium",
        "Low": "Low",
        "Minor": "Low",
    }
    if priority not in VALID_PRIORITIES:
        mapped_pri = priority_map.get(priority)
        if mapped_pri:
            warn_msg = f"Normalized non-standard priority '{priority}' to '{mapped_pri}'."
            warning = f"{warning} {warn_msg}".strip() if warning else warn_msg
            priority = mapped_pri
        else:
            warn_msg = f"Invalid priority '{priority}' returned by model; defaulted to 'High' for safety."
            warning = f"{warning} {warn_msg}".strip() if warning else warn_msg
            priority = "High"
            data["escalate"] = True

    raw_escalate = data.get("escalate", priority == "High")
    if isinstance(raw_escalate, str):
        escalate_bool = raw_escalate.strip().lower() in ("true", "1", "yes")
    else:
        escalate_bool = bool(raw_escalate)
    if priority == "High":
        escalate_bool = True

    try:
        confidence_val = float(data.get("confidence", 0.9))
        confidence_val = max(0.0, min(1.0, confidence_val))
    except (ValueError, TypeError):
        confidence_val = 0.9

    normalized = {
        "category": category,
        "priority": priority,
        "suggested_action": str(data["suggested_action"]).strip(),
        "reason": str(data["reason"]).strip(),
        "escalate": escalate_bool,
        "confidence": confidence_val,
    }
    return normalized, warning