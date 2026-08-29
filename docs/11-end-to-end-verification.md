# End-to-End Verification on H00F

**Miguel Hernandez, August 28, 2026**

First run of the full cache consume, redact, produce loop on a live node with
the real YAMNet model. Everything before this was tested against a stub, so this
is the first time the actual detector touched real audio in this pipeline.

## Setup

Node: H00F, Jetson AGX Thor, aarch64.

The plugin was run from a bare clone rather than the container, so a few things
had to be installed or pointed at by hand. Those are noted below because they
are real gaps in the repo, not just local setup.

```
pip3 install --break-system-packages soundfile mutagen ai-edge-litert==2.1.6
export BIRDNET_YAMNET_TFLITE=/home/mighdz/AI-Projects/speech-redaction/models/yamnet.tflite
```

Command:

```
python3 main.py --source cache \
  --input /media/plugin-data/local-cache/hummingcam-audio/hummingcam_mic \
  --output-cache /tmp/redacted-test2 \
  --seen-store /tmp/redacted-test2/.state/seen.json \
  --all-unseen --max-frames 2 --cache-max-count 100
```

## What was verified

**The real model runs on the node.** TensorFlow Lite created an XNNPACK delegate
for CPU and inference completed. No stub, no monkeypatching.

**Latency is about 250 ms per 15 second clip.** Two clips processed in roughly
half a second wall clock, including file reads and writes. The producer writes
one clip every 60 seconds, so there is a lot of headroom.

**Clean audio passes through intact.** Both clips returned zero redaction
windows, which is the expected result for a hummingbird feeder with nobody
talking nearby. Output files came out at 453 KB and 472 KB against roughly 476 KB
sources, so the audio is essentially unchanged.

**Fail closed works in production, not just in tests.** On the first attempt the
YAMNet model file was not where the plugin looked for it. Instead of passing raw
audio through, the plugin zeroed all 15 seconds of every clip and wrote the
reason into the sidecar:

```
"redaction_windows": [[0.0, 14.976]],
"redaction_fail_closed": true,
"redaction_fail_closed_reason": "YAMNet .tflite not found. Checked: ..."
```

That is the behavior the design calls for. If the detector cannot run, assume
everything is speech. The failure was accidental and the guarantee held anyway,
which is a better test than one I set up on purpose.

**The seen store survives restarts.** Ran the batch three times. Seen count went
2, then 4, and no frame was processed twice. State persisted across separate
process invocations on real hardware.

**Output naming and provenance are correct.** Redacted files keep the original
`capture_ts_ns` and change only the source label, so a downstream consumer can
still anchor to the real capture time:

```
1787923847947669575-v2-H00F-hummingcam_mic.flac
1787923847947669575-v2-H00F-hummingcam_mic_redacted.flac
```

Sidecars carry `source_unique_id` pointing back at the input clip, plus the
redaction windows and fail closed fields.

## The cache is bigger than expected

The input ring held 500 frames. At 15 seconds every 60 seconds that is roughly
8 hours of retention, or about 2 hours of actual audio. That is the number to
size the output cache caps against, which is still an open item.

## Bugs found

**Model path resolution is off by one directory.** The plugin checked
`/home/mighdz/AI-Projects/models/yamnet.tflite` when the model is at
`/home/mighdz/AI-Projects/speech-redaction/models/yamnet.tflite`. It computes the
repo root as the parent of the repo. This never surfaced in the container because
the model sits at `/app/models/` there, which is also on the search list. Anyone
running outside the container hits it.

**A missing `ai_edge_litert` crashes instead of failing closed.** When the model
file was missing, the fail closed path caught it correctly. When the runtime
package was missing, the `ModuleNotFoundError` propagated out of `_load_model`
and the batch aborted with zero frames processed and no output written. Aborting
is not a privacy failure, since nothing was written, but it is inconsistent with
how the missing file case is handled and it should route through the same path.

**`pywaggle` is absent on the host and the plugin continues without publishing.**
That is intended fail soft behavior for a host run, noted here so it is not
mistaken for a problem.

## Still open

- Output cache caps need real retention numbers
- The two bugs above
- Running inside the container on the node rather than from a bare clone
- Evaluation dataset, which is the remaining item from Pete's original list
