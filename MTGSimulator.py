# Python 3.10.6
"""
MTG Turing Machine - Core Simulation Engine

Simulates a Turing machine using Magic: The Gathering game rules.
Based on the construction from "Magic: The Gathering is Turing Complete".
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional

from UniversalTuringMachineTransitions import (
    BLANK,
    Color,
    CreatureType,
    State,
    Transition,
    is_halt_transition,
    lookup,
)


# --- Data Classes ---

@dataclass(frozen=True)
class Frame:
    """
    A single visual frame within a computational step.

    Represents the game state at a specific point in the turn sequence,
    including narration and visual diff information for the UI.
    """
    step_index: int
    substep_index: int
    phase: str
    stack: List[str] = field(default_factory=list)
    narration: List[str] = field(default_factory=list)
    cards_on_hand: List[str] = field(default_factory=list)
    deck: List[str] = field(default_factory=list)

    # Diff payload for UI highlighting
    head_from: Optional[int] = None
    head_to: Optional[int] = None
    read_pos: Optional[int] = None
    read_type: Optional[CreatureType] = None
    read_token_id: Optional[int] = None
    read_color: Optional[Color] = None
    written_pos: Optional[int] = None
    written_token_id: Optional[int] = None
    written_type: Optional[CreatureType] = None
    attached_to_token_id: Optional[int] = None
    state_from: Optional[State] = None
    state_to: Optional[State] = None
    left_shift: Optional[int] = None
    right_shift: Optional[int] = None
    changed_positions: List[int] = field(default_factory=list)
    phased_out: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class TokenPermanent:
    """Represents a creature token on the battlefield."""
    token_id: int
    creature_type: CreatureType
    color: Optional[Color] = None
    tapped: bool = False
    plus1_counters: int = 0
    minus1_counters: int = 0
    power: int = 2
    toughness: int = 2


# --- Exceptions ---

class MachineError(Exception):
    """Base exception for simulator errors."""


class MachineHaltedError(MachineError):
    """Raised when attempting to step a halted machine."""


class NoTransitionError(MachineError):
    """Raised when no transition exists for (state, read_type)."""

    def __init__(self, state: State, read_type: CreatureType):
        super().__init__(f"No transition for state={state}, read_type={read_type}")
        self.state = state
        self.read_type = read_type


# --- Main Simulator ---

@dataclass
class GameLikeMachine:
    """
    Turing machine simulator using MTG game rules.

    The tape is represented by creature tokens on the battlefield.
    Game phases (untap, upkeep, etc.) drive the computation.
    """

    # Turing machine state
    tape: Dict[int, TokenPermanent] = field(default_factory=dict)
    head: int = 0
    state: State = "q1"
    step_index: int = 0
    halted: bool = False
    winner: Optional[str] = None

    # Global P/T adjustments for tape zones
    white_pt_adj: int = 0
    green_pt_adj: int = 0
    infest_active: bool = False
    _infest_cutoff_id: int = field(default=0, repr=False)

    # MTG game state
    _next_token_id: int = 1
    illusory_gains_attached_to: Optional[int] = None
    cards_on_hand: List[str] = field(default_factory=lambda: ["Infest"])
    deck: List[str] = field(
        default_factory=lambda: ["Cleansing Beam", "Coalition Victory", "Soul Snuffers"]
    )
    alice_battlefield: List[str] = field(
        default_factory=lambda: [
            "Dread of Night", "Dread of Night",
            "Wheel of Sun and Moon", "Steely Resolve",
            "Mesmeric Orb", "Ancient Tomb", "Prismatic Omen",
            "Choke", "Vigor", "Blazing Archon",
        ]
    )

    # Internal state for multi-phase transitions
    _current_trans: Optional[Transition] = field(default=None, repr=False)
    _last_written: Optional[TokenPermanent] = field(default=None, repr=False)
    _pending_head_move: int = field(default=0, repr=False)
    _last_move_dir: int = field(default=1, repr=False)  # 1 for Right (White), -1 for Left (Green)
    _step_completed_flag: bool = field(default=False, repr=False)

    def _new_token(
            self,
            *,
            creature_type: CreatureType,
            color: Optional[Color] = None,
            tapped: bool = False,
            plus1_counters: int = 0,
            minus1_counters: int = 0,
    ) -> TokenPermanent:
        """Create a new token with a unique ID."""
        token = TokenPermanent(
            token_id=self._next_token_id,
            creature_type=creature_type,
            color=color,
            tapped=tapped,
            plus1_counters=plus1_counters,
            minus1_counters=minus1_counters,
        )
        self._next_token_id += 1
        return token

    def get_token(self, pos: int) -> TokenPermanent:
        """
        Get the token at a tape position with calculated P/T.
        """
        if pos in self.tape:
            tok = self.tape[pos]
        else:
            # Decide color for implicit Cephalids
            if pos < self.head:
                color = "green"
            elif pos > self.head:
                color = "white"
            else:
                # Head position color matches the last direction moved
                color = "green" if self._last_move_dir == -1 else "white"

            tok = TokenPermanent(token_id=0, creature_type=BLANK, color=color, tapped=False)

        # Determine base P/T: 2/2 + distance from head
        dist = abs(self.head - pos)
        base = 2 + dist

        adj = self.green_pt_adj if tok.color == "green" else self.white_pt_adj

        # Determine Infest penalty
        infest_minus = 0
        if self.infest_active:
            if tok.token_id == 0 or tok.token_id <= self._infest_cutoff_id:
                infest_minus = 2

        # All temporary modifiers go into counters
        plus = max(0, adj)
        minus = abs(min(0, adj)) + infest_minus

        return TokenPermanent(
            token_id=tok.token_id,
            creature_type=tok.creature_type,
            color=tok.color,
            tapped=tok.tapped,
            plus1_counters=plus,
            minus1_counters=minus,
            # power/toughness now only represents the base (2 + dist)
            power=base,
            toughness=base
        )

    def set_token(self, pos: int, token: TokenPermanent) -> None:
            """Write a token to a tape position."""
            self.tape[pos] = token

    def _move_dir_from_color(self, color: Color) -> Optional[int]:
        """Convert color to movement direction."""
        if color == "white":
            return -1
        if color == "green":
            return 1
        return None  # blue = halt

    def frames_for_next_step(self) -> Iterator[Frame]:
        """
        Execute one computational step, yielding frames for visualization.

        A step consists of:
        1. Alice's turn: Cast and resolve spells via Wild Evocation
        2. Bob's turn: Pass (simplified)
        3. Repeat until Soul Snuffers is cast (state change complete)

        Yields:
            Frame objects representing each phase of the turn

        Raises:
            MachineHaltedError: If the machine is already halted
            NoTransitionError: If no valid transition exists
        """
        if self.halted:
            raise MachineHaltedError("Machine already halted")

        self.step_index += 1
        self._step_completed_flag = False
        substep_counter = 0
        stack: List[str] = []
        current_phased_out: List[str] = []

        def emit(phase: str, narration: List[str], **diff) -> Frame:
            """Helper to create and yield a frame."""
            nonlocal substep_counter
            substep_counter += 1
            final_phased_out = diff.pop("phased_out", current_phased_out)
            return Frame(
                step_index=self.step_index,
                substep_index=substep_counter,
                phase=phase,
                stack=list(stack),
                narration=list(narration),
                cards_on_hand=list(self.cards_on_hand),
                deck=list(self.deck),
                phased_out=list(final_phased_out),
                **diff,
            )

        turn_count = 1

        while True:
            # Phase in/out engines based on current state
            current_phased_out = ["q2"] if self.state == "q1" else ["q1"]

            # --- Alice's Turn ---
            yield from self._alice_turn(turn_count, stack, emit, current_phased_out)

            if self.halted:
                break

            # --- Bob's Turn ---
            bob_phased_out = ["q1"] if self.state == "q1" else ["q2"]
            yield emit(
                f"T{turn_count} - BOB",
                ["Bob's turn begins.", "Bob has no legal moves.", "Bob's turn ends."],
                phased_out=bob_phased_out,
            )

            # Check if computational step is complete
            if self._step_completed_flag or self.halted:
                break

            turn_count += 1

        yield emit("END STEP", ["End of computational step."])

    def _alice_turn(
            self,
            turn: int,
            stack: List[str],
            emit,
            current_phased_out: List[str],
    ) -> Iterator[Frame]:
        """Execute Alice's turn phases."""
        # Untap step
        yield from self._untap_step(turn, stack, emit)

        # Upkeep step
        yield emit(f"T{turn} - UPKEEP", ["Upkeep Step."])

        # Wild Evocation trigger
        yield from self._wild_evocation(turn, stack, emit)

        # Draw step
        if self.deck:
            drawn = self.deck.pop(0)
            self.cards_on_hand.append(drawn)
            yield emit(f"T{turn} - DRAW", [f"Alice draws {drawn}."])

        # End of turn cleanup
        self.infest_active = False
        yield emit(f"T{turn} - ENDSTEP", ["Alice has no legal moves.", "Alice's turn ends."])

    def _untap_step(self, turn: int, stack: List[str], emit) -> Iterator[Frame]:
        """Untap all tapped permanents and handle Mesmeric Orb triggers."""
        untapped_any = False

        for pos, tok in list(self.tape.items()):
            if tok.tapped:
                self.tape[pos] = TokenPermanent(
                    token_id=tok.token_id,
                    creature_type=tok.creature_type,
                    color=tok.color,
                    tapped=False,
                    plus1_counters=tok.plus1_counters,
                    minus1_counters=tok.minus1_counters,
                )
                untapped_any = True

        yield emit(f"T{turn} - UNTAP", [f"Alice's Turn {turn} begins. Untap Step."])

        if untapped_any:
            yield from self._mesmeric_orb_trigger(turn, stack, emit)

    def _mesmeric_orb_trigger(self, turn: int, stack: List[str], emit) -> Iterator[Frame]:
        """Handle Mesmeric Orb mill trigger."""
        stack.append("Mesmeric Orb")
        yield emit(f"T{turn} - TRIGGER", ["Permanents untapped: Mesmeric Orb triggers."])

        if "Coalition Victory" in self.deck:
            self.deck.remove("Coalition Victory")
            stack.append("Wheel of Sun and Moon")
            yield emit(
                f"T{turn} - REPLACEMENT",
                ["Wheel of Sun and Moon triggers: Coalition Victory moved to bottom of library."],
            )
            self.deck.append("Coalition Victory")
            stack.pop()
            yield emit(
                f"T{turn} - RESOLVE",
                ["Mesmeric Orb resolves: Alice mills Coalition Victory (moved to bottom)."],
            )
        else:
            yield emit(f"T{turn} - RESOLVE", ["Mesmeric Orb resolves: Alice mills a card."])

        stack.pop()

    def _wild_evocation(self, turn: int, stack: List[str], emit) -> Iterator[Frame]:
        """Wild Evocation forces casting a card from hand."""
        stack.append("Wild Evocation")
        yield emit(f"T{turn} - TRIGGER", ["Wild Evocation triggers: Alice must cast a card from hand."])

        if not self.cards_on_hand:
            stack.pop()
            yield emit(f"T{turn} - UPKEEP", ["Alice has no cards in hand to cast."])
            return

        spell_name = self.cards_on_hand.pop(0)
        stack.append(spell_name)
        yield emit(f"T{turn} - CAST", [f"Wild Evocation resolves. Alice casts {spell_name}."])

        # Resolve spell
        if spell_name == "Infest":
            yield from self._resolve_infest(turn, stack, emit)
        elif spell_name == "Cleansing Beam":
            yield from self._resolve_cleansing_beam(turn, stack, emit)
        elif spell_name == "Coalition Victory":
            yield from self._resolve_coalition_victory(turn, stack, emit)
        elif spell_name == "Soul Snuffers":
            yield from self._resolve_soul_snuffers(turn, stack, emit)
        else:
            stack.pop()  # Unknown spell

        # Wheel of Sun and Moon replacement
        if spell_name in ["Infest", "Cleansing Beam", "Coalition Victory", "Soul Snuffers"]:
            stack.append("Wheel of Sun and Moon")
            self.deck.append(spell_name)
            yield emit(
                f"T{turn} - REPLACEMENT",
                [f"Wheel of Sun and Moon moves {spell_name} to bottom of library."],
            )
            stack.pop()

    def _resolve_infest(self, turn: int, stack: List[str], emit) -> Iterator[Frame]:
        """Resolve Infest: Read the head token and trigger reanimation."""
        token_to_read = self.get_token(self.head)
        read_type = token_to_read.creature_type
        read_id = token_to_read.token_id
        read_color = token_to_read.color
        head_pos = self.head

        stack.pop()  # Infest
        stack.pop()  # Wild Evocation

        # Identify which tokens are currently on the battlefield
        self.infest_active = True
        self._infest_cutoff_id = self._next_token_id - 1

        # Frame 1: Infest applies -2/-2
        yield emit(
            f"T{turn} - RESOLVE",
            [f"Infest resolves. All creatures get -2/-2 until end of turn."],
            changed_positions=[head_pos],
        )

        # Frame 2: State-Based Action: The creature dies
        # Physically remove from tape so it disappears visually in this frame
        if self.head in self.tape:
            del self.tape[self.head]

        yield emit(
            f"T{turn} - SBA",
            [f"The {read_type} at position {self.head} has 0 toughness and dies."],
            read_pos=head_pos,
            read_type=read_type,
            read_token_id=read_id,
            read_color=read_color,
            changed_positions=[head_pos],
        )

        # Look up transition
        try:
            trans = lookup(self.state, read_type)
        except KeyError:
            raise NoTransitionError(self.state, read_type)

        # Trigger reanimator effect
        trigger_card = "Xathrid Necromancer" if trans.tapped else "Rotlung Reanimator"
        stack.append(trigger_card)
        yield emit(
            f"T{turn} - TRIGGER",
            [f"{trigger_card} triggers: create a {trans.write_type} token."],
            read_type=read_type,
            written_type=trans.write_type,
            state_from=self.state,
        )

        # Write new token
        written = self._new_token(
            creature_type=trans.write_type, color=trans.move_color, tapped=trans.tapped
        )
        self.set_token(self.head, written)
        self.illusory_gains_attached_to = written.token_id
        self._current_trans = trans
        self._last_written = written

        stack.pop()
        yield emit(
            f"T{turn} - RESOLVE",
            [f"Trigger resolves: write {trans.write_type} at {self.head}. Tapped={trans.tapped}."],
            written_pos=head_pos,
            written_token_id=written.token_id,
            written_type=written.creature_type,
            attached_to_token_id=written.token_id,
            changed_positions=[head_pos],
        )

    def _resolve_cleansing_beam(self, turn: int, stack: List[str], emit) -> Iterator[Frame]:
        """Resolve Cleansing Beam: Apply +2/+2 to moving direction and store head move."""
        trans = self._current_trans
        written = self._last_written

        stack.pop()  # Cleansing Beam
        stack.pop()  # Wild Evocation

        if not trans or not written:
            yield emit(f"T{turn} - RESOLVE", ["Cleansing Beam resolves but finds no targets."])
            return

        # Direction determines which color gets hit/protected
        move_dir = self._move_dir_from_color(trans.move_color) or 0
        self._pending_head_move = move_dir

        if move_dir == -1:  # Move Left (White)
            self.white_pt_adj += 2
            target_color = "white"
        elif move_dir == 1:  # Move Right (Green)
            self.green_pt_adj += 2
            target_color = "green"
        else:
            target_color = "none"

        yield emit(
            f"T{turn} - RESOLVE",
            [
                f"Cleansing Beam deals 2 damage to {target_color} creatures.",
                f"Vigor converts damage: {target_color} creatures get two +1/+1 counters.",
                f"Head move of {move_dir} is pending."
            ]
        )

    def _resolve_coalition_victory(self, turn: int, stack: List[str], emit) -> Iterator[Frame]:
        """Resolve Coalition Victory: Check for halt condition."""
        trans = self._current_trans

        stack.pop()  # Coalition Victory
        stack.pop()  # Wild Evocation

        if trans and is_halt_transition(trans):
            self.halted = True
            self.winner = "Alice"
            old_state = self.state
            self.state = trans.next_state

            yield emit(
                "HALT",
                ["Alice controls lands and creatures of every color. Alice wins!"],
                state_from=old_state,
                state_to=trans.next_state,
            )
        else:
            yield emit(f"T{turn} - RESOLVE", ["Coalition Victory resolves. No win condition met."])

    def _resolve_soul_snuffers(self, turn: int, stack: List[str], emit) -> Iterator[Frame]:
        """Resolve Soul Snuffers: Apply -1/-1, then move head and reset offsets."""
        trans = self._current_trans
        old_state = self.state
        self.state = trans.next_state if trans else self.state

        self.alice_battlefield.append("Soul Snuffers")
        stack.pop()  # Soul Snuffers
        stack.pop()  # Wild Evocation
        yield emit(
            f"T{turn} - RESOLVE",
            [
                "Soul Snuffers resolves and enters the battlefield."
            ],
        )
        # Soul Snuffers ETB: Global -1/-1
        self.white_pt_adj -= 1
        self.green_pt_adj -= 1

        yield emit(
            f"T{turn} - SBA",
            [
                "Global Effect: All creatures get a -1/-1 counter."
            ],
        )

        # 1. State-based actions: Soul Snuffers dies
        stack.append("Dread of Night")
        stack.append("Dread of Night")
        
        yield emit(
            f"T{turn} - SBA",
            [
                "Dread of Night (x2) reduces Soul Snuffers toughness to 0.",
            ],
        )
        stack.pop()
        stack.pop()
        self.alice_battlefield.remove("Soul Snuffers")
        yield emit(
            f"T{turn} - SBA",
            [
                "Soul Snuffers dies.",
            ],
        )



        # 2. State update & head movement
        old_head = self.head
        move_dir = self._pending_head_move
        self.head += move_dir
        
        # Update the sticky movement direction
        if move_dir != 0:
            self._last_move_dir = move_dir
                
        self._pending_head_move = 0
            
        # Reset adjusted PT
        self.white_pt_adj = 0
        self.green_pt_adj = 0

        yield emit(
            f"T{turn} - UPDATE",
            [
                f"STATE UPDATE: {old_state} -> {self.state}.",
                f"Head moved to {self.head}.",
            ],
            state_from=old_state,
            state_to=self.state,
            head_from=old_head,
            head_to=self.head,
            changed_positions=[old_head, self.head],
        )

        self._step_completed_flag = True

    def _is_step_complete(self) -> bool:
        """Check if the computational step is complete."""
        return self._step_completed_flag


# --- Scenario Loading/Saving ---

def load_scenario(file_path: str) -> GameLikeMachine:
    """
    Load a machine configuration from a JSON file.

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

    Raises:
        ValueError: If the file format is invalid
    """
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError(f"Scenario must be a JSON object, got {type(data).__name__}")

    machine = GameLikeMachine()
    machine.state = data.get("state", "q1")
    machine.head = int(data.get("head", 0))

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
        machine: GameLikeMachine, file_path: str, *, name: str = "", description: str = ""
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
        machine = GameLikeMachine()

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