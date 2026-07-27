"""YAMNet wrapper for the redaction pipeline.

Feeds audio through YAMNet (TF Hub) and reduces each frame's 521-class
score vector to a single speech score via speech_classes.speech_score.
Output is one float per YAMNet frame (0.96s window, 0.48s hop), ready to
hand to RedactionGate.get_redaction_windows().
"""

import numpy as np

from speech_classes import speech_score

YAMNET_SAMPLE_RATE = 16000
YAMNET_HUB_URL = "https://tfhub.dev/google/yamnet/1"

_model = None


def _load_model():
    global _model
    if _model is None:
        import tensorflow_hub as hub  # deferred so tests run without TF installed
        _model = hub.load(YAMNET_HUB_URL)
    return _model


def _prepare_waveform(audio_1d, samplerate: int) -> np.ndarray:
    audio = np.asarray(audio_1d)
    if audio.ndim == 2:
        audio = audio.mean(axis=1)  # downmix interleaved stereo
    elif audio.ndim != 1:
        raise ValueError(f"expected 1-D (or 2-D multichannel) audio, got shape {audio.shape}")
    if audio.size == 0:
        raise ValueError("empty audio buffer")
    if samplerate <= 0:
        raise ValueError(f"invalid samplerate {samplerate}")

    if np.issubdtype(audio.dtype, np.integer):
        audio = audio / float(np.iinfo(audio.dtype).max)  # YAMNet expects float in [-1, 1]
    audio = audio.astype(np.float32)

    if samplerate != YAMNET_SAMPLE_RATE:
        # linear interpolation - no anti-aliasing filter, fine for a first pass;
        # swap for scipy.signal.resample_poly if downsampling from high rates matters
        n_out = int(round(audio.size * YAMNET_SAMPLE_RATE / samplerate))
        t_out = np.arange(n_out) * (samplerate / YAMNET_SAMPLE_RATE)
        audio = np.interp(t_out, np.arange(audio.size), audio).astype(np.float32)

    return audio


def speech_scores(audio_1d, samplerate: int, include_ambiguous: bool = False) -> list:
    waveform = _prepare_waveform(audio_1d, samplerate)
    model = _load_model()
    scores, _embeddings, _spectrogram = model(waveform)
    scores = np.asarray(scores)  # works for both tf.Tensor and plain arrays
    return [speech_score(frame, include_ambiguous=include_ambiguous) for frame in scores]
