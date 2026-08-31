# Evaluation: Recall, Leaked Speech, and Where the Detector Collapses

**Miguel Hernandez, August 29, 2026**

This is the first real measurement of how well the redaction detector actually
works, and to get it I built a synthetic set where I know exactly where the
speech is, because I placed it there myself. Every number in this doc is tied to
an SNR range, and that is on purpose, because the range changes the numbers a lot
and they get misread the moment you drop the context. So unless I say otherwise,
everything below is measured on the 0 to -20 dB set that I describe next.

An earlier version of this writeup rested on a set with one soundscape bed per
category, and it produced a speaker finding that turned out to be false once I
controlled for the bed. I have rebuilt the set to separate those two effects, and
I explain that in the rain section, because the correction is itself one of the
more useful things this evaluation produced.

One thing to say up front, so the numbers do not get misread: they are lower than
that earlier set, about 75% recall here against 87% there, and the plugin code did
not change at all between the two. The set got harder and more varied, so the drop
is the measurement getting more honest, not the detector getting worse.

## The dataset

There are 500 clips in total, and each one is 30 seconds long, 16 kHz, mono, and
24-bit (PCM_24), which is the same format the node itself produces now that the
plugin preserves the source subtype. Of those 500 clips, 400 contain speech and
100 are bed only.

The 400 speech clips are a full cross of 5 soundscape categories, 4 beds per
category, 4 speech sources, and 5 SNR levels. Crossing every source against every
bed is the important part, and it is what the earlier set got wrong: back then
there was a single bed per category, so the bed and the speaker were confounded
and I could not tell a bed effect from a speaker effect. Now each of the 4 beds in
a category is drawn independently, and all 4 speech sources are mixed into each
one, so the two effects come apart.

**Soundscape beds.** I used five ESC-50 categories that span from wilderness to
urban, which are `chirping_birds`, `crickets`, `wind`, `rain`, and `engine`.
Because an ESC-50 clip is only 5 seconds long, I built each 30-second bed by
concatenating 6 clips from the same category, and I drew 4 such beds per category.
I also deliberately stayed away from ESC-50's human-vocalization categories, such
as crying baby, laughing, and coughing, because those sounds would legitimately
trip a speech detector and would therefore pollute the false-positive number
rather than measure it.

**Loudness normalization.** Before I mix any speech in, I normalize every bed to
the same loudness target of -23 LUFS, using pyloudnorm and the EBU R128 standard.
This step matters more than it looks like it should, because if the beds are not
equalized first, then "speech at -5 dB SNR" ends up meaning a different real-world
level in each bed, and the whole sweep stops being comparable. If pyloudnorm is
not installed the script falls back to RMS and prints which method it used, but
this run used LUFS.

**Speech.** There are four speech sources, and I hold them constant across every
bed and every SNR so that the only things changing are the bed and the level. Two
of the sources are single speakers, one male and one female, both from LibriSpeech
dev-clean, and I read the sex from the SPEAKERS.TXT file that ships with the
corpus. The other two sources are overlapping-speaker mixes, which I make by
summing two different speakers so that both are talking at once. There are no
children in the set, because LibriSpeech has none, and I want to be clear that
this is a known gap rather than a design choice.

**SNR range.** The five levels are 0, -5, -10, -15, and -20 dB. I actually started
with a +10 to -10 range, but recall saturated near the top of it, so I shifted the
whole sweep down to find where the detector breaks. The important consequence is
that the 0 to -20 range is harder than the first one, so its numbers are not
comparable to the earlier numbers, and on top of that the crossed set is harder
still because it has more bed variety.

**Placement.** The speech always lands in the middle third of the clip, between
seconds 10 and 20, at a random start offset, with a random length somewhere
between 3 and 8 seconds and a 500 ms fade in and out, so that it sounds a bit like
someone walking past the microphone.

**Ground truth.** Each clip has a JSON sidecar next to it that records the bed
category, the bed index, the speech source id, the SNR, and the speech span. I
store the span as exact integer sample indices, `speech_start_sample` and
`speech_end_sample`, and I keep the seconds only as a rounded convenience. The
reason the samples are the real answer key is that they carry no floating-point
rounding at all, so there is never any ambiguity about which samples are speech.
For the speech-free clips, all of the speech fields are simply null.

## The metrics, and why leak matters more than recall

I measure three things, and the order I list them in is roughly the order of how
much they matter.

**Frame recall** is the fraction of the ground-truth speech samples that fell
inside a redaction window, weighted by samples. It is the obvious metric and it is
useful, but it is not the number I actually care about most.

**Leaked speech, measured in milliseconds,** is the ground-truth speech that no
window covered, and this is the privacy number. It matters more than recall,
because a clip can post 90% recall and still leak a whole spoken word, and one
leaked word is a privacy violation while a few extra percent of recall is not.
This is the same point I took from QUT-NOISE-TIMIT back in
[09](09-corpus-check-datasets.md), which is that you should tune a detector around
what the system is actually for rather than around frame-level agreement. For us,
that means the numbers to watch are leaked speech and lost bird audio, not frame
accuracy.

**False positives** are audio that got redacted where there was no speech, and
there are two versions of this that I have to keep apart, because they mean very
different things. The first version is the speech-free FP, which is measured on the
100 bed-only clips as the fraction of the clip that got redacted, and since there
is no speech anywhere in those clips, anything redacted is a genuine false trigger,
so this is the real ecology cost. The second version is the outside-span FP, which
is measured on the speech clips as the fraction of the non-speech samples that got
redacted, and this one is mostly the intended pre-roll and post-roll padding rather
than false detection. I used to only assert that split, but this time I measured
it, and the numbers are in the false-positive section below.

## Results at the default gate

The default gate is enter 0.25, exit 0.15, pre-roll 1.5 seconds, post-roll 0.75
seconds, and hangover 0.75 seconds, and everything in this table is on the 0 to
-20 dB set.

| SNR (dB) | recall % | mean leak (ms/clip) | worst leak (ms) |
|---:|---:|---:|---:|
| 0 | 92.5 | 399.9 | 6629.6 |
| -5 | 86.9 | 693.5 | 4959.1 |
| -10 | 79.4 | 1157.0 | 4294.4 |
| -15 | 69.5 | 1614.1 | 7781.0 |
| -20 | 49.3 | 2835.5 | 6979.0 |

Taken as a whole over the 0 to -20 dB range, the gate reaches 75.3% recall, leaks
1340.0 ms per clip on average, and leaks 7781.0 ms on its single worst clip. The
speech-free false-positive rate is 0.77%, and the outside-span figure is 5.9%,
which, as I show below, is mostly padding rather than error.

## Rain, and why the crossing mattered

Grouping the same results by bed category shows that the collapse is not spread
evenly, and one bed is doing most of the damage. These numbers are over the whole
0 to -20 dB range:

| bed | recall % | mean leak (ms) | worst leak (ms) |
|---|---:|---:|---:|
| chirping_birds | 78.2 | 1207.9 | 4510.2 |
| crickets | 79.4 | 1126.7 | 4890.1 |
| engine | 75.2 | 1361.6 | 6595.9 |
| rain | 57.0 | 2279.3 | 7781.0 |
| wind | 86.4 | 724.6 | 5923.0 |

Rain sits about 20 points below every other bed, so as an aggregate finding, rain
is clearly the hardest soundscape for the detector, and that makes sense, because
rain is broadband noise that overlaps the speech spectrum and masks it in a way
that tonal or narrowband soundscapes like wind, crickets, and birds do not.

The interesting part is what the earlier, confounded set got wrong. On that set
each category had a single bed, and the one rain bed happened to be paired with the
female speaker, who collapsed, while a later look at a male speaker in a different
rain bed showed a strong score. That looked like a clean speaker finding, that the
male voice punches through rain, and it was plausible. But once I crossed every
speaker against every rain bed, it fell apart. Here is the peak YAMNet score in the
speech span for all four sources against all four rain beds, at -20 dB:

| source | bed0 | bed1 | bed2 | bed3 |
|---|---:|---:|---:|---:|
| single male | 0.68 | 0.26 | 0.04 | 0.20 |
| single female | 0.06 | 0.15 | 0.57 | 0.03 |
| overlap A | 0.83 | 0.37 | 0.51 | 0.05 |
| overlap B | 0.18 | 0.01 | 0.29 | 0.03 |

The male does not survive rain across the board. He fires on bed0 and bed1 but is
blind on bed2 and bed3, so he clears the 0.25 enter threshold on only two of the
four rain beds. Meanwhile the female is blind on three of the four beds but
survives strongly on bed2, at 0.57, which is the exact opposite of the male. And
bed3 buries every source, with no peak above 0.20. In other words, at -20 dB in
rain, whether the detector fires is driven more by which specific rain bed you drew
than by which speaker is talking, and there is no stable speaker effect here at
all.

That is the methodology point, and it is worth stating plainly. The confounded
design produced a finding that was specific, plausible, and false, and the only
reason I caught it was that I controlled for the bed. A single bed per category is
not enough to make any claim about what the soundscape does to the detector,
because a claim like that needs the bed to vary while the speaker is held fixed,
and the other way around.

## Tuning: post-roll beats the enter threshold, at a cost

To understand the gate, I swept the enter threshold on its own while holding
everything else, and then I separately swept post-roll and hangover while holding
enter and exit, and all of this is on the 0 to -20 dB set.

First, here is the enter threshold sweep, with exit 0.15, pre-roll 1.5, post-roll
0.75, and hangover 0.75. The enter 0.10 row uses exit 0.10, clamped down, because
hysteresis requires the exit threshold to sit at or below the enter threshold:

| enter | exit | recall % | mean leak (ms) | worst leak (ms) | speech-free FP % |
|---:|---:|---:|---:|---:|---:|
| 0.10 | 0.10 | 81.8 | 987.6 | 6950.6 | 2.09 |
| 0.15 | 0.15 | 78.9 | 1142.8 | 7781.0 | 1.37 |
| 0.20 | 0.15 | 77.0 | 1249.2 | 7781.0 | 1.09 |
| 0.25 | 0.15 | 75.3 | 1340.0 | 7781.0 | 0.77 |

Next, here is the post-roll and hangover sweep, with enter 0.25, exit 0.15, and
pre-roll 1.5:

| post-roll (s) | hangover (s) | recall % | mean leak (ms) | worst leak (ms) | speech-free FP % |
|---:|---:|---:|---:|---:|---:|
| 0.75 | 0.75 | 75.3 | 1340.0 | 7781.0 | 0.77 |
| 0.75 | 1.50 | 75.6 | 1324.1 | 7781.0 | 0.77 |
| 0.75 | 2.50 | 75.9 | 1307.1 | 7781.0 | 0.77 |
| 1.50 | 0.75 | 79.8 | 1098.4 | 7781.0 | 0.94 |
| 1.50 | 1.50 | 80.0 | 1084.3 | 7781.0 | 0.94 |
| 1.50 | 2.50 | 80.2 | 1072.9 | 7781.0 | 0.94 |
| 2.50 | 0.75 | 83.7 | 885.4 | 7781.0 | 1.17 |
| 2.50 | 1.50 | 83.9 | 875.3 | 7781.0 | 1.17 |
| 2.50 | 2.50 | 83.9 | 871.1 | 7781.0 | 1.17 |

When I put the two levers side by side, post-roll is the stronger one, and it
beats lowering the enter threshold on recall and leak at the same time:

| change from default | recall % | mean leak (ms) | speech-free FP % |
|---|---:|---:|---:|
| baseline (enter 0.25, post 0.75) | 75.3 | 1340.0 | 0.77 |
| lower enter to 0.10 | 81.8 | 987.6 | 2.09 |
| raise post-roll to 2.5 | 83.7 | 885.4 | 1.17 |

So raising post-roll buys more recall and less leak than lowering enter does, and
it does so at a smaller false-positive cost, which is a nice result to be able to
back with numbers. It also makes sense once you connect it to the failure analysis
from earlier, because the enter threshold controls whether an utterance gets caught
at all, while post-roll controls how much of a caught utterance actually gets
covered, and the leak lives in the trailing edge that the frame timing keeps
missing. So the operating-point move that this points to is to raise post-roll
toward 1.5 to 2.5 seconds and leave the enter threshold at 0.25, rather than to
drop the enter threshold, and the cost belongs in the same sentence: going from
0.75 to 2.5 seconds of post-roll lifts the speech-free false-positive rate from
0.77% to 1.17%, because the padding extends every false detection just as it
extends the true ones. It is still a good trade given how lopsided the privacy
cost is, but it is a trade, not a free win.

## False positives and the padding split

I finally measured the padding split instead of just asserting it, by running the
gate with pre-roll and post-roll both set to zero and comparing. On the 0 to -20 dB
set:

| | with padding (1.5 / 0.75) | zero padding |
|---|---:|---:|
| outside-span FP | 5.9% | 0.7% |
| speech-free FP | 0.77% | 0.24% |

So about 88% of the 5.9% outside-span figure is intended padding rather than false
detection, which confirms the claim the old draft could only assert. The same
comparison also shows something the old draft missed, which is that padding roughly
triples the speech-free false-positive rate, from 0.24% to 0.77%, because a single
false frame gets extended into a two-second-plus window by the guard band. So the
padding is not only a cost on the speech clips, it is a cost on the genuine false
positives too.

Broken down by bed, the speech-free false-positive rate at the default gate is
small but not zero, and it is the birdsong number that matters most, because that
is the direct BirdNET cost:

| bed | speech-free FP % |
|---|---:|
| chirping_birds | 1.15 |
| crickets | 0.00 |
| engine | 1.07 |
| rain | 0.00 |
| wind | 1.61 |

Overall this is 0.77% across the 100 speech-free clips, so on average the detector
almost never fires on beds with no speech in them, which is good news for the bird
science. But it is not perfectly clean. Birdsong does trip it at 1.15%, wind trips
it a bit more at 1.61%, and the single worst speech-free clip is a birdsong clip
that got 23% of its 30 seconds redacted, which would be a real chunk of lost bird
audio if it happened in the field. Two things are worth saying about these numbers.
The first is that they are draw-sensitive, and an earlier, smaller speech-free set
of 25 clips showed a birdsong rate around 11% purely because of an unlucky draw,
which is why I raised the speech-free count to 100 to get a stable measurement. The
second is that anything that redacts real birdsong is exactly the cost this whole
project is trying to keep low, so the birdsong false-positive rate is worth
tracking as the set grows.

## What this eval cannot tell me yet

The points in this section are gaps in the evaluation, and I want to keep them
separate from the results so they do not get read as findings.

**Hangover is untested, not useless.** Hangover exists to bridge short pauses
inside a single utterance, so that the gate does not drop out in the middle of a
sentence. However, LibriSpeech is continuous read speech with very few internal
pauses, so this dataset barely contains any within-utterance gaps for hangover to
work on, which is exactly why the post-roll sweep above shows hangover moving the
numbers by only a few milliseconds at each post-roll setting. Real conversation has
gaps, so to actually exercise hangover I would need conversational or spontaneous
speech with pauses rather than read audiobook sentences.

**The rain floor is a detector limit, not a tuning target.** On the rain beds that
bury the speech, YAMNet's output sits down at the noise floor, so no value of
enter, exit, post-roll, or hangover can recover speech that the detector simply
cannot hear. Moving that floor would take a spectrally-aware or purpose-trained
detector, which is the ecoVAD direction I wrote up in
[09](09-corpus-check-datasets.md), rather than any amount of gate tuning.

**The set is small and synthetic.** It has 4 speakers and mixed audio rather than
field recordings, with no children. Crossing sources against 4 beds per category is
enough to separate bed effects from speaker effects and to kill the false speaker
finding, but it is not enough to pick a final operating point for a real
deployment, and four speakers is too few to say anything general about speakers at
all.

## Reproducing

The scripts, along with setup and download instructions, live in their own repo at
[github.com/Miguel-Hernandez1/speech-redaction-qa](https://github.com/Miguel-Hernandez1/speech-redaction-qa),
so anyone can reproduce this without my local paths. There are three of them.
`generate_qa.py` builds the clips and their sidecars, `score_qa.py` runs the
plugin's own `speech_scores` exactly once and saves the raw per-frame scores into
`scores/`, and `evaluate_qa.py` applies the gate to those saved scores and prints
the tables, grouped by both SNR and bed category. The split is the whole point,
because scoring is the expensive step and it only has to run once, which means that
sweeping gate parameters against the saved scores takes seconds instead of
re-running the model. On top of that, all of the counts, which are the categories,
the beds per category, the speech sources, the SNR levels, and the speech-free
count, are top-of-file constants, so the set can be scaled up later without
touching any of the logic.
