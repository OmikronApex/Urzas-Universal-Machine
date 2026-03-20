from __future__ import annotations
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from typing import Dict, Iterator, List, Optional, Union
from UniversalTuringMachineTransitions import Color, CreatureType, BLANK

@dataclass(frozen=True)
class Frame:
    step_index: int
    substep_index: int
    phase: str
    stack: List[str] = field(default_factory=list)
    narration: List[str] = field(default_factory=list)
    cards_on_hand: List[str] = field(default_factory=list)
    deck: List[str] = field(default_factory=list)
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
    state_from: Optional[str] = None
    state_to: Optional[str] = None
    left_shift: Optional[int] = None
    right_shift: Optional[int] = None
    changed_positions: List[int] = field(default_factory=list)
    phased_out: List[str] = field(default_factory=list)

@dataclass(frozen=True)
class TokenPermanent:
    token_id: int
    creature_type: CreatureType
    color: Optional[Color] = None
    tapped: bool = False
    plus1_counters: int = 0
    minus1_counters: int = 0
    power: int = 2
    toughness: int = 2

class MachineError(Exception):
    """Base exception for simulator errors."""

class MachineHaltedError(MachineError):
    """Raised when attempting to step a halted machine."""

class NoTransitionError(MachineError):
    """Raised when no transition exists for (state, read_type)."""
    def __init__(self, state: str, read_type: str):
        super().__init__(f"No transition for state={state}, read_type={read_type}")
        self.state = state
        self.read_type = read_type

@dataclass
class BaseMTGMachine(ABC):
    engine_name: str = "base"
    tape: Dict[Union[int, str], TokenPermanent] = field(default_factory=dict)
    head: Union[int, str] = 0
    state: str = "q1"
    step_index: int = 0
    halted: bool = False
    winner: Optional[str] = None
    _next_token_id: int = 1
    illusory_gains_attached_to: Optional[int] = None
    cards_on_hand: List[str] = field(default_factory=list)
    deck: List[str] = field(default_factory=list)
    alice_battlefield: List[str] = field(default_factory=list)
    _step_completed_flag: bool = field(default=False, repr=False)
    players: List[str] = field(default_factory=lambda: ["Alice", "Bob"])
    current_player_index: int = 1

    def _new_token(self, **kwargs) -> TokenPermanent:
        token = TokenPermanent(token_id=self._next_token_id, **kwargs)
        self._next_token_id += 1
        return token

    def set_token(self, pos: Union[int, str], token: TokenPermanent) -> None:
        self.tape[pos] = token

    @abstractmethod
    def get_token(self, pos: Union[int, str]) -> TokenPermanent: pass

    @abstractmethod
    def get_visible_tape(self) -> Dict[Union[int, str], TokenPermanent]: pass

    @abstractmethod
    def get_phased_out_labels(self) -> List[str]: pass

    def get_extra_snapshot_data(self) -> dict: return {}

    @abstractmethod
    def _resolve_spell(self, spell_name: str, turn: int, stack: List[str], emit) -> Iterator[Frame]: pass

    # ... move frames_for_next_step, _alice_turn, _untap_step, _wild_evocation etc here ...
