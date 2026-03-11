# Python 3.10.6
import json
from typing import Dict, List, Optional
from UniversalTuringMachineTransitions import BLANK, UTM

FULL_UTM_ALPHABET = {
    "0": "Sliver",
    "1": "Aetherborn",
    "_": "Cephalid",    # Blank
    "+": "Basilisk",
    "-": "Demon",
    "*": "Elf",
    "!": "Faerie",
    "?": "Giant",
    ">": "Harpy",
    "<": "Illusion",
    "|": "Juggernaut",
    "#": "Kavu",
    "$": "Leviathan",
    "%": "Myr",
    "@": "Noggle",
    "&": "Orc",
    "~": "Pegasus",
    "X": "Rhino"       # The "Halt-trigger" symbol
}


class MTGCompiler:

    def __init__(self, symbol_mapping: Dict[str, str] = None):
        """
        :param symbol_mapping: Maps user chars to MTG types. Defaults to FULL_UTM_ALPHABET.
        """
        self.symbol_mapping = symbol_mapping or FULL_UTM_ALPHABET

    @classmethod
    def from_config(cls, config_path: str) -> "MTGCompiler":
        with open(config_path, "r") as f:
            data = json.load(f)
        return cls(data.get("mapping", {}))

    def compile_tape(self, high_level_tape: str, start_pos: int = 0) -> Dict[int, str]:
        """
        Translates a string like "1101" into {0: "Aetherborn", 1: "Aetherborn", ...}
        """
        tape = {}
        for i, char in enumerate(high_level_tape):
            if char not in self.symbol_mapping:
                raise ValueError(f"Symbol '{char}' not found in mapping.")
            tape[start_pos + i] = self.symbol_mapping[char]
        return tape

    def create_scenario(self,
                        name: str,
                        input_data: str,
                        start_state: str = "q1",
                        head_pos: int = 0) -> Dict:
        """
        Generates a data-only scenario dictionary ready for the simulator.
        """
        return {
            "name": name,
            "state": start_state,
            "head": head_pos,
            "tape": {str(k): v for k, v in self.compile_tape(input_data, start_pos=head_pos).items()},
            "meta": {
                "compiler_mapping": self.symbol_mapping,
                "input_string": input_data
            }
        }

    def create_program_scenario(
        self,
        *,
        name: str,
        assembler_code: str,
        initial_data: str = "",
        start_state: str = "q1",
        head_pos: int = 0,
    ) -> Dict:
        """
        Compile TAS layout code into a full scenario dict.
        """
        from MTGAssembler import MTGAssembler
        assembler = MTGAssembler()

        # The assembler.assemble() now returns the FULL scenario dict
        # { name, state, head, tape }
        scenario = assembler.assemble(assembler_code, initial_data=initial_data)

        # Apply overrides from UI if they weren't specified in the layout code
        if name:
            scenario["name"] = name

        # Add metadata for the UI
        scenario["meta"] = {
            "mode": "layout",
            "input_string": initial_data,
        }

        return scenario


def load_scenario_data(data: Dict) -> "GameLikeMachine":
    """
    Build a GameLikeMachine directly from a scenario dict (no file I/O).
    Same contract as MTGSimulator.load_scenario but takes a dict.
    """
    from MTGSimulator import GameLikeMachine

    if not isinstance(data, dict):
        raise ValueError(f"Scenario must be a dict, got {type(data).__name__}")

    m = GameLikeMachine()
    m.state = data.get("state", "q1")
    m.head = int(data.get("head", 0))

    # Initialize library and hand correctly: hand has the first spell, library has the rest.
    m.cards_on_hand = data.get("cards_on_hand", ["Infest"])
    m.deck = data.get("deck", ["Cleansing Beam", "Coalition Victory", "Soul Snuffers"])

    tape_raw = data.get("tape", {})
    if not isinstance(tape_raw, dict):
        raise ValueError("'tape' must be a dict mapping position -> creature type")

    for pos_str, creature_type in tape_raw.items():
        pos = int(pos_str)
        if not isinstance(creature_type, str):
            raise ValueError(f"Tape value at position {pos} must be a string")
        
        # Initialize color based on position relative to head
        color = "green" if pos < m.head else "white"
        token = m._new_token(creature_type=creature_type, color=color)
        m.set_token(pos, token)

    # Ensure head has a physical token for Illusory Gains
    head_token = m.tape.get(m.head)
    if head_token is None:
        # Create an explicit Cephalid token at the head position
        explicit_blank = m._new_token(creature_type=BLANK, color="white")
        m.set_token(m.head, explicit_blank)
        m.illusory_gains_attached_to = explicit_blank.token_id
    else:
        m.illusory_gains_attached_to = head_token.token_id

    return m


if __name__ == "__main__":
    mapping = {
        "0": "Sliver",
        "1": "Aetherborn",
        "_": "Cephalid"
    }
    compiler = MTGCompiler(mapping)
    scenario = compiler.create_scenario("Compiled Binary String", "1101")
    print(json.dumps(scenario, indent=2))
