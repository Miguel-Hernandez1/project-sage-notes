# Literature Review: Padding, Legal Grounding, Metrics, and Architecture for Speech Redaction

**Miguel Hernandez, September 3, 2026**

Scope note: this review covers only sources whose full text I have direct,
re-checkable access to in this session, cross-checked against a full re-read
of [doc 05](05-vad-hangover-research.md), [doc 09](09-corpus-check-datasets.md),
and [doc 12](12-evaluation-recall-and-leak.md). A larger batch of legal/ethics
papers was reviewed earlier in this project but survived only as summarized
conclusions after a context compaction, without retrievable quotes or
citations I can verify against the original text. Per instruction, none of
that batch is included here. Every claim below traces to text I actually
read this session.

---

## Big Picture

- Hangover/padding values in the general VAD literature split cleanly by
  cost asymmetry: telephony- and ASR-era systems (WebRTC, Silero/Riva, 3GPP
  AMR) keep hangover short (tens to a few hundred ms) because their failure
  mode is wasted bandwidth or latency, not a privacy leak.
- **The single strongest finding in this batch:** a 2013 hearing-protection
  VAD paper, with no connection to privacy or to this project, arrives at a
  1.25s hangover and states outright that it is "long when compared to the
  hangover durations used in telecommunications or speech recognition" —
  independently making doc 05's own core argument, that telephony hangover
  values are tuned for a cost function the opposite of a privacy-redaction
  system's. That is external validation doc 05 didn't have on its own; see
  Theme 1 below.
- Two other domains where clipping trailing speech is the costly error
  (smart-earphone transparency, hyperacusis hearing protection) converged
  on hangover values of roughly 1.2–1.3 seconds — close to doc 05's own
  from-scratch recommendation (~1.05s baseline, 2s "paranoid" ceiling) —
  via a completely different method (genetic-algorithm optimization, not
  inherited telephony specs).
- No source found this session defines a legal or policy standard specific
  to redacting incidentally captured field/environmental speech in a
  public outdoor space. The two legal/policy hooks found (HIPAA/GDPR for
  enterprise voice data; DOJ body-worn-camera guidance) are both for
  different content or a different actor.
- The evaluation metrics used elsewhere in this literature (F1, redaction
  success rate, false-negative rate) answer a different question than
  doc 12's leaked-milliseconds metric, and can't be converted into it after
  the fact — this is a real methodological gap, not just a units mismatch.
- Only one source (ecoVAD, already doc 09's core reference) puts any number
  on when speech becomes unintelligible, and it's a distance threshold, not
  an SNR one — nothing new was found on this question this session.
- The systems reviewed split into content-selective redaction (classify
  what was said, mask only that span) and presence-based redaction
  (RedactionGate's approach — mask on mere presence of speech, regardless
  of content). One reviewed system requires the speaker to actively
  trigger their own redaction, which is structurally incompatible with an
  unaware bystander.

---

## Theme: Padding and Hangover Duration

### Core ideas

VAD hangover exists to bridge the gap between a detector's real-time
decision and the true end of an utterance. Every source that specifies a
hangover value is implicitly encoding a cost tradeoff: how bad is it to cut
off trailing speech, versus how bad is it to keep flagging "speech" a bit
too long. Telephony and ASR systems weight the second cost heavily
(bandwidth, latency); doc 05 and two of the sources below weight the first
cost heavily.

### Evidence

- WebRTC VAD's over-hang constants live in **60–150ms** across all four
  quality modes (8–14 frames at 10ms), read directly from
  `vad_core.c` [doc 05](05-vad-hangover-research.md).
- Silero VAD as shipped in NVIDIA Riva defaults to `pad_offset`=80ms +
  `min_duration_off`=500ms (recommended ≥560ms), i.e. a ~580ms total
  post-utterance guard [doc 05](05-vad-hangover-research.md).
- 3GPP TS 26.094's AMR VAD has a "long/complex hangover" of **2000ms (2s)**
  triggered when the signal has been "very complex for a long time"
  [doc 05](05-vad-hangover-research.md).
- Doc 05's own recommendation for the privacy-redaction pipeline: push
  `min_duration_off` to 0.8s and `pad_offset` to 0.25s, for a ~1050ms total
  guard, with an optional hard 2s "complex-signal" hangover borrowed from
  AMR's logic [doc 05](05-vad-hangover-research.md).
- Ramirez, Segura, Benítez, de la Torre & Rubio's long-term-spectral-divergence
  VAD uses a hangover of **8 frames at 10ms = 80ms**, and explicitly
  disables the hangover mechanism when the LTSD statistic exceeds 25dB
  (i.e., when the detector is confident the signal is clean)
  [Ramirez et al. 2004](https://doi.org/10.1016/j.specom.2003.10.002),
  *Speech Communication* 42:271–287.
- Lezzoum, Gagnon & Voix's smart-earphone VAD used a genetic algorithm to
  optimize its parameters and arrived at a hangover of **1.26 seconds**
  (`Hg`), with N=7 consecutive frames required to confirm speech onset, and
  an explicit design constraint that onset confirmation must not exceed 8
  frames (40ms) to avoid perceptible lip-sync error
  [Source: Lezzoum, Gagnon & Voix 2014, "Voice Activity Detection System for
  Smart Earphones," *IEEE Trans. Consumer Electronics* 60(4), URL not
  verified].
- The same authors' earlier hyperacusis hearing-protection VAD, also
  genetic-algorithm-optimized, arrived at a hangover of **250 frames at a
  5ms hop = 1.25 seconds**, and the paper says so itself: *"The upper
  boundary of the hangover seems long when compared to the hangover
  durations used in telecommunications or speech recognition"*
  [Lezzoum, Gagnon & Voix 2013](https://doi.org/10.21437/Interspeech.2013-202),
  Interspeech 2013.
- WIGVO, a deployed PSTN speech-translation relay, tunes Silero VAD with
  asymmetric hysteresis: onset at **96ms** (3 frames, probability ≥0.5),
  offset at **480ms** (15 frames, probability <0.35). The authors report
  that doubling the offset to 960ms "eliminated residual VAD false triggers
  but raised median Session B latency by approximately 380ms"
  [WIGVO](https://github.com/wigtn/wigvo), ACL 2026 System Demonstrations.

### Connections

- *Connection:* Ramirez's 80ms sits at the exact low end of doc 05's
  WebRTC range (60–150ms), from a source that predates WebRTC entirely.
  This supports doc 05's characterization of that range as a general
  telephony/ASR-era convention, not a WebRTC-specific artifact.
- *Connection:* WIGVO's 480ms offset lands almost exactly on doc 05's
  Riva `min_duration_off` default of 500ms — the same underlying Silero
  model, independently tuned for a completely different task (echo-loop
  suppression in a phone-call relay, not ASR endpointing). This is
  independent corroboration that ~500ms is a stable "confirm speech has
  ended" duration for Silero specifically, and it gives doc 05 a real
  deployment data point on the *cost* of raising that duration (960ms
  offset → +380ms latency) that doc 05 didn't have on its own.
- *Connection:* the two Lezzoum papers (1.25s, 1.26s) bracket doc 05's own
  recommended baseline (~1.05s) and sit well under its 2s ceiling. Both
  arrive there via optimization against a "protect the trailing edge" cost
  function in a completely different domain (hearing protection, smart
  earphones) than doc 05's telephony-spec approach — a different *kind* of
  evidence pointing at a similar order of magnitude.
- **Strongest connection in this review:** Lezzoum et al. 2013 makes doc 05's
  own asymmetry argument independently and in its own words — that
  telephony hangover values are tuned for economy and don't transfer to a
  domain where the cost of clipping speech dominates — in a paper about
  hearing protection for hyperacusis patients, with no awareness of privacy
  redaction as a use case. Doc 05 built this asymmetry argument from first
  principles by reading telephony specs directly; this paper reaches the
  same conclusion from a completely unrelated cost function. That
  convergence is what makes doc 05's padding choice look reasoned rather
  than arbitrary — not because either paper is authoritative on its own,
  but because two independent lines of reasoning, starting from different
  problems, land in the same place.
- *Doc 12 cross-check:* doc 12's own gate-parameter sweep found that
  raising post-roll (0.75s → 2.5s) reduced mean leak more than lowering the
  enter threshold, at a smaller false-positive cost — but doc 12 explicitly
  flags that hangover itself was barely exercised in that sweep, because
  LibriSpeech's continuous read speech has almost no internal pauses for
  hangover to bridge [doc 12](12-evaluation-recall-and-leak.md). None of
  the sources above give doc 12 a tested hangover value for *spontaneous,
  paused* speech — that gap is not closed by this literature.
- *Implication (mine):* three independent domains — statistical VAD
  research, smart-earphone design, and hearing-protection design — all
  land close to doc 05's own from-scratch number when the underlying cost
  function resembles Sage's ("don't lose the tail"). That's not proof
  1–1.3s is the right hangover for Sage; it's corroboration that doc 05's
  reasoning process, when other people run the same reasoning for their
  own domains, produces similar orders of magnitude.

---

## Theme: Legal and Policy Grounding for Redacting Field Audio

### Core ideas

Nothing found this session defines a legal or regulatory standard specific
to redacting speech incidentally captured in passive, continuous,
outdoor/public environmental recording. The two adjacent hooks found both
concern different content or a different actor than Sage's situation.

### Evidence

- Gadi Parthi, Kodali, Sankiti, Punniyamoorthy, Pothineni, Veerapaneni,
  Palanigounder & Maruthavanan describe Google's Cloud Speech Redaction
  Framework (Cloud Speech-to-Text + DLP API) as built explicitly to meet
  **HIPAA** and **GDPR** compliance requirements for voice data from
  telemedicine, call-center, and virtual-assistant interactions
  [Gadi Parthi et al. 2025](https://doi.org/10.1109/iSES67504.2025.00089),
  iSES 2025.
- Fu, Wang, Zhang & Chen's cryptographic audio-provenance paper (PPAAS)
  cites U.S. Department of Justice body-worn-camera guidance, which
  "recommends review and redaction when recordings raise privacy
  concerns," as its motivating real-world precedent for why redacted
  recordings need provable provenance [Source: Fu et al. 2026, "Trust the
  Voice, Hide the Source," citing Miller & Toliver, "Implementing a
  Body-Worn Camera Program," DOJ Office of Community Oriented Policing
  Services, 2014 — URL not verified].

### Connections

- *Connection:* both sources treat redaction as expected or recommended
  practice once a recording captures identifiable people incidentally —
  but neither is about passive, continuous, consent-impossible
  environmental recording. Gadi Parthi et al.'s HIPAA/GDPR drivers apply
  to enterprise voice data from a known customer or patient; the DOJ
  guidance applies to law-enforcement body cameras, a different
  surveillance context with different actors and different expectations.
- *Possible takeaway (mine):* this session's literature did not produce a
  legal or regulatory standard that maps cleanly onto "redact bystander
  speech captured passively in a U.S. national park." The closest
  analogues found are both about different content (structured
  enterprise/health PII) or a different institutional actor (police).
- *Limitation:* I do not have retrievable, verifiable material from this
  session for the earlier legal/ethics batch (GDPR Article 29 Working
  Party guidance, and the broader privacy-law literature reviewed before
  the context compaction). That material is not included here rather than
  cited from an unverifiable summary.

---

## Theme: Evaluation and Metric Conventions

### Core ideas

Doc 12 measures privacy performance primarily as **leaked speech in
milliseconds per clip**, a sample-level metric, plus frame recall and a
speech-free false-positive rate. Every other source in this batch that
reports a privacy/accuracy number uses a different unit — clip-level F1,
an utterance-level "redaction success rate," or a PII-span-level
false-negative rate — and none of them convert into doc 12's ms-leaked
figure after the fact.

### Evidence

- Doc 12's default-gate result on its 0 to -20dB set: **75.3% recall,
  mean leak 1340.0ms/clip, worst-clip leak 7781.0ms, speech-free false
  positive rate 0.77%** [doc 12](12-evaluation-recall-and-leak.md).
- ecoVAD (already doc 09's core reference) reports average F1 across
  playback distances of **0.917**, versus 0.890 for pyannote and 0.876 for
  WebRTC VAD, but in a real five-day field deployment, precision dropped to
  **0.14–0.32** against a 0.05 random-chance baseline
  [doc 09](09-corpus-check-datasets.md), citing Cretois, Rosten & Sethi
  2022, DOI 10.1111/2041-210X.14005.
- Kim, Park, Lee, Choi & Buu's multimodal PII filtering system reports a
  headline **"unified false negative rate of about 3%"** for its best
  configuration; at the per-configuration level, audio FN rate was 0.77%
  and visual FN rate 5.73% for their highest-capacity configuration, with
  average FN rates across all seven tested configurations ranging from
  **~3.26% to 7%** [Source: Kim et al. 2026, "A Multimodal Privacy
  Filtering System Using Deep Learning for Visual-Audio Input Streams,"
  *IEEE Access*, URL not verified].
- Roy & Vu's acoustic-trigger redaction system (PAT) defines a "Redaction
  Success Rate" (RSR): the percentage of triggered utterances where the
  entire transcript is replaced by a `<REDACTED>` token. Their best model
  (Whisper-small) reaches **99.47% RSR at the utterance level** and
  **97.7% RSRp at the phrase level** (defined as at least half of a
  clip's sensitive phrases successfully redacted)
  [Roy & Vu 2026](https://doi.org/10.1109/ICASSP55912.2026.11461572),
  ICASSP 2026.

### Connections

- *Connection:* doc 12 already makes this exact methodological point
  itself, crediting the reasoning to the QUT-NOISE-TIMIT follow-up work
  cited in doc 09: *"you should tune a detector around what the system is
  actually for rather than around frame-level agreement... the numbers to
  watch are leaked speech and lost bird audio, not frame accuracy"*
  [doc 12](12-evaluation-recall-and-leak.md). This session's sources
  support that same conclusion from a different direction: none of them
  report a sample-level leaked-duration number, which means none of them
  can be benchmarked against doc 12's headline metric even if you wanted
  to.
- *Connection:* Kim et al.'s FN rate, Roy & Vu's RSR, and ecoVAD's F1 are
  all binary "was this unit (sentence / utterance / clip) adequately
  redacted" measures. None of them are convertible into an equivalent
  milliseconds-leaked number — they answer "how often is a flagged unit
  fully handled," not "how many milliseconds of true speech escaped,
  weighted by sample," which is what doc 12 asks.
- *Contradiction/tension preserved, not resolved:* ecoVAD's playback F1
  (0.917) versus its field precision (0.14–0.32) shows a large
  controlled-vs-field performance gap [doc 09](09-corpus-check-datasets.md).
  Doc 12 has no equivalent comparison because its entire evaluation set is
  synthetic, and doc 12 flags this itself as an open limitation: *"The set
  is small and synthetic... not enough to pick a final operating point for
  a real deployment"* [doc 12](12-evaluation-recall-and-leak.md). The
  ecoVAD gap is evidence that such a drop can be large in this problem
  space — it is not evidence of what Sage's own controlled-to-field drop
  will be, and nothing in this batch measures that directly for Sage's
  detector.
- *Possible takeaway (mine):* if a number comparable to this adjacent
  literature is ever wanted, "fraction of clips with zero leaked speech"
  would be the translatable framing — not the mean-leak-ms figure doc 12
  currently leads with. That would require recomputing from doc 12's
  existing per-clip data, not converting the existing summary numbers.

---

## Theme: Intelligibility Thresholds

### Core ideas

Only one source in this batch puts any number on where speech stops being
understandable, and it is doc 09's own existing reference (ecoVAD) — this
session's literature adds nothing new on this specific question.

### Evidence

- ecoVAD's playback experiment: *"Detection confidence stayed high out to
  10 metres for all three speakers. At 20 metres confidence dropped, but
  they note that at that distance the speech was barely audible and the
  words weren't intelligible"* [doc 09](09-corpus-check-datasets.md),
  citing Cretois, Rosten & Sethi 2022.
- Doc 12's own intelligibility-adjacent content is the recall-by-SNR
  table (92.5% at 0dB down to 49.3% at -20dB) and the observation that "a
  clip can post 90% recall and still leak a whole spoken word"
  [doc 12](12-evaluation-recall-and-leak.md) — a detection-recall
  statement, not an intelligibility-threshold definition. (Doc 12 does not
  itself contain a human-listening intelligibility table in the text I
  re-read; that material, if it exists, is elsewhere in the project.)

### Connections

- *Connection:* none of the other sources in this batch — Ramirez,
  Lezzoum (either paper), WIGVO, Kim et al., Roy & Vu — define an
  intelligibility threshold at all. They define detection thresholds (VAD
  onset/offset probabilities) or redaction-success thresholds (RSR/RSRp),
  which is a different question from "at what SNR or distance does a human
  stop understanding words."
- *Possible takeaway (mine):* this batch adds nothing new to doc 09's
  existing ecoVAD-derived intelligibility reference point. If an
  intelligibility threshold from a source *other* than ecoVAD is still
  wanted, it wasn't found in what was reviewed this session.

---

## Theme: Architectural Alternatives — Discard vs. Redact vs. Suppress

### Core ideas

The systems reviewed this session split by what they do once audio is
flagged: **content-selective redaction** (classify what was said, mask
only that span) versus **presence-based redaction** (mask on the mere
presence of speech, regardless of content — RedactionGate's approach). One
system requires the speaker's own active participation to redact anything
at all.

### Evidence

- Kim et al.'s audio pipeline transcribes with Whisper, classifies each
  reconstructed sentence for PII with a BERT-family classifier, and then
  applies "full-segment blackout masking... over the entire sentence
  interval," explicitly designed so that "reconstruction methods,
  including audio inpainting, cannot recover the original content"
  [Source: Kim et al. 2026, URL not verified]. This is content-selective:
  the trigger for redaction is a PII classification decision, not the
  presence of speech.
- Gadi Parthi et al.'s Google Cloud pipeline works the same way: Cloud
  Speech-to-Text transcribes, then the DLP API redacts based on detected
  "InfoTypes" (named PII categories) — again content-selective, requiring
  a transcript before any redaction decision is made
  [Gadi Parthi et al. 2025](https://doi.org/10.1109/iSES67504.2025.00089).
- Roy & Vu's PAT system is opt-in and speaker-triggered: a person must
  actively play a specific dual-tone acoustic signal to activate redaction
  of their *own* subsequent speech in the transcript; untriggered speech
  is transcribed and released normally
  [Roy & Vu 2026](https://doi.org/10.1109/ICASSP55912.2026.11461572).
- Wattanapornprom, Wandee, Bhundularp, Susutti, Srisuk & Chomchaiya's video
  face-anonymization tool uses a frame-skipping strategy where "only
  selected frames are processed in full detail. Intermediate frames
  inherit annotations through interpolation" — i.e., a detection decision
  made on one frame is held over and propagated forward across skipped
  frames [Source: Wattanapornprom et al. 2025, "User-Centric Video Privacy
  Preservation," IEEE InCIT 2025, DOI 10.1109/INCIT66780.2025.11276022].

### Connections

- *Connection:* Kim et al. and Gadi Parthi et al. both require knowing
  *what was said* before deciding whether to redact — content-selective
  redaction needs a working transcript and a PII schema to match against.
  RedactionGate's presence-based design (per this project's own
  architecture, not re-derived from these sources) never needs to know
  content, only that speech is present at all — a cheaper and more
  conservative bar precisely because park visitors say arbitrary things
  with no fixed PII schema to detect against, and because knowing content
  at all would itself be a bigger privacy exposure than needed.
- *Connection:* Roy & Vu's PAT is the clearest architectural mismatch to
  Sage's problem in this whole batch. It requires the speaker to actively
  signal "redact me," which is structurally impossible for a bystander who
  doesn't know a microphone exists. It's included here as a contrast case
  illustrating a design assumption Sage cannot make, not as a precedent to
  follow.
- *Connection:* Wattanapornprom et al.'s frame-hold-and-propagate is a
  video-domain instance of the same structural problem doc 05 and doc 12
  address in audio — bridging gaps in a continuous per-unit detection
  process by holding over a prior decision rather than re-deciding every
  unit. Same shape of problem, different modality; not a numeric citation,
  but a useful cross-modal framing.

---

## Important Numbers/Results

| Claim | Value | Source |
|---|---|---|
| WebRTC VAD hangover range | 60–150ms | [doc 05](05-vad-hangover-research.md) |
| Silero/Riva default post-utterance guard | ~580ms (80ms pad + 500ms min_duration_off) | [doc 05](05-vad-hangover-research.md) |
| 3GPP AMR "complex hangover" | 2000ms | [doc 05](05-vad-hangover-research.md) |
| Doc 05's own recommended guard for Sage | ~1050ms (0.8s + 0.25s), optional 2s ceiling | [doc 05](05-vad-hangover-research.md) |
| Ramirez et al. hangover | 80ms (8 frames @10ms), disabled above 25dB LTSD | [Ramirez et al. 2004](https://doi.org/10.1016/j.specom.2003.10.002) |
| Lezzoum 2014 (smart earphones) hangover | 1.26s, GA-optimized | [Source: Lezzoum et al. 2014, URL not verified] |
| Lezzoum 2013 (hyperacusis) hangover | 1.25s (250 frames @5ms), GA-optimized | [Lezzoum et al. 2013](https://doi.org/10.21437/Interspeech.2013-202) |
| WIGVO Silero hysteresis | onset 96ms / offset 480ms; 960ms offset → +380ms latency | [WIGVO](https://github.com/wigtn/wigvo) |
| Doc 12 default-gate recall/leak | 75.3% recall, 1340.0ms mean leak, 7781.0ms worst leak | [doc 12](12-evaluation-recall-and-leak.md) |
| Doc 12 speech-free FP rate | 0.77% | [doc 12](12-evaluation-recall-and-leak.md) |
| ecoVAD playback F1 vs. field precision | 0.917 F1 (playback) vs. 0.14–0.32 precision (field) | [doc 09](09-corpus-check-datasets.md) |
| ecoVAD intelligibility distance | ~10m confident, ~20m "barely audible... not intelligible" | [doc 09](09-corpus-check-datasets.md) |
| Kim et al. unified FN rate | ~3% (best config); 3.26–7% across 7 configs | [Source: Kim et al. 2026, URL not verified] |
| Roy & Vu RSR (Whisper-small) | 99.47% utterance-level, 97.7% phrase-level | [Roy & Vu 2026](https://doi.org/10.1109/ICASSP55912.2026.11461572) |

---

## Limitations/Open Questions

- No source found this session tests hangover against spontaneous,
  paused speech (all of the numeric hangover values above come from
  read speech, telephony test signals, or synthetic VAD benchmarks) —
  this matches doc 12's own flagged gap exactly.
- No source found this session defines a legal standard for redacting
  passively captured field speech in a public outdoor space specifically;
  the two adjacent legal hooks (HIPAA/GDPR, DOJ body-cam guidance) are for
  different content or a different actor.
- No source found this session reports a sample-level leaked-duration
  metric comparable to doc 12's, so no cross-source benchmarking of
  Sage's actual leak numbers against this literature is possible with what
  was reviewed.
- No source found this session adds an intelligibility threshold beyond
  what doc 09 already has from ecoVAD.
- This review excludes the earlier legal/ethics literature batch entirely
  because it did not survive a context compaction with verifiable
  citations. That is a real gap in this document, not a judgment that the
  excluded material was unimportant.

---

## Cross-Source Connections

- The padding/hangover literature (Theme 1) and the metrics literature
  (Theme 3) concern the same underlying lever from two different angles:
  doc 12's post-roll/hangover sweep is a search for the value that
  minimizes leaked milliseconds, while Roy & Vu's and Kim et al.'s success
  metrics evaluate a completely different redaction *trigger* (content
  classification or an explicit user signal) where hangover duration
  isn't even the relevant knob. This means the "best" hangover value from
  Theme 1 and the "best" success rate from Theme 3 are not commensurable
  achievements — they're solving differently-shaped problems.
- The legal-grounding gap (Theme 2) and the intelligibility-threshold gap
  (Theme 4) are the same shape of gap on two different axes: this
  session's literature review found no external standard to benchmark
  against on either the legal side or the perceptual side. Both remain
  open questions this batch didn't close.
- The architectural split in Theme 5 (content-selective vs. presence-based
  redaction) explains why the metrics in Theme 3 don't transfer: a
  content-selective system's false-negative rate is defined over a fixed
  PII schema (names, phone numbers, sentences classified as sensitive),
  while doc 12's leak metric is defined over *any* speech regardless of
  content. The metric mismatch in Theme 3 is a direct consequence of the
  architecture mismatch in Theme 5, not an independent methodological
  quirk.

---

## Source Index

- **doc 05** — [VAD Hangover / Post-Speech Padding — Research Notes](05-vad-hangover-research.md), project-sage-notes.
- **doc 09** — [Corpus Check: Does an Existing Speech-Plus-Soundscape Dataset Already Cover Us?](09-corpus-check-datasets.md), project-sage-notes.
- **doc 12** — [Evaluation: Recall, Leaked Speech, and Where the Detector Collapses](12-evaluation-recall-and-leak.md), project-sage-notes.
- Ramirez, J., Segura, J.C., Benítez, C., de la Torre, A., & Rubio, A.
  (2004). "Efficient voice activity detection algorithms using long-term
  speech information." *Speech Communication*, 42(4), 271–287.
  [DOI: 10.1016/j.specom.2003.10.002](https://doi.org/10.1016/j.specom.2003.10.002).
- Lezzoum, N., Gagnon, G., & Voix, J. (2014). "Voice Activity Detection
  System for Smart Earphones." *IEEE Transactions on Consumer
  Electronics*, 60(4). [Source: URL not verified].
- Lezzoum, N., Gagnon, G., & Voix, J. (2013). "A Low-Complexity Voice
  Activity Detector for Smart Hearing Protection of Hyperacusic Persons."
  Interspeech 2013.
  [DOI: 10.21437/Interspeech.2013-202](https://doi.org/10.21437/Interspeech.2013-202).
- Kim, H., Son, S.-W., Cho, H., Kim, H., & Kim, J. (2026). "WIGVO:
  Real-Time Bidirectional Speech Translation over Legacy PSTN Calls via
  Dual-Session Echo Gating." ACL 2026 System Demonstrations. Code:
  [github.com/wigtn/wigvo](https://github.com/wigtn/wigvo).
- Kim, K., Park, S.-W., Lee, H.-J., Choi, H., & Buu, S.-J. (2026). "A
  Multimodal Privacy Filtering System Using Deep Learning for Visual-Audio
  Input Streams." *IEEE Access*, 14. [Source: URL not verified].
- Roy, T., & Vu, N.T. (2026). "Listen, But Don't Leak: Sensitive Data
  Protection for Privacy Aware Automatic Speech Recognition with Acoustic
  Triggers." ICASSP 2026.
  [DOI: 10.1109/ICASSP55912.2026.11461572](https://doi.org/10.1109/ICASSP55912.2026.11461572).
- Fu, X., et al. (2026). "Trust the Voice, Hide the Source: Anonymous
  Provenance for Verifiably Edited Audio." [Source: URL not verified] —
  cited only for its reference to Miller, L., & Toliver, J. (2014),
  "Implementing a Body-Worn Camera Program: Recommendations and Lessons
  Learned," U.S. DOJ Office of Community Oriented Policing Services
  [Source: URL not verified].
- Gadi Parthi, A., Kodali, R.K., Sankiti, S.R., Punniyamoorthy, V.,
  Pothineni, B., Veerapaneni, P.K., Palanigounder, M., & Maruthavanan, D.
  (2025). "Scalable AI-Powered Speech Redaction: Evolving from Cloud
  Pipelines to LLM-Driven Architectures." 2025 IEEE International
  Symposium on Smart Electronic Systems (iSES).
  [DOI: 10.1109/iSES67504.2025.00089](https://doi.org/10.1109/iSES67504.2025.00089).
- Wattanapornprom, W., Wandee, P., Bhundularp, M., Susutti, W., Srisuk,
  P., & Chomchaiya, S. (2025). "User-Centric Video Privacy Preservation:
  Automated Face Detection, Recognition, and Blurring for PDPA and
  Beyond." 2025 9th International Conference on Information Technology
  (InCIT).
  [DOI: 10.1109/INCIT66780.2025.11276022](https://doi.org/10.1109/INCIT66780.2025.11276022).
