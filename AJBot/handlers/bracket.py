"""Shared single-elimination bracket engine.

Used by the Beautiful Place tournament (items = places.json indices) and
/tournament (items = arbitrary strings, ids = list indices). The state dict
is JSON-serializable and identical in shape for both:

  round, queue (unpaired ids this round), advancers (through to next round),
  match ({"no","a","b","votes"} or None), match_no, final_draws,
  champion (id or None), total
"""
import random


def new_bracket(ids: list[int]) -> dict:
    ids = list(ids)
    random.shuffle(ids)
    return {
        # nonce ties vote buttons to THIS bracket, so buttons from a
        # pre-reset bracket can't cast votes in the new one
        "nonce": random.randrange(1, 1_000_000),
        "round": 1,
        "queue": ids,
        "advancers": [],
        "match": None,
        "match_no": 0,
        "final_draws": 0,
        "champion": None,
        "total": len(ids),
    }


def remaining(state: dict) -> int:
    return (
        len(state["queue"])
        + len(state["advancers"])
        + (2 if state["match"] else 0)
        + (1 if state["champion"] is not None else 0)
    )


def start_next_match(state: dict) -> tuple[dict | None, bool]:
    """Pair the next two contenders, rolling into a new round (or crowning a
    champion) when the current one is exhausted. Returns (match, new_round);
    match is None when a champion was just crowned."""
    new_round = False
    while True:
        q = state["queue"]
        if len(q) >= 2:
            a, b = q.pop(), q.pop()
            state["match_no"] += 1
            state["match"] = {"no": state["match_no"], "a": a, "b": b, "votes": {}}
            return state["match"], new_round
        if q:  # odd one out gets a bye
            state["advancers"].append(q.pop())
        if len(state["advancers"]) <= 1:
            state["champion"] = (
                state["advancers"][0] if state["advancers"] else None
            )
            state["advancers"] = []
            return None, False
        random.shuffle(state["advancers"])
        state["queue"], state["advancers"] = state["advancers"], []
        state["round"] += 1
        new_round = True
