# Python 3.10.6
# MTG Turing Machine - core engine

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Iterator

from UniversalTuringMachineTransitions import BLANK, Color, CreatureType, State, Transition, lookup


@dataclass(frozen=True)
class Frame:
    """
    A single visual frame within a computational step.
    The UI should render the board *after* any state changes that occurred before the yield.
    """
    step_index: int
    substep_index: int
    phase: str
    stack: List[str] = field(default_factory=list)
    narration: List[str] = field(default_factory=list)
    cards_on_hand: List[str] = field(default_factory=list)
    deck: List[str] = field(default_factory=list)

    # --- diff payload (optional; used by the UI for highlights) ---
    head_from: Optional[int] = None
    head_to: Optional[int] = None

    read_pos: Optional[int] = None
    read_type: Optional[CreatureType] = None

    written_pos: Optional[int] = None
    written_token_id: Optional[int] = None
    written_type: Optional[CreatureType] = None

    attached_to_token_id: Optional[int] = None  # Illusory Gains target (if any)

    state_from: Optional[State] = None
    state_to: Optional[State] = None

    left_shift: Optional[int] = None
    right_shift: Optional[int] = None

    changed_positions: List[int] = field(default_factory=list)
    phased_out: List[str] = field(default_factory=list)


class MachineError(Exception):
    """Base error for the simulator."""


class MachineHaltedError(MachineError):
    """Raised when stepping a halted machine."""


class NoTransitionError(MachineError):
    """Raised when no transition exists for (state, read_type)."""

    def __init__(self, state: State, read_type: CreatureType):
        super().__init__(f"No transition for state={state}, read_type={read_type}")
        self.state = state
        self.read_type = read_type


class InvalidMoveError(MachineError):
    """Raised when a transition implies an invalid movement."""


@dataclass(frozen=True)
class TokenPermanent:
    token_id: int
    creature_type: CreatureType
    color: Optional[Color] = None
    tapped: bool = False
    plus1_counters: int = 0
    minus1_counters: int = 0


@dataclass
class GameLikeMachine:
    """
    A minimal simulator of the paper’s MTG construction:
    - tape cells are creature-type tokens
    - Infest 'reads' by killing the head token
    - Reanimator/Necromancer trigger 'writes' by creating a new token type + color for movement
    - tapped token encodes 'state change' timing trick (Mesmeric Orb / skip Coalition Victory draw)
    """
    tape: Dict[int, TokenPermanent] = field(default_factory=dict)
    head: int = 0
    state: State = "q1"
    step_index: int = 0
    halted: bool = False
    winner: Optional[str] = None
    _next_token_id: int = 1
    illusory_gains_attached_to: Optional[int] = None  # token_id
    cards_on_hand: List[str] = field(default_factory=lambda: ["Infest"])
    deck: List[str] = field(default_factory=lambda: ["Cleansing Beam", "Coalition Victory", "Soul Snuffers"])
    alice_battlefield: List[str] = field(default_factory=lambda: [
        "Dread of Night", "Dread of Night", 
        "Wheel of Sun and Moon", "Steely Resolve", 
        "Vigor", "Mesmeric Orb", "Ancient Tomb", 
        "Prismatic Omen", "Choke", "Blazing Archon"
    ])

    def _new_token(
        self,
        *,
        creature_type: CreatureType,
        color: Optional[Color] = None,
        tapped: bool = False,
        plus1_counters: int = 0,
        minus1_counters: int = 0,
    ) -> TokenPermanent:
        t = TokenPermanent(
            token_id=self._next_token_id,
            creature_type=creature_type,
            color=color,
            tapped=tapped,
            plus1_counters=plus1_counters,
            minus1_counters=minus1_counters,
        )
        self._next_token_id += 1
        return t

    def get_token(self, pos: int) -> TokenPermanent:
        # Blank cells are implicit tokens (not stored on the battlefield until written)
        if pos in self.tape:
            return self.tape[pos]
        
        # According to the paper, tokens left of head are green, right/at head are white.
        # Cephalid is the blank symbol.
        color = "green" if pos < self.head else "white"
        return TokenPermanent(token_id=0, creature_type=BLANK, color=color, tapped=False)

    def initialize_default_library(self):
        """Initializes Alice's library with the required rotation of spells."""
        self.deck = ["Cleansing Beam", "Coalition Victory", "Soul Snuffers"]

    def set_token(self, pos: int, token: TokenPermanent) -> None:
        self.tape[pos] = token

    def _move_dir_from_color(self, color: Color) -> Optional[int]:
        if color == "white":
            return -1
        if color == "green":
            return 1
        return None  # blue means HALT token in this construction

    def frames_for_next_step(self) -> Iterator[Frame]:
        """
        Produce MTG-like frames for one computational step using a universal logic:
        1. Alice Upkeep: Wild Evocation casts a card from hand.
        2. Resolution: The spell resolves, then Wheel of Sun and Moon moves it to deck.
        3. Draw: Alice draws a card.
        4. Bob's Turn: (Simplified pass).
        Loops until the 'computational step' (the write/move logic) is logically complete.
        """
        if self.halted:
            raise MachineHaltedError("Machine already halted")

        self.step_index += 1
        sub = 0
        stack: List[str] = []
        current_phased_out: List[str] = []

        def emit(phase: str, narration: List[str], **diff) -> Frame:
            nonlocal sub
            sub += 1
            # If phased_out is not explicitly passed in diff, use the current_phased_out state
            final_phased_out = diff.pop("phased_out", current_phased_out)
            return Frame(
                step_index=self.step_index,
                substep_index=sub,
                phase=phase,
                stack=list(stack),
                narration=list(narration),
                cards_on_hand=list(self.cards_on_hand),
                deck=list(self.deck),
                phased_out=list(final_phased_out),
                **diff,
            )

        # In this simulator, a 'computational step' is the full rotation of Alice's spells
        # until a state update or halt occurs.
        turn_count = 1
        while True:
            # Update phasing for Alice's turn: Machine's current state engine phases IN (others OUT)
            current_phased_out = ["q2"] if self.state == "q1" else ["q1"]

            # --- Alice Untap Step ---
            untapped_any = False
            for pos, tok in list(self.tape.items()):
                if tok.tapped:
                    # Untap the token
                    self.tape[pos] = TokenPermanent(
                        token_id=tok.token_id,
                        creature_type=tok.creature_type,
                        color=tok.color,
                        tapped=False,
                        plus1_counters=tok.plus1_counters,
                        minus1_counters=tok.minus1_counters
                    )
                    untapped_any = True

            yield emit(f"T{turn_count} - UNTAP", [f"Alice's Turn {turn_count} begins. Untap Step."])

            # Mesmeric Orb check: triggered by the act of untapping
            if untapped_any:
                stack.append("Mesmeric Orb")
                yield emit(f"T{turn_count} - TRIGGER", ["Permanents untapped: Mesmeric Orb triggers."])
                
                # Mill logic: remove Coalition Victory if it's in the deck
                if "Coalition Victory" in self.deck:
                    self.deck.remove("Coalition Victory")
                    
                    # Wheel of Sun and Moon replacement effect
                    stack.append("Wheel of Sun and Moon")
                    yield emit(f"T{turn_count} - REPLACEMENT", ["Wheel of Sun and Moon triggers: Coalition Victory is moved to the bottom of the library instead of the graveyard."])
                    self.deck.append("Coalition Victory")
                    stack.pop()
                    
                    yield emit(f"T{turn_count} - RESOLVE", ["Mesmeric Orb resolves: Alice mills Coalition Victory (moved to bottom)."])
                else:
                    yield emit(f"T{turn_count} - RESOLVE", ["Mesmeric Orb resolves: Alice mills a card."])
                stack.pop()

            # --- Alice Upkeep ---
            yield emit(f"T{turn_count} - UPKEEP", ["Upkeep Step."])

            # --- Wild Evocation ---
            stack.append("Wild Evocation")
            yield emit(f"T{turn_count} - TRIGGER", ["Wild Evocation triggers: Alice must cast a card from her hand."])
            spell_name = None
            if not self.cards_on_hand:
                stack.pop()
                yield emit(f"T{turn_count} - UPKEEP", ["Alice has no cards on hand to cast."])
            else:
                # Alice casts the first card in her hand (deterministic for this machine)
                spell_name = self.cards_on_hand.pop(0)
                stack.append(spell_name)
                yield emit(f"T{turn_count} - CAST", [f"Wild Evocation resolves. Alice casts {spell_name}."])

                # --- Spell Resolution ---
                if spell_name == "Infest":
                    yield from self._resolve_infest(turn_count, stack, emit)
                elif spell_name == "Cleansing Beam":
                    yield from self._resolve_cleansing_beam(turn_count, stack, emit)
                elif spell_name == "Coalition Victory":
                    yield from self._resolve_coalition_victory(turn_count, stack, emit)
                elif spell_name == "Soul Snuffers":
                    yield from self._resolve_soul_snuffers(turn_count, stack, emit)
                else:
                    stack.pop() # Unknown spell whiffs
                
                    # Check for halt immediately after resolution (e.g. Coalition Victory)
                    if self.halted:
                        break

                # After any Alice spell resolves, Wheel of Sun and Moon triggers
                if spell_name in ["Infest", "Cleansing Beam", "Coalition Victory", "Soul Snuffers"]:
                    stack.append("Wheel of Sun and Moon")
                    self.deck.append(spell_name)
                    yield emit(f"T{turn_count} - REPLACEMENT", [f"Wheel of Sun and Moon moves {spell_name} to the bottom of the library."])
                    stack.pop()

            # --- Alice Draw ---
            if self.deck:
                drawn = self.deck.pop(0)
                self.cards_on_hand.append(drawn)
                yield emit(f"T{turn_count} - DRAW", [f"Alice draws {drawn}."])
                yield emit(f"T{turn_count} - ENDSTEP", ["Alice has no legal moves.", "Alice' turn ends."])

            # Update phasing for Bob's turn: Machine's current state engine phases OUT
            current_phased_out = ["q1"] if self.state == "q1" else ["q2"]

            if self.state == "q1":
                bob_phased_out = ["q1"]
            else:
                bob_phased_out = ["q2"]

            yield emit(f"T{turn_count} - BOB", ["Bob's turn begin.", "Bob has no legal moves.", "Bob's turn ends."], phased_out=bob_phased_out)
            
            # Update current_phased_out for the potential loop back to Alice or completion
            # After Bob's turn, we are back to Alice's "active" phasing state.
            current_phased_out = ["q2"] if self.state == "q1" else ["q1"]

            # Logical Step ends AFTER Soul Snuffers is cast and rotation is complete
            if spell_name == "Soul Snuffers":
                break
            
            turn_count += 1

        yield emit("END STEP", ["End of computational step."])

    def _resolve_infest(self, turn, stack, emit) -> Iterator[Frame]:
        # Infest logic: Read the current token
        token_to_read = self.get_token(self.head)
        read_type = token_to_read.creature_type
        head_pos = self.head
        state_before = self.state

        stack.pop() # Pop Infest
        stack.pop() # Pop Wild Evocation
        yield emit(f"T{turn} - RESOLVE", 
                   [f"Infest resolves. The {read_type} at position {self.head} dies."],
                   read_pos=head_pos, read_type=read_type, changed_positions=[head_pos])

        # Lookup transition
        try:
            trans = lookup(self.state, read_type)
        except KeyError:
            raise NoTransitionError(self.state, read_type)

        # Trigger Necromancer/Reanimator
        trigger_card = "Xathrid Necromancer" if trans.tapped else "Rotlung Reanimator"
        stack.append(trigger_card)
        yield emit(f"T{turn} - TRIGGER", [f"{trigger_card} triggers: create a {trans.write_type} token."])

        # Create new token
        written = self._new_token(creature_type=trans.write_type, color=trans.move_color, tapped=trans.tapped)
        self.set_token(self.head, written)
        self.illusory_gains_attached_to = written.token_id
        self._current_trans = trans # Store for Cleansing Beam
        self._last_written = written
        stack.pop()
        yield emit(f"T{turn} - RESOLVE", 
                   [f"Trigger resolves: write {trans.write_type} at {self.head}. Tapped={trans.tapped}."],
                   written_pos=head_pos, written_token_id=written.token_id, 
                   written_type=written.creature_type, attached_to_token_id=written.token_id,
                   changed_positions=[head_pos])

    def _resolve_cleansing_beam(self, turn, stack, emit) -> Iterator[Frame]:
        trans = getattr(self, "_current_trans", None)
        written = getattr(self, "_last_written", None)
        stack.pop() # Pop Beam
        stack.pop() # Pop Wild Evocation

        if not trans or not written:
            yield emit(f"T{turn} - RESOLVE", ["Cleansing Beam resolves but finds no targets."])
            return

        # Movement check
        move_dir = self._move_dir_from_color(trans.move_color)
        if move_dir is None:
            move_dir = 0
        old_head = self.head

        self.head += move_dir
        yield emit(f"T{turn} - RESOLVE",
                   [f"Cleansing Beam resolves. Head moves to {self.head}."],
                   head_from=old_head, head_to=self.head, changed_positions=[old_head, self.head])

    def _resolve_coalition_victory(self, turn, stack, emit) -> Iterator[Frame]:
        trans = getattr(self, "_current_trans", None)
        stack.pop()
        stack.pop()
        # HALT Check
        if trans and trans.move_color == "blue" and trans.write_type == "Assassin":
            self.halted = True
            self.winner = "Alice"
            self.state = trans.next_state
            # This yield is critical for the server/UI to see the halt
            yield emit("HALT", ["Alice controls lands and creatures of every color. Alice wins!"],
                       state_from=self.state, state_to=trans.next_state)
            return
        else:
            yield emit(f"T{turn} - RESOLVE", ["Coalition Victory resolves. No win condition met."])

    def _resolve_soul_snuffers(self, turn, stack, emit) -> Iterator[Frame]:
        trans = getattr(self, "_current_trans", None)
        old_state = self.state
        self.state = trans.next_state if trans else self.state

        # Soul Snuffers enters Alice's battlefield
        self.alice_battlefield.append("Soul Snuffers")
        stack.pop() # Pop Snuffers
        stack.pop() # Pop Wild Evocation
        
        yield emit(f"T{turn} - RESOLVE", 
                   ["Soul Snuffers resolves and enters the battlefield.",
                    "When Soul Snuffers enters the battlefield, put a -1/-1 counter on each creature."])

        # State-based actions: Dread of Night kills Soul Snuffers
        stack.append("Dread of Night")
        stack.append("Dread of Night")
        yield emit(f"T{turn} - SBA",
                   ["Dread of Night State Based Action is performed twice: Black Creatures get -1/-1.",
                    "The two -1/-1 counters reduces toughness of Soul Snuffers to 0.",
                    "Soul Snuffers dies."])
        
        self.alice_battlefield.remove("Soul Snuffers")
        stack.pop()
        stack.pop()

        yield emit(f"T{turn} - RESOLVE", 
                   [f"STATE UPDATE: {old_state} -> {self.state}."],
                   state_from=old_state, state_to=self.state)




def load_scenario(file_path: str) -> GameLikeMachine:
    """
    Load a scenario JSON file and return a ready-to-run GameLikeMachine.

    Expected format:
    {
      "name": "...",            // optional
      "description": "...",     // optional
      "state": "q1",
      "head": 0,
      "tape": {"0": "Rhino", "1": "Elf", ...}
    }
    Unmentioned tape positions default to BLANK (Cephalid).
    """
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError(f"Scenario file must contain a JSON object, got {type(data).__name__}")

    m = GameLikeMachine()
    m.state = data.get("state", "q1")
    m.head = int(data.get("head", 0))

    # Load deck/hand if present in JSON, otherwise class defaults remain
    if "cards_on_hand" in data:
        m.cards_on_hand = data["cards_on_hand"]
    if "deck" in data:
        m.deck = data["deck"]

    tape_raw = data.get("tape", {})
    if not isinstance(tape_raw, dict):
        raise ValueError(f"'tape' must be a JSON object mapping position -> creature type")

    for pos_str, creature_type in tape_raw.items():
        try:
            pos = int(pos_str)
        except (TypeError, ValueError):
            raise ValueError(f"Tape position must be an integer, got {pos_str!r}")
        if not isinstance(creature_type, str):
            raise ValueError(f"Tape value at position {pos} must be a creature type string, got {type(creature_type).__name__}")
        
        # Initialize color based on position relative to head (including Cephalids if explicitly listed)
        color = "green" if pos < m.head else "white"
        token = m._new_token(creature_type=creature_type, color=color)
        m.set_token(pos, token)

    # Ensure head has a physical token for Illusory Gains to attach to
    head_token = m.tape.get(m.head)
    if head_token is None:
        # Create an explicit Cephalid token at the head position
        explicit_blank = m._new_token(creature_type=BLANK, color="white")
        m.set_token(m.head, explicit_blank)
        m.illusory_gains_attached_to = explicit_blank.token_id
    else:
        m.illusory_gains_attached_to = head_token.token_id

    return m

def save_scenario(m: GameLikeMachine, file_path: str, *, name: str = "", description: str = "") -> None:
    """
    Save the current machine state as a scenario JSON file (can be loaded later).
    """
    tape_out: Dict[str, str] = {}
    for pos, tok in m.tape.items():
        ctype = getattr(tok, "creature_type", BLANK)
        if ctype != BLANK:
            tape_out[str(pos)] = ctype

    data = {
        "name": name,
        "description": description,
        "state": m.state,
        "head": m.head,
        "tape": tape_out,
    }
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        scenario_path = sys.argv[1]
        print(f"Loading scenario: {scenario_path}")
        machine = load_scenario(scenario_path)
    else:
        machine = GameLikeMachine()
        # Simple CLI runner - run one step and print results
    print(f"Initial state: {machine.state}, head: {machine.head}, halted: {machine.halted}")
    print("Running one step...")

    try:
        for frame in machine.frames_for_next_step():
            print(f"  [{frame.phase}] {', '.join(frame.narration)}")
            if frame.phase == "END STEP":
                break
    except Exception as e:
        print(f"Error: {e}")

    print(f"Final state: {machine.state}, head: {machine.head}, halted: {machine.halted}")
    print("\nFor interactive visualization, run: python web_server.py")