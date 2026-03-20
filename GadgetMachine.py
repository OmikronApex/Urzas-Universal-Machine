from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional, Union
from MTGCommon import BaseMTGMachine, TokenPermanent, Frame, BLANK
import json

@dataclass
class ModularGadgetMachine(BaseMTGMachine):
    """The 2024 construction using Choice Gadgets and Player Control."""
    engine_name: str = "modular_2024"

    # controllers: token_id -> Player Name
    controllers: Dict[int, str] = field(default_factory=dict)
    
    # connections: gadget_id -> { "input": token_id, "outputs": [token_id, ...] }
    gadgets: Dict[str, dict] = field(default_factory=dict)

    def __post_init__(self):
        # 4 Players are standard for the 2024 modular construction
        self.players = ["Alice", "Bob", "Charlie", "Desdemona"]
        if not self.alice_battlefield:
            self.alice_battlefield = ["Confusion in the Ranks", "Wheel of Sun and Moon"]
        if not self.deck:
            self.deck = ["Peer through Depths", "Donate", "Artificial Evolution"]

    def get_token(self, pos: Union[int, str]) -> TokenPermanent:
        return self.tape.get(pos, TokenPermanent(token_id=0, creature_type=BLANK))

    def get_visible_tape(self) -> Dict[Union[int, str], TokenPermanent]:
        return self.tape

    def get_extra_snapshot_data(self) -> dict:
        return {"controllers": self.controllers}

    def get_phased_out_labels(self) -> List[str]:
        return []

    def _resolve_spell(self, spell_name: str, turn: int, stack: List[str], emit) -> Iterator[Frame]:
        """Implement modular gadget resolution."""
        if spell_name == "Peer through Depths":
            yield from self._resolve_clock_cycle(turn, stack, emit)
        elif spell_name == "Donate":
            yield from self._resolve_control_transfer(turn, stack, emit)
        else:
            stack.pop()
            yield emit(f"T{turn} - RESOLVE", [f"{spell_name} resolves but has no targets."])

    def _resolve_clock_cycle(self, turn: int, stack: List[str], emit) -> Iterator[Frame]:
        """Simulate the 'Clock' gadget advancing the signal."""
        stack.pop() # Peer
        
        # In the 2024 paper, Peer through Depths helps Alice find the next trigger.
        # Logic: Find tokens controlled by Bob/Charlie and trigger swaps.
        narration = ["Alice peers through depths, identifying the next gadget instruction."]
        
        # Placeholder for actual trigger logic:
        # If a specific signal creature is controlled by Bob, Alice moves the 'head'
        yield emit(f"T{turn} - RESOLVE", narration)
        
        # Advance the computational state
        self._step_completed_flag = True

    def _resolve_control_transfer(self, turn: int, stack: List[str], emit) -> Iterator[Frame]:
        """Simulate a player gaining control of a gadget part."""
        stack.pop() # Donate
        yield emit(f"T{turn} - RESOLVE", ["Donate resolves: Alice gives Bob a permanent."])
