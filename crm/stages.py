"""Participant-owned stage proposal storage and decision handling."""


def proposals(store, workspace):
    """Expose saved proposals to the owner desk and CRM state readback."""
    return []


def decide(store, workspace, proposal_id, decision):
    """Apply the owner's decision and record its Activity in one transaction."""
    raise NotImplementedError


def clear(store, workspace):
    """Clear participant-owned proposal storage for this workspace within reset's transaction."""
