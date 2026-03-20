from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional, Union
from MTGCommon import BaseMTGMachine, TokenPermanent, Frame, BLANK
from UniversalTuringMachineTransitions import Color, CreatureType


@dataclass
class ModularGadgetMachine(BaseMTGMachine):
    """
    The 2024 construction using Choice Gadgets and Player Control.
    Signal is represented by player control of specific tokens.
    """
    engine_name: str = "gadget"

    # controllers: token_id -> Player Name ("Alice", "Bob", "Charlie", "Desdemona")
    controllers: Dict[int, str] = field(default_factory=dict)

    # gadget_map: token_id -> { "type": "choice", "owner": "Bob", "outputs": [tid1, tid2] }
    gadget_map: Dict[int, dict] = field(default_factory=dict)

    def __post_init__(self):
        self.players = ["Alice", "Bob", "Charlie", "Desdemona"]
        # Standard initial setup for 2024 logic
        if not self.alice_battlefield:
            self.alice_battlefield = [
                "Confusion in the Ranks",
                "Wheel of Sun and Moon",
                "Privileged Position",
                "Ancient Tomb",
                "Prismatic Omen"
            ]
        if not self.bob_battlefield:
            self.bob_battlefield = [
                "Artificial Evolution",
                "Donate",
                "Confusion in the Ranks"
            ]
        if not self.deck:
            self.deck = [
                "Peer through Depths",
                "Donate",
                "Artificial Evolution",
                "Peer through Depths",
                "Peer through Depths"
            ]
        if not self.cards_on_hand:
            self.cards_on_hand = ["Peer through Depths"]

    def get_token(self, pos: Union[int, str]) -> TokenPermanent:
        return self.tape.get(pos, TokenPermanent(token_id=0, creature_type=BLANK))

    def get_visible_tape(self) -> Dict[Union[int, str], TokenPermanent]:
        return self.tape

    def get_extra_snapshot_data(self) -> dict:
        return {"controllers": self.controllers}

    def get_phased_out_labels(self) -> List[str]:
        return []

    def _resolve_spell(self, spell_name: str, turn: int, stack: List[str], emit) -> Iterator[Frame]:
        """Core modular logic resolution."""
        if spell_name == "Peer through Depths":
            yield from self._resolve_clock_cycle(turn, stack, emit)
        elif spell_name == "Donate":
            yield from self._resolve_donate(turn, stack, emit)
        else:
            stack.pop()
            yield emit(f"T{turn} - RESOLVE", [f"{spell_name} resolves but has no gadget effect."])

    def _resolve_clock_cycle(self, turn: int, stack: List[str], emit) -> Iterator[Frame]:
        """The 'Clock' triggers the current signal to move to the next gadget."""
        stack.pop() # Peer
        
        # 1. Identify the 'Signal' token (the one controlled by a non-Alice player)
        signal_token_id = None
        for tid, controller in self.controllers.items():
            if controller != "Alice":
                signal_token_id = tid
                break
        
        if signal_token_id is None:
            yield emit(f"T{turn} - RESOLVE", ["Alice peers through depths but finds no active signal."])
            self._step_completed_flag = True
            return

        # 2. Logic for 'Confusion in the Ranks' trigger
        # In the 2024 construction, Alice casts a spell, creates a token, 
        # and Confusion swaps it with the signal to move computation forward.
        yield emit(f"T{turn} - RESOLVE", [f"Clock Cycle: Processing signal from token #{signal_token_id}."])
        
        # For now, we simulate a state transition by ending the step
        self._step_completed_flag = True

    def _resolve_donate(self, turn: int, stack: List[str], emit) -> Iterator[Frame]:
        """Alice gives control of a permanent to Bob to set the initial signal."""
        stack.pop() # Donate
        # Placeholder: assign first token to Bob
        if self.tape:
            first_tid = list(self.tape.values())[0].token_id
            self.controllers[first_tid] = "Bob"
            yield emit(f"T{turn} - RESOLVE", [f"Donate: Bob now controls token #{first_tid} (Signal Start)."])
