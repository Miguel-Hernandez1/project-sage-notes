# Speech Redaction: Possible Next Steps

**Miguel Hernandez, August 11, 2026**

Notes from my presentation on the speech redaction project (August 10),
written up as possible options. I grouped the ideas by theme and tried to
include what each one would give us, along with the main tradeoffs or work
involved.

## Where things currently stand

The microphone path now works end-to-end, and YAMNet runs on the Thor through
LiteRT; the gate creates padded redaction windows, speech is zeroed in memory
before anything gets written, and the system fails closed. It is also packaged
as a standalone plugin with its own ecr-meta, and we have built and run it in
its container on H032.

But there are still two things we have not proven yet: a live capture from a
physical microphone and a run against a mounted shared cache, since that cache
does not yet exist on the nodes. Additionally, the camera path is designed but
has not been built, so that is also an option for next steps.

The biggest gap that came out of the presentation is evaluation methods for the
software. Right now the test set is only about 5 clips and 2 songs, and they
separate so cleanly that they do not really tell us where the thresholds should
be or how the system behaves when the conditions are less ideal.

## 1. Evaluation data: the thing that unblocks everything else

Several people made basically the same point during the meeting: before this
can be considered credible anywhere close to a real deployment, we need
evidence that actually holds up when someone starts asking questions about how
well it works.

One option that was brought up was to build a synthetic evaluation set. We
could take real field recordings from public soundscape libraries, ideally
recordings with real birds and realistic background conditions, and then mix
human speech into them at known times and known levels. Since we control when
and how the speech is added, the ground truth is exact, and we know exactly
which parts contain speech, which means recall and false-positive rate become
actual measurements rather than estimates.

The set should cover a few different conditions, including:

- Loudness, from close conversation down to distant or barely audible speech
- Distance and direction from the microphone
- Multiple languages and accents
- Speech overlapping with birdsong instead of only appearing during quiet parts
- Different recording qualities, since microphones and stream settings will not
  all behave the same way

I also think a human QA step would be important, another thing brought up in the
meeting. This is because automated metrics can tell us how the classifier
performed, but someone actually listening to the redacted output and confirming
that the speech is gone while the birdsong is still there gives us a different
kind of evidence. And if we eventually have to explain this system to a park
service, that kind of demonstration is going to be more convincing than just
showing a precision and recall number.

The main benefit here is that it gives us a defensible answer to the basic
question of "how do you know it works?" It also gives us a real operating point
for the thresholds instead of relying on conservative defaults, and it would let
us measure how much birdsong we are actually losing because of the padding
around speech detections.

The downside is mostly the amount of work; sourcing the recordings, building the
mixing pipeline, generating the test cases, and then doing the listening pass is
the largest single item on this list. At the same time, a lot of the other
decisions depend on having this data, so it is probably worth doing first.

## 2. Separating speech instead of blanking the whole time window

Right now, when speech is detected, we zero out the entire redaction window.
That means we also remove any birdsong that happens to be in that same window.
On the demo clip, for example, about 82 percent of the audio ended up being
erased, and although that might be fine in a quiet park where speech is rare, if
we move to an urban setting where people are talking more often, we could end up
destroying most of the useful signal.

So a possible next step is source separation, where the model tries to separate
the human voice from everything else and then masks only the voice. In that
case, birdsong that happens at the same time as someone talking could still be
kept. This is a much more capable approach than what we have now, and it would
make the system more useful in noisier or more populated areas.

The other idea that came up is almost the opposite approach: instead of
detecting speech and removing it, detect birds and keep only the bird audio. So
start from silence and only add back sounds that we have positively identified
as birds. This gives us a much stricter privacy posture because anything the
system does not recognize gets thrown away by default rather than kept by
default. The tradeoff, however, is that we would lose any real soundscape data
that is neither bird nor speech, and the whole approach would depend heavily on
how good the bird detector is.

Either approach could greatly reduce the amount of useful audio that gets lost,
which is the main reason to look into it. The downside is that this becomes a
real modeling problem rather than just a threshold-tuning problem, and source
separation models are also heavier than YAMNet, so we would need to check
whether the on-node compute is enough.

## 3. Where redaction happens in the pipeline

The current design redacts before anything is written to disk, and the
reasoning is: once raw speech has been persisted, we have already recorded that
person, even if we plan to delete or redact it later.

The counterargument is that doing the redaction later in the pipeline, as long
as it happens before upload or long-term storage, gives us more flexibility.
Also, not every deployment may have the same level of risk, so it may not make
sense to force every site into the strictest possible setup.

I think both arguments make sense, but for different phases of the project.

During development and evaluation, immediately redacting the audio creates a
problem because we lose the evidence we need to evaluate the system. And if the
original speech is gone, we cannot tell what the system missed. So this means
that keeping the originals in a controlled environment is what makes the
evaluation work in section 1 possible in the first place.

For a deployment like Haleakalā, where the requirement is that it should be
impossible to accidentally record a visitor, redacting in memory before anything
is persisted is what actually gives us that guarantee. Because of that, a
reasonable solution may be to make this a configurable privacy posture rather
than forcing one design everywhere. And a strict mode could redact in memory
before any write, while a more permissive mode could retain the original for a
short, bounded period and redact it before upload. However, the underlying
detection logic would stay the same.

There is also a related question that I think is worth answering more
concretely: how late in the pipeline can redaction happen while still being
useful? Being able to redact audio after it has already been collected could be
valuable even if a particular site ultimately chooses the strict mode, since it
would give us a way to fix data that has already been collected.

The main benefit of thinking about it this way is that the system can support
more than one type of deployment, while also giving us a clear answer to the
objection that redaction has to happen at one specific point in every situation.
The downside is that we would have two code paths to maintain, along with a
policy for deciding which sites are allowed to use which mode.

## 4. Sensor and signal level

Another good point was raised during the presentation; it was suggested that the
microphone itself may matter almost as much as the software. And if we can avoid
capturing as much human speech in the first place, then the redaction system has
less work to do and does not have to be perfect.

For example, directional microphones could be aimed away from trails or toward
areas where people are not expected to be, which could reduce how much speech
gets picked up in the first place.

The frequency response of the microphone also matters. If the sensor or
filtering is better suited to the frequency ranges where birds are active, then
there may be less speech energy in the signal before it even reaches the
classifier.

It is also worth talking with Samin about noise gating and frequency filtering
before classification because some signal processing here might improve the
input enough that the model does not have to do all of the work itself.

The main benefit is that if there is less speech in the input, there is less
speech to redact, and we become less dependent on the classifier being perfect.
The tradeoff is that this becomes partly a hardware decision, and filtering the
signal too aggressively could also remove legitimate parts of the soundscape.

## 5. Model and pipeline alternatives

There are a few other things that are worth testing, although I would put them
behind the evaluation work above.

- Whisper or similar speech models could be tested against YAMNet, either as a
  second opinion or potentially as a replacement. But I would rather benchmark
  this than assume another model will be better.
- Per-microphone tuning could also help. Different sensors will behave
  differently, so a model or threshold set tuned for each microphone type might
  perform better than one global setting.
- Reprocessing existing recordings could give us another way to build evaluation
  evidence. So instead of collecting everything from scratch, we could run the
  pipeline over audio we already have, along with its metadata, and use that to
  look for failure cases and tune the system.

## 6. Smaller items

There are also a few smaller pieces that are probably worth cleaning up as we
continue.

- Redaction events as a data product. The system already emits a tuple with the
  start time and duration for each redaction. Formalizing that schema for
  Beehive would make the events easier to query and audit, and it would also
  help distinguish a genuinely quiet site from a sensor or pipeline that has
  stopped working.
- Zeroed audio could confuse downstream processing. Some audio tools do not
  always behave well when the signal suddenly drops to exact zero. It would be
  worth testing whether BirdNET is affected and whether a very low noise floor
  would be safer than true silence.
- Make the gate parameters plugin arguments. The current values are hardcoded
  defaults, so these should be configurable for different deployments once we
  have a better idea of the right operating range.
- Finish the two live integration runs. We still need a live microphone run and
  a live cache run, which are the remaining integration pieces mentioned above.

## Suggested priority

If the immediate goal is to get to a demonstration that we can actually defend,
I would put section 1 first. Without a real evaluation set, it is hard to make a
strong argument about anything else, and the results from that work should give
us the measurements we need to make the other decisions.

After that, section 2 is the most interesting technical direction, especially if
we expect this to work somewhere that is not a quiet site. Source separation or
a similar approach could make a big difference in how much useful birdsong we
lose.

I would also settle section 3 relatively early, since the choice about where
redaction happens affects how we collect and preserve data during the evaluation
work in section 1. In other words, the evaluation work should probably come
first, but we should decide what data we are allowed to keep before we start
collecting a lot more of it.
