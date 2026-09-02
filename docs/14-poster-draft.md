# Poster Draft: Speech Redaction at the Edge

**Miguel Hernandez**

Content draft for the internship poster. This is the text and the figures, not
the layout. Sending it this way first so the numbers and the claims can be
checked before anything gets designed.

Every number here comes from the current committed version of doc 12, a
500-clip evaluation set (400 speech-positive clips plus 100 speech-free
controls), or from the listening test data in the qa repo. The earlier
125-clip numbers are stale and are not used.

---

## Title

**Redacting human speech at the edge, before it is ever uploaded**

Subtitle: a Sage plugin that removes speech from field audio so passive
acoustic monitoring can run in public places

---

## The problem

Passive acoustic monitoring works by leaving a microphone outside and recording
continuously. At a place like Haleakala National Park that means recording park
visitors along with the birds.

Manual filtering does not scale and asking every passerby for consent is not
possible. So the audio has to be cleaned automatically, on the node, before
anything is shared.

The constraint that shaped the design: the existing BirdNET app writes the full
recording to disk before it classifies anything. A speech filter added at the
end would be too late. The guarantee this design holds today is that redaction
happens before audio is uploaded or exposed to any downstream consumer. Raw
clips currently still reach the node's disk first, written there by the
upstream producer; moving that cache to volatile memory, so unredacted audio
never touches disk at all, is the remaining step.

---

## What was built

A standalone Sage plugin that sits in the v2 cache pipeline as both a consumer
and a producer, the same pattern as the YOLO and BioCLIP cascade already running
on H00F.

```
media-sampler3  ->  raw audio cache  ->  speech-redaction  ->  redacted cache  ->  BirdNET
```

Every few minutes the plugin wakes, reads the unseen clips, scores each frame
with YAMNet, and zeroes the speech while the audio is still an in-memory array.
It writes the redacted clip and a sidecar into a separate cache area and exits.

Design decisions worth naming:

**Fail closed.** If the detector cannot run, the whole buffer is zeroed rather
than passed through. Both failure modes lose data, but for a privacy pipeline
dropping audio is the safer one.

**Provenance travels with the artifact.** Each output carries the redaction
windows, the original capture timestamp, and a pointer back to the source clip,
so a downstream consumer can see exactly what was removed.

**White noise fill instead of silence**, matched to the level of the surrounding
audio, so the gaps do not confuse other detectors.

---

## Verified on the node

Ran end to end on H00F against the live media-sampler3 cache with the real
YAMNet model.

- About 250 ms per 15 second clip, against a producer writing one clip a minute
- Speech-free regions are preserved unless the detector triggers
- The seen store survives restarts, so nothing is reprocessed
- 45 tests passing on the node

Fail closed proved itself by accident. On the first run the model file was not
where the plugin expected it. Instead of passing raw audio through, the plugin
zeroed all 15 seconds of every clip and wrote the reason into the sidecar. The
failure was unplanned and the guarantee held.

---

## Does it actually work

To find out, I built an evaluation set where the ground truth is exact because I
placed the speech myself: LibriSpeech mixed into ESC-50 soundscape beds,
loudness normalized before mixing. The 400 speech-positive clips are a full
cross of 5 soundscape categories (4 beds drawn per category), 4 speech sources,
and 5 SNR levels from 0 to -20 dB; the 100 speech-free controls measure false
positives.

At the current gate settings, across that full range:

| Recall | Mean leaked speech | Mean fraction of each speech-free clip redacted |
|---:|---:|---:|
| 75.3% | 1340 ms per clip | 0.77% |

By SNR:

| SNR (dB) | Recall % | Mean leak (ms) |
|---:|---:|---:|
| 0 | 92.5 | 400 |
| -5 | 86.9 | 694 |
| -10 | 79.4 | 1157 |
| -15 | 69.5 | 1614 |
| -20 | 49.3 | 2836 |

Recall alone is the wrong number to watch. A clip can post high recall and still
leak a whole spoken word. Leaked speech is the privacy metric.

---

## Human intelligibility falls before speech detection does

Recall numbers only matter if you know where a human stops being able to
understand the speech. So I ran a blind listening test on 40 clips from the set,
scoring each one for whether I could hear a voice and whether I could make out
the actual words.

| SNR (dB) | Human made out words (n=8) | Detector recall, same 40 clips |
|---:|---:|---:|
| 0 | 50% (4 of 8 clips) | 99.5% |
| -5 | 38% (3 of 8 clips) | 86.0% |
| -10 | 38% (3 of 8 clips) | 91.5% |
| -15 | **0% (0 of 8 clips)** | 84.0% |
| -20 | **0% (0 of 8 clips)** | 65.8% |

Both columns above come from the same 40 clips, a paired comparison, not an
aggregate one. The full-set detector numbers earlier in this document (92.5,
86.9, 79.4, 69.5, 49.3 by SNR) are the average across all 400 speech-positive
clips, a different and larger set than this exact 40. On this matched set, at
-15 dB and -20 dB not a single clip was intelligible, while the detector's
sample-level recall on those same clips was 84% and 66%. The two are different
measures, fraction of clips a listener understood versus fraction of speech
samples the detector caught, but side by side they point the same direction:
the detector keeps catching speech well past the level where a person stops
understanding it.

So the leak measured above is largely leaking audio nobody could understand. The
real cost of the system's sensitivity is the bird audio it redacts by mistake: a
mean of 0.77% of each speech-free clip's duration.

One more thing the listening test showed: a voice was audible on all 40 clips,
including at -20 dB where no words came through. Presence leaks before content
does.

---

## Where it fails: rain

The collapse below -10 dB is not spread evenly. It is concentrated in one bed.

| Bed | Recall % |
|---|---:|
| wind | 86.4 |
| crickets | 79.4 |
| chirping_birds | 78.2 |
| engine | 75.2 |
| **rain** | **57.0** |

A likely reason: rain is broadband noise that overlaps the speech spectrum,
unlike tonal soundscapes such as crickets and birdsong. I have not tested that
mechanism directly, only its effect. At -20 dB in rain, YAMNet's output sits at
the noise floor and no tested gate setting recovered it. That is a limit of the
detector, not something to tune around.

It matters for the deployment target, because Haleakala is a wet mountain park
and rain is not an edge case there.

Rain also destroyed human comprehension in the listening test, zero words made
out. So the detector and the listener fail on the same material, which is at
least consistent. Birdsong is the interesting divergence: it hurt human
comprehension badly (0% of words made out) while the detector handled it fine
(78.2% recall). One possible reason is that bird chirps overlap frequencies used
by speech formants, which could hurt human parsing without confusing YAMNet's
classifier, but I have not tested that mechanism directly.

---

## Why these numbers should be trusted

Twice during this work a plausible finding turned out to be an artifact of too
small a sample, and both were caught by enlarging the design rather than by
noticing them by eye.

**"The male voice survives rain."** With one soundscape bed per category, the
male speaker appeared to punch through rain where the female did not. Crossing
every speaker against multiple beds killed it: the male survives on 2 of 4 rain
beds and the female survives on a different one. What drives detection at -20 dB
is which rain recording you drew, not who is speaking.

**"Birdsong causes an 11% false positive rate."** That came from 25 speech-free
clips, 5 per category. Raising it to 100 brought the real figure to about 1%.

The redesign that killed that finding also moved overall recall from 86.8% down
to 75.3%, because crossing every speaker against multiple beds made the set
harder and more varied. The system did not get worse. The measurement got
honest.

---

## What this does not answer yet

**The listening test is one listener.** I ran all 40 clips myself. The
intelligibility threshold reported here is a single person's, and it needs two
or three more listeners before it is a real number.

**No children and only four speakers.** LibriSpeech has no child voices and most
children's speech corpora are license restricted. The set has two single
speakers and two overlapping-speaker mixes.

**Synthetic, not field recorded.** Mixed audio with known ground truth is the
right way to get exact labels, but it is not the same as real speech at real
distances in real weather.

**Hangover is untested, not proven useless.** LibriSpeech is continuous read
speech with almost no internal pauses, so this set barely exercises the gate's
pause-bridging behavior. Real conversation has gaps.

**Raw audio still reaches the SSD.** The producer writes unredacted clips to the
node's disk before this plugin reads them. Moving that to ramdisk, so nothing
unredacted survives a reboot, is the next step and is planned with Peter.

---

## Figures to include

1. Before and after waveform on a real clip, speech spans marked. Already have
   this from the H032 validation run.
2. The pipeline diagram: media-sampler3 to redacted cache to BirdNET.
3. Human intelligibility against detector recall, plotted by SNR. Already
   rendered at `speech-redaction-qa/listening/human_vs_detector.png`. This is
   the centerpiece.
4. The per-bed recall bar chart, with rain called out.

---

## Links

- Plugin: github.com/Miguel-Hernandez1/speech-redaction
- Evaluation: github.com/Miguel-Hernandez1/speech-redaction-qa
- Full writeup: github.com/Miguel-Hernandez1/project-sage-notes

---

## Notes on numbers, for review not for the poster

The matched detector numbers in the table above come from
`score_listening.py`'s `matched_yamnet_recall()`, run on the same 40 clips as
the human column. That function reads `scores/` and `mixed/`, which are
gitignored, not because the result can't be reproduced but because they are
regenerated data: run `generate_qa.py` then `score_qa.py` locally (see the qa
repo's README) and `score_listening.py` will reproduce this table from there.
