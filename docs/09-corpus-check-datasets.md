# Corpus Check: Does an Existing Speech-Plus-Soundscape Dataset Already Cover Us?

**Miguel Hernandez, August 19, 2026**

Pete asked whether there was already a dataset of speech mixed with environmental sound that we could use instead of generating our own. Here's what I found.

## Short answer

There isn't one dataset we can just download and use. But Pete's approach is already pretty well established, and we can reuse a couple of the pieces, so the dataset build is smaller than I initially thought.

More importantly, I found prior work that's very close to what we're doing. It gives us some baselines to compare against and, more importantly, a generation pipeline that someone has already used for this exact kind of data.

## The closest prior work: ecoVAD

**Cretois, B., Rosten, C.M., & Sethi, S.S. (2022). Voice activity detection in
eco-acoustic data enables privacy protection and is a proxy for human
disturbance. Methods in Ecology and Evolution, 13(12), 2865-2874.**
DOI: 10.1111/2041-210X.14005. Open access.
Code: github.com/NINAnor/ecoVAD. Weights and some data: osf.io/f4mt5

This is the same problem statement as ours; they claim that eco-acoustic monitoring networks inevitably record human speech, that manual filtering and prior consent aren't practical at scale, and that automated anonymization is therefore required. Additionally, they mention that existing voice activity detection work was built for close-microphone or urban settings rather than natural soundscapes, and that bird calls overlap in frequency with speech and can cause false positives.

### What they built

They built a synthetic data pipeline, similar to our plan, just with the details spelled out:

- Soundscape recordings split into non-overlapping 3 second segments
- Each segment mixed with speech plus background, speech only, background only, or left unmixed
- Their ratios: 5 percent both, 45 percent speech only, 25 percent background only, 25 percent untouched
- Speech from LibriSpeech, chosen because it's roughly 360 hours of clean 16 kHz English with an even male to female split
- Background from ESC-50 (environmental sounds) and BirdCLEF 2017 (birds)
- Added audio scaled to vary between about -56 and -8 dBFS, a range they set from the minimum and maximum levels in their own field recordings
- Random start offsets and a 500 ms fade in and out, to simulate a person walking toward and past the recorder

### How they evaluated it

Playback experiments. Three speakers, a man, a woman, and a child, each reading the same sentence, recorded in a soundproof environment. Played back through a portable speaker calibrated so the male voice registered 60 dB SPL, at 1, 5, 10 and 20 metres, both facing and behind the recorder, in two landscape types.

### Their results

Detection confidence stayed high out to 10 metres for all three speakers. At 20 metres confidence dropped, but they note that at that distance the speech was barely audible and the words weren't intelligible.

Against two established baselines, average F1 across distances was 0.917 for ecoVAD, 0.890 for pyannote, and 0.876 for WebRTC VAD.

In a real five-day deployment on a hiking trail, speech was present in about 5 percent of the test data. Precision numbers there were much lower than the playback numbers, between 0.14 and 0.32 depending on site and configuration, against a random-chance baseline of 0.05. Their controlled numbers and their field numbers were very different, and I'd expect the same for us.

One thing worth noting about their false positives: when they listened to a sample of them, animal sounds accounted for only about 5 percent. Most came from sounds the listeners couldn't identify at all, possibly faint wind.

### Why this matters to us

The main thing is that we're not inventing the dataset generation approach because ecoVAD used essentially the same setup, so we have a concrete reference for how to build the synthetic data instead of making up our own mixing strategy.

Additionally, it gives us some useful baselines. For instance, pyannote and WebRTC VAD are both runnable, and ecoVAD has its code on GitHub with weights on OSF. So we could report YAMNet against those three on our own data rather than only showing how YAMNet performs by itself.

The playback experiment is useful for Pete's intelligibility ranking too since he wants a human listening test to establish the "can you actually make out the words?" line, and Cretois gives us a published reference point for where intelligibility starts falling off. Our results won't necessarily match theirs, but we can at least compare them.

Lastly, their discussion of thresholds also lines up with how we're approaching the gate because they point out that the right threshold depends on the use case, and that lower thresholds make sense when missing speech is especially costly. That's similar to our situation, since we'd rather redact some bird audio than let speech through.

## The follow-up work on edge deployment

**Priebe, D., Ghani, B., & Stowell, D. (2024). Efficient Speech Detection in
Environmental Audio Using Acoustic Recognition and Knowledge Distillation.
Sensors, 24(7), 2046.** DOI: 10.3390/s24072046

They distilled ecoVAD down for edge hardware. Their reported figures:

| Model | Parameters | Memory | Inference time | Avg F1 |
|---|---|---|---|---|
| ecoVAD teacher | 59.5M | 227 MB | 0.17 s | 0.917 |
| Student 1 | 4.7M | 17 MB | 0.038 s | 0.905 |
| Student 4 | 52K | 0.19 MB | 0.005 s | 0.862 |

This is relevant because it shows you can make the detector much smaller without losing much accuracy. It also gives us another reason to use the ecoVAD playback data as an evaluation set.

## The general-purpose VAD corpus: QUT-NOISE-TIMIT

**Dean, D., Sridharan, S., Vogt, R., & Mason, M. (2010). The QUT-NOISE-TIMIT
corpus for evaluation of voice activity detection algorithms. Proceedings of
Interspeech 2010, 3110-3113.**

They recorded over 10 hours of background noise at 10 locations across 5 scenarios, then mixed TIMIT speech into it across a range of SNRs and speech proportions. The result is 600 hours of noisy speech built specifically to evaluate VAD systems.

Potentially useful: the QUT-NOISE background audio is CC-BY-SA, and the code for building the mixed corpus is BSD licensed, both at github.com/qutsaivt/QUT-NOISE.

Not usable as-is: the speech half is TIMIT, which requires an LDC license. TIMIT is also adult American English only, so it has no children and no overlapping speakers.

Their 2015 follow-up makes a point I want to carry into our metrics. They mention that you should tune the detector around what the system is actually for, rather than trying to match the true speech boundaries perfectly. So for us that means measuring leaked speech and lost bird detections, not frame-level agreement.

## What I'd reuse vs. what we'd still need to build

**Reuse:**
- ecoVAD's mixing pipeline as the starting point, and potentially their repo directly if the license allows it
- QUT-NOISE backgrounds and BSD mixing code for the urban end of the range
- ESC-50 for environmental sounds, LibriSpeech for speech
- pyannote, WebRTC VAD, and ecoVAD as comparison baselines

**Build:**
- The ten soundscapes spanning urban to wilderness that Pete asked for
- The speaker variety that LibriSpeech doesn't give us, especially children and overlapping speakers
- The ten mixing levels, with speech in the middle third of the 30-second clips
- The human intelligibility ranking

## Open issues to flag

**Child speech is a licensing problem, not just a sourcing one.** LibriSpeech has no children. Most children's speech corpora are restricted precisely because they're recordings of minors. I need to check what's actually usable before we promise child voices in the set.

**We need speech-free clips.** Pete's spec puts speech in the middle third of every clip. If every clip contains speech, we can't measure how often we redact when nobody is talking, which is the number that tells us how much bird audio we lose. ecoVAD's pipeline left 25 percent of segments untouched for this reason. I plan to add speech-free clips to the set.

**YAMNet may not be the best detector here.** ecoVAD exists partly because general-purpose VAD models underperform in natural soundscapes, and YAMNet is general purpose. Our evaluation may show that. Our piece is the pipeline around the detector, not the detector itself, so a better model would slot in rather than replace the work.

**Recording permission.** Cretois had to get a municipal research permit to record and use audio in a public forest. Haleakalā is a US national park, so it's worth checking whether Sage needs something equivalent.

## Next
I'm going ahead with the build using ecoVAD's pipeline as the reference, and moving to the media-sampler3 refactor today.
