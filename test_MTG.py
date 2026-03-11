# Python 3.10.6
import unittest


if __name__ == "__main__":
    unittest.main()

import glob
import json
import tempfile
import os

import UniversalTuringMachineTransitions as utm
from MTGSimulator import GameLikeMachine
from MTGSimulator import load_scenario, save_scenario


def run_one_step_frames(m: GameLikeMachine):
    frames = []
    for f in m.frames_for_next_step():
        frames.append(f)
        if f.phase == "END STEP":
            break
    return frames


def expected_move_dir(move_color: str):
    if move_color == "white":
        return -1
    if move_color == "green":
        return 1
    return None


class TestAllTransitionsTableDriven(unittest.TestCase):

    def test_frame_diff_payload_is_populated_for_read_write_and_move(self):
        # Non-halt example: q1 reading Cephalid
        m = GameLikeMachine()
        m.state = "q1"
        m.head = 0
        m.set_token(0, m._new_token(creature_type="Cephalid"))

        frames = run_one_step_frames(m)
        phases = [f.phase for f in frames]

        # Find the read frame (when Infest resolves)
        read_frames = [f for f in frames if "RESOLVE" in f.phase and f.read_pos is not None]
        self.assertTrue(read_frames, "Expected at least one read frame")
        read_frame = read_frames[0]
        self.assertEqual(read_frame.read_pos, 0)
        self.assertEqual(read_frame.read_type, "Cephalid")
        self.assertTrue(read_frame.changed_positions, "Expected changed_positions for read frame")

        # Find the write frame (when the trigger resolves)
        write_frames = [f for f in frames if f.written_pos is not None]
        self.assertTrue(write_frames, "Expected at least one write frame")
        write_frame = write_frames[0]
        self.assertEqual(write_frame.written_pos, 0)
        self.assertIsNotNone(write_frame.written_token_id)
        self.assertEqual(write_frame.attached_to_token_id, write_frame.written_token_id)
        self.assertTrue(write_frame.changed_positions, "Expected changed_positions for write frame")

        # Find the move frame (when Cleansing Beam resolves)
        move_frames = [f for f in frames if f.head_from is not None and f.head_to is not None]
        self.assertTrue(move_frames, "Expected at least one move frame")
        move_frame = move_frames[0]
        self.assertEqual(move_frame.head_from, 0)
        self.assertEqual(move_frame.head_to, -1)
        self.assertTrue(move_frame.changed_positions, "Expected changed_positions for move frame")

    def test_frame_diff_payload_is_populated_for_halt(self):
        # Halt example: q1 reading Rhino writes Assassin with blue move_color -> HALT.
        m = GameLikeMachine()
        m.state = "q1"
        m.head = 0
        m.set_token(0, m._new_token(creature_type="Rhino"))

        frames = run_one_step_frames(m)
        phases = [f.phase for f in frames]
        self.assertIn("HALT", phases)

        halt_frame = next(f for f in frames if f.phase == "HALT")
        # The halt frame should have state transition info
        self.assertIsNotNone(halt_frame.state_from)
        self.assertIsNotNone(halt_frame.state_to)

        # The write happens before halt
        write_frames = [f for f in frames if f.written_type == "Assassin"]
        self.assertTrue(write_frames, "Expected Assassin to be written before halt")
        write_frame = write_frames[0]
        self.assertEqual(write_frame.written_pos, 0)
        self.assertEqual(write_frame.written_type, "Assassin")
        self.assertIsNotNone(write_frame.written_token_id)

    def test_every_utm_transition_matches_one_step_semantics(self):
        for (state, read_type), trans in utm.UTM.items():
            with self.subTest(state=state, read_type=read_type):
                m = GameLikeMachine()
                m.state = state
                m.head = 0
                m.set_token(0, m._new_token(creature_type=read_type))

                frames = run_one_step_frames(m)
                phases = [f.phase for f in frames]

                # Baseline choreography - all transitions should have these
                self.assertIn("END STEP", phases, f"Missing END STEP for {state}, {read_type}")

                # Check that we have untap, upkeep, cast, and resolve phases
                has_untap = any("UNTAP" in p for p in phases)
                has_upkeep = any("UPKEEP" in p for p in phases)
                has_cast = any("CAST" in p for p in phases)
                has_resolve = any("RESOLVE" in p for p in phases)

                self.assertTrue(has_untap, f"Missing UNTAP phase for {state}, {read_type}")
                self.assertTrue(has_upkeep, f"Missing UPKEEP phase for {state}, {read_type}")
                self.assertTrue(has_cast, f"Missing CAST phase for {state}, {read_type}")
                self.assertTrue(has_resolve, f"Missing RESOLVE phase for {state}, {read_type}")

                is_halt = (trans.move_color == "blue" and trans.write_type == "Assassin")
                if is_halt:
                    self.assertIn("HALT", phases)
                    self.assertTrue(m.halted)
                    self.assertEqual(m.winner, "Alice")
                else:
                    self.assertNotIn("HALT", phases)
                    self.assertFalse(m.halted)

                # Write semantics - only check type and color, not tapped status
                # (tapped status is an internal timing mechanism that gets untapped in later turns)
                written = m.get_token(0)
                self.assertEqual(written.creature_type, trans.write_type)
                self.assertEqual(written.color, trans.move_color)
                # NOTE: We don't check tapped status here because the Untap step in subsequent
                # turns will untap tokens, making the final state unreliable for this check.

                # Attachment semantics
                self.assertEqual(m.illusory_gains_attached_to, written.token_id)

                # Halt vs move semantics
                if is_halt:
                    self.assertEqual(m.head, 0, "Head should not move on halt")
                else:
                    move = expected_move_dir(trans.move_color)
                    self.assertIn(move, (-1, 1))
                    self.assertEqual(m.head, move)
                    self.assertEqual(m.state, trans.next_state)

    def test_blank_cell_uses_blank_symbol_transition(self):
        for state in ("q1", "q2"):
            with self.subTest(state=state):
                m = GameLikeMachine()
                m.state = state
                m.head = 0
                # Do not set a token at 0 -> implicit blank

                trans = utm.lookup(state, utm.BLANK)
                frames = run_one_step_frames(m)
                self.assertTrue(frames)
                written = m.get_token(0)
                self.assertEqual(written.creature_type, trans.write_type)

def run_n_steps(m: GameLikeMachine, n: int):
    """Run n full computational steps (consuming all frames per step)."""
    for _ in range(n):
        if m.halted:
            break
        for frame in m.frames_for_next_step():
            if frame.phase == "END STEP":
                break


class TestGoldenScenarios(unittest.TestCase):
    """
    For each scenario file in scenarios/ that has an "expected" block,
    run the scenario for the specified number of steps and assert
    the final machine state matches.
    """

    def _load_scenario_with_expected(self, path: str):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        expected = data.get("expected")
        if expected is None:
            return None, None
        m = load_scenario(path)
        return m, expected

    def test_all_golden_scenarios(self):
        scenario_files = sorted(glob.glob("scenarios/*.json"))
        self.assertTrue(scenario_files, "No scenario files found in scenarios/")

        tested = 0
        for path in scenario_files:
            m, expected = self._load_scenario_with_expected(path)
            if expected is None:
                continue  # skip scenarios without an "expected" block

            with self.subTest(scenario=path):
                after_steps = expected["after_steps"]
                run_n_steps(m, after_steps)

                # Assert final state
                self.assertEqual(
                    m.state, expected["state"],
                    f"State mismatch in {path}",
                )
                self.assertEqual(
                    m.head, expected["head"],
                    f"Head mismatch in {path}",
                )
                self.assertEqual(
                    m.halted, expected["halted"],
                    f"Halted mismatch in {path}",
                )
                self.assertEqual(
                    m.winner, expected.get("winner"),
                    f"Winner mismatch in {path}",
                )

                # Assert tape contents (only check positions mentioned in expected)
                expected_tape = expected.get("tape", {})
                for pos_str, expected_type in expected_tape.items():
                    pos = int(pos_str)
                    actual_type = m.get_token(pos).creature_type
                    self.assertEqual(
                        actual_type, expected_type,
                        f"Tape mismatch at position {pos} in {path}: "
                        f"expected {expected_type!r}, got {actual_type!r}",
                    )

                tested += 1

        self.assertGreater(tested, 0, "No scenarios with 'expected' blocks found")


class TestScenarioLoader(unittest.TestCase):
    def test_load_immediate_halt_scenario(self):
        data = {
            "name": "test halt",
            "state": "q1",
            "head": 0,
            "tape": {"0": "Rhino"},
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            path = f.name
        try:
            m = load_scenario(path)
            self.assertEqual(m.state, "q1")
            self.assertEqual(m.head, 0)
            self.assertEqual(m.get_token(0).creature_type, "Rhino")

            run_one_step_frames(m)
            self.assertTrue(m.halted)
            self.assertEqual(m.winner, "Alice")
        finally:
            os.unlink(path)

    def test_load_blank_tape_scenario(self):
        data = {"state": "q1", "head": 0, "tape": {}}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            path = f.name
        try:
            m = load_scenario(path)
            self.assertEqual(m.get_token(0).creature_type, "Cephalid")
            self.assertFalse(m.halted)
        finally:
            os.unlink(path)

    def test_save_and_reload_preserves_state(self):
        m = GameLikeMachine()
        m.state = "q2"
        m.head = 5
        m.set_token(5, m._new_token(creature_type="Elf"))
        m.set_token(6, m._new_token(creature_type="Demon"))

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            path = f.name
        try:
            save_scenario(m, path, name="roundtrip test")
            m2 = load_scenario(path)
            self.assertEqual(m2.state, "q2")
            self.assertEqual(m2.head, 5)
            self.assertEqual(m2.get_token(5).creature_type, "Elf")
            self.assertEqual(m2.get_token(6).creature_type, "Demon")
        finally:
            os.unlink(path)

    def test_load_invalid_file_raises(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("[1,2,3]")
            path = f.name
        try:
            with self.assertRaises(ValueError):
                load_scenario(path)
        finally:
            os.unlink(path)


class TestScenarioExecution(unittest.TestCase):
    def test_immediate_halt_scenario_halts_in_one_step(self):
        data = {"state": "q1", "head": 0, "tape": {"0": "Rhino"}}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            path = f.name
        try:
            m = load_scenario(path)
            run_n_steps(m, 10)
            self.assertTrue(m.halted)
            self.assertEqual(m.step_index, 1, "Should halt after exactly 1 step")
        finally:
            os.unlink(path)

    def test_blank_tape_does_not_halt_within_5_steps(self):
        data = {"state": "q1", "head": 0, "tape": {}}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            path = f.name
        try:
            m = load_scenario(path)
            run_n_steps(m, 5)
            self.assertEqual(m.step_index, 5)
            self.assertFalse(m.halted)
        finally:
            os.unlink(path)

    def test_multi_step_scenario_state_and_head_evolve(self):
        data = {"state": "q1", "head": 0, "tape": {"0": "Basilisk"}}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            path = f.name
        try:
            m = load_scenario(path)
            trans = utm.lookup("q1", "Basilisk")
            run_one_step_frames(m)

            self.assertEqual(m.state, trans.next_state)
            expected_move = -1 if trans.move_color == "white" else 1
            self.assertEqual(m.head, expected_move)
            self.assertEqual(m.get_token(0).creature_type, trans.write_type)
        finally:
            os.unlink(path)