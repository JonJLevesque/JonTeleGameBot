import random

from handlers.bracket import new_bracket, remaining, start_next_match


def _play_out(n, draw_rate=0.3):
    s = new_bracket(range(n))
    guard = 0
    while s["champion"] is None:
        m, _ = start_next_match(s)
        if m is None:
            break
        guard += 1
        assert guard < n * 10, "bracket did not converge"
        is_final = not s["queue"] and not s["advancers"]
        s["match"] = None
        if random.random() >= draw_rate:
            s["advancers"].append(random.choice([m["a"], m["b"]]))
        elif not is_final:
            s["advancers"] += [m["a"], m["b"]]
        elif s["final_draws"] < 1:
            s["final_draws"] += 1
            s["queue"] = [m["a"], m["b"]]
        else:
            s["advancers"].append(random.choice([m["a"], m["b"]]))
        if not s["queue"] and len(s["advancers"]) == 1:
            s["champion"] = s["advancers"].pop()
    return s


def test_champion_always_crowned():
    for n in (2, 3, 5, 64, 100):
        for _ in range(50):
            s = _play_out(n)
            assert s["champion"] is not None
            assert remaining(s) == 1


def test_total_and_first_match():
    s = new_bracket(range(10))
    assert s["total"] == 10 and s["round"] == 1
    m, new_round = start_next_match(s)
    assert m["no"] == 1 and not new_round
    assert remaining(s) == 10
