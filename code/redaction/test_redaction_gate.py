import math

import pytest

from redaction_gate import RedactionGate, RedactionGateFailure


def test_isolated_spike():
    gate = RedactionGate(
        enter_threshold=0.5, exit_threshold=0.3,
        pre_roll_seconds=1.0, hangover_seconds=1.0, post_roll_seconds=1.0,
        frame_hop=1.0, frame_duration=1.0,
    )
    scores = [0.0, 0.0, 0.9, 0.0, 0.0]
    windows = gate.get_redaction_windows(scores)
    assert windows == [(1.0, 4.0)]


def test_sustained_speech():
    gate = RedactionGate(
        enter_threshold=0.5, exit_threshold=0.3,
        pre_roll_seconds=1.0, hangover_seconds=1.0, post_roll_seconds=1.0,
        frame_hop=1.0, frame_duration=1.0,
    )
    scores = [0.0, 0.0] + [0.9] * 5 + [0.0, 0.0, 0.0]
    windows = gate.get_redaction_windows(scores)
    assert windows == [(1.0, 8.0)]


def test_flickering_scores_merge_into_one_window():
    gate = RedactionGate(
        enter_threshold=0.5, exit_threshold=0.3,
        pre_roll_seconds=0.0, hangover_seconds=1.0, post_roll_seconds=1.0,
        frame_hop=1.0, frame_duration=1.0,
    )
    scores = [0.9, 0.2, 0.9, 0.2, 0.9]
    windows = gate.get_redaction_windows(scores)
    assert windows == [(0.0, 5.0)]


def test_flickering_scores_split_when_gap_exceeds_hangover():
    gate = RedactionGate(
        enter_threshold=0.5, exit_threshold=0.3,
        pre_roll_seconds=0.0, hangover_seconds=1.0, post_roll_seconds=1.0,
        frame_hop=1.0, frame_duration=1.0,
    )
    scores = [0.9, 0.2, 0.2, 0.2, 0.9]
    windows = gate.get_redaction_windows(scores)
    assert len(windows) == 2


def test_speech_at_start_of_buffer_clamps_pre_roll():
    gate = RedactionGate(
        enter_threshold=0.5, exit_threshold=0.3,
        pre_roll_seconds=2.0, hangover_seconds=0.5, post_roll_seconds=0.5,
        frame_hop=1.0, frame_duration=1.0,
    )
    scores = [0.9, 0.9, 0.0, 0.0]
    windows = gate.get_redaction_windows(scores)
    assert windows == [(0.0, 2.5)]
    assert windows[0][0] >= 0.0


def test_overlapping_yamnet_frames_extend_past_naive_hop_math():
    # hop=0.48, duration=0.96 (real YAMNet params) - a single spike frame's audio
    # actually extends to i*hop + duration, not (i+1)*hop. This is the bug the
    # code review caught: naive hop-only math under-redacts by (duration - hop).
    gate = RedactionGate(
        enter_threshold=0.5, exit_threshold=0.3,
        pre_roll_seconds=0.0, hangover_seconds=0.0, post_roll_seconds=0.0,
        frame_hop=0.48, frame_duration=0.96,
    )
    scores = [0.0, 0.0, 0.9, 0.0, 0.0]
    windows = gate.get_redaction_windows(scores)
    assert len(windows) == 1
    start, end = windows[0]
    assert math.isclose(start, 0.96, rel_tol=1e-9)
    assert math.isclose(end, 1.92, rel_tol=1e-9)
    # naive (last_frame + 1) * hop would give 1.44 here - half a frame_hop short
    naive_end = 3 * 0.48
    assert end - naive_end > 0.4


def test_empty_scores_fail_closed_by_default():
    gate = RedactionGate()
    with pytest.raises(RedactionGateFailure):
        gate.get_redaction_windows([])


def test_empty_scores_can_opt_into_fail_open():
    gate = RedactionGate(fail_closed=False)
    assert gate.get_redaction_windows([]) == []
