"""The shared agent loop: a manual tool-use loop over a set of tools (by default the
read-only audit tools in agents/tools.py), ending when the agent calls its submit tool with a payload that
validates against `submission_model`.

A validation error goes back to the model as an is_error tool_result so it can
correct and resubmit; the run only fails on refusal, truncation or running out of
turns.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Generic, TypeVar

import anthropic
from pydantic import BaseModel, ValidationError

from app.agents.tools import execute_tool

S = TypeVar("S", bound=BaseModel)

# (ctx, tool name, args) -> (content, is_error). Content is text, or a list of content
# blocks (e.g. text + an image) for tools that return a screenshot.
Executor = Callable[[Any, str, dict], Awaitable[tuple[str | list[dict], bool]]]


class AgentError(Exception):
    pass


@dataclass
class LoopResult(Generic[S]):
    submission: S
    input_tokens: int
    output_tokens: int


def submit_definition(name: str, description: str, model: type[BaseModel]) -> dict:
    return {"name": name, "description": description, "input_schema": model.model_json_schema()}


async def run_tool_loop(
    client: anthropic.AsyncAnthropic,
    *,
    model: str,
    system: str,
    tools: list[dict],
    submit_tool: dict,
    submission_model: type[S],
    first_message: str,
    ctx: Any,
    max_turns: int,
    executor: Executor = execute_tool,
) -> LoopResult[S]:
    submit_name = submit_tool["name"]
    tools = [*tools, submit_tool]
    messages: list[dict] = [{"role": "user", "content": first_message}]
    input_tokens = output_tokens = 0

    for turn in range(max_turns):
        request = dict(
            model=model,
            max_tokens=16000,
            system=system,
            tools=tools,
            messages=messages,
            thinking={"type": "adaptive"},
            output_config={"effort": "high"},
            # Auto-caches the growing prefix (tools, system, history) turn over turn.
            cache_control={"type": "ephemeral"},
        )
        if turn == max_turns - 1:
            # Last turn: force the submit, so a run that used its budget still returns
            # what it found instead of nothing.
            request["tool_choice"] = {"type": "tool", "name": submit_name}
        try:
            response = await client.messages.create(**request)
        except anthropic.BadRequestError:
            if "tool_choice" not in request:
                raise
            # Some platform/model combinations only allow forced tool use without thinking.
            response = await client.messages.create(**{**request, "thinking": {"type": "disabled"}})
        usage = response.usage
        input_tokens += (usage.input_tokens or 0) + (usage.cache_read_input_tokens or 0) + (usage.cache_creation_input_tokens or 0)
        output_tokens += usage.output_tokens or 0

        if response.stop_reason == "refusal":
            raise AgentError("Het model weigerde deze opdracht (stop_reason=refusal).")
        if response.stop_reason == "max_tokens":
            raise AgentError("Antwoord afgekapt op max_tokens.")

        messages.append({"role": "assistant", "content": response.content})
        tool_uses = [b for b in response.content if b.type == "tool_use"]

        if not tool_uses:
            messages.append({"role": "user", "content": f"Lever je resultaat in via {submit_name}."})
            continue

        async def handle(block) -> tuple[dict, S | None]:
            if block.name == submit_name:
                try:
                    submission = submission_model.model_validate(block.input)
                except ValidationError as exc:
                    return {"type": "tool_result", "tool_use_id": block.id, "is_error": True, "content": str(exc)}, None
                return {"type": "tool_result", "tool_use_id": block.id, "content": "Ontvangen."}, submission
            content, is_error = await executor(ctx, block.name, dict(block.input or {}))
            result = {"type": "tool_result", "tool_use_id": block.id, "content": content}
            if is_error:
                result["is_error"] = True
            return result, None

        handled = await asyncio.gather(*(handle(b) for b in tool_uses))
        submission = next((s for _, s in handled if s is not None), None)
        if submission is not None:
            return LoopResult(submission, input_tokens, output_tokens)

        content: list[dict] = [r for r, _ in handled]
        if turn == max_turns - 2:
            content.append({"type": "text", "text": f"Laatste beurt: dien nu je resultaat in via {submit_name}, met wat je tot nu toe weet."})
        messages.append({"role": "user", "content": content})

    raise AgentError(f"Geen resultaat ingediend binnen {max_turns} beurten.")
