"""Battleship pure game logic: placement, shots, sinks, full playouts."""
import random

from handlers.battleship import (
    FLEET, SIZE, apply_shot, new_state, outcome, place_fleet,
)


def _is_straight(cells):
    rows = [c // SIZE for c in cells]
    cols = [c % SIZE for c in cells]
    if len(set(rows)) == 1:  # horizontal: consecutive columns
        return sorted(cols) == list(range(min(cols), min(cols) + len(cells)))
    if len(set(cols)) == 1:  # vertical: consecutive rows
        return sorted(rows) == list(range(min(rows), min(rows) + len(cells)))
    return False


def test_place_fleet_always_legal():
    for _ in range(200):
        fleet = place_fleet()
        assert sorted(len(s) for s in fleet) == sorted(FLEET)
        cells = [c for ship in fleet for c in ship]
        assert len(cells) == len(set(cells)) == sum(FLEET)
        assert all(0 <= c < SIZE * SIZE for c in cells)
        assert all(_is_straight(ship) for ship in fleet)


def test_hit_keeps_turn_miss_passes():
    state = new_state()
    target = state["ships"][1][0][0]  # a known enemy ship cell
    result = apply_shot(state, 0, target)
    assert result == {"hit": True, "sunk": None}  # one hit can't sink a 4-ship
    assert state["turn"] == 0  # streak: shooter goes again

    enemy_cells = {c for ship in state["ships"][1] for c in ship}
    water = next(i for i in range(SIZE * SIZE) if i not in enemy_cells)
    result = apply_shot(state, 0, water)
    assert result == {"hit": False, "sunk": None}
    assert state["turn"] == 1  # miss passes the turn


def test_repeat_and_out_of_range_shots_rejected():
    state = new_state()
    assert isinstance(apply_shot(state, 0, 64), str)
    assert isinstance(apply_shot(state, 0, -1), str)
    cell = state["ships"][1][0][0]
    apply_shot(state, 0, cell)
    before = list(state["shots"][0])
    assert isinstance(apply_shot(state, 0, cell), str)
    assert state["shots"][0] == before  # state unchanged on rejection


def test_sink_detection():
    state = new_state()
    ship = min(state["ships"][1], key=len)  # the length-2 ship
    results = [apply_shot(state, 0, c) for c in ship]
    assert results[-1]["sunk"] == len(ship)
    assert all(r["hit"] for r in results)
    assert f"length {len(ship)}" in state["note"]


def test_win_only_when_whole_fleet_down():
    state = new_state()
    enemy_cells = [c for ship in state["ships"][1] for c in ship]
    for c in enemy_cells[:-1]:
        apply_shot(state, 0, c)
        assert outcome(state) is None
    apply_shot(state, 0, enemy_cells[-1])
    assert outcome(state) == {"winner": 0}


def test_random_playout_terminates_with_winner():
    rng = random.Random(42)
    for _ in range(20):
        state = new_state()
        fired = 0
        while outcome(state) is None:
            player = state["turn"]
            options = [i for i in range(SIZE * SIZE)
                       if i not in state["shots"][player]]
            assert options, "ran out of squares without a winner"
            apply_shot(state, player, rng.choice(options))
            fired += 1
            assert fired <= 2 * SIZE * SIZE
        win = outcome(state)
        assert win["winner"] in (0, 1)
        enemy = {c for ship in state["ships"][1 - win["winner"]] for c in ship}
        assert enemy <= set(state["shots"][win["winner"]])
