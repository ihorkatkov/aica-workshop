import json
import os
import urllib.error
import urllib.request

from google.adk.models import BaseLlm, LlmResponse
from google.genai import types

from . import chatgpt
from .store import ACTIONS

def openai_call(messages, tools=None):
    key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL")
    if not key or not model:
        raise RuntimeError("Set OPENAI_API_KEY and OPENAI_MODEL in .env, or use replay.")
    base = os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1"
    payload = {"model": model, "messages": messages}
    if tools:
        payload.update(tools=tools, tool_choice="required", parallel_tool_calls=False)
    call = urllib.request.Request(base.rstrip("/") + "/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(call, timeout=20) as response:
            return json.load(response)["choices"][0]["message"]
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Model HTTP {e.code}. Check key, billed quota, endpoint and model.") from None
    except (OSError, ValueError, KeyError, IndexError):
        raise RuntimeError("Model did not return a usable Chat Completions response.") from None

def smoke_model(mode="live"):
    if mode == "chatgpt":
        schema = {"type": "object", "properties": {"reply": {"type": "string", "enum": ["OK"]}},
                  "required": ["reply"], "additionalProperties": False}
        return chatgpt.decision([{"role": "user", "content": "Reply with OK."}], schema) == {"reply": "OK"}
    return bool(openai_call([{"role": "user", "content": "Reply with OK."}]).get("content"))


class WorkshopModel(BaseLlm):
    """Translate ADK turns into replay, Chat Completions or Codex decisions."""
    mode: str

    async def generate_content_async(self, llm_request, stream=False):
        responses = [part.function_response for content in llm_request.contents
                     for part in content.parts or [] if part.function_response]
        tools = llm_request.tools_dict
        if not responses:
            part = types.Part.from_function_call(name="get_deal", args={})
        elif len(tools) == 1:
            part = types.Part.from_text(text="Deal read.")
        else:
            name = next(name for name in tools if name != "get_deal")
            last = responses[-1].response
            retry = (len(responses) == 2 and name == "propose_action"
                     and last.get("status") == "rejected" and last.get("allowed"))
            if len(responses) == 1 or retry:
                args = self.choose(llm_request, responses, name)
                part = types.Part.from_function_call(name=name, args=args)
            else:
                part = types.Part.from_text(text="Workshop action complete.")
        yield LlmResponse(content=types.Content(role="model", parts=[part]))

    def choose(self, request, responses, name):
        last = responses[-1].response
        if self.mode == "replay":
            action = ("request_review_update" if "request_review_update" in last.get("allowed", [])
                      else "schedule_kickoff")
            return {"action": action}

        messages = [{"role": "system", "content": request.config.system_instruction},
                    {"role": "user", "content": request.contents[0].parts[0].text
                     + " Record: " + json.dumps(responses[0].response)}]
        # ADK may omit function IDs in model-facing history. Chat Completions
        # requires the same nonempty ID on the call and its subsequent result.
        call_id = None
        for content in request.contents:
            for part in content.parts or []:
                call = part.function_call
                response = part.function_response
                if call and call.name == name:
                    call_id = call.id or f"action-{len(messages)}"
                    messages.append({"role": "assistant", "tool_calls": [{
                        "id": call_id, "type": "function", "function": {
                            "name": name, "arguments": json.dumps(call.args)}}]})
                if response and response.name == name:
                    messages.append({"role": "tool", "tool_call_id": call_id,
                                     "content": json.dumps(response.response)})
        schema = {"type": "object", "properties": {"action": {"type": "string",
                  "enum": sorted(ACTIONS)}}, "required": ["action"], "additionalProperties": False}
        if self.mode == "chatgpt":
            args = chatgpt.decision(messages, schema)
        else:
            tool = {"type": "function", "function": {"name": name,
                    "description": request.tools_dict[name].description, "parameters": schema}}
            calls = openai_call(messages, [tool]).get("tool_calls") or []
            if len(calls) != 1 or calls[0]["function"]["name"] != name:
                raise RuntimeError("Unexpected tool or action; no action applied.")
            args = json.loads(calls[0]["function"]["arguments"])
        if (not isinstance(args, dict) or set(args) != {"action"} or
                not isinstance(args["action"], str) or args["action"] not in ACTIONS):
            raise RuntimeError("Unexpected tool or action; no action applied.")
        return args
