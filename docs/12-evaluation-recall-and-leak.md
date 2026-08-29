# Evaluation: Recall, Leaked Speech, and Where the Detector Collapses

**Miguel Hernandez, August 29, 2026**

This is the first real measurement of how well the redaction detector actually
works, and to get it I built a synthetic set where I know exactly where the
speech is, because I placed it there myself. Every number in this doc is tied to
an SNR range, and that is on purpose, because the range changes the numbers a lot
and they get misread the moment you drop the context. So unless I say otherwise,
everything below is measured on the 0 to -20 dB set that I describe next.

## The dataset

There are 125 clips in total, and each one is 30 seconds long, 16 kHz, mono, and
24-bit (PCM_24), which is the same format the node itself produces now that the
plugin preserves the source subtype. Of those 125 clips, 100 contain speech and
25 are bed only, and the 100 speech clips are a full cross of 5 soundscape beds,
4 speech sources, and 5 SNR levels.

**Soundscape beds.** I used five ESC-50 categories that span from wilderness to
urban, which are `chirping_birds`, `crickets`, `wind`, `rain`, and `engine`.
Because an ESC-50 clip is only 5 seconds long, I built each 30-second bed by
concatenating 6 clips from the same category. I also deliberately stayed away
from ESC-50's human-vocalization categories, such as crying baby, laughing, and
coughing, because those sounds would legitimately trip a speech detector and
would therefore pollute the false-positive number rather than measure it.

**Loudness normalization.** Before I mix any speech in, I normalize every bed to
the same loudness target of -23 LUFS, using pyloudnorm and the EBU R128
standard. This step matters more than it looks like it should, because if the
beds are not equalized first, then "speech at -5 dB SNR" ends up meaning a
different real-world level in each bed, and the whole sweep stops being
comparable. If pyloudnorm is not installed the script falls back to RMS and prints
which method it used, but this run used LUFS.

**Speech.** There are four speech sources, and I hold them constant across every
bed and every SNR so that the only things changing are the bed and the level. Two
of the sources are single speakers, one male and one female, both from
LibriSpeech dev-clean, and I read the sex from the SPEAKERS.TXT file that ships
with the corpus. The other two sources are overlapping-speaker mixes, which I make
by summing two different speakers so that both are talking at once. There are no
children in the set, because LibriSpeech has none, and I want to be clear that
this is a known gap rather than a design choice.

**SNR range.** The five levels are 0, -5, -10, -15, and -20 dB. I actually started
with a +10 to -10 range, but recall saturated near the top of it, so I shifted the
whole sweep down to find where the detector breaks. The important consequence is
that the 0 to -20 range is harder than the first one, so its numbers are not
comparable to the earlier numbers. In other words, the 86.8% overall recall you
will see below is not the same measurement as the 96.3% I got at +10 to -10, even
though they look like they should line up.

**Placement.** The speech always lands in the middle third of the clip, between
seconds 10 and 20, at a random start offset, with a random length somewhere
between 3 and 8 seconds and a 500 ms fade in and out, so that it sounds a bit like
someone walking past the microphone.

**Ground truth.** Each clip has a JSON sidecar next to it that records the bed
category, the speech source id, the SNR, and the speech span. I store the span as
exact integer sample indices, `speech_start_sample` and `speech_end_sample`, and I
keep the seconds only as a rounded convenience. The reason the samples are the
real answer key is that they carry no floating-point rounding at all, so there is
never any ambiguity about which samples are speech. For the speech-free clips, all
of the speech fields are simply null.

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
25 bed-only clips as the fraction of the clip that got redacted, and since there is
no speech anywhere in those clips, anything redacted is a genuine false trigger, so
this is the real ecology cost. The second version is the outside-span FP, which is
measured on the speech clips as the fraction of the non-speech samples that got
redacted, and this one is mostly the intended pre-roll and post-roll padding rather
than false detection. The reason is that the gate adds 1.5 seconds before and 0.75
seconds after every detection on purpose, and on a speech clip that padding falls
outside the exact ground-truth span and gets counted here. So the way to read these
is to treat the speech-free number as the false-positive rate, and to treat the
outside-span number as a measure of how much guard band the padding adds, which
means you should expect it to grow whenever I raise the roll.

## Results at the default gate

The default gate is enter 0.25, exit 0.15, pre-roll 1.5 seconds, post-roll 0.75
seconds, and hangover 0.75 seconds, and everything in this table is on the 0 to
-20 dB set.

| SNR (dB) | recall % | mean leak (ms/clip) | worst leak (ms) |
|---:|---:|---:|---:|
| 0 | 98.9 | 54.5 | 894.8 |
| -5 | 97.8 | 118.5 | 1001.2 |
| -10 | 97.2 | 172.1 | 1351.9 |
| -15 | 82.4 | 1007.9 | 4914.8 |
| -20 | 58.5 | 2340.0 | 6704.4 |

Taken as a whole over the 0 to -20 dB range, the gate reaches 86.8% recall, leaks
738.6 ms per clip on average, and leaks 6704.4 ms on its single worst clip. The
speech-free false-positive rate is 1.35%, and the outside-span figure is 7.5%,
which, as I explained above, is mostly padding rather than error.

## Where it collapses, and why it is rain

Recall holds around 97 to 99% all the way down through -10 dB, then it drops to
82.4% at -15, and finally it falls to 58.5% at -20. However, that collapse is not
spread evenly across the beds, and once I looked closer it turned out to be mostly
one bed doing the damage.

The clearest way to see it is to take the same single female speaker and look at
the peak YAMNet score inside her speech span across every bed and SNR:

| bed | 0 dB | -5 dB | -10 dB | -15 dB | -20 dB |
|---|---:|---:|---:|---:|---:|
| chirping_birds | 0.995 | 0.902 | 0.982 | 0.875 | 0.879 |
| crickets | 0.888 | 0.803 | 0.965 | 0.970 | 0.810 |
| wind | 0.995 | 0.995 | 0.987 | 0.991 | 0.965 |
| rain | 0.978 | 0.637 | 0.944 | 0.108 | 0.033 |
| engine | 0.859 | 0.896 | 0.877 | 0.573 | 0.442 |

The exact same voice that YAMNet hears at 0.965 in wind at -20 dB, it barely hears
at all, at 0.033, in rain at the same -20 dB. So rain is the killer, and the reason
is that rain is broadband noise that overlaps the speech spectrum, which means it
masks speech in a way that tonal or narrowband soundscapes like crickets, birds,
and wind simply do not. Engine is the second-worst bed for the same reason, though
it is not nearly as extreme.

The worst-case leak clips are always at -20 dB, but if you look at them closely
there are actually two different failure modes hiding in there. The first is the
detector-blind case, and the example is `speech_070`, which is rain at -20 dB with
a peak score of 0.033, right at the noise floor. Because YAMNet never fires on it,
no gate setting can recover it, since there is simply nothing to threshold, and
this is a real limit that I want to state plainly rather than try to tune around.
The second is the threshold-margin case, and the example is `speech_055`, which is
wind at -20 dB with a peak score of 0.235, just under the 0.25 enter threshold.
Here YAMNet actually did fire, only weakly, and the gate just did not let it
through, so this one is recoverable by lowering the enter threshold below 0.235.
That is exactly why `speech_055` is the single worst clip at enter 0.25 but stops
being the worst as soon as you drop the threshold.

## Tuning: post-roll beats the enter threshold

To understand the gate, I swept the enter threshold on its own while holding
everything else, and then I separately swept post-roll and hangover while holding
enter and exit, and all of this is on the 0 to -20 dB set.

First, here is the enter threshold sweep, with exit 0.15, pre-roll 1.5, post-roll
0.75, and hangover 0.75. The enter 0.10 row uses exit 0.10, clamped down, because
hysteresis requires the exit threshold to sit at or below the enter threshold:

| enter | exit | recall % | mean leak (ms) | worst leak (ms) | speech-free FP % |
|---:|---:|---:|---:|---:|---:|
| 0.10 | 0.10 | 90.1 | 557.3 | 5712.7 | 2.46 |
| 0.15 | 0.15 | 88.7 | 632.0 | 5712.7 | 1.84 |
| 0.20 | 0.15 | 87.8 | 686.7 | 5712.7 | 1.41 |
| 0.25 | 0.15 | 86.8 | 738.6 | 6704.4 | 1.35 |

Next, here is the post-roll and hangover sweep, with enter 0.25, exit 0.15, and
pre-roll 1.5:

| post-roll (s) | hangover (s) | recall % | mean leak (ms) | worst leak (ms) | speech-free FP % |
|---:|---:|---:|---:|---:|---:|
| 0.75 | 0.75 | 86.8 | 738.6 | 6704.4 | 1.35 |
| 0.75 | 1.50 | 87.4 | 708.8 | 6704.4 | 1.35 |
| 0.75 | 2.50 | 87.4 | 708.8 | 6704.4 | 1.35 |
| 1.50 | 0.75 | 89.6 | 582.6 | 6704.4 | 1.65 |
| 1.50 | 1.50 | 89.9 | 567.9 | 6704.4 | 1.65 |
| 1.50 | 2.50 | 89.9 | 567.9 | 6704.4 | 1.65 |
| 2.50 | 0.75 | 91.7 | 467.1 | 6704.4 | 2.05 |
| 2.50 | 1.50 | 91.7 | 464.8 | 6704.4 | 2.05 |
| 2.50 | 2.50 | 91.7 | 464.8 | 6704.4 | 2.05 |

When I put the two levers side by side, post-roll turns out to be the stronger
one, and it actually beats lowering the enter threshold on all three axes at the
same time:

| change from default | recall % | mean leak (ms) | speech-free FP % |
|---|---:|---:|---:|
| baseline (enter 0.25, post 0.75) | 86.8 | 738.6 | 1.35 |
| lower enter to 0.10 | 90.1 | 557.3 | 2.46 |
| raise post-roll to 2.5 | 91.7 | 465 | 2.05 |

So raising post-roll buys more recall and less leak than lowering enter does, and
it does so at a lower false-positive cost, which is a nice result to be able to
back with numbers. It also makes sense once you connect it to the failure analysis
from earlier, because the enter threshold controls whether an utterance gets caught
at all, while post-roll controls how much of a caught utterance actually gets
covered, and the leak lives in the trailing edge that the frame timing keeps
missing. As a result, the operating-point move that this points to is to raise
post-roll toward 1.5 to 2.5 seconds and leave the enter threshold at 0.25, rather
than to drop the enter threshold.

There is one thing that post-roll cannot do, though, and it shows up clearly in the
tables. The worst-case leak stays pinned at 6704.4 ms across the entire post-roll
and hangover sweep, and that is `speech_055` again, which never clears the 0.25
enter threshold, so there is no detected window for the padding to extend. In other
words, padding only helps on clips where detection has already fired, so the clips
that are buried in rain stay a detection-floor problem, and nothing on the padding
side touches them.

## What this eval cannot tell me yet

The points in this section are gaps in the evaluation, and I want to keep them
separate from the results so they do not get read as findings.

**Hangover is untested, not useless.** Hangover exists to bridge short pauses
inside a single utterance, so that the gate does not drop out in the middle of a
sentence. However, LibriSpeech is continuous read speech with very few internal
pauses, so this dataset barely contains any within-utterance gaps for hangover to
work on, which is exactly why it only moves the numbers by a few milliseconds here.
Real conversation has gaps, so to actually exercise hangover I would need
conversational or spontaneous speech with pauses rather than read audiobook
sentences.

**The rain floor is a detector limit, not a tuning target.** At -15 and -20 dB in
rain, YAMNet's output sits down at the noise floor, so no value of enter, exit,
post-roll, or hangover can recover speech that the detector simply cannot hear.
Moving that floor would take a spectrally-aware or purpose-trained detector, which
is the ecoVAD direction I wrote up in [09](09-corpus-check-datasets.md), rather
than any amount of gate tuning.

**The set is small and synthetic.** It has 4 speakers, 5 beds, and 100 speech
clips, with no children, and everything is mixed rather than recorded in the field.
That is enough to find the rain collapse and to rank the gate levers against each
other, but it is not enough to pick a final operating point for a real deployment.

## Reproducing

There are three scripts for this, and they live in `~/AI-Projects/qa-dataset`,
which is a scratch area rather than part of this repo. `generate_qa.py` builds the
clips and their sidecars, `score_qa.py` runs the plugin's own `speech_scores`
exactly once and saves the raw per-frame scores into `scores/`, and
`evaluate_qa.py` applies the gate to those saved scores and prints the tables. The
split is the whole point, because scoring is the expensive step and it only has to
run once, which means that sweeping gate parameters against the saved scores takes
seconds instead of re-running the model. On top of that, all of the counts, which
are the beds, the speech sources, the SNR levels, and the speech-free count, are
top-of-file constants, so the set can be scaled up later without touching any of
the logic.
