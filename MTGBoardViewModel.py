# Python 3.10.6
# MTG board view + terminal renderer for the TM simulator.

from __future__ import annotations

from dataclasses import dataclass, field, asdict, is_dataclass
from typing import List, Optional, Tuple, Iterator, Any
import json
import sys
import time
import select
import os
from types import SimpleNamespace

from UniversalTuringMachineTransitions import BLANK, Color, CreatureType, State


# ── ANSI helpers ──────────────────────────────────────────────────────────────

class _Ansi:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    ITALIC  = "\033[3m"
    RED     = "\033[91m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    BLUE    = "\033[94m"
    WHITE   = "\033[97m"
    CYAN    = "\033[96m"
    MAGENTA = "\033[95m"
    BG_YELLOW = "\033[43m"
    BG_RED    = "\033[41m"


def _color_for_mtg(color: Optional[str]) -> str:
    if color == "white":
        return _Ansi.WHITE + _Ansi.BOLD
    if color == "green":
        return _Ansi.GREEN
    if color == "blue":
        return _Ansi.BLUE + _Ansi.BOLD
    return ""


def _colorize(text: str, ansi: str) -> str:
    if not ansi:
        return text
    return f"{ansi}{text}{_Ansi.RESET}"


# ── View dataclasses ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class StackItemView:
    name: str
    controller: str = "Alice"
    rules_text: str = ""


@dataclass(frozen=True)
class PermanentView:
    label: str
    pos: Optional[int] = None
    color: Optional[Color] = None
    tapped: bool = False
    is_head: bool = False
    has_marker: bool = False


@dataclass
class BoardViewModel:
    step: int
    active_player: str
    state: State
    head: int
    halted: bool
    winner: Optional[str]
    stack: List[StackItemView] = field(default_factory=list)
    battlefield: List[PermanentView] = field(default_factory=list)
    graveyard: List[str] = field(default_factory=list)
    narration: List[str] = field(default_factory=list)


# ── Rendering helpers ────────────────────────────────────────────────────────

def _token_box(text: str, width: int = 16, *, color_code: str = "", is_head: bool = False, has_marker: bool = False, tapped: bool = False) -> str:
    t = text[: width - 2]
    inner = f"{t:^{width-2}}"

    if tapped:
        inner = _colorize(inner, _Ansi.DIM + _Ansi.ITALIC + color_code)
    elif color_code:
        inner = _colorize(inner, color_code)

    if has_marker:
        bracket_l = _colorize("[", _Ansi.RED + _Ansi.BOLD)
        bracket_r = _colorize("]", _Ansi.RED + _Ansi.BOLD)
    elif is_head:
        bracket_l = _colorize("[", _Ansi.YELLOW + _Ansi.BOLD)
        bracket_r = _colorize("]", _Ansi.YELLOW + _Ansi.BOLD)
    else:
        bracket_l = "["
        bracket_r = "]"

    return f"{bracket_l}{inner}{bracket_r}"


def _render_zone(title: str, lines: List[str], *, width: int = 78) -> str:
    bar = _colorize("=" * width, _Ansi.DIM)
    colored_title = _colorize(f"{title:^{width}}", _Ansi.CYAN + _Ansi.BOLD)
    out: List[str] = [bar, colored_title, bar]
    if not lines:
        out.append(_colorize("(empty)", _Ansi.DIM))
    else:
        out.extend(lines)
    return "\n".join(out)


# ── Snapshot / replay helpers ────────────────────────────────────────────────

def _frame_to_jsonable(frame: Any) -> dict:
    if frame is None:
        return {}
    if is_dataclass(frame):
        d = asdict(frame)
    elif isinstance(frame, dict):
        d = dict(frame)
    else:
        d = dict(getattr(frame, "__dict__", {}))
    d.setdefault("stack", [])
    d.setdefault("narration", [])
    d.setdefault("changed_positions", [])
    return d


def _snapshot_machine(m: "GameLikeMachine") -> dict:
    tape_out: dict = {}
    for pos, tok in getattr(m, "tape", {}).items():
        tape_out[str(pos)] = {
            "token_id": getattr(tok, "token_id", 0),
            "creature_type": getattr(tok, "creature_type", BLANK),
            "color": getattr(tok, "color", None),
            "tapped": bool(getattr(tok, "tapped", False)),
            "plus1_counters": int(getattr(tok, "plus1_counters", 0)),
            "minus1_counters": int(getattr(tok, "minus1_counters", 0)),
        }
    return {
        "step_index": int(getattr(m, "step_index", 0)),
        "state": getattr(m, "state", "q1"),
        "head": int(getattr(m, "head", 0)),
        "halted": bool(getattr(m, "halted", False)),
        "winner": getattr(m, "winner", None),
        "illusory_gains_attached_to": getattr(m, "illusory_gains_attached_to", None),
        "blank": BLANK,
        "tape": tape_out,
    }


def save_frames_json(frames: List[Any], file_path: str) -> None:
    payload = {
        "version": 2,
        "frames": [_frame_to_jsonable(f) for f in frames],
    }
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)


def load_frames_json(file_path: str) -> List[Any]:
    with open(file_path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    frames = payload.get("frames", [])
    if not isinstance(frames, list):
        raise ValueError("Invalid replay file: 'frames' must be a list")
    out: List[Any] = []
    for d in frames:
        if not isinstance(d, dict):
            raise ValueError("Invalid replay file: each frame must be an object")
        d.setdefault("stack", [])
        d.setdefault("narration", [])
        d.setdefault("changed_positions", [])
        out.append(SimpleNamespace(**d))
    return out


def _machine_from_snapshot(snapshot: dict) -> Any:
    blank = snapshot.get("blank", BLANK)
    tape_raw = snapshot.get("tape", {}) or {}
    tape: dict = {}
    for k, v in tape_raw.items():
        try:
            pos = int(k)
        except (TypeError, ValueError):
            continue
        tape[pos] = SimpleNamespace(
            token_id=v.get("token_id", 0),
            creature_type=v.get("creature_type", blank),
            color=v.get("color", None),
            tapped=bool(v.get("tapped", False)),
            plus1_counters=int(v.get("plus1_counters", 0)),
            minus1_counters=int(v.get("minus1_counters", 0)),
        )

    class _SnapshotMachine:
        def __init__(self, snapshot_dict: dict, tape_dict: dict, blank_symbol: str):
            self.step_index = int(snapshot_dict.get("step_index", 0))
            self.state = snapshot_dict.get("state", "q1")
            self.head = int(snapshot_dict.get("head", 0))
            self.halted = bool(snapshot_dict.get("halted", False))
            self.winner = snapshot_dict.get("winner", None)
            self.illusory_gains_attached_to = snapshot_dict.get("illusory_gains_attached_to", None)
            self.tape = tape_dict
            self._blank = blank_symbol

        def get_token(self, pos: int):
            return self.tape.get(
                pos,
                SimpleNamespace(creature_type=self._blank, color=None, tapped=False, token_id=0),
            )

    return _SnapshotMachine(snapshot, tape, blank)


# ── Tape / camera helpers ────────────────────────────────────────────────────

def known_tape_range(m: "GameLikeMachine") -> Tuple[int, int]:
    if not m.tape:
        return (m.head, m.head)
    lo = min(min(m.tape.keys()), m.head)
    hi = max(max(m.tape.keys()), m.head)
    return (lo, hi)


def compute_camera_window(*, full_lo: int, full_hi: int, center: int, half_width: int) -> Tuple[int, int]:
    if full_lo > full_hi:
        full_lo, full_hi = full_hi, full_lo
    lo = center - half_width
    hi = center + half_width
    if lo < full_lo:
        hi += (full_lo - lo)
        lo = full_lo
    if hi > full_hi:
        lo -= (hi - full_hi)
        hi = full_hi
    if lo < full_lo:
        lo = full_lo
    if hi > full_hi:
        hi = full_hi
    return lo, hi


# ── Board view builder ───────────────────────────────────────────────────────

def build_board_view(
    m: "GameLikeMachine",
    last: Optional["StepLog"],
    *,
    radius: int = 6,
    camera_center: Optional[int] = None,
    frame: Optional[Any] = None,
) -> "BoardViewModel":
    vm = BoardViewModel(
        step=m.step_index,
        active_player="Alice",
        state=m.state,
        head=m.head,
        halted=m.halted,
        winner=m.winner,
    )

    changed_positions = set(getattr(frame, "changed_positions", []) or [])
    written_pos = getattr(frame, "written_pos", None)
    read_pos = getattr(frame, "read_pos", None)
    read_type = getattr(frame, "read_type", None)

    if frame is not None:
        for item in getattr(frame, "stack", []):
            vm.stack.append(StackItemView(name=item))
        vm.narration.extend(getattr(frame, "narration", []))
        phase = getattr(frame, "phase", None)
        sub = getattr(frame, "substep_index", None)
        if phase is not None:
            vm.narration.insert(0, f"Frame: {phase}" + (f" (substep {sub})" if sub is not None else ""))
    else:
        vm.stack.append(StackItemView(name="Infest", rules_text="Destroy (read) the head token."))
        if last is not None and not last.halted:
            vm.stack.append(StackItemView(name="Cleansing Beam", rules_text="Forces the movement via Vigor/counters."))
            if last.transition.tapped:
                vm.stack.append(StackItemView(name="Soul Snuffers", rules_text="Early (T3) due to tapped-token timing."))
            else:
                vm.stack.append(StackItemView(name="Coalition Victory", rules_text="Usually a whiff unless HALT token exists."))
                vm.stack.append(StackItemView(name="Soul Snuffers", rules_text="Late (T4) cleanup."))
        if last is not None and last.halted:
            vm.stack.append(StackItemView(name="Coalition Victory", rules_text="Condition satisfied → win the game."))

    full_lo, full_hi = known_tape_range(m)
    center = m.head if camera_center is None else camera_center
    win_lo, win_hi = compute_camera_window(full_lo=full_lo, full_hi=full_hi, center=center, half_width=radius)

    vm.narration.append(f"Battlefield extent: positions {full_lo}..{full_hi} (camera {win_lo}..{win_hi}, center={center}).")

    if win_lo > full_lo:
        vm.battlefield.append(PermanentView(label=f"... {full_lo}..{win_lo - 1} ..."))

    for pos in range(win_lo, win_hi + 1):
        tok = m.get_token(pos)
        tapped = getattr(tok, "tapped", False)
        color = getattr(tok, "color", None)
        token_id = getattr(tok, "token_id", 0)
        gains = ""
        if getattr(m, "illusory_gains_attached_to", None) == token_id and token_id != 0:
            gains = " IG"

        markers: List[str] = []
        if pos in changed_positions:
            markers.append("Δ")
        if written_pos is not None and pos == written_pos:
            markers.append("NEW")
        if read_pos is not None and pos == read_pos and read_type is not None:
            markers.append("DIED")

        marker_text = f" [{' '.join(markers)}]" if markers else ""
        tapped_text = "T" if tapped else "U"

        vm.battlefield.append(
            PermanentView(
                label=f"{pos}:{tok.creature_type} ({color or '-'},{tapped_text})#{token_id}{gains}{marker_text}",
                pos=pos,
                is_head=(pos == m.head),
                tapped=tapped,
                color=color,
                has_marker=bool(markers),
            )
        )

    if win_hi < full_hi:
        vm.battlefield.append(PermanentView(label=f"... {win_hi + 1}..{full_hi} ..."))

    if read_type is not None and read_pos is not None:
        vm.graveyard.append(f"{read_type} token (from position {read_pos})")
    elif last is not None:
        vm.graveyard.append(f"{last.read_type} token (from position {last.head_before})")

    if frame is None:
        if last is None:
            vm.narration.append("Ready: start of game loop. Press Enter to perform T1–T4 for the next computational step.")
        else:
            vm.narration.extend(last.notes[-6:])

    return vm


# ── Board renderer (ANSI-colored) ───────────────────────────────────────────

def render_mtg_board(vm: "BoardViewModel", *, width: int = 78) -> str:
    # Header
    state_color = _Ansi.GREEN if vm.state == "q1" else _Ansi.MAGENTA
    header = (
        f"{_Ansi.BOLD}STEP {vm.step}{_Ansi.RESET}"
        f" | Active: {_colorize(vm.active_player, _Ansi.YELLOW)}"
        f" | TM state={_colorize(vm.state, state_color + _Ansi.BOLD)}"
        f" | Head={_colorize(str(vm.head), _Ansi.YELLOW)}"
        f" | Halted={_colorize(str(vm.halted), _Ansi.RED + _Ansi.BOLD if vm.halted else '')}"
    )
    if vm.winner:
        header += f" | Winner: {_colorize(vm.winner, _Ansi.GREEN + _Ansi.BOLD)}"

    # Stack
    stack_lines = []
    for i, item in enumerate(reversed(vm.stack), start=1):
        line = f"  {_colorize(str(i) + '.', _Ansi.DIM)} {_colorize(item.controller, _Ansi.YELLOW)} - {_colorize(item.name, _Ansi.BOLD)}"
        if item.rules_text:
            line += f" {_colorize(':: ' + item.rules_text, _Ansi.DIM)}"
        stack_lines.append(line)

    # Battlefield
    bf_lines: List[str] = []
    row: List[str] = []
    for p in vm.battlefield:
        label = p.label
        if p.is_head:
            label = f"▶ {label}"
        color_code = _color_for_mtg(p.color)
        row.append(_token_box(label, width=18, color_code=color_code, is_head=p.is_head, has_marker=p.has_marker, tapped=p.tapped))

    per_line = max(1, width // 18)
    for i in range(0, len(row), per_line):
        bf_lines.append(" ".join(row[i : i + per_line]))

    # Graveyard
    gy_lines = [_colorize(g, _Ansi.RED) for g in vm.graveyard] if vm.graveyard else [_colorize("(none)", _Ansi.DIM)]

    # Narration
    nar_lines = vm.narration[:] if vm.narration else [_colorize("(none)", _Ansi.DIM)]

    parts = [
        header,
        "",
        _render_zone("STACK", stack_lines, width=width),
        "",
        _render_zone("BATTLEFIELD", bf_lines, width=width),
        "",
        _render_zone("GRAVEYARD", gy_lines, width=width),
        "",
        _render_zone("NARRATION", nar_lines, width=width),
        "",
        _colorize(
            "Controls: [Enter]=frame | n=end step | p=autoplay | q=quit | a/d=pan | +/-=zoom/speed | s/l=save/load replay",
            _Ansi.DIM,
        ),
    ]
    return "\n".join(parts)


# ── Replay ───────────────────────────────────────────────────────────────────

def run_replay(frames: List[Any], *, radius: int = 6) -> None:
    idx = 0
    while True:
        print("\033[2J\033[H", end="")

        if not frames:
            input("Replay is empty. Press Enter to exit replay...")
            return

        idx = max(0, min(idx, len(frames) - 1))
        current = frames[idx]
        snapshot = getattr(current, "snapshot", None)

        if not isinstance(snapshot, dict):
            input("This replay file has no snapshots (older format). Press Enter to exit replay...")
            return

        m = _machine_from_snapshot(snapshot)
        vm = build_board_view(m, last=None, radius=radius, camera_center=None, frame=current)
        print(render_mtg_board(vm))

        cmd = input(f"\n{_colorize('REPLAY', _Ansi.CYAN + _Ansi.BOLD)} > [Enter]=next | b=back | q=quit : ").strip().lower()
        if cmd in {"q", "quit", "exit"}:
            return
        if cmd in {"b", "back"}:
            idx -= 1
            continue
        idx += 1


# ── Non-blocking input helper ────────────────────────────────────────────────

def _input_available(timeout: float) -> Optional[str]:
    """
    Wait up to `timeout` seconds for user input.
    Returns the input string if available, or None if timeout expired.
    Works on Unix (select) and falls back to blocking on Windows.
    """
    if os.name == "nt":
        # Windows: no easy non-blocking stdin; just sleep and return None.
        # User can press Enter during the sleep to queue input for next iteration.
        time.sleep(timeout)
        return None
    else:
        ready, _, _ = select.select([sys.stdin], [], [], timeout)
        if ready:
            return sys.stdin.readline().strip()
        return None


# ── Interactive loop ─────────────────────────────────────────────────────────

def run_interactive(m: "GameLikeMachine", *, radius: int = 6, max_steps: Optional[int] = None) -> None:
    last: Optional["StepLog"] = None

    camera_center: Optional[int] = None
    view_radius = radius

    frame_iter: Optional[Iterator[Any]] = None
    current_frame: Optional[Any] = None
    recorded_frames: List[Any] = []

    autoplay = False
    autoplay_delay = 0.3  # seconds per frame

    while True:
        print("\033[2J\033[H", end="")

        vm = build_board_view(m, last, radius=view_radius, camera_center=camera_center, frame=current_frame)
        print(render_mtg_board(vm))

        if autoplay:
            print(_colorize(f"\n  ▶ AUTOPLAY (speed: {autoplay_delay:.2f}s)  - press p to pause", _Ansi.GREEN + _Ansi.BOLD))

        if m.halted:
            input(f"\n{_colorize('Game over.', _Ansi.RED + _Ansi.BOLD)} Press Enter to exit...")
            return
        if max_steps is not None and m.step_index >= max_steps:
            input(f"\nReached max_steps={max_steps}. Press Enter to exit...")
            return

        # ── Get input (blocking or non-blocking depending on autoplay) ──
        if autoplay:
            user = _input_available(autoplay_delay)
            if user is not None:
                cmd = user.lower()
            else:
                cmd = ""  # auto-advance
        else:
            raw = input("\n> ").strip()
            cmd = raw.lower()

        # ── Process commands ──
        if cmd in {"q", "quit", "exit"}:
            return

        if cmd == "p":
            autoplay = not autoplay
            continue

        if cmd == "a":
            camera_center = m.head if camera_center is None else camera_center
            camera_center -= max(1, view_radius // 2)
            continue
        if cmd == "d":
            camera_center = m.head if camera_center is None else camera_center
            camera_center += max(1, view_radius // 2)
            continue
        if cmd == "+":
            if autoplay:
                autoplay_delay = max(0.05, autoplay_delay - 0.05)
            else:
                view_radius = min(60, view_radius + 2)
            continue
        if cmd == "-":
            if autoplay:
                autoplay_delay = min(2.0, autoplay_delay + 0.05)
            else:
                view_radius = max(2, view_radius - 2)
            continue
        if cmd in {"f", "follow"}:
            camera_center = None
            continue

        if cmd == "n":
            # Skip to end of current computational step
            try:
                if frame_iter is None:
                    frame_iter = m.frames_for_next_step()
                while True:
                    current_frame = next(frame_iter)
                    frame_dict = _frame_to_jsonable(current_frame)
                    frame_dict["snapshot"] = _snapshot_machine(m)
                    recorded_frames.append(frame_dict)
                    if getattr(current_frame, "phase", "") == "END STEP":
                        frame_iter = None
                        current_frame = None
                        last = None
                        break
            except StopIteration:
                frame_iter = None
                current_frame = None
            except Exception as e:
                print(f"\nERROR: {e}")
                input("Press Enter to exit...")
                return
            continue

        if not autoplay and cmd.startswith("s"):
            parts = cmd.split(maxsplit=1)
            path = parts[1] if len(parts) == 2 else "replay_frames.json"
            try:
                save_frames_json(recorded_frames, path)
                input(f"\nSaved {len(recorded_frames)} frames to {path}. Press Enter...")
            except Exception as e:
                input(f"\nERROR saving replay: {e}\nPress Enter...")
            continue

        if not autoplay and cmd.startswith("l"):
            parts = cmd.split(maxsplit=1)
            if len(parts) != 2:
                input("\nUsage: l path/to/replay_frames.json\nPress Enter...")
                continue
            path = parts[1]
            try:
                frames = load_frames_json(path)
                run_replay(frames, radius=view_radius)
            except Exception as e:
                input(f"\nERROR loading replay: {e}\nPress Enter...")
            continue

        # ── Advance one frame (Enter, autoplay tick, or unrecognized command) ──
        try:
            if frame_iter is None:
                frame_iter = m.frames_for_next_step()
            current_frame = next(frame_iter)

            frame_dict = _frame_to_jsonable(current_frame)
            frame_dict["snapshot"] = _snapshot_machine(m)
            recorded_frames.append(frame_dict)

            if getattr(current_frame, "phase", "") == "END STEP":
                frame_iter = None
                current_frame = None
                last = None
        except StopIteration:
            frame_iter = None
            current_frame = None
        except Exception as e:
            print(f"\nERROR: {e}")
            input("Press Enter to exit...")
            return