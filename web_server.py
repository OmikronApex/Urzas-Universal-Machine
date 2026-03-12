# Python 3.10.6
from __future__ import annotations

import asyncio
import glob
import json
import os
from dataclasses import asdict, is_dataclass
from typing import Any, Dict, Iterator, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from MTGSimulator import GameLikeMachine, load_scenario
from UniversalTuringMachineTransitions import UTM

APP_HOST = "127.0.0.1"
APP_PORT = 60720

WEB_DIR = os.path.join(os.path.dirname(__file__), "web")
SCENARIOS_DIR = os.path.join(os.path.dirname(__file__), "scenarios")


def _list_scenarios() -> List[str]:
    paths = sorted(glob.glob(os.path.join(SCENARIOS_DIR, "*.json")))
    return [os.path.basename(p) for p in paths]


def _frame_to_jsonable(frame: Any) -> dict:
    if frame is None:
        return {}
    if is_dataclass(frame):
        d = asdict(frame)
    elif isinstance(frame, dict):
        d = dict(frame)
    else:
        d = dict(getattr(frame, "__dict__", {}))
    d.setdefault("stack", [])
    d.setdefault("narration", [])
    d.setdefault("changed_positions", [])
    return d


def _snapshot_machine(m: GameLikeMachine) -> dict:
    if m is None:
        return {
            "step_index": 0,
            "state": "q1",
            "head": 0,
            "halted": False,
            "winner": None,
            "illusory_gains_attached_to": None,
            "cards_on_hand": [],
            "alice_battlefield": [],
            "tape": {},
            "phased_out": [],
        }
    
    # Initial/Snapshot phasing logic: 
    # Assume we are in the state after Bob's turn.
    # Bob's turn phases OUT the engine for the CURRENT state.
    phased_out = ["q1"] if m.state == "q1" else ["q2"]

    tape_out: Dict[str, dict] = {}
    for pos, tok in getattr(m, "tape", {}).items():
        tape_out[str(pos)] = {
            "token_id": int(getattr(tok, "token_id", 0)),
            "creature_type": getattr(tok, "creature_type", "Cephalid"),
            "color": getattr(tok, "color", None),
            "tapped": bool(getattr(tok, "tapped", False)),
            "plus1_counters": int(getattr(tok, "plus1_counters", 0)),
            "minus1_counters": int(getattr(tok, "minus1_counters", 0)),
        }
    return {
        "step_index": int(m.step_index),
        "state": m.state,
        "head": int(m.head),
        "halted": bool(m.halted),
        "winner": m.winner,
        "illusory_gains_attached_to": m.illusory_gains_attached_to,
        "cards_on_hand": list(m.cards_on_hand),
        "alice_battlefield": list(m.alice_battlefield),
        "tape": tape_out,
        "phased_out": phased_out,
    }

class _Session:
    def __init__(self) -> None:
        self.scenario_name: str = "short_run.json"
        self.machine: GameLikeMachine = self._load(self.scenario_name)
        self.frame_iter: Optional[Iterator[Any]] = None
        self.graveyard_cards: List[dict] = []
        self.current_stack: List[str] = [] # Track stack server-side

    def _load(self, scenario_name: str) -> GameLikeMachine:
        path = os.path.join(SCENARIOS_DIR, scenario_name)
        return load_scenario(path)

    def reset(self) -> None:
        self.machine = self._load(self.scenario_name)
        self.frame_iter = None
        self.graveyard_cards = []
        self.current_stack = [] # Clear on reset

    def load_scenario(self, scenario_name: str) -> None:
        self.scenario_name = scenario_name
        self.reset()

    def step_one_frame(self) -> dict:
        # Check if already halted AND the iterator is done
        if self.machine.halted and self.frame_iter is None:
            return {
                "type": "frame",
                "frame": {"phase": "HALTED", "narration": ["Machine is halted."], "stack": []},
                "snapshot": _snapshot_machine(self.machine),
                "graveyard": self.graveyard_cards,
                "stack": self.current_stack,
            }

        if self.frame_iter is None:
            self.frame_iter = self.machine.frames_for_next_step()

        try:
            frame = next(self.frame_iter)
        except StopIteration:
            self.frame_iter = None
            return self.step_one_frame()

        frame_dict = _frame_to_jsonable(frame)
    
        # Update the persistent stack state from the frame
        if "stack" in frame_dict:
            self.current_stack = frame_dict["stack"]

        # Check for resolve events to update graveyard with full color identity
        if "RESOLVE" in frame_dict.get("phase", "") and frame_dict.get("read_pos") is not None:
            read_pos = frame_dict["read_pos"]
            tok = self.machine.get_token(read_pos)
        
            self.graveyard_cards.append({
                "creature_type": frame_dict.get("read_type", "Cephalid"),
                "color": getattr(tok, "color", "white"),
                "token_id": getattr(tok, "token_id", 0)
            })
            if len(self.graveyard_cards) > 5:
                self.graveyard_cards.pop(0)

        msg = {
            "type": "frame", 
            "frame": frame_dict, 
            "snapshot": _snapshot_machine(self.machine),
            "graveyard": self.graveyard_cards,
            "stack": self.current_stack
        }

        # If this frame explicitly marks the end or a halt, clear iterator
        phase = frame_dict.get("phase", "")
        if phase == "END STEP" or phase == "HALT":
            self.frame_iter = None

        return msg

    def step_one_step(self) -> List[dict]:
        out: List[dict] = []
        # Max safety to prevent infinite loops if logic fails
        for _ in range(100): 
            msg = self.step_one_frame()
            out.append(msg)
            phase = msg.get("frame", {}).get("phase")
            # Terminate on any end-of-step or halt signal
            if phase in ["END STEP", "HALT", "HALTED"]:
                return out

app = FastAPI(title="MTG Turing Machine - Web UI (local)")
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

_session = _Session()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(os.path.join(WEB_DIR, "index.html"))


@app.get("/api/scenarios")
def scenarios() -> dict:
    return {"scenarios": _list_scenarios(), "selected": _session.scenario_name}


@app.get("/api/scenario/{name}")
def scenario_contents(name: str) -> dict:
    path = os.path.join(SCENARIOS_DIR, name)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def get_full_utm_dict():
    """Converts the UTM table into a UI-friendly nested dict."""
    out = {"q1": {}, "q2": {}}
    for (state, read_type), trans in UTM.items():
        out[state][read_type] = {
            "write_type": trans.write_type,
            "move_color": trans.move_color,
            "next_state": trans.next_state,
            "tapped": trans.tapped
        }
    return out

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()

    # Send initial scenario list + state + UTM Rules + Graveyard + Stack + Alice's Board
    await ws.send_json({"type": "scenario_list", "scenarios": _list_scenarios(), "selected": _session.scenario_name})
    
    snapshot = _snapshot_machine(_session.machine)
    await ws.send_json({
        "type": "state", 
        "snapshot": snapshot,
        "utm_rules": get_full_utm_dict(),
        "graveyard": _session.graveyard_cards,
        "stack": _session.current_stack,
        "alice_battlefield": snapshot.get("alice_battlefield", []) # Explicitly pass
    })

    try:
        while True:
            msg = await ws.receive_json()
            mtype = msg.get("type")

            if mtype == "ping":
                await ws.send_json({"type": "pong"})
                continue

            if mtype == "load_scenario":
                name = msg.get("name")
                if not isinstance(name, str) or not name.endswith(".json"):
                    await ws.send_json({"type": "error", "message": "Invalid scenario name."})
                    continue
                if name not in _list_scenarios():
                    await ws.send_json({"type": "error", "message": f"Scenario not found: {name}"})
                    continue

                _session.load_scenario(name)
                await ws.send_json({"type": "state", "snapshot": _snapshot_machine(_session.machine)})
                continue

            if mtype == "reset":
                _session.reset()
                await ws.send_json({"type": "state", "snapshot": _snapshot_machine(_session.machine)})
                continue

            if mtype == "step_frame":
                try:
                    await ws.send_json(_session.step_one_frame())
                except Exception as e:
                    await ws.send_json({"type": "error", "message": str(e)})
                continue

            if mtype == "step_step":
                try:
                    frames = _session.step_one_step()
                    for f in frames:
                        await ws.send_json(f)
                        await asyncio.sleep(0)  # let the UI breathe
                except Exception as e:
                    await ws.send_json({"type": "error", "message": str(e)})
                continue

            if mtype == "step_logical":
                try:
                    frames = _session.step_logical()
                    # For logical steps, usually we just want the final result frame
                    if frames:
                        await ws.send_json(frames[-1])
                except Exception as e:
                    await ws.send_json({"type": "error", "message": str(e)})
                continue

            await ws.send_json({"type": "error", "message": f"Unknown message type: {mtype!r}"})

    except WebSocketDisconnect:
        return


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("web_server:app", host=APP_HOST, port=APP_PORT, reload=True)