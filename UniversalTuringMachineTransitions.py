# Python 3.10.6
# mtg_tc/utm18.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple, Literal, Optional

State = Literal["q1", "q2"]
Color = Literal["white", "green", "blue"]
CreatureType = str

@dataclass(frozen=True)
class Transition:
    write_type: CreatureType
    move_color: Color          # white = Left, green = Right, blue = HALT token (Assassin)
    next_state: State
    tapped: bool               # tapped token encodes “state change” mechanism in the paper

# Creature types used in Table II (also serve as “symbols”)
# Blank symbol is Cephalid (paper Section IV-E).
BLANK: CreatureType = "Cephalid"

# Table II: “Whenever <type> dies, create a <token>” for the (2,18) UTM.
# Encoding notes:
# - “create a 2/2 white X” -> move left
# - “create a 2/2 green X” -> move right
# - “create a tapped 2/2 ... X” -> tapped=True (used to trigger the Mesmeric Orb timing trick when changing state)
# - HALT transition: Rhino -> blue Assassin
#
# Keys are (state, read_type) where read_type is the dying tape token’s creature type.
UTM: Dict[Tuple[State, CreatureType], Transition] = {
        # --- q1 (Processing State) ---
        ("q1", "Aetherborn"): Transition(write_type="Sliver",    move_color="white", next_state="q1", tapped=False),
        ("q1", "Basilisk"):  Transition(write_type="Elf",       move_color="green", next_state="q1", tapped=False),
        ("q1", "Cephalid"):  Transition(write_type="Sliver",    move_color="white", next_state="q1", tapped=False),
        ("q1", "Demon"):     Transition(write_type="Aetherborn",move_color="green", next_state="q1", tapped=False),
        ("q1", "Elf"):       Transition(write_type="Demon",     move_color="white", next_state="q1", tapped=False),
        ("q1", "Faerie"):    Transition(write_type="Harpy",     move_color="green", next_state="q1", tapped=False),
        ("q1", "Giant"):     Transition(write_type="Juggernaut",move_color="green", next_state="q1", tapped=False),
        ("q1", "Harpy"):     Transition(write_type="Faerie",    move_color="white", next_state="q1", tapped=False),
        ("q1", "Illusion"):  Transition(write_type="Faerie",    move_color="green", next_state="q1", tapped=False),
        ("q1", "Juggernaut"):Transition(write_type="Illusion",  move_color="white", next_state="q1", tapped=False),

        # Canonical q1 -> q2 transitions (Churchill Section 4.2)
        ("q1", "Kavu"):      Transition(write_type="Leviathan", move_color="white", next_state="q2", tapped=True),
        ("q1", "Leviathan"): Transition(write_type="Illusion",  move_color="white", next_state="q2", tapped=True),
        ("q1", "Myr"):       Transition(write_type="Basilisk",  move_color="white", next_state="q2", tapped=True),
        ("q1", "Pegasus"):   Transition(write_type="Rhino",     move_color="green", next_state="q2", tapped=True),

        ("q1", "Noggle"):    Transition(write_type="Orc",       move_color="green", next_state="q1", tapped=False),
        ("q1", "Orc"):       Transition(write_type="Pegasus",   move_color="white", next_state="q1", tapped=False),
        ("q1", "Rhino"):     Transition(write_type="Assassin",  move_color="blue",  next_state="q1", tapped=False), # HALT
        ("q1", "Sliver"):    Transition(write_type="Cephalid",  move_color="green", next_state="q1", tapped=False),

        # --- q2 (Search/Cleanup State) ---
        ("q2", "Aetherborn"):Transition(write_type="Cephalid",  move_color="green", next_state="q2", tapped=False),
        ("q2", "Basilisk"):  Transition(write_type="Cephalid",  move_color="green", next_state="q2", tapped=False),
        ("q2", "Cephalid"):  Transition(write_type="Basilisk",  move_color="white", next_state="q2", tapped=False),
        ("q2", "Demon"):     Transition(write_type="Elf",       move_color="green", next_state="q2", tapped=False),
        ("q2", "Elf"):       Transition(write_type="Aetherborn",move_color="white", next_state="q2", tapped=False),

        # Canonical q2 -> q1 transitions (Churchill Section 4.2)
        ("q2", "Faerie"):    Transition(write_type="Kavu",      move_color="green", next_state="q1", tapped=True),
        ("q2", "Kavu"):      Transition(write_type="Faerie",    move_color="green", next_state="q1", tapped=True),
        ("q2", "Rhino"):     Transition(write_type="Sliver",    move_color="white", next_state="q1", tapped=True),

        ("q2", "Giant"):     Transition(write_type="Harpy",     move_color="green", next_state="q2", tapped=False),
        ("q2", "Harpy"):     Transition(write_type="Giant",     move_color="white", next_state="q2", tapped=False),
        ("q2", "Illusion"):  Transition(write_type="Juggernaut",move_color="green", next_state="q2", tapped=False),
        ("q2", "Juggernaut"):Transition(write_type="Giant",     move_color="white", next_state="q2", tapped=False),
        ("q2", "Leviathan"): Transition(write_type="Juggernaut",move_color="green", next_state="q2", tapped=False),
        ("q2", "Myr"):       Transition(write_type="Orc",       move_color="green", next_state="q2", tapped=False),
        ("q2", "Noggle"):    Transition(write_type="Orc",       move_color="green", next_state="q2", tapped=False),
        ("q2", "Orc"):       Transition(write_type="Noggle",    move_color="white", next_state="q2", tapped=False),
        ("q2", "Pegasus"):   Transition(write_type="Sliver",    move_color="green", next_state="q2", tapped=False),
        ("q2", "Sliver"):    Transition(write_type="Myr",       move_color="white", next_state="q2", tapped=False),
}

def lookup(state: State, read_type: CreatureType) -> Transition:
    try:
        return UTM[(state, read_type)]
    except KeyError as e:
        raise KeyError(f"No transition for state={state}, read_type={read_type}") from e
