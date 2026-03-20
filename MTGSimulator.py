# Python 3.10.6
"""
MTG Turing Machine - Core Simulation Engine

Simulates a Turing machine using Magic: The Gathering game rules.
Based on the construction from "Magic: The Gathering is Turing Complete".
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional, Union
from MTGCommon import BaseMTGMachine, TokenPermanent, MachineHaltedError, MachineError, NoTransitionError
from RogozhinMachine import Rogozhin218Machine
from UniversalTuringMachineTransitions import (
    BLANK,
    Color,
    CreatureType,
    State,
)


# --- Scenario Loading/Saving ---

def load_scenario(file_path: str) -> BaseMTGMachine:
    """
    Load a machine configuration from a JSON file.
    Decides between Rogozhin and Gadget engines.

    Expected format:
    {
        "name": "...",
        "description": "...",
        "state": "q1",
        "head": 0,
        "tape": {"0": "Rhino", "1": "Elf", ...},
        "cards_on_hand": [...],
        "deck": [...]
    }

    Args:
        file_path: Path to the JSON scenario file

    Returns:
        Initialized GameLikeMachine

    """
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError(f"Scenario must be a JSON object, got {type(data).__name__}")

    engine_type = data.get("engine", "rogozhin")

    if engine_type == "gadget_2024":
        from GadgetMachine import ModularGadgetMachine
        machine = ModularGadgetMachine()
    else:
        from RogozhinMachine import Rogozhin218Machine
        machine = Rogozhin218Machine()

    machine.state = data.get("state", "q1")
    machine.head = data.get("head", 0)

    # Load deck/hand if specified
    if "cards_on_hand" in data:
        machine.cards_on_hand = data["cards_on_hand"]
    if "deck" in data:
        machine.deck = data["deck"]

    # Load tape
    tape_raw = data.get("tape", {})
    if not isinstance(tape_raw, dict):
        raise ValueError("'tape' must be a JSON object mapping position -> creature type")

    for pos_str, creature_type in tape_raw.items():
        try:
            pos = int(pos_str)
        except (TypeError, ValueError):
            raise ValueError(f"Tape position must be an integer, got {pos_str!r}")

        if not isinstance(creature_type, str):
            raise ValueError(
                f"Tape value at position {pos} must be a creature type string, "
                f"got {type(creature_type).__name__}"
            )

        color = "green" if pos < machine.head else "white"
        token = machine._new_token(creature_type=creature_type, color=color)
        machine.set_token(pos, token)

    # Initialize Illusory Gains at head - 1
    initial_gains_pos = machine.head - 1
    target_token = machine.get_token(initial_gains_pos)

    # If head-1 is empty, we must create a token for it to attach to
    if target_token.token_id == 0:
        color = "green" if initial_gains_pos < machine.head else "white"
        explicit_blank = machine._new_token(creature_type=BLANK, color=color)
        machine.set_token(initial_gains_pos, explicit_blank)
        machine.illusory_gains_attached_to = explicit_blank.token_id
    else:
        machine.illusory_gains_attached_to = target_token.token_id

    return machine


def save_scenario(
        machine: Rogozhin218Machine, file_path: str, *, name: str = "", description: str = ""
) -> None:
    """
    Save the current machine state to a JSON file.

    Args:
        machine: The machine to save
        file_path: Output file path
        name: Optional scenario name
        description: Optional scenario description
    """
    tape_out: Dict[str, str] = {}
    for pos, tok in machine.tape.items():
        creature_type = tok.creature_type
        if creature_type != BLANK:
            tape_out[str(pos)] = creature_type

    data = {
        "name": name,
        "description": description,
        "state": machine.state,
        "head": machine.head,
        "tape": tape_out,
    }

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)


# --- CLI Entry Point ---

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        scenario_path = sys.argv[1]
        print(f"Loading scenario: {scenario_path}")
        machine = load_scenario(scenario_path)
    else:
        machine = Rogozhin218Machine()

    print(f"Initial state: {machine.state}, head: {machine.head}, halted: {machine.halted}")
    print("Running one step...\n")

    try:
        for frame in machine.frames_for_next_step():
            print(f"  [{frame.phase}] {', '.join(frame.narration)}")
            if frame.phase == "END STEP":
                break
    except Exception as e:
        print(f"Error: {e}")

    print(f"\nFinal state: {machine.state}, head: {machine.head}, halted: {machine.halted}")
    print("\nFor interactive visualization, run: python web_server.py")
