import pytest

from speech_classes import AMBIGUOUS, CORE_SPEECH, NUM_YAMNET_CLASSES, speech_score


def test_core_speech_index_count():
    assert len(CORE_SPEECH) == 12


def test_ambiguous_index_count():
    assert len(AMBIGUOUS) == 4


def test_no_overlap_between_core_and_ambiguous():
    assert set(CORE_SPEECH).isdisjoint(AMBIGUOUS)


def test_speech_score_uses_core_only_by_default():
    scores = [0.0] * NUM_YAMNET_CLASSES
    scores[0] = 0.7    # Speech
    scores[64] = 0.9   # Crowd (ambiguous) - ignored by default
    assert speech_score(scores) == 0.7


def test_speech_score_includes_ambiguous_when_requested():
    scores = [0.0] * NUM_YAMNET_CLASSES
    scores[64] = 0.9  # Crowd
    assert speech_score(scores, include_ambiguous=True) == 0.9
    assert speech_score(scores, include_ambiguous=False) == 0.0


def test_speech_score_raises_on_wrong_length_vector():
    short_scores = [0.0] * 10
    with pytest.raises(ValueError):
        speech_score(short_scores)
