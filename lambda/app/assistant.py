"""HR assistant with authorized tools, guardrails and bounded inline judging.

The application uses a Converse-shaped interface. The gateway adapter translates
model calls to LiteLLM, which routes to Bedrock and enforces key budgets and limits.
The Lambda reads its scoped gateway key from Secrets Manager using its AWS role.
Policy retrieval and employee-record permissions remain enforced by the backend.
"""

from app.model_gateway import GatewayUnavailable

import json
import re
import time
from functools import cache

from botocore.exceptions import BotoCoreError, ClientError

from app import config, database, employees, guardrails, retrieval
from app.inline_judge import validate_answer
from app.telemetry import observed

# Nova narrates its reasoning inside the answer text. Worth seeing once, and not
# something a person asking about holiday should ever read.
_THINKING = re.compile(r"<thinking>.*?</thinking>\s*", re.DOTALL | re.IGNORECASE)

NOT_COVERED = (
    "That isn't covered by Northwind's HR policies or your employee record, so I "
    "can't answer it. For anything else HR related, contact People Operations."
)

GREETING_WORDS = {"hi", "hello", "hey", "hiya", "howdy", "greetings", "morning",
                  "afternoon", "evening", "yo"}
THANKS_WORDS = {"thanks", "thank", "thx", "ty", "cheers", "appreciated", "ok", "okay",
                "cool", "great", "perfect", "bye", "goodbye"}
FILLER_WORDS = {"a", "all", "and", "are", "good", "how", "i", "is", "it", "much", "so",
                "the", "there", "to", "today", "very", "you", "your", "again", "doing"}
ABOUT_ME = {"who are you", "what are you", "what can you do", "help"}


def small_talk_reply(question, employee):
    """A fixed reply for greetings and thanks, or None for anything that is a question."""
    words = re.sub(r"[^\w\s]", " ", question).lower().split()
    first_name = employee["full_name"].split()[0]
    offer = (f"Hello {first_name}. I answer questions about Northwind's HR policies "
             "and your own employee record: leave, pay, benefits, expenses and more.")
    if not words or " ".join(words) in ABOUT_ME:
        return offer
    if len(words) > 6 or not all(w in GREETING_WORDS | THANKS_WORDS | FILLER_WORDS for w in words):
        return None
    if any(w in GREETING_WORDS for w in words):
        return offer
    if any(w in THANKS_WORDS for w in words):
        return "You're welcome. Ask me anything else about Northwind's HR policies."
    return offer


# How many times round the ask, run tools, ask again loop before giving up.
MAX_TOOL_ROUNDS = 5
MAX_ANSWER_TOKENS = 2048

# Zero reduces sampling variation, but provider execution can still vary.
# Repeated evaluations measure that remaining variation.
TEMPERATURE = 0.0


@cache
def client():
    from app.model_gateway import GatewayClient
    return GatewayClient(timeout=20)


# The tools, described so the model knows what each one does and what input it
# needs. Neither takes "who is asking" as input: that comes from the Cognito
# sign-in, so a question can never nominate whose records to read.
TOOLS = [
    {
        "toolSpec": {
            "name": "search_hr_policies",
            "description": (
                "Search the HR policy documents: leave, benefits, expenses, "
                "conduct, pay bands and more. Write the query as a full, standalone "
                "question that includes the topic from earlier in the chat (for "
                "'what about for food?' after a question about allowances, search "
                "'allowance for food and drinks'). Only current policy is returned, "
                "unless the query names an older year or says 'previous policy', "
                "e.g. '2024 expense policy meal limit'."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "get_employee_records",
            "description": (
                "Get the employee records the signed-in person may see: salary, "
                "bonus, level, manager, and remaining vacation (PTO) days."
            ),
            "inputSchema": {"json": {"type": "object", "properties": {}}},
        }
    },
]

from app.prompt_registry import load_prompt
SYSTEM_PROMPT = load_prompt()


def _label(chunk):
    """The heading the model sees above each passage: which document, which version,
    which country, and whether it is still in force."""
    label = f"{chunk['title']} - {chunk['section']}"
    if chunk.get("version"):
        label += f" (version {chunk['version']}"
        if chunk.get("effective_date"):
            label += f", effective {chunk['effective_date']}"
        label += ")"
    if chunk.get("region") and chunk["region"] != "global":
        label += f" APPLIES TO: {chunk['region'].upper()} only"
    if chunk.get("status") == "superseded":
        label += " SUPERSEDED: no longer in force"
    return label


@observed("Authorized HR tool", "tool")
def run_tool(name, tool_input, employee, sources, old_version=False):
    """Run the tool the model asked for, and return the result as text.

    old_version comes from the person's own question, not the model's search query:
    the model often drops "2024" when it writes the query.
    """
    if name == "search_hr_policies":
        results = retrieval.search_policies(
            tool_input.get("query", ""), employee["role"], old_version=old_version
        )
        sources.extend(results)
        if old_version:
            # Older versions first: the current text is usually the closer match,
            # and left in search order the model answered from it instead.
            results = sorted(results, key=lambda r: r.get("status") != "superseded")
        extracts = [f"[{_label(r)}]\n{r['content']}" for r in results]
        if old_version and any(r.get("status") == "superseded" for r in results):
            extracts.insert(0, "The person is asking about an older version. Answer from "
                               "the SUPERSEDED passages only. Include current rules only if the person requests a comparison.")
        return "\n\n".join(extracts) or "No matching policy text."

    if name != "get_employee_records":
        raise ValueError("Unknown tool")

    # get_employee_records: the database only returns rows this employee may see
    return json.dumps(employees.visible_records(employee), default=str)


def _text_of(message):
    """Join the text blocks of a Converse message, dropping any reasoning aloud."""
    parts = [block["text"] for block in message.get("content", []) if "text" in block]
    return _THINKING.sub("", "".join(parts)).strip()


def _cited(text, sources):
    """Keep only the passages from documents the answer names in its "Sources:" line.

    Search returns its closest passages even when none of them answers the question.
    Listing all of them under "that isn't covered" looks like evidence and isn't.
    """
    # The model sometimes puts "Sources:" at the end of its last sentence rather
    # than on its own line, so look for the last occurrence anywhere.
    lowered = text.lower()
    marker = lowered.rfind("sources:")
    if marker == -1:
        return []
    cited = lowered[marker:]
    return [source for source in sources if source["title"].lower() in cited]


def _strip_empty_sources(text, sources):
    """Remove a trailing "Sources:" line when there is nothing to cite.

    Models add one out of habit, including after an answer built purely from
    employee records. A citation that points at no document is worse than no
    citation: it looks like evidence and cannot be checked. The prompt asks for
    this too, and this is the half that does not depend on the model obeying.
    """
    if sources:
        return text

    lines = text.rstrip().split("\n")

    # Drop any blank lines at the end, then the "Sources:" line if there is one.
    while lines and not lines[-1].strip():
        lines.pop()
    if lines and lines[-1].lstrip().lower().startswith("sources:"):
        lines.pop()

    return "\n".join(lines).rstrip()


@observed("Bedrock model call", "generation")
def _call_model(model, request, usage):
    """Call the model. If it will not answer, try the fallback model instead.

    Returns (response, model_used). Once we have moved to the fallback we stay
    there for the rest of this question, so the caller keeps the model back.
    """
    try:
        return client().converse(modelId=model, **request), model
    except (BotoCoreError, ClientError, GatewayUnavailable) as error:
        # A model can be throttled, still warming up, withdrawn, or simply not
        # enabled in this account. None of that is the user's problem, and every
        # model here speaks the same Converse shape, so the same conversation
        # can carry on with a different one.
        fallback = config.FALLBACK_CHAT_MODEL
        if not fallback or model == fallback:
            raise
        print(f"{model} unavailable ({error}), falling back to {fallback}")
        usage["tools_used"].append("model_fallback")
        return client().converse(modelId=fallback, **request), fallback


def _run_requested_tools(message, employee, sources, usage, old_version=False, policy_context=None):
    """Run every tool the model asked for, and return the results to send back."""
    results = []
    for block in message.get("content", []):
        if "toolUse" not in block:
            continue

        call = block["toolUse"]
        usage["tools_used"].append(call["name"])
        tool_input = dict(call.get("input") or {})
        if call["name"] == "search_hr_policies" and policy_context:
            # Keep the previous topic when the current question is a short follow-up.
            tool_input["query"] = policy_context
        output = run_tool(call["name"], tool_input, employee, sources, old_version)
        results.append({
            "toolResult": {
                "toolUseId": call["toolUseId"],
                "content": [{"text": output}],
            }
        })
    return results


def policy_question_context(question, history):
    """Resolve short follow-ups using the last user question, not invented facts."""
    follow_up = re.search(r"\b(it|that|those|back then|what about|current policy)\b", question, re.I)
    if not follow_up:
        return question
    previous = [message["content"] for message in history if message["role"] == "user"]
    if not previous:
        return question
    topic_question = previous[-1]
    # A conversation may contain several pronoun-only turns. Keep its last named HR topic.
    topics = r"\b(pto|time off|vacation|leave|tuition|degrees?|expense|meal|allowance|benefits?|salary|pay|wellness|reimbursement)\b"
    for previous_question in reversed(previous):
        if re.search(topics, previous_question, re.I):
            topic_question = previous_question
            break
    context = topic_question + " " + question
    if re.search(r"\b(back then|previous|old|older)\b", question, re.I):
        years = re.findall(r"\b20\d\d\b", " ".join(previous))
        if years:
            context = years[-1] + " " + context
    return context


@observed("HR answer", "agent")
def answer(question, history, employee):
    """Answer a question. Returns (answer_text, sources)."""
    started = time.time()
    usage = {"input_tokens": 0, "output_tokens": 0, "tools_used": []}

    # 1. Guardrail on the question
    blocked, guarded_text = guardrails.check(question, "INPUT")
    if blocked:
        usage["tools_used"].append("guardrail_blocked_input")
        log_request(employee, question, usage, started)
        return guarded_text, []

    # Greetings and thanks get a fixed reply: no model call, and nothing for the
    # ungrounded-answer check below to mistake for an invented answer.
    social = small_talk_reply(question, employee)
    if social:
        usage["tools_used"].append("small_talk")
        log_request(employee, question, usage, started)
        return social, []

    # The model remembers nothing, so the whole conversation goes every time.
    # Converse wants content as a list of blocks; history holds plain strings.
    messages = [
        {"role": m["role"], "content": [{"text": m["content"]}]} for m in history
    ]
    messages.append({"role": "user", "content": [{"text": question}]})
    sources = []

    # "what was it back then" after "the 2024 policy" still wants the old version,
    # so the last few questions count, not only this one.
    recent_questions = [m["content"] for m in history[-6:] if m["role"] == "user"]
    contextual_question = policy_question_context(question, history)
    policy_context = contextual_question if contextual_question != question else None
    wants_current = bool(re.search(r'\b(current|today|now)\b', question, re.I))
    old_version = not wants_current and any(
        retrieval.asks_for_old_version(text) for text in recent_questions + [question]
    )

    # Start on the model we want. If it will not answer, the loop below moves to
    # the fallback and stays there for the rest of this question.
    model = config.CHAT_MODEL

    # 2-3. Ask, run the tools it wants, repeat
    for round_number in range(MAX_TOOL_ROUNDS):
        tool_config = {"tools": TOOLS}
        if round_number == 0:
            # The first step of every question must be a tool call. Asked politely in
            # the prompt, the model still answered follow-ups from memory, and invented
            # the figures (15 days of PTO, 60 carried over). "any" makes the lookup a
            # rule of the code, not a request to the model.
            # Policy figures must come from policy documents, not inferred salaries.
            policy_question = re.search(
                r"\b(policy|policies|carryover|carry over|salary band|pay band|entitlement|tuition|degrees?|pto|time off)\b",
                contextual_question, re.I,
            )
            if policy_question:
                tool_config["tools"] = [TOOLS[0]]
            tool_config["toolChoice"] = {"any": {}}

        request = {
            "messages": messages,
            "system": [{"text": SYSTEM_PROMPT.format(**employee)}],
            "inferenceConfig": {"maxTokens": MAX_ANSWER_TOKENS, "temperature": TEMPERATURE},
            "toolConfig": tool_config,
        }
        response, model = _call_model(model, request, usage)

        tokens = response.get("usage", {})
        usage["input_tokens"] += tokens.get("inputTokens", 0)
        usage["output_tokens"] += tokens.get("outputTokens", 0)
        message = response["output"]["message"]

        if response.get("stopReason") != "tool_use":
            text = _strip_empty_sources(_text_of(message), sources)
            sources = _cited(text, sources)

            # An answer with nothing behind it: no policy cited, no employee record
            # read, and not a question back to the person. Asked for "SRE" or
            # "devops", the model said the policies did not cover it and then
            # explained it from general knowledge anyway. The prompt forbids that;
            # this is the half that does not depend on the model obeying.
            if not sources and "get_employee_records" not in usage["tools_used"] and "?" not in text:
                usage["tools_used"].append("ungrounded_answer_replaced")
                text = NOT_COVERED

            # Hold the draft for a bounded judge/revision; no additional tool access.
            text = validate_answer(contextual_question, text, messages, employee, judge_client(), remaining_seconds=max(0, 25-(time.time()-started)))
            sources = _cited(text, sources)

            # 4. Guardrail on the answer
            changed, text = guardrails.check(text, "OUTPUT")
            if changed:
                usage["tools_used"].append("guardrail_changed_output")

            log_request(employee, question, usage, started)
            return text, sources

        # Send the model's own turn back verbatim, then the tool results.
        messages.append(message)
        results = _run_requested_tools(message, employee, sources, usage, old_version, policy_context)
        messages.append({"role": "user", "content": results})

    log_request(employee, question, usage, started)
    return "Sorry, I couldn't finish that answer. Please try again.", sources


def log_request(employee, question, usage, started):
    """Monitoring: one row per question with its speed, token use and tools."""
    database.query(
        """
        INSERT INTO request_log
            (employee_id, question, tools_used, input_tokens, output_tokens, latency_ms)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            employee["employee_id"],
            question,
            usage["tools_used"],
            usage["input_tokens"],
            usage["output_tokens"],
            int((time.time() - started) * 1000),
        ),
    )

@cache
def judge_client():
    from app.model_gateway import GatewayClient
    return GatewayClient(timeout=6)
