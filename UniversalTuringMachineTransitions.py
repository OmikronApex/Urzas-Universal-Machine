# Python 3.10.6
"""
Universal Turing Machine Transitions

Defines the state transition table for Rogozhin's (2, 18) UTM encoded in MTG rules.
Based on "Magic: The Gathering is Turing Complete" (Churchill, Biderman, Herrick, 2019).
Table II from https://arxiv.org/pdf/1904.09828

Maps (state, creature_type) -> (write_type, move_color, next_state, tapped).

Creature type mapping from paper:
1=Aetherborn, 2=Basilisk, 3=Demon, 4=Elf, 5=Faerie, 6=Giant, 7=Harpy, 8=Illusion,
9=Juggernaut, 10=Kavu, 11=Leviathan, 12=Myr, 13=Noggle, 14=Orc, 15=Pegasus,
16=Rhino, 17=Sliver, 18=Cephalid (blank)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Literal, Tuple

# Type aliases for clarity
State = Literal["q1", "q2"]
CreatureType = Literal[
    "Cephalid",    # 18 - Blank symbol (S in Rogozhin notation)
    "Aetherborn",  # 1
    "Basilisk",    # 2
    "Demon",       # 3
    "Elf",         # 4
    "Faerie",      # 5
    "Giant",       # 6
    "Harpy",       # 7
    "Illusion",    # 8
    "Juggernaut",  # 9
    "Kavu",        # 10
    "Leviathan",   # 11
    "Myr",         # 12
    "Noggle",      # 13
    "Orc",         # 14
    "Pegasus",     # 15
    "Rhino",       # 16
    "Sliver",      # 17
    "Assassin",    # Special: halt symbol (not in Rogozhin, added for MTG)
]
Color = Literal["white", "green", "blue"]

# Canonical blank symbol
BLANK: CreatureType = "Cephalid"


@dataclass(frozen=True)
class Transition:
    """Represents a single UTM transition rule."""
    write_type: CreatureType
    move_color: Color
    next_state: State
    tapped: bool


# Rogozhin's (2, 18) Universal Turing Machine transition table from the paper
# Table II: Encoding of the UTM program
# Format: "Whenever a [READ] dies, create a 2/2 [COLOR] [WRITE]"
# Movement: white = left (-1), green = right (+1), blue = halt
# State transitions encoded via tapped status + Soul Snuffers timing
UTM: Dict[Tuple[State, CreatureType], Transition] = {
    # State 1 (q1) transitions - from Table II
    ("q1", "Aetherborn"): Transition("Sliver", "white", "q1", False),      # 1→17, L, 1
    ("q1", "Basilisk"):   Transition("Elf", "green", "q1", False),         # 2→4, R, 1
    ("q1", "Demon"):      Transition("Aetherborn", "green", "q1", False),  # 3→1, R, 1
    ("q1", "Elf"):        Transition("Demon", "white", "q1", False),       # 4→3, L, 1
    ("q1", "Faerie"):     Transition("Harpy", "green", "q1", False),       # 5→7, R, 1
    ("q1", "Giant"):      Transition("Juggernaut", "green", "q1", False),  # 6→9, R, 1
    ("q1", "Harpy"):      Transition("Faerie", "white", "q1", False),      # 7→5, L, 1
    ("q1", "Illusion"):   Transition("Faerie", "green", "q1", False),      # 8→5, R, 1
    ("q1", "Juggernaut"): Transition("Illusion", "white", "q1", False),    # 9→8, L, 1
    ("q1", "Kavu"):       Transition("Leviathan", "white", "q2", True),    # 10→11, L, 2 (tapped)
    ("q1", "Leviathan"):  Transition("Illusion", "white", "q2", True),     # 11→8, L, 2 (tapped)
    ("q1", "Myr"):        Transition("Basilisk", "white", "q2", True),     # 12→2, L, 2 (tapped)
    ("q1", "Noggle"):     Transition("Orc", "green", "q1", False),         # 13→14, R, 1
    ("q1", "Orc"):        Transition("Pegasus", "white", "q1", False),     # 14→15, L, 1
    ("q1", "Pegasus"):    Transition("Rhino", "green", "q2", True),        # 15→16, R, 2 (tapped)
    ("q1", "Rhino"):      Transition("Assassin", "blue", "q1", False),     # 16→HALT, X, 1
    ("q1", "Sliver"):     Transition("Cephalid", "green", "q1", False),    # 17→18, R, 1
    ("q1", "Cephalid"):   Transition("Sliver", "white", "q1", False),      # 18→17, L, 1


    # State 2 (q2) transitions - from Table II
    ("q2", "Aetherborn"): Transition("Cephalid", "green", "q2", False),    # 1→18, R, 2
    ("q2", "Basilisk"):   Transition("Cephalid", "green", "q2", False),    # 2→18, R, 2
    ("q2", "Demon"):      Transition("Elf", "green", "q2", False),         # 3→4, R, 2
    ("q2", "Elf"):        Transition("Aetherborn", "white", "q2", False),  # 4→1, L, 2
    ("q2", "Faerie"):     Transition("Kavu", "green", "q1", True),         # 5→10, R, 1 (tapped)
    ("q2", "Giant"):      Transition("Harpy", "green", "q2", False),       # 6→7, R, 2
    ("q2", "Harpy"):      Transition("Giant", "white", "q2", False),       # 7→6, L, 2
    ("q2", "Illusion"):   Transition("Juggernaut", "green", "q2", False),  # 8→9, R, 2
    ("q2", "Juggernaut"): Transition("Giant", "white", "q2", False),       # 9→6, L, 2
    ("q2", "Kavu"):       Transition("Faerie", "green", "q1", True),       # 10→5, R, 1 (tapped)
    ("q2", "Leviathan"):  Transition("Juggernaut", "green", "q2", False),  # 11→9, R, 2
    ("q2", "Myr"):        Transition("Orc", "green", "q2", False),         # 12→14, R, 2
    ("q2", "Noggle"):     Transition("Orc", "green", "q2", False),         # 13→14, R, 2
    ("q2", "Orc"):        Transition("Noggle", "white", "q2", False),      # 14→13, L, 2
    ("q2", "Pegasus"):    Transition("Sliver", "green", "q2", False),      # 15→17, R, 2
    ("q2", "Rhino"):      Transition("Sliver", "white", "q1", True),       # 16→17, R, 1 (tapped)
    ("q2", "Sliver"):     Transition("Myr", "white", "q2", False),         # 17→12, L, 2
    ("q2", "Cephalid"):   Transition("Basilisk", "white", "q2", False),    # 18→2, L, 2
}


def lookup(state: State, creature_type: CreatureType) -> Transition:
    """
    Look up a transition in the UTM table.
    

    Args:
        state: Current machine state
        creature_type: Creature type being read
        
    Returns:
        The transition rule to apply
        
    Raises:
        KeyError: If no transition exists for the given (state, creature_type)
    """
    return UTM[(state, creature_type)]


def is_halt_transition(trans: Transition) -> bool:
    """Check if a transition represents a halt condition."""
    return trans.move_color == "blue" and trans.write_type == "Assassin"
