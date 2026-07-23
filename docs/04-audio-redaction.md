# Audio Privacy Redaction on Sage Nodes

Working notes for speech-triggered redaction at the edge. Driver: Sage is
deploying a node at Haleakala National Park, and NPS does not want people
recorded. Goal is to offer automatic speech redaction as an alternative to
turning the microphone off entirely.

Node: H032 (Jetson AGX Thor, aarch64)
Repo under test: https://github.com/flint-pete/birdnet

---

## 1. Key finding: the current pipeline persists audio before classifying it

This is an architecture problem, not something a classifier can fix.

Both audio acquisition paths in `app.py` write the full capture to a temp
FLAC file before any inference runs. Adding a speech filter downstream does
not help, because raw speech is already on disk by then.

### Camera path (`record_from_camera()`, app.py:181-237)

- Builds a temp path via `tempfile.mkdtemp(prefix="birdnet_")`
- Runs ffmpeg as a blocking subprocess with output args:
  `-vn -acodec flac -ar <sample_rate> -ac 1 -t <duration> <flac_path>`
- ffmpeg writes the entire capture directly to disk through the kernel
- `capture_output=True` means Python receives only the return code and stderr
- Python never holds the PCM array at any point
- Temp dir deleted after inference via `shutil.rmtree` in a `finally` block

Consequence: the audio array is locked inside the ffmpeg subprocess. To get a
no-file pipeline here you would either pipe ffmpeg output to stdout (`-` as
output) and decode in-process, or read the FLAC back with `soundfile.read()`
after the fact. The second option still means raw speech touched disk.

### Microphone path (`record_from_microphone()`, app.py:160-178)

This one is salvageable. pywaggle already exposes the array:

- `Microphone.record(duration)` (waggle/data/audio.py:43-50) returns an
  `AudioSample`
- `AudioSample` is a NamedTuple (audio.py:12-15): `data: np.ndarray`,
  `samplerate: int`, `timestamp: int`
- `sample.save(flac_path)` is a separate optional step that just calls
  `soundfile.write(...)` (audio.py:17-19)

So `sample.data` is a 1-D float32 array in memory *before* any save happens.
`app.py` simply does not use this capability.

```python
from waggle.data.audio import Microphone

mic = Microphone(samplerate=48000)
sample = mic.record(duration_s)
audio_arr = sample.data        # 1-D float32, mono (channels=1 default)
sr = sample.samplerate
ts = sample.timestamp          # waggle nanosecond timestamp
```

Caveats from the source:
- `Microphone` defaults to `channels=1`, and `app.py` does not override it.
  Passing `channels=2` returns shape `(nframes, channels)` and would need
  monoizing for BirdNET.
- dtype is float32 PCM in [-1, 1] from the soundcard backend.

### Design principle this implies

Redaction has to happen before persistence, not after. The safe default state
of the system is "redacting," and successful speech classification is what
*permits* recording, not what triggers redaction.

---

## 2. No existing VAD or speech work in the repo

Searched the repo for `yamnet|vad|silero|webrtc|speech|voice activity`.
All hits are in `RESEARCH.md` (a survey document) plus false positives in
`model/labels.txt` from species names containing "salvadori" and "avadavat".

No code, no config, no tests. YAMNet is a documented future enhancement with
nothing behind it yet.

Note: BirdNET does classify some human/noise classes (Siren, Human, etc.,
bucketed by `sound_category()` at app.py:259-269), but these are published as
detections, not used for filtering. Earlier testing confirmed BirdNET's human
classes do not reliably catch real speech, which is why YAMNet is the right
tool for this step.

---

## 3. RedactionGate: hysteresis state machine

Built as a standalone testable module. Takes per-frame speech scores, returns
time ranges to redact.

### Parameters

| Parameter | Purpose |
|---|---|
| `enter_threshold` | score that starts redaction |
| `exit_threshold` | score below which redaction can end (must be <= enter) |
| `pre_roll_seconds` | padding backward from segment start |
| `hangover_seconds` | gap tolerance before splitting one segment into two |
| `post_roll_seconds` | padding forward past segment end |
| `frame_hop` | 0.48s for YAMNet |
| `frame_duration` | 0.96s for YAMNet |

Hysteresis (low bar to enter, harder bar to exit) prevents flicker mid-sentence
where scores dip between words and the gate unmutes.

### Threshold reasoning

This is an asymmetric cost problem and the threshold should reflect that:

- False negative: speech gets through, a park visitor was recorded. Catastrophic.
- False positive: a few seconds of birdsong redacted. Cheap.

So bias hard toward recall. Starting point is ~0.25 enter / 0.15 exit, well
below the 0.5+ you would use for a confident bird ID. To be tuned empirically
against real clips.

Do not threshold on YAMNet's single "Speech" class. Take the max across the
AudioSet speech family (Speech, Conversation, Male speech, Female speech,
Child speech, Narration, Shout, Yell, Screaming, Whispering, Babbling). Distant
or mumbled speech may score low on Speech alone while lighting up neighbors.

Verify class indices against the actual `yamnet_class_map.csv` rather than
trusting any list from memory or from an LLM.

### Two bugs found in review

**Frame duration vs frame hop.** YAMNet frames are 0.96s long with a 0.48s hop,
so they overlap. Computing a segment end as `(last_frame + 1) * hop` assumes
non-overlapping frames and under-redacts by 0.48s on every window. Correct:

```python
total_duration = (n - 1) * frame_hop + frame_duration
end_time = last_frame * frame_hop + frame_duration + post_roll_seconds
```

This was invisible in tests using `frame_hop=1.0` and only appeared with real
YAMNet parameters. A test with hop=0.48 / duration=0.96 now asserts the correct
1.92s end against the naive 1.44s.

**Failing open.** Returning an empty list on empty input means "redact nothing,"
so a model load failure or empty buffer would publish raw audio. Now raises
`RedactionGateFailure` by default (`fail_closed=True`), forcing the caller,
which knows the actual buffer duration, to decide explicitly.

Also: gap comparisons use frame counts
(`math.ceil(hangover_seconds / frame_hop)`) rather than float seconds, which
is fragile at 0.48s hops.

---

## 4. Open design questions

**What gets written during a redaction.** Options are silence, comfort noise
matched to background level, or band-limited masking.

Leaning toward silence in the audio plus a separate published measurement
(timestamp + duration) marking the redaction. Reasoning:

- The downstream consumer is BirdNET, not a human listener. Synthetic noise
  invites spurious detections.
- Sage data feeds soundscape analysis (acoustic complexity, biophony ratios,
  amplitude envelopes). Injected noise silently corrupts all of these.
- NPS needs an auditable guarantee. "Nothing was recorded, here is the log of
  when" is a stronger claim than "we replaced it with something that sounds
  like the background."

Making redaction events their own data product also yields free statistics on
human presence at a site.

Counterargument worth weighing: silence is itself metadata and creates hard-cut
artifacts. In broadcast and telephony, comfort noise is standard for exactly
this reason. The difference here is that the consumer is a classifier and a
science record, not an ear.

**Capture boundary leakage.** Each cycle is an isolated fixed-length block with
no streaming or overlap. Speech crossing a boundary gets less padding than
speech in the middle: the first block's post-roll cannot extend forward and the
second block's pre-roll cannot reach back. Options: overlap captures, carry
gate state across cycles, or unconditionally redact the leading/trailing N
seconds when speech is detected near an edge.

**Padding duration.** Starting at 1-2s pre-roll. Reasoning: YAMNet's 0.96s
window makes onset detection coarse, unvoiced onsets (fricatives, plosives)
are low energy and can precede the triggering frame, and speaker identity is
recoverable from very little audio. Telephony VAD hangover is typically
200-500ms but that is tuned for not clipping a call, a much lower-stakes goal.
Worth grounding in VAD hangover literature rather than intuition.

---

## 5. Hardware

- Reolink RLC-81MA: PoE IP camera, built-in mic and speaker, 802.3af, also has
  a 12V DC port. Audio and video on one device means one clock, which matters
  for the audio-to-video sync problem (detect a sound event at t=11s, retrieve
  the video around it).
- NETGEAR 8-port gigabit smart managed plus switch. **Verify whether this model
  is actually PoE.** Much of that product line is not, despite the name. If not,
  use a PoE injector or the camera's 12V adapter.

Unverified: whether the RLC-81MA exposes audio over RTSP, or only through the
Reolink app's two-way audio. These are not the same thing. Check with:

```bash
ffprobe rtsp://<user>:<pass>@<CAMERA_IP>:554/h264Preview_01_main
```

Looking for an audio stream, its codec, and sample rate.

Then test whether ffmpeg can pipe to stdout instead of a file:

```bash
ffmpeg -i rtsp://... -vn -ac 1 -ar 16000 -f wav -t 10 - | wc -c
```

If that produces bytes, `record_from_camera()` can be restructured to decode
in-process and never write raw audio to disk, which fixes the architecture
problem for the camera path.

Sample rate note: YAMNet wants 16 kHz mono, BirdNET wants 48 kHz. Capture at
48k and downsample a copy for the speech gate.

---

## 6. Next steps

- [ ] Verify NETGEAR switch is PoE
- [ ] Confirm RTSP audio stream exists on the RLC-81MA
- [ ] Test ffmpeg stdout piping for a no-disk camera path
- [ ] Confirm BirdNET's `run_arrays` API in-container (documented in
      RESEARCH.md:91-101 but not verifiable on the dev host, where birdnet
      is not installed)
- [ ] Wire YAMNet, verifying speech class indices against the class map CSV
- [ ] Record test clips at varying distance and volume against realistic
      ambient noise, then tune thresholds against that corpus
- [ ] Plot recall vs threshold, pick for target recall, report precision cost
- [ ] Decide silence vs comfort noise with Pete
- [ ] Define the redaction event measurement schema for Beehive
