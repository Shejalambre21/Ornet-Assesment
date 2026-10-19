# AI Support Ticket Triage Agent

**Task 4: Mini AI Agent Development**

## Overview

The AI Support Ticket Triage Agent automates ticket intake, classification, priority evaluation, and next-action routing. A customer's support request is sent to an LLM, which returns a structured triage decision. The agent then looks up the matching support policy (SLA), stores the ticket in a priority-ordered queue, and escalates urgent or ambiguous cases to a human.

Urgent client-facing issues, such as a website outage during a live client presentation or sales demo, are immediately escalated as **High** priority.

The LLM is always tried first. A built-in offline interpreter is used only if the LLM call fails, so the system keeps working when the API is unavailable. The result always reports which engine produced it.

---

## Features

- Web UI for submitting requests, viewing the ticket store, live metrics, and running the test suite
- OpenAI-compatible LLM integration (configurable base URL, model, and API key)
- Optional Gemini secondary LLM
- Offline fallback interpreter if all LLM calls fail
- Strict input validation and ambiguity detection
- Output validation that repairs or rejects malformed LLM responses (including `<think>` tags and markdown fences)
- Two tools: policy lookup and ticket storage (High → Medium → Low ordering)
- Full execution trace for every ticket

---

## Assessment Requirements Traceability

| Req # | Requirement | Implementation |
| :--- | :--- | :--- |
| **1** | Accept support request as input | Accepts customer ID, generation timestamp, and support description via CLI and web UI. |
| **2** | Classify into categories | Categorizes into `Billing`, `Technical`, `Account Access`, or `General`. |
| **3** | Assign priority (Low, Medium, High) | Live client demo outages, payment failures, and account lockouts are **High**; functional glitches are **Medium**; feature requests and FAQs are **Low**. |
| **4** | Use LLM for structured output | The request is parsed by the LLM into a structured schema (`category`, `priority`, `suggested_action`, `reason`, `escalate`, `confidence`). |
| **5** | Implement at least two tools | **Tool 1:** `lookup_support_policy(category)` returns SLA windows and triggers.<br>**Tool 2:** `create_and_store_ticket(...)` stores and sorts tickets (High → Medium → Low). |
| **6** | Generate recommended action and reason | Produces an operational next step (for example, SRE incident escalation) with a concise explanation. |
| **7** | Escalate urgent or ambiguous cases | Vague inputs (for example, `"It is not working at all, please fix it!"`) are escalated to a human triage specialist instead of guessed. |
| **8** | Handle edge cases and failures | Guards against empty or whitespace input, malformed LLM responses, LLM/API failures, policy tool failures, and storage failures. |
| **9** | Include test cases (at least 5) | The test suite includes **12 scenarios** (billing, account lockout, production outage, live client demo failure, empty input, malformed LLM recovery, and more). |

---

## How It Works

```text
Support request
      │
      ▼
1. Input validation          (empty / too short / too long / non-descriptive)
      │
      ▼
2. LLM structured triage     Configured LLM  →  Gemini (if set)  →  offline fallback
      │                      output validated and normalized against the schema
      ▼
3. Tool 1: lookup_support_policy   → policy ID, department, SLA target, auto-escalation triggers
      │
      ▼
4. Tool 2: create_and_store_ticket → ticket stored, sorted High → Medium → Low
      │
      ▼
Result: category, priority, suggested action, reason, escalate flag, SLA, trace
```

### LLM output schema

```json
{
  "category": "Billing | Technical | Account Access | General",
  "priority": "Low | Medium | High",
  "suggested_action": "Clear, specific next step",
  "reason": "One-sentence explanation",
  "escalate": true,
  "confidence": 0.95
}
```

Non-standard values are normalized where possible (for example `Critical` → `High`). Unknown categories default to `General` with escalation, and invalid priorities default to `High` for safety. All `High` priority tickets are always escalated.

---

## Tools Implementation (Requirement 5)

### Tool 1: `lookup_support_policy(category)`

Retrieves the department, SLA resolution windows, and auto-escalation triggers for a category:

| Category | Policy ID | High | Medium | Low |
| :--- | :--- | :--- | :--- | :--- |
| Billing | `POL-BIL-01` | 1 hour | 8 hours | 24 hours |
| Account Access | `POL-ACC-02` | 30 minutes | 4 hours | 24 hours |
| Technical | `POL-TECH-03` | 2 hours | 12 hours | 48 hours |
| General | `POL-GEN-04` | 4 hours | 24 hours | 72 hours |

If the request text contains one of the policy's auto-escalation triggers, the ticket is raised to High priority and escalated. If the tool fails, a safe fallback SLA is applied.

### Tool 2: `create_and_store_ticket(...)`

Simulates persistent ticket storage and enforces priority queueing:

- **High** priority tickets are placed at the top of the queue.
- A resolution handler (`resolve_ticket`) marks tickets as completed with a timestamp.
- If storage fails, the ticket is held in a temporary fallback record and a warning is returned.

---

## Priority Criteria and Triage Rules

### High priority (immediate escalation)
- **Live client / demo outage:** the customer is in a presentation, client meeting, or product demo and the app or site is not working.
- **Critical technical outage:** production down, API 500 errors across all users, data corruption.
- **Severe billing discrepancy:** duplicate charges, unauthorized card deductions, paid subscription inaccessible.
- **Account lockout / compromise:** unauthorized login alerts, 2FA lockout on active production accounts.

### Medium priority (standard queue)
- Functional bugs with workarounds (for example, CSV export timeout).
- Authentication assistance (for example, password reset email delays).
- Standard billing inquiries (GST/tax number updates, refund eligibility checks).

### Low priority (routine queue)
- Product feature suggestions (for example, dark mode).
- General questions or documentation requests.

### Escalation rule
`escalate` is always `true` for High priority issues **or** when the request is ambiguous or unclear. The agent never invents actions for vague requests.

---

## Project Structure

```text
├── index.html              # Web UI (served by app.py, talks to the REST API)
├── app.py                  # Local web server + REST API (Python standard library)
├── agent.py                # Core triage agent: LLM gateway, fallback, tool orchestration
├── tools.py                # Policy lookup tool and TicketStore
├── validators.py           # Input validation, ambiguity detection, LLM output parsing
├── task4_triage_agent.py   # Standalone Python agent runner
├── demo.py                 # Interactive CLI demo
├── test_agent.py           # 12 automated tests
├── sample_tickets.json     # Sample ticket dataset
├── .env                    # LLM configuration (API keys) — do not commit
├── requirements.txt        # Python dependencies
└── README.md               # Project documentation
```

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

The LLM integration uses the official `openai` package (`pip install openai` if it is not listed in `requirements.txt`).

### 2. Configure the LLM

Create a `.env` file next to `agent.py`:

```env
XKIRO_API_KEY=your_api_key_here
XKIRO_BASE_URL=https://api.xkiro.com/v1
XKIRO_MODEL=qwen/qwen3.5-plus:free

# Optional secondary LLM
GEMINI_API_KEY=
```

| Variable | Purpose | Default |
| :--- | :--- | :--- |
| `XKIRO_API_KEY` (or `OPENAI_API_KEY`, `LLM_API_KEY`) | API key for the OpenAI-compatible provider | none |
| `XKIRO_BASE_URL` (or `LLM_BASE_URL`) | Provider base URL | `https://api.xkiro.com/v1` |
| `XKIRO_MODEL` (or `LLM_MODEL`) | Model name | `qwen/qwen3.5-plus:free` |
| `GEMINI_API_KEY` | Optional Gemini fallback (`gemini-2.5-flash`) | none |

Notes:
- Use the format `KEY=value` with no spaces around `=`.
- A value left as `your_api_key_here` is treated as "no key".
- The model name must be one that your provider actually serves.
- Never commit `.env` to version control.

If no key is configured, or the LLM call fails, the agent falls back to the built-in offline interpreter and reports the reason in the result's `warnings`.

---

## Running the Project

### Web UI

```bash
python app.py
```

Open **http://localhost:8000** in your browser.

1. Enter a customer ID and a support description.
2. Click **Generate Ticket**.
3. The result card shows the category, priority, suggested action, reason, and which engine answered (for example `Configured LLM (qwen/qwen3.5-plus:free)`). If the agent fell back to offline mode, the reason is displayed.
4. Use the **Status & Metrics**, **Ticket Store**, and **Test Cases** tabs to review tickets, resolve them, and run the suite.

### Verify the LLM connection from Python

```python
from agent import SupportTicketTriageAgent

agent = SupportTicketTriageAgent()
result = agent.triage_ticket("The dashboard shows the wrong timezone after I changed my profile")

print(result["engine_used"])    # should start with "Configured LLM"
print(result["used_fallback"])  # False when the LLM answered
print(result["warnings"])       # explains any fallback
```

### CLI demo

```bash
python demo.py
```

### Tests

```bash
python test_agent.py
```

Runs the 12 test cases that verify all requirements.

---

## REST API

`app.py` serves the UI and these endpoints:

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/` | Web UI |
| `POST` | `/api/triage` | Runs `triage_ticket()`; body: `request_text`, `customer_id`, `created_at` |
| `GET` | `/api/tickets` | Lists stored tickets (High → Medium → Low) |
| `POST` | `/api/resolve` | Marks a ticket as resolved; body: `ticket_id` |
| `GET` | `/api/stats` | Live metrics (total, pending, resolved, High/Medium/Low) |
| `POST` | `/api/clear` | Clears stored tickets |
| `GET` | `/api/policies` | Returns the predefined support policies |
| `GET` | `/api/samples` | Returns `sample_tickets.json` |

Example:

```bash
curl -X POST http://localhost:8000/api/triage \
  -H "Content-Type: application/json" \
  -d '{"request_text": "My payment was deducted twice and I cannot access my subscription", "customer_id": "CUST-2041"}'
```

---

## Edge Cases and Failure Handling (Requirement 8)

| Scenario | Behavior |
| :--- | :--- |
| Empty, whitespace, or `None` input | Rejected with `EMPTY_INPUT` |
| Input under 5 or over 2000 characters | Rejected with `INPUT_TOO_SHORT` / `INPUT_TOO_LONG` |
| Only numbers or symbols | Rejected with `NON_DESCRIPTIVE_INPUT` |
| Vague or ambiguous request | Escalated to a human triage specialist |
| Malformed LLM output | Repaired if possible; otherwise falls back to the offline interpreter |
| LLM or network failure | Falls back to the offline interpreter and records the error in `warnings` |
| Policy tool failure | Safe fallback SLA applied |
| Storage tool failure | Temporary fallback ticket returned with a warning |

---

## Troubleshooting

**The UI shows the offline fallback engine.**
Read the **Why fallback** line on the result card, or `result["warnings"]` in Python:

| Message | Meaning |
| :--- | :--- |
| `No external LLM API key configured` | The key was not loaded. Check `.env` location and format. |
| `HTTP 401` | The key was rejected (wrong or expired). |
| `HTTP 404` / model not found | The model name or base URL is wrong for your provider. |
| Connection error or timeout | Check the base URL and your network. |

**"Cannot reach the backend" in the UI.**
Start the server with `python app.py` and open `http://localhost:8000`.

**An old key keeps being used.**
Check for a leftover `XKIRO_API_KEY` set in your shell or system environment variables.