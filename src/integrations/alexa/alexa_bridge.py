"""Alexa bridge — FastAPI-free Flask server that handles Workspace Assistant skill requests.

Architecture: Echo Dot → Amazon Cloud → https://alexa.wsbridge.uk/alexa → this server (port 8080)
Auth: Amazon request signature verification + Skill ID check
"""
import os
import sqlite3
import logging
from datetime import datetime, timezone

from flask import Flask
from ask_sdk_core.skill_builder import SkillBuilder
from ask_sdk_core.dispatch_components import AbstractRequestHandler, AbstractExceptionHandler
from ask_sdk_core.utils import is_request_type, is_intent_name
from ask_sdk_core.handler_input import HandlerInput
from ask_sdk_model import Response
from flask_ask_sdk.skill_adapter import SkillAdapter
from ask_sdk_webservice_support.verifier import RequestVerifier, TimestampVerifier

log = logging.getLogger(__name__)

SKILL_ID = os.environ["ALEXA_SKILL_ID"]
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "manifest_todos.db")
DB_PATH = os.path.normpath(DB_PATH)

VALID_PROJECTS = {"workspace", "sigmacapital", "music", "quantum", "aimanifest", "life"}

# Spoken word → DB project key
PROJECT_ALIASES: dict[str, str] = {
    "workspace": "workspace",
    "sigma capital": "sigmacapital",
    "capital": "sigmacapital",
    "music": "music",
    "heart music": "music",
    "quantum": "quantum",
    "ai manifest": "aimanifest",
    "manifest": "aimanifest",
    "life": "life",
    "infinite life": "life",
}

skill_builder = SkillBuilder()


def _resolve_project(spoken: str) -> str | None:
    key = spoken.lower().strip()
    return PROJECT_ALIASES.get(key) or (key if key in VALID_PROJECTS else None)


def _insert_todo(text: str, project: str, priority: int) -> int:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute(
        "INSERT INTO todos (project, source, text, done, created_at, priority, autonomy_level)"
        " VALUES (?, 'alexa', ?, 0, ?, ?, 'supervised')",
        (project, text, datetime.now(timezone.utc).isoformat(), priority),
    )
    row_id = cur.lastrowid
    conn.commit()
    conn.close()
    return row_id


def _query_todos(project: str, limit: int = 5) -> list[tuple[str, int]]:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT text, priority FROM todos WHERE done=0 AND project=?"
        " ORDER BY priority DESC LIMIT ?",
        (project, limit),
    ).fetchall()
    conn.close()
    return rows


# ---------------------------------------------------------------------------
# Intent handlers
# ---------------------------------------------------------------------------

@skill_builder.request_handler(can_handle_func=is_request_type("LaunchRequest"))
def launch_handler(handler_input: HandlerInput) -> Response:
    speech = "Workspace Assistant ready. Say add a todo, or ask about your backlog."
    return handler_input.response_builder.speak(speech).ask(speech).response


@skill_builder.request_handler(can_handle_func=is_intent_name("AddTodoIntent"))
def add_todo_handler(handler_input: HandlerInput) -> Response:
    from ask_sdk_model.dialog import ElicitSlotDirective
    slots = handler_input.request_envelope.request.intent.slots
    todo_text = (slots.get("todoText") or {}).get("value") if slots else None
    project_spoken = (slots.get("project") or {}).get("value") if slots else None
    priority_val = (slots.get("priority") or {}).get("value") if slots else None
    intent = handler_input.request_envelope.request.intent

    # Elicit missing slots one at a time
    if not todo_text:
        return handler_input.response_builder.speak("What would you like to add?").ask("What's the todo?").add_directive(
            ElicitSlotDirective(slot_to_elicit="todoText", updated_intent=intent)
        ).response
    if not project_spoken:
        return handler_input.response_builder.speak("Which project? Workspace, music, quantum, capital, manifest, or life?").ask("Which project?").add_directive(
            ElicitSlotDirective(slot_to_elicit="project", updated_intent=intent)
        ).response
    if not priority_val:
        return handler_input.response_builder.speak("What priority? Say a number from 1 to 10.").ask("What priority?").add_directive(
            ElicitSlotDirective(slot_to_elicit="priority", updated_intent=intent)
        ).response

    project = _resolve_project(project_spoken)
    if not project:
        speech = f"I don't recognize the project {project_spoken}. Valid projects are workspace, music, quantum, capital, manifest, and life."
        return handler_input.response_builder.speak(speech).ask(speech).response

    try:
        priority = int(priority_val)
    except ValueError:
        speech = f"Priority must be a number. Got {priority_val}."
        return handler_input.response_builder.speak(speech).ask(speech).response

    _insert_todo(todo_text, project, priority)
    speech = f"Added: {todo_text}. Project {project}, priority {priority}."
    return handler_input.response_builder.speak(speech).response


@skill_builder.request_handler(can_handle_func=is_intent_name("QueryTodosIntent"))
def query_todos_handler(handler_input: HandlerInput) -> Response:
    slots = handler_input.request_envelope.request.intent.slots
    project_spoken = (slots.get("project") or {}).get("value") if slots else None

    if not project_spoken:
        speech = "Which project backlog would you like to hear?"
        return handler_input.response_builder.speak(speech).ask(speech).response

    project = _resolve_project(project_spoken)
    if not project:
        speech = f"I don't recognize the project {project_spoken}."
        return handler_input.response_builder.speak(speech).ask(speech).response

    rows = _query_todos(project)
    if not rows:
        speech = f"No open todos for {project}."
    else:
        items = ". ".join(f"{text}, priority {pri}" for text, pri in rows)
        speech = f"Top {len(rows)} open todos for {project}: {items}."

    return handler_input.response_builder.speak(speech).response


@skill_builder.request_handler(
    can_handle_func=lambda hi: is_intent_name("AMAZON.CancelIntent")(hi)
    or is_intent_name("AMAZON.StopIntent")(hi)
)
def cancel_stop_handler(handler_input: HandlerInput) -> Response:
    return handler_input.response_builder.speak("Goodbye.").response


@skill_builder.request_handler(can_handle_func=is_request_type("SessionEndedRequest"))
def session_ended_handler(handler_input: HandlerInput) -> Response:
    return handler_input.response_builder.response


@skill_builder.exception_handler(can_handle_func=lambda hi, ex: True)
def catch_all_handler(handler_input: HandlerInput, exception: Exception) -> Response:
    log.error("Alexa bridge error: %s", exception, exc_info=True)
    speech = "Something went wrong on my end. Please try again."
    return handler_input.response_builder.speak(speech).response


# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------

app = Flask(__name__)
skill_adapter = SkillAdapter(
    skill=skill_builder.create(),
    skill_id=SKILL_ID,
    verifiers=[RequestVerifier(), TimestampVerifier()],
    app=app,
)
skill_adapter.register(app, route="/alexa")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from waitress import serve
    log.info("Alexa bridge listening on http://localhost:8080")
    serve(app, host="127.0.0.1", port=8080)
