from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional, Union
from MTGCommon import BaseMTGMachine, TokenPermanent, Frame, MachineHaltedError, NoTransitionError
from UniversalTuringMachineTransitions import BLANK, Color, CreatureType, Transition, lookup, is_halt_transition


@dataclass
class Rogozhin218Machine(BaseMTGMachine):
    """
    The original (2,18) UTM implementation using Soul Snuffers and Infest.
    """
    engine_name: str = "rogozhin"

    # Rogozhin-specific state
    white_pt_adj: int = 0
    green_pt_adj: int = 0
    infest_active: bool = False
    _infest_cutoff_id: int = field(default=0, repr=False)

    _current_trans: Optional[Transition] = field(default=None, repr=False)
    _last_written: Optional[TokenPermanent] = field(default=None, repr=False)
    _pending_head_move: int = field(default=0, repr=False)
    _last_move_dir: int = field(default=1, repr=False)

    def __post_init__(self):
        # Default starting zones for Rogozhin
        if not self.cards_on_hand:
            self.cards_on_hand = ["Infest"]
        if not self.deck:
            self.deck = ["Cleansing Beam", "Coalition Victory", "Soul Snuffers"]
        if not self.alice_battlefield:
            self.alice_battlefield = [
                "Dread of Night", "Dread of Night", "Wheel of Sun and Moon",
                "Steely Resolve", "Mesmeric Orb", "Ancient Tomb",
                "Prismatic Omen", "Choke", "Vigor", "Blazing Archon",
            ]

    def get_token(self, pos: Union[int, str]) -> TokenPermanent:
        """
        Get the token at a tape position with calculated P/T.
        """
        # Rogozhin uses integer positions
        try:
            p = int(pos)
        except (ValueError, TypeError):
            p = 0

        if p in self.tape:
            tok = self.tape[p]
        else:
            # Decide color for implicit Cephalids
            if p < self.head:
                color = "green"
            elif p > self.head:
                color = "white"
            else:
                # Head position color matches the last direction moved
                color = "green" if self._last_move_dir == -1 else "white"

            tok = TokenPermanent(token_id=0, creature_type=BLANK, color=color, tapped=False)

        # Determine base P/T: 2/2 + distance from head
        dist = abs(self.head - p)
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
            power=base,
            toughness=base
        )

    def get_visible_tape(self) -> Dict[Union[int, str], TokenPermanent]:
        """Rogozhin implementation: return a radius around the head."""
        # Note: The view radius logic moved here from the web server
        try:
            head_pos = int(self.head)
        except (ValueError, TypeError):
            head_pos = 0

        view_radius = 15
        result = {}
        for pos in range(head_pos - view_radius, head_pos + view_radius + 1):
            result[pos] = self.get_token(pos)
        return result

    def _resolve_spell(self, spell_name: str, turn: int, stack: List[str], emit) -> Iterator[Frame]:
        """Dispatch spell resolution to Rogozhin-specific handlers."""
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

    def get_phased_out_labels(self) -> List[str]:
        """
        Rogozhin Phasing logic: Engines toggle every turn.
        If state is q1, the q1 engine is active (phased IN) on Alice's turns.
        """
        player = self.players[self.current_player_index]
        if self.state == "q1":
            return ["q2"] if player == "Alice" else ["q1"]
        # state == "q2"
        return ["q1"] if player == "Alice" else ["q2"]