"""Stage proposals and account-owner decisions in the CRM."""

import json
from uuid import uuid4


def proposals(store, workspace):
    rows = store.db.execute(
        "SELECT data FROM records WHERE workspace=? AND kind='stage_proposals' ORDER BY rowid",
        (workspace,),
    )
    return [json.loads(row["data"]) for row in rows]


def propose(store, workspace, deal_id, to_stage, rationale):
    rationale = rationale.strip()
    if not rationale:
        raise ValueError("Include the customer evidence supporting the proposed change.")

    def txn():
        deal = store.get(workspace, deal_id)
        if deal.get("stage") != "pilot":
            raise ValueError("A rollout proposal requires a deal in Pilot.")
        for existing in proposals(store, workspace):
            if existing["deal_id"] == deal_id and existing["status"] == "pending":
                if existing["to_stage"] == to_stage and existing["rationale"] == rationale:
                    return existing
                raise ValueError("This deal already has a pending stage proposal.")
        proposal = {
            "id": f"PR-{uuid4().hex}",
            "deal_id": deal_id,
            "from_stage": deal["stage"],
            "to_stage": to_stage,
            "rationale": rationale,
            "status": "pending",
        }
        store.save(workspace, "stage_proposals", proposal)
        return proposal

    return store.transaction(txn)


def decide(store, workspace, proposal_id, decision):
    def txn():
        proposal = store.get(workspace, proposal_id)
        if "from_stage" not in proposal or proposal.get("status") != "pending":
            raise ValueError("Select a pending stage proposal.")
        deal = store.get(workspace, proposal["deal_id"])
        original_destination = proposal["to_stage"]
        if decision.decision == "approve":
            if deal["stage"] != proposal["from_stage"]:
                raise ValueError("The deal stage changed since this proposal was created.")
            destination = decision.to_stage or original_destination
            deal.update(stage=destination, revision=deal["revision"] + 1)
            store.save(workspace, "deals", deal)
            proposal.update(status="approved", to_stage=destination)
        else:
            proposal["status"] = "rejected"

        store.save(workspace, "stage_proposals", proposal)
        store.log(workspace, "stage_decided", {
            **proposal,
            "actor": "human",
            "proposed_to_stage": original_destination,
            "current_stage": deal["stage"],
            "to_stage": deal["stage"],
        })
        return proposal

    return store.transaction(txn)
