from unittest.mock import patch

import numpy as np
import pytest

import yamnet_speech
from speech_classes import AMBIGUOUS, CORE_SPEECH, NUM_YAMNET_CLASSES
from yamnet_speech import YAMNET_SAMPLE_RATE, _prepare_waveform, speech_scores


class FakeYamnet:
    """Stands in for the TF Hub model: records the waveform it was called
    with and returns a preset (scores, embeddings, spectrogram) tuple."""

    def __init__(self, scores):
        self.scores = np.asarray(scores, dtype=np.float32)
        self.called_with = None

    def __call__(self, waveform):
        self.called_with = waveform
        n = len(self.scores)
        return self.scores, np.zeros((n, 1024)), np.zeros((n, 64))


def _frames(n):
    return np.zeros((n, NUM_YAMNET_CLASSES), dtype=np.float32)


def test_one_score_per_frame():
    fake = FakeYamnet(_frames(5))
    with patch.object(yamnet_speech, "_load_model", return_value=fake):
        out = speech_scores(np.zeros(16000, dtype=np.float32), 16000)
    assert len(out) == 5


def test_scores_reduce_over_core_speech_classes():
    frames = _frames(2)
    frames[0, CORE_SPEECH[0]] = 0.7   # Speech
    frames[0, AMBIGUOUS[0]] = 0.9     # ambiguous - excluded by default
    frames[1, CORE_SPEECH[-1]] = 0.4  # Hubbub
    fake = FakeYamnet(frames)
    with patch.object(yamnet_speech, "_load_model", return_value=fake):
        out = speech_scores(np.zeros(16000, dtype=np.float32), 16000)
    assert out == pytest.approx([0.7, 0.4])


def test_include_ambiguous_passes_through():
    frames = _frames(1)
    frames[0, AMBIGUOUS[0]] = 0.9
    fake = FakeYamnet(frames)
    with patch.object(yamnet_speech, "_load_model", return_value=fake):
        out = speech_scores(np.zeros(16000, dtype=np.float32), 16000, include_ambiguous=True)
    assert out == pytest.approx([0.9])


def test_resamples_to_16k_before_model():
    fake = FakeYamnet(_frames(1))
    with patch.object(yamnet_speech, "_load_model", return_value=fake):
        speech_scores(np.zeros(48000, dtype=np.float32), 48000)  # 1s at 48kHz
    assert fake.called_with is not None
    assert len(fake.called_with) == YAMNET_SAMPLE_RATE
    assert fake.called_with.dtype == np.float32


def test_int16_audio_normalized_to_unit_range():
    audio = np.full(16000, 16384, dtype=np.int16)  # half full-scale
    waveform = _prepare_waveform(audio, 16000)
    assert waveform.dtype == np.float32
    assert np.all(np.abs(waveform) <= 1.0)
    assert waveform[0] == pytest.approx(0.5, abs=1e-3)


def test_stereo_downmixed_to_mono():
    audio = np.zeros((16000, 2), dtype=np.float32)
    audio[:, 0] = 1.0
    waveform = _prepare_waveform(audio, 16000)
    assert waveform.ndim == 1
    assert waveform[0] == pytest.approx(0.5)


def test_empty_audio_raises():
    with pytest.raises(ValueError):
        _prepare_waveform(np.array([], dtype=np.float32), 16000)


def test_model_returning_wrong_class_count_raises():
    fake = FakeYamnet(np.zeros((3, 10), dtype=np.float32))  # not 521 classes
    with patch.object(yamnet_speech, "_load_model", return_value=fake):
        with pytest.raises(ValueError):
            speech_scores(np.zeros(16000, dtype=np.float32), 16000)
