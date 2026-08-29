# Speech Redaction at the Edge

**Miguel Hernandez**, Northwestern University
Sage Grande: Summer of AI 2026

> Keep a Sage node listening for birds without ever recording the people
> walking past it.

## The Problem

Sage is deploying a node at Haleakalā National Park in Hawaii. The park runs
a BirdNET acoustic pipeline to identify birds from their calls, which means
the node has a microphone that is always listening. The National Park Service
does not want park visitors recorded, and their default request was simple:
turn the microphone off.

Turning the microphone off also turns off the bird science. This project
offers an alternative: automatically detect and erase human speech at the
edge, so the node can continue classifying birdsong while preventing detected
human speech from being written to disk or uploaded.

The requirement is strict. It should be **impossible** to accidentally record
a person, which means the guarantee has to hold even when the speech detector
fails: the system is designed to fail closed, so that if speech detection
cannot complete successfully, the audio is redacted rather than written to
disk.

## The Approach

The core insight came from reading how the existing BirdNET node application
actually handles audio: **it writes every recording to disk before it
classifies anything.** A speech filter added at the end of the pipeline would
be too late, because the raw audio, human speech included, is already saved
by the time classification runs.

So redaction has to happen before the audio is persisted, while it is still
an in-memory array. The pipeline is:

```
microphone capture (in-memory audio array)
   -> YAMNet speech scoring (one score per 0.48s frame)
   -> RedactionGate (turns scores into speech time-windows)
   -> zero out the speech windows in the array, in place
   -> BirdNET classification and publish
   -> publish redaction event (timestamp, duration)
   (the plugin only ever persists the redacted array, never unredacted audio)
```

**Detecting speech.** BirdNET's own human-sound classes do not reliably catch
real speech, so this project uses **YAMNet**, a general audio classifier, for
the speech-detection step. YAMNet produces a speech score for every short
frame of audio. These scores are the input to the decision logic.

**Deciding what to erase.** A `RedactionGate` turns those per-frame scores
into the actual time-windows to erase. It uses hysteresis: a frame has to
clear a higher threshold to *start* a speech window, and drop below a lower
threshold to *end* one, so the gate does not flicker on and off in the middle
of a sentence. Each detected window is padded on both sides (pre-roll and
post-roll) so the edges of an utterance are never clipped and leaked.

**Failing safe.** The safe default state of the system is *redacting*.
Successful speech classification is what permits recording, not what triggers
redaction. The gate raises on missing scores rather than silently redacting
nothing, and in the integrated microphone path, if YAMNet errors, returns
nothing, or the gate hits any unexpected failure, the system zeroes the
entire audio buffer before saving rather than risk letting speech through.

## My Contribution

- **Found the architectural constraint** that redaction must happen before
  persistence, by tracing both audio paths in the BirdNET application and
  finding they write to disk before classifying.
- **Built and tested the redaction components**: a YAMNet speech-scoring
  wrapper, a verified list of YAMNet's speech-related classes (checked
  against the canonical class map rather than assumed), and the
  `RedactionGate` hysteresis state machine. Caught and fixed a frame-timing
  bug in the gate that was under-redacting the tail of each speech segment.
- **Integrated the gate into the microphone recording path** of the BirdNET
  application, so the in-memory audio array is redacted in place before the
  file is ever written, with the fail-closed behavior described above.
- **Verified the pipeline on the target hardware** (an NVIDIA Jetson AGX
  Thor) and produced a before/after demo on real speech audio.

## Key finding, in detail: the pipeline persists audio before it classifies it

The existing `flint-pete/birdnet` node application writes every capture to a
temporary FLAC file before any classification runs, on both audio paths:

- **Microphone path** (`record_from_microphone` in the upstream application):
  pywaggle's `Microphone.record()` returns an in-memory `AudioSample`, but
  the code immediately calls `sample.save()` to a temp FLAC before doing
  anything else.
- **Camera path** (`record_from_camera` in the upstream application): ffmpeg
  writes the capture straight to disk; the PCM samples never exist as a
  Python array.

This means redaction cannot be a downstream filter: by the time BirdNET
runs, raw speech is already on disk. Redaction has to happen **before
persistence**.

The microphone path is fixable, because `sample.data` is a 1-D float32 array
available in memory before `save()`. Redaction can operate on that array in
place, and only the already-redacted array is written. The camera path is
harder and would require piping ffmpeg to stdout to decode in-process.

## What I built

Three tested Python modules (all with unit tests, verified against source
rather than assumed).

**`RedactionGate`** is a hysteresis state machine that takes per-frame speech
scores and returns the time ranges to redact. It has configurable enter/exit
thresholds (higher bar to enter redaction, lower bar to exit, so it does not
flicker mid-sentence), pre-roll padding, hangover (gap tolerance), and
post-roll padding. It fails closed on empty input.

- Caught and fixed a real bug: YAMNet frames are 0.96s long with a 0.48s
  hop, so they overlap. Naive frame-hop math under-redacted the tail of
  every speech segment by 0.48s. Fixed by tracking frame duration separately
  from hop.

**`speech_classes.py`** holds the verified YAMNet AudioSet speech class
indices, checked against the canonical `yamnet_class_map.csv`, split into
core speech classes and ambiguous ones (crowd, chatter, children). It
reduces a 521-class YAMNet frame vector to a single speech score by taking
the max across the speech family. (Note: "Male speech" and "Female speech"
are not YAMNet classes, a detail worth verifying rather than assuming.)

**`yamnet_speech.py`** wraps YAMNet to turn a raw audio array into per-frame
speech scores: resample to 16kHz mono, run YAMNet, reduce each frame through
`speech_classes`. Model load is lazy and cached, and the model file path is
resolved by an existence-filtered fallback chain (env override, plugin
container, persistent dev path, volatile dev scratch) so the model survives
node reboots.

## What has been verified on hardware (Jetson AGX Thor, aarch64)

The full detection-and-redaction pipeline has been run on the Thor node
against real speech audio, end to end:

- YAMNet runs on the Thor via `ai_edge_litert` (LiteRT) using a TFLite model
  converted on the node, on the ARM CPU with no GPU required. Note: the
  `tensorflow_hub` load path used in the standalone module is not available
  on this node, so the deployed front end uses the LiteRT/TFLite path. The
  `RedactionGate` and `speech_classes` modules are used unchanged; only the
  YAMNet front end is swapped to LiteRT. The LiteRT adapter and the
  validation harness live in the birdnet fork (hermes-mighdz/birdnet);
  upstreaming a copy of the adapter here is pending.
- The converted YAMNet `.tflite` lives at a persistent location on the node
  (`/home/mighdz/AI-Projects/models/yamnet.tflite`) so it survives reboots;
  the path is picked up via the `BIRDNET_YAMNET_TFLITE` env var (or the
  fallback chain documented on the fork).
- On a ~21s real speech clip (three spoken bursts with silence between),
  YAMNet's per-frame speech scores sat at the noise floor (~0.01) during
  silence and saturated near 0.99 during speech: clean discrimination.
- `RedactionGate` consumed those scores and produced two redaction windows
  that correctly bracketed the speech, with the configured 1.5s pre-roll
  reaching backward from speech onset and 0.75s post-roll/hangover reaching
  forward past the last speech frame. A short mid-speech pause was absorbed
  by the hangover (windows merged); a longer silence correctly split the
  windows. The output audio had the speech zeroed out while the surrounding
  ambient sound was preserved untouched. This last part matters: the goal is
  not to blank the recording, it is to remove only human speech while
  keeping the soundscape that BirdNET depends on.
- A live `ffprobe -show_streams` against a networked Reolink camera of the
  same family (on the lab network, from Pete's credential sheet) confirmed
  an audio stream over RTSP: AAC LC, 16 kHz, mono, which matches YAMNet's
  native input rate, so no resampling is needed for that source. A different
  camera model on the same sheet had no audio stream at all. My own physical
  RLC-81MA unit has not been individually probed yet, so the exact stream on
  the deployment camera is still to be confirmed. A capture with no speaker
  present produced zero redaction windows (no false positives on ambient
  audio).

Together these confirm the runtime half of the design: the speech detector
runs on the target hardware, and the redaction gate fires correctly on real
speech and stays quiet on real non-speech.

**Mic-path integration: done.** The in-memory, never-persists integration is
now landed on the birdnet fork (hermes-mighdz/birdnet): `redact_speech` is
wired into `record_from_microphone` so the raw array is redacted before the
save call, failing closed if scoring is unavailable. The redaction modules
have 14 unit tests, and the full 43-test repo suite passes with no
regressions on the fork. A before/after demo (raw vs redacted output on the
same speech clip) was produced.

**Standalone redaction plugin: built, containerized, and published.** The
microphone-path redaction has been refactored out of the birdnet fork into a
separate Sage application (https://github.com/Miguel-Hernandez1/speech-redaction),
its own ECR app with its own `sage.yaml` and `ecr-meta`, distinct from birdnet.
It is a local-cache consumer/producer: it reads audio from the node's local
cache, redacts speech in memory (reusing the same fail-closed `redact_speech`,
so the raw unredacted array is never re-published), and writes a redacted audio
product back into the cache as a new versioned frame for a downstream plugin
such as BirdNET to consume. The consume/produce code, the Layer-1 ring writer,
capture-timestamp preservation, and the redaction-event and heartbeat
publishing, is built and unit-tested. The container was built with `pluginctl`
on the Thor (H032) and ran end to end: YAMNet loaded via LiteRT inside the
container and redacted speech from a real clip. The image is published to ECR
(built, currently private). What is not yet done is a live run against an
actual mounted `/local-cache`: the shared cache mount is not deployed on the
nodes yet (per Pete's local-cache design doc), so the full cache
consume-redact-produce loop has so far only been exercised in-container on a
single clip, not against the live shared cache.

**Threshold tuning: harness built and verified; real tuning pending better
data.** A sweep harness (`redaction/scripts/tune_thresholds.py` on the
fork's `redaction-mic-integration` branch) sweeps `enter_threshold` and
reports recall vs false-positive rate on labeled clips. It runs correctly on
real audio, but has only been exercised on a 3-clip labeled set so far,
which is too cleanly separable to pick an operating point from. A richer
labeled set spanning borderline cases (distant or mumbled speech, ambient
sounds that trip YAMNet's speech classes) is needed before it yields a real
tuned threshold.

**Camera path: design proposal, not built.**
`redaction/CAMERA-PATH-DESIGN.md` on the fork proposes extending redaction
to the camera path via an ffmpeg stdout-pipe (so raw audio never touches
disk), plus the audio/video time-windowing idea (detect an audio event at
time t, snip the video around it). None of it is implemented yet.

## Grounded parameter choices

Padding and threshold choices are chosen by analogy to telephony voice
activity detection hangover timing (WebRTC VAD, NVIDIA Riva/Silero, 3GPP
AMR), which uses 60-580ms hangover. Telephony VAD is tuned for the opposite
cost trade-off (do not waste bandwidth on silence), so the analogy is not
direct; for privacy redaction, where under-redacting is far more costly, the
recommended guard is ~1s post-utterance with a longer hold when the signal
is non-stationary.

## Redaction as a data product

Rather than filling redacted spans with comfort noise (which would corrupt
the bioacoustic record BirdNET and downstream soundscape analysis depend
on), the proposal, pending sign-off from Pete, is to write silence plus
publish a separate `audio.redacted` measurement with timestamp and duration.
This makes each redaction auditable and distinguishable from a dead sensor,
and gives NPS a verifiable log of when redaction occurred, without revealing
what was said. It also yields free statistics on human presence at the site.

## Current status and next steps

- **Done:** the microphone-path integration, the tested redaction
  components, on-Thor validation of YAMNet, the before/after demo on real
  speech, and the standalone `speech-redaction` plugin (a separate ECR app,
  built into a container with `pluginctl` on the Thor, run end to end on a
  real clip, and published to ECR as a currently-private image).
- **Done, plugin refactor:** the microphone-path implementation has been
  refactored into a standalone producer/consumer Sage plugin
  (https://github.com/Miguel-Hernandez1/speech-redaction) that consumes audio
  from the local cache, redacts it in memory, and produces a redacted audio
  product back into the cache for downstream applications such as BirdNET. The
  consume/produce code is built and tested.
- **Pending, live cache-mount run:** the plugin's consume-redact-produce loop
  has been exercised in-container on a single clip, but not yet against an
  actual mounted `/local-cache`. The shared cache mount is not deployed on the
  nodes yet (per Pete's local-cache design doc), so a live run over the real
  shared cache is the open item.
- **Pending, live microphone run:** the integration has been validated by
  feeding recorded audio through the pipeline; the next step is a live run
  pulling directly from a physical microphone on the node.
- **Proposed, not built, camera path:** a live `ffprobe` on a networked
  Reolink of the same family (from the lab credential sheet) confirmed an
  RTSP audio stream at AAC 16 kHz mono, though my specific RLC-81MA unit has
  not been individually probed. A design proposal is written
  (`redaction/CAMERA-PATH-DESIGN.md` on the fork); implementing the ffmpeg
  stdout-pipe decode is the open item. None of it is implemented yet.
- **Pending, threshold tuning:** build a richer labeled clip set
  (distant/mumbled speech, YAMNet-confusable ambient) and run
  `tune_thresholds.py` over it to pick an operating point: target recall
  99%+, report the precision cost. The system currently ships on
  conservative defaults that err toward over-redacting.
- **Pending, redaction data product:** define the `audio.redacted`
  measurement schema for Beehive.

## Repositories

- Notes, design docs, and redaction modules:
  https://github.com/Miguel-Hernandez1/project-sage-notes
- Integration analysis (birdnet fork):
  https://github.com/hermes-mighdz/birdnet

## Acknowledgment

This work was supported in part by the National Science Foundation under
Awards No. 2331263 and 2436842.
