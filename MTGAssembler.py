# Python 3.10.6
import re
from typing import Dict, List, Tuple, Any
from MTGCompiler import FULL_UTM_ALPHABET, BLANK

class MTGAssembler:
    """
    A sophisticated Tape Layout engine for the (2,18) UTM.
    Allows users to define patterns and place them at specific offsets.
    """

    def __init__(self):
        self.symbols = FULL_UTM_ALPHABET

    def _parse_layout(self, code: str) -> List[Tuple[int, List[str]]]:
        """
        Parses layout code while strictly ignoring metadata lines.
        """
        layout = []
        lines = [l.strip() for l in code.split('\n') if l.strip() and not l.startswith('#')]
    
        current_offset = 0
        for line in lines:
            # Strictly skip metadata lines so they don't leak into tape symbols
            if re.match(r"^(HEAD|STATE):", line, re.IGNORECASE):
                continue

            # Handle OFFSET command
            off_match = re.match(r"OFFSET\s+(-?\d+):\s*(.*)", line, re.IGNORECASE)
            if off_match:
                offset, data = off_match.groups()
                symbols = data.split()
                layout.append((int(offset), symbols))
            else:
                # Default behavior: treat line as sequence of symbols starting at current_offset
                symbols = line.split()
                layout.append((current_offset, symbols))
                current_offset += len(symbols)
        return layout

    def assemble(self, code: str, initial_data: str = "") -> Dict[str, Any]:
        """
        Returns a full scenario dict for the simulator.
        """
        tape_dict = {}
        
        # 1. Process initial_data (simple string) as base
        for i, char in enumerate(initial_data):
            if char in self.symbols:
                tape_dict[i] = self.symbols[char]

        # 2. Process Layout code (overwrites/extends base)
        layout = self._parse_layout(code)
        for offset, symbols in layout:
            for i, sym in enumerate(symbols):
                # Filter out metadata lines that might have leaked into symbols
                if sym.upper().endswith(':') or sym.upper() in ["HEAD", "STATE"]:
                    continue
                creature = self.symbols.get(sym, sym) 
                tape_dict[offset + i] = creature

        # 3. Extract Metadata (Head/State)
        head = 0
        state = "q1"
        for line in code.split('\n'):
            clean_line = line.strip()
            # Explicitly handle metadata and ignore the rest
            if clean_line.upper().startswith("HEAD:"):
                try:
                    head = int(clean_line.split(":")[1].strip())
                except (ValueError, IndexError): pass
            elif clean_line.upper().startswith("STATE:"):
                try:
                    state = clean_line.split(":")[1].strip()
                except IndexError: pass

        return {
            "name": "Assembled Tape",
            "state": state,
            "head": head,
            "tape": {str(k): v for k, v in tape_dict.items() if v != BLANK}
        }