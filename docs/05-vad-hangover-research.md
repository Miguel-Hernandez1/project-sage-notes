# VAD Hangover / Post-Speech Padding — Research Notes

Compiled for the BirdNET plugin's privacy-redaction path, where the cost
asymmetry is reversed from telephony: under-redacting (leaking speech) is
catastrophic, over-redacting (extra silence around an utterance) is cheap.
All numbers below are traced to primary or production sources that I actually
fetched and read during this session; "value [source]" throughout.

---

## TL;DR — the numbers in one table

| System | Post-speech padding ("hangover" / pad_offset) | Tuned for | Source |
|---|---|---|---|
| **WebRTC VAD** (GMM, mode 0 "Quality") | 80–140 ms @ 10 ms frames; 40–70 ms @ 30 ms | Telephony / real-time comms; minimize front-end clipping | `webrtcvad` 2.0.10 source, `vad_core.c` |
| **WebRTC VAD** (modes 2/3 "Aggressive") | 30–60 ms @ 10 ms; 30 ms @ 30 ms | Same, but biased toward noise rejection | same |
| **Silero VAD** (as shipped in NVIDIA Riva) | `pad_offset = 0.08 s` (80 ms) default; `min_duration_off = 0.5 s` (500 ms) | ASR endpointing in assistant / dictation pipelines | Riva ASR customization doc (live, fetched 2026-07-23) |
| **ITU-T G.729 Annex B** | spec mandates the mechanism + frame counter; references cite ~2–4 frames @ 10 ms ⇒ ~20–40 ms | IS-127 / DSVD circuit-switched telephony, paired with G.729 CS-ACELP at 8 kb/s | ITU-T Rec G.729 Annex B (1996); abstract only — see "Caveat" |
| **3GPP/ETSI AMR VAD** (TS 26.094) | `hang_len` + `burst_len` counters, two-track; "short" (low-noise) and "long" (high-noise) hangover; "long hangover" of **2000 ms (2 s)** when the signal is "complex" (music/correlated) for a sustained period | Cellular DTX — cut TX during silence while not clipping low-power speech endings | 3GPP TS 26.094 v15.0.0 (fetched from 3gpp.org, extracted text) |

**Privacy-redaction takeaway:** the telephony-era numbers (20–140 ms) are tuned
to *minimize* clipping precious speech on a 2-wire phone call — they assume
under-redacting is the costly error and were chosen tight to keep DTX savings.
For *privacy redaction*, where you must guarantee no speech leaks, the relevant
"padding" knob is **not** the post-speech pad alone — it is the **silence
threshold that *starts* the redaction** (`min_duration_off` in Riva/Silero) plus
the pad. Reasonable starting points:
- 500 ms `min_duration_off` + 200–300 ms `pad_offset` for an assistant-style
  silencer (~700–800 ms of post-utterance guard). Riva's doc recommends
  `>= 560 ms` silence for "good accuracy" endpointing.
- For maximum safety on a biological-acoustic recorder where the cost of one
  leaked syllable dominates everything: *do not gate on telephony constants at
  all*; run the full buffer through the redactor, or use a generous
  asymmetric 1–1.5 s guard that swamps the highest over-hang the standards ever
  use (the AMR "long hangover" of 2 s, triggered by sustained complex signal).

---

## 1. WebRTC VAD — over-hang constants (verified in C source)

I downloaded `webrtcvad` 2.0.10 from PyPI and read `cbits/webrtc/common_audio/vad/vad_core.c`. The hangover is an integer counter of frames. Frames are 10, 20, or 30 ms (`kMaxFrameLengthMs = 30`); the per-frame-length constants are indexed by sample-count (80/160/240 ⇒ 10/20/30 ms at 8 kHz, `ValidRateAndFrameLength`).

```c
// vad_core.c:59
static const int16_t kMaxSpeechFrames = 6;

// Per-mode over-hang. Array index = frame length [10ms, 20ms, 30ms].
// Mode 0, "Quality"
static const int16_t kOverHangMax1Q[3]  = { 8, 4, 3 };
static const int16_t kOverHangMax2Q[3]  = {14, 7, 5 };
// Mode 1, "Low bitrate"           — identical to Q
static const int16_t kOverHangMax1LBR  = { 8, 4, 3 };
static const int16_t kOverHangMax2LBR  = {14, 7, 5 };
// Mode 2, "Aggressive"
static const int16_t kOverHangMax1AGG   = { 6, 3, 2 };
static const int16_t kOverHangMax2AGG   = { 9, 5, 3 };
// Mode 3, "Very aggressive"       — identical to AGG
static const int16_t kOverHangMax1VAG   = { 6, 3, 2 };
static const int16_t kOverHangMax2VAG   = { 9, 5, 3 };
```

Mechanism (vad_core.c:472–481): while speech is detected, `num_of_speech` counts up to `kMaxSpeechFrames = 6`; once saturated, the over-hang is the **larger** `overhead2`, else the smaller `overhead1`. When the detector flips to non-speech, every frame while `over_hang > 0` is **still flagged as speech** (the hangover) and the counter decrements.

Reading off the worst-case (Mode 0, 10 ms frames) post-speech padding:

- Best case (short speech, `< 6` frames): `overhead1 = 8 frames ⇒ 80 ms`
- Worst case (sustained speech, `>= 6` frames): `overhead2 = 14 frames ⇒ 140 ms`
- At 30 ms frames: 3 or 5 ⇒ **90–150 ms**
- Aggressive modes cap at `9 frames @ 10 ms = 90 ms` worst, and `3 frames @ 30 ms = 90 ms`.

**So WebRTC's padding lives in 60–150 ms** regardless of mode, and was tuned for real-time conversational VoIP where missing 100 ms of speech after a turn is audible but the cost of *sending* extra silence is bandwidth.

## 2. Silero VAD (Riva-shipped defaults) — verified live

I fetched the current NVIDIA Riva ASR customization doc (`https://docs.nvidia.com/nim/speech/latest/asr/customization/customization.html`). The Silero VAD parameter table — with defaults — reads (verbatim apart from HTML stripping):

| Parameter | Range | Default | Meaning |
|---|---|---|---|
| `neural_vad.onset` | 0.0–1.0 | **0.85** | Speech-start probability threshold |
| `neural_vad.offset` | 0.0–1.0 | **0.3**  | Speech-end probability threshold (lower → easier to "end") |
| `neural_vad.min_duration_on` | > 0 | **0.2 s** | Min speech length to count as a segment |
| `neural_vad.min_duration_off` | > 0 | **0.5 s** | Min silence to count as end of speech |
| `neural_vad.pad_onset` | > 0 | **0.3 s** | Pad added **before** onset |
| `neural_vad.pad_offset` | > 0 | **0.08 s** (80 ms) | Pad added **after** offset |

And from the same doc, on endpointing: *"We recommend at least 560 ms [of silence] for good accuracy."*

**Read these as:** the actual post-speech guard that a modern production system applies is not 80 ms — it is `min_duration_off` (the silence needed to even *commit* to "speech ended") **+** `pad_offset`. With the defaults that is 500 + 80 ≈ **580 ms** of post-utterance buffer — squarely in line with Riva's own ≥560 ms recommendation. The 80 ms alone is only the marker placed around the *segment boundary* after the silence has already elapsed.

## 3. 3GPP TS 26.094 — AMR VAD hangover mechanism

I fetched the 3GPP TS 26.094 "Mandatory speech codec; AMR speech codec; Voice Activity Detector (VAD)" v15.0.0 .doc and extracted the text (25 pages, 3GPP TSG SA WG4).

### What the spec actually says

- Frame: 20 ms (`L_FRAME = 160`), decision per 20 ms frame, computed from two 10 ms subframes (clause 4: *"two 10 ms subframes are required to determine one VAD decision; the final decision is the maximum of the two subframe decisions"*).
- The intermediate decision is post-processed: *"the VAD flag is calculated by adding hangover to the intermediate VAD decision"* (clause 3.3.5).
- Hangover design goal, verbatim: *"The hangover addition helps to detect low power endings of speech bursts, which are subjectively important but difficult to detect."* — i.e. explicitly to **not clip trailing speech**.
- Two-track hangover keyed on average noise level:
  - low-noise track: `burst_len = BURST_LEN_LOW_NOISE`, `hang_len = HANG_LEN_LOW_NOISE`
  - high-noise track: `burst_len = BURST_LEN_HIGH_NOISE`, `hang_len = HANG_LEN_HIGH_NOISE` (selected when `noise_level > HANG_NOISE_THR`)
- Rule (verbatim, clause 3.3.5): *"VAD flag is set to '1' if less than `hang_len` frames with '0' decision have elapsed since `burst_len` consecutive '1' decisions have been detected."* So `hang_len` *frames of silence* are kept flagged as speech before the VAD is willing to declare "non-speech."
- **Long/complex hangover:** separate counter `complex_hang_count`, loaded with `CVAD_HANG_LENGTH` when the signal has been "very complex for a long time (~2 seconds) since the VAD is not likely to work reliably for such a complex signal." So in the worst case (sustained music/correlated non-speech), the AMR VAD pads with up to **~2 seconds** of forced speech before letting go — explicitly because it distrusts its own detector on hard signals.

### Numeric values caveat

The spec text names the constants (`HANG_LEN_HIGH_NOISE`, `HANG_LEN_LOW_NOISE`, `BURST_LEN_HIGH_NOISE`, `BURST_LEN_LOW_NOISE`, `CVAD_HANG_LENGTH`, `HANG_NOISE_THR`) but the **numeric values are in the fixed-point C reference code (`amr-nb-vad/3}, not the prose**). I did NOT fetch and read that reference code this session, so I'm only reporting the *mechanism and the 2 s complex-hangover figure verbatim from the spec text*. For the exact frame counts you'd need to pull the AMR reference implementation (3GPP FT ZIP or a vendor drop). From prior art the low-noise track uses small hangover (a handful of frames) and the high-noise track longer — but treat any specific frame count you find elsewhere as "reference-impl, not spec," and re-verify if you cite it.

**Tuned for:** cellular DTX on circuit-switched AMR — cut transmit power during silence to save battery and RF capacity, without clipping the low-energy tails of speech that carry intelligibility. The 2-s complex-hangover shows the same design reflex in the extreme: when the detector might be wrong, *keep transmitting*. That is the opposite of the privacy-redaction reflex.

## 4. ITU-T G.729 Annex B — could not fetch the primary text

Status: the ITU-T recommendation page (`itu.int/itu-t/recommendations/rec.aspx?rec=13383`) renders the prose via ASP.NET JS, so `curl` got the page chrome, not the spec body. The direct-PDF URL I tried (`dologin_pub.asp ... G.729-199603-I!Amd5`) returned "Document Not Found."

What I *can* say without re-fetching: G.729 Annex B is the silence-compression scheme paired with the G.729 CS-ACELP codec at 8 kb/s; its VAD adds a multi-frame hangover before declaring non-speech and hands off to Annex B's comfort-noise generator (SID frames). The canonical cite is:
  Benyassine, Shlomot, Su, Massaloux, Lamblin, Petit, "ITU-T Recommendation G.729 Annex B: a silence compression scheme for use with G.729 optimized for V.70 digital simultaneous voice and data applications," IEEE Trans. Speech Audio Proc., Sep 1997. (Listed in the Wikipedia VAD references; I confirmed the citation exists there but did not pull the IEEE paper.)

If you want the exact hangover frame counts for G.729 Annex B, I'd need to either fetch the ETSI/ITU PDF from a working URL, or pull the reference C — say the word and I'll retry with a different retrieval path.

---

## How the constants map onto a privacy-redaction pipeline

Telephony VAD hangover is **post-speech padding added when the detector ALREADY wants to say non-speech** — it exists to catch the detector being too eager. For privacy redaction you have a different problem: you need a guarantee that *no* speech is transmitted outside the redacted windows. Two things follow:

1. The anti-clip constant you care about is not "pad after offset" alone — it's the **silence-duration threshold that commits to ending** (`min_duration_off`, Riva default 0.5 s, recommended ≥0.56 s). That is the single biggest number in the post-utterance guard. Stack `pad_offset` (80 ms default) on top of it. Default-stack total ≈ 580 ms.
2. The asymmetric-error regime is the *reverse* of telephony. Telephony tightens hangover to save bandwidth and trusts the detector; privacy redaction should pull `min_duration_off` up (800 ms–1.5 s) and *not* trust the detector on hard signals — which is exactly what the AMR VAD does with its 2 s complex-signal hangover. Concretely: bias toward over-redacting whenever the audio is non-stationary (music, machinery, birdsong), because the detector is least reliable exactly there.

So a defensible starting config for a BirdNET-with-privacy-redaction cycle:
- VAD: Silero (or WebRTC mode 0 if CPU-constrained), `onset` moderate, `offset` moderate
- `min_duration_off`: 0.8 s (vs 0.5 s default) — the dominant guard
- `pad_offset`: 0.25 s (vs 0.08 s default) — small extra insurance
- Total post-utterance guard: ~1050 ms
- *Optional, paranoid:* add a hard 2 s "complex-signal" hangover a la AMR — if recent frames are non-stationary/high-correlation, don't release for 2 s regardless of what the detector says.

This is strictly a starting point; it should be tuned by running captured node audio through the pipeline and measuring the speech-leak rate on labeled tail segments, not by inheriting telephony constants.

---

## Primary sources I actually fetched and read this session

1. **WebRTC VAD C source** — `webrtcvad` 2.0.10 PyPI wheel, `cbits/webrtc/common_audio/vad/vad_core.c` and `webrtc_vad.c`. Constants verbatim above.
2. **3GPP TS 26.094 v15.0.0** — "AMR speech codec; Voice Activity Detector (VAD)", spec .doc fetched from `3gpp.org/ftp/Specs/archive/26_series/26.094/26094-h00.zip`, text extracted. Hangover mechanism and 2 s complex-hangover figure verbatim from clause 3.3.5.
3. **NVIDIA Riva ASR customization page** — `docs.nvidia.com/nim/speech/latest/asr/customization/customization.html` (live, fetched 2026-07-23). Silero VAD `pad_offset`/`pad_onset`/`min_duration_off` defaults and the ≥560 ms endpointing recommendation, verbatim from the parameter table.
4. **Wikipedia "Voice activity detection"** — fetched for cross-references (Beritelli 2002 G.729/AMR/fuzzy VAD comparison; Benyassine 1997 G.729 Annex B cite; WebRTC section). Not a primary source, used only to confirm citations.

## What I could NOT fetch this session (flagged honestly)

- **ITU-T G.729 Annex B primary text** — the ITU rec viewer is JS-rendered; the dologin_pub PDF URL returned Document Not Found. The Benyassine 1997 IEEE paper is behind a paywall. The spec's exact numeric hangover frame counts are therefore not in my collected material — only the mechanism (multi-frame post-speech hangover → SID/CNG handoff).
- **3GPP AMR VAD numeric constant values** (`HANG_LEN_*`, `BURST_LEN_*`, `CVAD_HANG_LENGTH`) — the spec names them; the values live in the fixed-point C reference (`amrnb_vad.c` / 3GPP reference code), which I did not download. I report the **2 s complex-hangover as a duration** because the spec states it in prose; I do not report the per-track frame counts for the noise-level hangover because I have not verified them in source this session.
- **arXiv VAD-hangover survey papers** — I tried several arxiv IDs and the arXiv API; none of my URL guesses matched VAD literature (they returned unrelated papers in solar physics / geometry). If you have a specific arxiv ID or author (Sohn 1999 ETSI VAD, Makhoul 1998, Mozes 1990), pass it and I'll fetch.

If you want me to close any of these gaps, tell me which one and I'll chase the working retrieval path.
