# MTG Turing Machine Simulator

An implementation and visualization of the Magic: The Gathering (MTG) Universal Turing Machine, based on the research paper "Magic: The Gathering is Turing Complete".

This project simulates a game of MTG where the board state represents a Turing Machine's tape and Alice's deck/hand rotation drives the computational steps.

## Overview

The simulator mimics the specific card interactions required to perform computation:
- **Tape Cells:** Represented by creature tokens with specific types (e.g., Sliver, Elf, Rhino).
- **Read/Write Head:** Controlled by the position of Alice's `Illusory Gains`.
- **Instruction Execution:** Driven by Alice casting spells like `Infest` (to read/kill), `Rotlung Reanimator` (to write), and `Cleansing Beam` (to move the head).
- **State Changes:** Handled through the `Mesmeric Orb` timing trick and phasing mechanics.

## Project Structure

- `MTGSimulator.py`: The core engine that runs the game logic and produces step-by-step "frames".
- `UniversalTuringMachineTransitions.py`: Contains the (2,18) UTM transition table mapped to MTG creature types.
- `web_server.py`: A FastAPI-based server to host the interactive visualization.
- `web/`: Contains the frontend assets (HTML, CSS, JS) and card images.
- `scenarios/`: JSON files defining initial tape configurations and states.

## Getting Started

### Prerequisites

- Python 3.10.6
- `virtualenv`

### Installation

1. Clone the repository to your local machine.
2. Create and activate a virtual environment:
   ```bash
   virtualenv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install fastapi uvicorn pyyaml
   ```

### Running the Simulator

To launch the web interface:
1. Run the web server:
   ```bash
   python web_server.py
   ```
2. Open your browser and navigate to `http://127.0.0.1:60720`.
3. Select a scenario from the dropdown (e.g., `short_run.json`) and use the **Step** or **Autoplay** buttons to watch the computation unfold.

## Scenarios

Scenarios are defined in JSON format. Example structure:
```json
{
  "name": "Example",
  "state": "q1",
  "head": 0,
  "tape": {
    "0": "Rhino",
    "1": "Elf"
  }
}
```

## Credits

Based on the work of Alex Churchill, Stella Biderman, and Austin Herrick in "Magic: The Gathering is Turing Complete".
