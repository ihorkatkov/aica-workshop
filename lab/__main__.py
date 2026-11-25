import argparse
import asyncio
import json
import sys
import httpx
from . import config
from .tools import request


async def run_agent(args):
    from .runtime import Conversation

    conversation = Conversation(args.workspace or "workshop")
    try:
        return await conversation.turn(args.prompt)
    finally:
        await conversation.close()


def main():
    parser = argparse.ArgumentParser(
        description="AICA real-LLM workshop; synthetic CRM only."
    )
    parser.add_argument("--workspace")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("reset")
    sub.add_parser("state")
    sub.add_parser("smoke-trace")
    sub.add_parser("verify-trace").add_argument("trace_id")
    sub.add_parser("run").add_argument("prompt")
    sub.add_parser("preflight")
    for name in ["inspect", "approve", "promote"]:
        sub.add_parser(name).add_argument("proposal_id")
    review = sub.add_parser("set-review")
    review.add_argument("deal_id")
    review.add_argument("value", choices=["open", "cleared", "expired", "missing"])
    args = parser.parse_args()
    workspace = args.workspace or "workshop"
    if args.command == "run":
        return asyncio.run(run_agent(args))
    if args.command in ["smoke-trace", "verify-trace"]:
        from .telemetry import smoke, verify

        return smoke() if args.command == "smoke-trace" else verify(args.trace_id)
    if args.command == "preflight":
        config.require_model()
        args.prompt = "Read deal D-104 from the CRM and report its review status. Do not write or propose anything."
        result = asyncio.run(run_agent(args))
        if (
            not result["tool_calls"]
            or result["status"] != "complete"
            or not result["agent_said"]
        ):
            raise RuntimeError("Model preflight did not complete a tool round trip")
        from .telemetry import verify

        return {**result, "langwatch": verify(result["trace_id"])}
    if args.command == "reset":
        return request(workspace, "POST", "reset", human=True)
    if args.command == "state":
        return request(workspace, "GET", "state", human=True)
    if args.command == "set-review":
        return request(
            workspace,
            "POST",
            f"deals/{args.deal_id}/review",
            human=True,
            json={"status": args.value},
        )
    path = f"proposals/{args.proposal_id}"
    return request(
        workspace,
        "GET" if args.command == "inspect" else "POST",
        path if args.command == "inspect" else path + "/" + args.command,
        human=True,
    )


if __name__ == "__main__":
    try:
        print(json.dumps(main(), indent=2))
    except (RuntimeError, ValueError, httpx.HTTPError) as error:
        print(f"Lab: {error}", file=sys.stderr)
        raise SystemExit(1)
