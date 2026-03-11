# generate_golden.py - run once, then delete or keep for regeneration

import json
import sys
from MTGSimulator import load_scenario, GameLikeMachine

def run_n_steps(m: GameLikeMachine, n: int):
    for _ in range(n):
        if m.halted:
            break
        for frame in m.frames_for_next_step():
            if frame.phase == "END STEP":
                break

def extract_tape(m: GameLikeMachine) -> dict:
    out = {}
    for pos, tok in sorted(m.tape.items()):
        out[str(pos)] = tok.creature_type
    return out

if __name__ == "__main__":
    path = sys.argv[1]
    with open(path) as f:
        data = json.load(f)

    steps = int(sys.argv[2]) if len(sys.argv) > 2 else 5

    m = load_scenario(path)
    run_n_steps(m, steps)

    print(json.dumps({
        "after_steps": steps,
        "state": m.state,
        "head": m.head,
        "halted": m.halted,
        "winner": m.winner,
        "tape": extract_tape(m),
    }, indent=2, sort_keys=True))
