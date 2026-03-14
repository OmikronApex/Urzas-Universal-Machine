# Python 3.10.6
"""
MTG Turing Machine - Web Server

FastAPI-based web server providing a WebSocket interface for the simulator.
Serves the interactive visualization UI.
"""

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

# Server configuration
APP_HOST = "127.0.0.1"
APP_PORT = 60720

# Paths
WEB_DIR = os.path.join(os.path.dirname(__file__), "web")
SCENARIOS_DIR = os.path.join(os.path.dirname(__file__), "scenarios")


def _list_scenarios() -> List[str]:
    """Get list of available scenario files."""
    paths = sorted(glob.glob(os.path.join(SCENARIOS_DIR, "*.json")))
    return [os.path.basename(p) for p in paths]


def _frame_to_jsonable(frame: Any) -> dict:
    """Convert a Frame object to a JSON-serializable dict."""
    if frame is None:
        return {}

    if is_dataclass(frame):
        data = asdict(frame)
    elif isinstance(frame, dict):
        data = dict(frame)
    else:
        data = dict(getattr(frame, "__dict__", {}))

    # Ensure required fields exist
    data.setdefault("stack", [])
    data.setdefault("narration", [])
    data.setdefault("changed_positions", [])

    return data


def _snapshot_machine(machine: GameLikeMachine) -> dict:
    """Create a JSON-serializable snapshot of the machine state."""
    if machine is None:
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

    # Phasing logic: After Bob's turn, engine for CURRENT state is phased out
    phased_out = ["q1"] if machine.state == "q1" else ["q2"]

    # Convert tape to JSON
    tape_out: Dict[str, dict] = {}
    
    # Define the visible range to ensure Cephalids are included
    # We'll take a generous radius around the head
    view_radius = 15 
    for pos in range(machine.head - view_radius, machine.head + view_radius + 1):
        token = machine.get_token(pos)
        tape_out[str(pos)] = {
            "token_id": int(getattr(token, "token_id", 0)),
            "creature_type": getattr(token, "creature_type", "Cephalid"),
            "color": getattr(token, "color", None),
            "tapped": bool(getattr(token, "tapped", False)),
            "plus1_counters": int(getattr(token, "plus1_counters", 0)),
            "minus1_counters": int(getattr(token, "minus1_counters", 0)),
            "power": int(getattr(token, "power", 2)),
            "toughness": int(getattr(token, "toughness", 2)),
        }

    return {
        "step_index": int(machine.step_index),
        "state": machine.state,
        "head": int(machine.head),
        "halted": bool(machine.halted),
        "winner": machine.winner,
        "illusory_gains_attached_to": machine.illusory_gains_attached_to,
        "cards_on_hand": list(machine.cards_on_hand),
        "alice_battlefield": list(machine.alice_battlefield),
        "tape": tape_out,
        "phased_out": phased_out,
        "deck": list(machine.deck),
    }


def _get_full_utm_dict() -> dict:
    """Convert the UTM table to a UI-friendly nested dict."""
    result = {"q1": {}, "q2": {}}
    for (state, read_type), trans in UTM.items():
        result[state][read_type] = {
            "write_type": trans.write_type,
            "move_color": trans.move_color,
            "next_state": trans.next_state,
            "tapped": trans.tapped,
        }
    return result


class _Session:
    """Maintains server-side state for a client session."""

    def __init__(self) -> None:
        self.scenario_name: str = "short_run.json"
        self.machine: GameLikeMachine = self._load(self.scenario_name)
        self.frame_iter: Optional[Iterator[Any]] = None
        self.graveyard_cards: List[dict] = []
        self.current_stack: List[str] = []

    def _load(self, scenario_name: str) -> GameLikeMachine:
        """Load a scenario by name."""
        path = os.path.join(SCENARIOS_DIR, scenario_name)
        return load_scenario(path)

    def reset(self) -> None:
        """Reset the current scenario to initial state."""
        self.machine = self._load(self.scenario_name)
        self.frame_iter = None
        self.graveyard_cards = []
        self.current_stack = []

    def load_scenario(self, scenario_name: str) -> None:
        """Load a different scenario."""
        self.scenario_name = scenario_name
        self.reset()

    def step_one_frame(self) -> dict:
        """
        Execute one frame of the simulation.

        Returns:
            JSON-serializable message containing frame data
        """
        # Check if already halted
        if self.machine.halted and self.frame_iter is None:
            return {
                "type": "frame",
                "frame": {"phase": "HALTED", "narration": ["Machine is halted."], "stack": []},
                "snapshot": _snapshot_machine(self.machine),
                "graveyard": self.graveyard_cards,
                "stack": self.current_stack,
            }

        # Initialize frame iterator if needed
        if self.frame_iter is None:
            self.frame_iter = self.machine.frames_for_next_step()

        # Get next frame
        try:
            frame = next(self.frame_iter)
        except StopIteration:
            self.frame_iter = None
            return self.step_one_frame()  # Recursively try again

        frame_dict = _frame_to_jsonable(frame)

        # Update persistent stack
        if "stack" in frame_dict:
            self.current_stack = frame_dict["stack"]

        # Update graveyard on death events (SBA phase with a read creature)
        if "SBA" in frame_dict.get("phase", "") and frame_dict.get("read_pos") is not None:
            self.graveyard_cards.append({
                "creature_type": frame_dict.get("read_type", "Cephalid"),
                "color": frame_dict.get("read_color", "white"),
                "token_id": frame_dict.get("read_token_id", 0),
            })

            # Keep only last 5 cards
            if len(self.graveyard_cards) > 5:
                self.graveyard_cards.pop(0)

        message = {
            "type": "frame",
            "frame": frame_dict,
            "snapshot": _snapshot_machine(self.machine),
            "graveyard": self.graveyard_cards,
            "stack": self.current_stack,
        }

        # Clear iterator on end/halt
        phase = frame_dict.get("phase", "")
        if phase in ["END STEP", "HALT"]:
            self.frame_iter = None

        return message

    def step_one_step(self) -> List[dict]:
        """
        Execute a full computational step (all frames until END STEP).

        Returns:
            List of frame messages
        """
        frames: List[dict] = []
        aggregated_narration: List[str] = []

        # Safety limit to prevent infinite loops
        for _ in range(100):
            message = self.step_one_frame()
            frame_data = message.get("frame", {})
            
            # Collect narration from every frame
            if "narration" in frame_data:
                aggregated_narration.extend(frame_data["narration"])

            phase = frame_data.get("phase")
            if phase in ["END STEP", "HALT", "HALTED"]:
                # Attach the full turn's narration to the final frame
                frame_data["narration"] = aggregated_narration
                frames.append(message)
                break

        return frames


# --- FastAPI Application ---

app = FastAPI(title="MTG Turing Machine - Web UI")
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

_session = _Session()


@app.get("/")
def index() -> FileResponse:
    """Serve the main HTML page."""
    return FileResponse(os.path.join(WEB_DIR, "index.html"))


@app.get("/api/scenarios")
def scenarios() -> dict:
    """Get list of available scenarios."""
    return {"scenarios": _list_scenarios(), "selected": _session.scenario_name}


@app.get("/api/scenario/{name}")
def scenario_contents(name: str) -> dict:
    """Get the contents of a specific scenario file."""
    path = os.path.join(SCENARIOS_DIR, name)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    """
    WebSocket endpoint for real-time simulation control.

    Accepts commands:
    - ping: Health check
    - load_scenario: Load a different scenario
    - reset: Reset current scenario
    - step_frame: Execute one frame
    - step_step: Execute one full step
    """
    await websocket.accept()

    # Send initial state
    await websocket.send_json({
        "type": "scenario_list",
        "scenarios": _list_scenarios(),
        "selected": _session.scenario_name,
    })

    snapshot = _snapshot_machine(_session.machine)
    await websocket.send_json({
        "type": "state",
        "snapshot": snapshot,
        "utm_rules": _get_full_utm_dict(),
        "graveyard": _session.graveyard_cards,
        "stack": _session.current_stack,
        "alice_battlefield": snapshot.get("alice_battlefield", []),
    })

    try:
        while True:
            message = await websocket.receive_json()
            msg_type = message.get("type")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            if msg_type == "load_scenario":
                name = message.get("name")
                if not isinstance(name, str) or not name.endswith(".json"):
                    await websocket.send_json({
                        "type": "error",
                        "message": "Invalid scenario name.",
                    })
                    continue

                if name not in _list_scenarios():
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Scenario not found: {name}",
                    })
                    continue

                _session.load_scenario(name)
                await websocket.send_json({
                    "type": "state",
                    "snapshot": _snapshot_machine(_session.machine),
                    "utm_rules": _get_full_utm_dict(),
                })
                continue

            if msg_type == "reset":
                _session.reset()
                await websocket.send_json({
                    "type": "state",
                    "snapshot": _snapshot_machine(_session.machine),
                    "utm_rules": _get_full_utm_dict(),
                })
                continue

            if msg_type == "step_frame":
                try:
                    await websocket.send_json(_session.step_one_frame())
                except Exception as e:
                    await websocket.send_json({"type": "error", "message": str(e)})
                continue

            if msg_type == "step_step":
                try:
                    frames = _session.step_one_step()
                    # Only send the last frame (the result of the step) to the UI
                    if frames:
                        await websocket.send_json(frames[-1])
                except Exception as e:
                    await websocket.send_json({"type": "error", "message": str(e)})
                continue

            await websocket.send_json({
                "type": "error",
                "message": f"Unknown message type: {msg_type!r}",
            })

    except WebSocketDisconnect:
        return


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("web_server:app", host=APP_HOST, port=APP_PORT, reload=True)