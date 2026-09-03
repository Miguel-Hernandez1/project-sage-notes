# Literature Review: Padding, Legal Grounding, Metrics, and Architecture for Speech Redaction

**Miguel Hernandez, September 3, 2026**

## Big Picture

- One of the clearest patterns across the VAD research is that the right amount of hangover or padding depends a lot on what the system is actually trying to avoid. Systems built for telephony or speech recognition, like WebRTC, Silero/Riva, and older 3GPP systems, usually try to keep hangover relatively short because extra speech detection means more bandwidth, more latency, or slower responses. For our privacy-redaction system, the tradeoff is different because keeping the gate open for a little too long is much less serious than closing it too early and letting part of someone's speech through.
- The strongest new finding from this research is a 2013 hearing-protection VAD paper that independently makes almost the same argument I made in doc 05. Their system ended up using a 1.25 second hangover, and the authors specifically point out that this is long compared with values normally used in telecommunications and speech recognition. Their project has nothing to do with privacy or Sage, which actually makes the comparison more useful, because they reached a similar conclusion from a completely different problem where cutting off the end of speech was also considered worse than keeping the detector active for too long.
- A second paper from the same researchers on smart earphones ended up at about 1.26 seconds, so two systems where protecting the end of speech mattered landed around 1.2 to 1.3 seconds. That is pretty close to the roughly 1.05 second baseline I recommended in doc 05 and still comfortably below the optional 2 second conservative ceiling. These papers did not copy telephony defaults either. Their values came from optimization against their own system goals.
- I still did not find a law or policy that directly says how incidentally captured speech from passive environmental recordings in a public outdoor space should be handled. There are related examples involving HIPAA, GDPR, enterprise voice recordings, and police body cameras, but none of those situations map onto what Sage is doing.
- There is also a pretty important mismatch in how different papers evaluate privacy. Doc 12 focuses on how many milliseconds of real speech leak through the redaction system, while most of the other work reports things like F1, false-negative rate, or whether an entire utterance was successfully redacted. Those numbers can still help us understand other systems, but they cannot be directly compared with leaked milliseconds because they are measuring different things.
- I did not find a new source that gives a clear SNR threshold where speech becomes unintelligible. ecoVAD, already covered in doc 09, is still the closest useful result because it discusses intelligibility as a function of distance.
- Architecturally, the systems I reviewed mostly fall into two groups. Some first figure out what was said and then redact only sensitive content, while our approach treats the presence of speech itself as enough reason to redact. There is also one system where the speaker has to intentionally trigger redaction themselves, which does not really work for Sage because random people near a sensor may not even know the microphone exists.

---

## 1. Padding and Hangover Duration

### Main idea

VAD hangover is the extra amount of time a system continues treating audio as speech after the detector starts thinking speech has ended. The important thing I found is that there is not one universal "correct" hangover value, because the number depends on what kind of mistake the system cares about more.

For something like a phone call or speech assistant, leaving the detector on too long can waste bandwidth or make the system feel slow, so short hangovers make sense. For Sage, the bigger problem is the opposite. If the detector turns off too early and somebody is still finishing a word or sentence, that speech could make it into the saved environmental audio. This means values designed for telephony are useful reference points, but they should not automatically become our privacy thresholds.

### What the sources actually use

- WebRTC VAD uses over-hang values of roughly 60 to 150ms depending on the quality mode, based on the constants in `vad_core.c`. This is one of the shortest ranges I found and makes sense for a system designed around real-time communication. [doc 05](05-vad-hangover-research.md)
- Silero VAD through NVIDIA Riva defaults to an 80ms `pad_offset` and a 500ms `min_duration_off`, giving roughly 580ms of protection after an utterance. [doc 05](05-vad-hangover-research.md)
- 3GPP AMR VAD has a much more aggressive special case where a signal classified as complex for a long time can trigger a 2000ms (2 second) hangover. [doc 05](05-vad-hangover-research.md)
- Based on those systems, doc 05 recommended increasing Sage's `min_duration_off` to around 0.8 seconds and its `pad_offset` to around 0.25 seconds, giving about a 1.05 second total guard, with a 2 second maximum suggested as a more conservative option for difficult signals. [doc 05](05-vad-hangover-research.md)
- Ramirez et al. (2004) use an 80ms hangover, calculated as eight 10ms frames. Their detector can also disable hangover when its long-term spectral divergence statistic goes above 25dB, meaning the system is confident enough about the signal that it no longer needs the extra protection. [Ramirez et al. 2004](https://doi.org/10.1016/j.specom.2003.10.002)
- Lezzoum, Gagnon, and Voix (2014) built a VAD for smart earphones and used a genetic algorithm to optimize the parameters instead of copying existing telephony values. Their optimization produced a 1.26 second hangover. They also required seven consecutive frames to confirm speech onset and limited onset confirmation to eight frames (40ms), because anything longer could create noticeable lip-sync problems. [Source: Lezzoum, Gagnon & Voix 2014, *IEEE Trans. Consumer Electronics* 60(4), URL not verified]
- Their earlier 2013 hyperacusis hearing-protection system produced almost the exact same result, using 250 frames at a 5ms hop for a 1.25 second hangover. What makes this paper especially useful for our project is that the authors themselves point out that this value is long compared with the hangovers normally used in telecommunications and speech recognition. [Lezzoum, Gagnon & Voix 2013](https://doi.org/10.21437/Interspeech.2013-202)
- WIGVO, a real-time PSTN speech-translation system using Silero VAD, uses different timing for entering and leaving speech. It confirms speech onset after 96ms but waits 480ms before confirming that speech has ended. The researchers also tested increasing the offset to 960ms, which removed remaining VAD false triggers but increased median latency by about 380ms. [WIGVO](https://github.com/wigtn/wigvo)

### How this connects to Sage

Ramirez's 80ms value is almost exactly at the low end of WebRTC's 60 to 150ms range, even though the Ramirez paper predates WebRTC. That makes me more confident this very short range is not just a WebRTC implementation choice, but part of a broader tradition in speech-processing systems where keeping latency and unnecessary speech detection low matters.

WIGVO is also useful because its 480ms speech-offset window is almost identical to Riva's 500ms `min_duration_off` default, even though WIGVO is using Silero for a different application. More importantly, WIGVO gives us information about what happens when that value is increased. Going from 480 to 960ms helped eliminate false triggers, but it added roughly 380ms of latency. That tradeoff matters a lot for a phone translation system, while it matters much less for Sage because our system is not having a real-time conversation with someone.

The most interesting comparison is with the two Lezzoum papers. They independently arrive at 1.25 and 1.26 seconds, which is close to doc 05's proposed 1.05 second baseline. Their reason for allowing a longer hangover is similar to ours: the system cares more about accidentally cutting speech than it does about leaving the detector active a little longer.

That does not prove Sage should use exactly 1.25 seconds. Their audio, users, detectors, and application are all different from ours. What it does show is that once the cost of cutting off speech becomes more important than the cost of keeping the gate open, other researchers have independently moved toward hangovers in the same general range.

There is still an important hole here. Doc 12's experiments found that increasing post-roll from 0.75 to 2.5 seconds reduced average leaked speech more effectively than simply lowering the enter threshold, and did so without as large a false-positive penalty. But those experiments mostly used continuous LibriSpeech reading, so they did not really test the exact situation hangover is supposed to solve: someone pausing naturally in the middle of spontaneous speech. [doc 12](12-evaluation-recall-and-leak.md)

So the literature makes the current padding choice look reasonable, but we still need our own test with realistic speech containing pauses before treating any specific value as final.

---

## 2. Legal and Policy Grounding

### What I found

This was probably the least conclusive part of the research. I did not find a law, regulation, or policy that directly says how a system like Sage should handle speech incidentally recorded by a passive environmental sensor in a public outdoor space.

There are still some useful nearby examples, but they should be treated as context, not as direct legal authority for the project.

- Gadi Parthi et al. (2025) describe Google's Cloud Speech Redaction Framework, which combines Cloud Speech-to-Text with Google's DLP API and is designed around privacy requirements including HIPAA and GDPR. Their use cases include telemedicine, call centers, and virtual assistants. [Gadi Parthi et al. 2025](https://doi.org/10.1109/iSES67504.2025.00089)
- Fu et al. (2026) discuss privacy-preserving audio provenance and reference U.S. Department of Justice guidance for police body-worn cameras. That guidance recommends reviewing and redacting recordings when they create privacy concerns. [Source: Fu et al. 2026, citing Miller & Toliver 2014, URL not verified]

### How this applies to Sage

Both examples support the broader idea that when recordings contain identifiable or sensitive information about people, redaction is already a normal privacy tool in other domains. The problem is that neither example is close enough to Sage to say "this is the legal rule we should follow."

The Google system is mainly dealing with known users, customers, or patients whose voice data may contain structured sensitive information. Police body cameras are closer in the sense that they can capture people incidentally, but police recording has its own legal framework, institutional responsibilities, and expectations that are very different from environmental research sensors.

So for now, the safest conclusion from this research is that redaction has strong precedent as a privacy-protection technique, but I still do not have a source establishing a specific legal redaction requirement for passive environmental audio in a U.S. national park. That distinction matters because I do not want to make the project sound legally justified by a paper that is actually discussing a completely different setting.

### NPS-specific findings (added September 3, 2026)

I ran one more search focused specifically on the National Park Service and Haleakalā, since that is the actual deployment target and general privacy law does not tell us much about it.

NPS does have an established acoustic monitoring program relevant to this project. NPS Management Policy 4.9 directs the agency to preserve natural soundscapes, and the Natural Sounds and Night Skies Division (NSNSD) runs acoustic monitoring at more than 300 sites across over 60 park units, including sites in Hawaii. [NPS Natural Sounds Program brochure](https://www.npshistory.com/brochures/acoustic-mon.pdf) One of NSNSD's own reference pages includes a photo specifically captioned "Acoustic monitoring station in Haleakala National Park," so NPS already operates acoustic monitoring infrastructure at the deployment site. [Source: NPS Reference Manual 47, Chapter 2, URL not independently verified]

I could not find anything in NSNSD's public materials addressing consent, redaction, or handling of incidentally captured human speech. Their own description of the program's audio recordings says the recordings help identify "sounds' source of origin, such as wildlife, weather, park visitors, and park operations," meaning capturing visitor sound already happens as a normal part of their monitoring and nothing in what I found addresses it as a privacy concern. [NPS Sound Gallery](https://www.nps.gov/subjects/sound/gallery.htm)

Separately, NPS does regulate audio recording, but in the other direction from what Sage does. Under the EXPLORE Act (Public Law 118-234, January 2025), codified at 54 U.S.C. 100905, NPS permit requirements govern visitors who bring recording equipment into a park. [NPS Filming, Still Photography, and Audio Recording](https://www.nps.gov/aboutus/news/film-and-photo-permits.htm) That policy is about whether a person needs a permit to record in the park, not about whether a park's own passive sensor may capture a visitor's speech. It is a near miss, not a hit, and I am flagging it here specifically so it is not mistaken for on-point authority later.

Updated conclusion for this section: there is real NPS acoustic monitoring policy and infrastructure that touches this exact deployment site, but nothing found establishes a rule for handling incidentally captured human speech. NSNSD's own program appears to capture visitor sound already without treating it as a privacy question. That gap is either an opportunity, since this project could be a genuinely useful model for how NPS acoustic monitoring should handle visitor speech, or a sign that this question has not been raised inside NPS as an established concern.

---

## 3. Evaluation and Metrics

### Main idea

One thing that became much clearer from this research is that different privacy systems report numbers that look comparable at first but actually measure very different things.

For Sage, doc 12 focuses heavily on how many milliseconds of real speech escape the redaction gate. That makes sense for our problem because even if the detector catches 95 percent of someone's speech, the missing 5 percent could still contain a complete word or short phrase. Most of the other papers do not measure privacy at that level.

### Results

- Doc 12's default gate produced 75.3% recall, 1340ms of mean leaked speech per clip, 7781ms in the worst clip, and a 0.77% false-positive rate on speech-free audio. [doc 12](12-evaluation-recall-and-leak.md)
- ecoVAD reports an average playback F1 score of 0.917, compared with 0.890 for pyannote and 0.876 for WebRTC VAD. During an actual five-day field deployment, precision fell to around 0.14 to 0.32, compared with a 0.05 random baseline. [doc 09](09-corpus-check-datasets.md)
- Kim et al. (2026) report a unified false-negative rate of about 3% for their strongest multimodal privacy configuration. Their audio false-negative rate was 0.77% and their visual rate was 5.73%, while average false-negative rates across the seven tested configurations ranged from roughly 3.26% to 7%. [Source: Kim et al. 2026, URL not verified]
- Roy and Vu (2026) use something called Redaction Success Rate, which measures whether a triggered utterance is completely replaced with a `<REDACTED>` token. Their Whisper-small model reaches 99.47% utterance-level RSR and 97.7% phrase-level RSRp. [Roy & Vu 2026](https://doi.org/10.1109/ICASSP55912.2026.11461572)

### Why these numbers do not directly compare

A 99.47% redaction success rate does not mean the same thing as 99.47% of speech samples being removed, and an F1 score of 0.917 does not tell us how many milliseconds of understandable speech were accidentally saved.

Doc 12 already gets at this when it argues that the detector should be evaluated around what the system is actually supposed to protect, rather than only around frame-level accuracy. For Sage, the important outputs are things like how much speech leaked and how much useful environmental or bird audio was unnecessarily removed. [doc 12](12-evaluation-recall-and-leak.md)

The ecoVAD result is especially important for another reason. Its controlled playback performance looked strong, but its field precision was much worse. We cannot assume Sage will have the same drop because the systems are different, but it is a clear warning that a detector that looks good on a controlled dataset can behave very differently once it is outside with real environmental noise. That matters because doc 12's current evaluation is also synthetic, a limitation the document already recognizes, so ecoVAD gives us an outside example showing the controlled-to-field gap can be large.

One useful metric we could add later is the percentage of clips with zero leaked speech. That would be easier to compare conceptually with papers that report whether an entire utterance or clip was successfully protected, while still keeping leaked milliseconds as our more detailed privacy metric.

---

## 4. Intelligibility Thresholds

This part of the literature search did not really produce anything new.

ecoVAD is still the most useful reference we have. In its playback experiment, detection confidence remained high out to around 10 meters for all three speakers. At 20 meters, confidence fell, and the researchers noted the speech was barely audible and the words were no longer intelligible. [doc 09](09-corpus-check-datasets.md)

Doc 12 gives us detection recall at different SNRs, ranging from 92.5% at 0dB to 49.3% at -20dB, but that is not the same thing as measuring whether a human listener can understand what is being said. A detector missing speech and a human being unable to understand speech are related questions, but they are not interchangeable. [doc 12](12-evaluation-recall-and-leak.md)

None of the other papers I reviewed gave a clear SNR or distance where human speech becomes unintelligible, so this is still an open question for the project.

---

## 5. Other Ways Systems Handle Privacy

The other useful thing from this research was seeing how differently privacy systems decide when audio should be redacted.

Our current RedactionGate approach is conservative. If speech is present, we redact it. We do not first need to know what the person said. Other systems make a different choice.

Kim et al. first transcribe speech with Whisper, reconstruct sentences, classify those sentences for PII using a BERT-family model, and then black out the full time interval corresponding to a sensitive sentence. Their system needs to understand enough of the speech to determine whether it contains sensitive information before deciding whether to remove it. [Source: Kim et al. 2026, URL not verified]

Gadi Parthi et al. use a similar content-based architecture. Their system transcribes the audio with Cloud Speech-to-Text and then sends the transcript through a DLP system that looks for specific sensitive information types. [Gadi Parthi et al. 2025](https://doi.org/10.1109/iSES67504.2025.00089)

Roy and Vu's PAT system takes an even more different approach. The speaker intentionally plays a specific acoustic signal that tells the system to redact their following speech. Speech without that trigger is processed normally. [Roy & Vu 2026](https://doi.org/10.1109/ICASSP55912.2026.11461572)

That last design is a useful contrast for Sage because it depends on something our system cannot assume: that the person knows they are being recorded and actively asks to be redacted. Someone walking past an environmental sensor may have no idea there is even a microphone nearby.

This is one reason I still think presence-based redaction makes sense for Sage. We do not need to transcribe somebody's speech, determine whether it contains a name or another predefined type of PII, and then decide whether that speech deserves privacy. We can make the simpler and more conservative decision that human speech itself is something we do not need to keep.

There is also an interesting parallel with Wattanapornprom et al.'s video anonymization system. Their system fully analyzes selected video frames and then carries those annotations across intermediate frames instead of making a completely new decision on every frame. [Wattanapornprom et al. 2025](https://doi.org/10.1109/INCIT66780.2025.11276022)

It is not the same problem as audio hangover, but the basic idea is similar: once a continuous system detects something sensitive, it can be safer and more efficient to hold that decision across a short gap instead of assuming the sensitive content disappeared the instant the detector stops seeing it.

---

## Main Takeaways

The biggest thing this research added is stronger support for the idea behind our padding strategy. The 1.05 second guard proposed in doc 05 is not directly proven by these papers, but systems from completely different areas that also care about protecting the trailing edge of speech ended up around 1.25 to 1.26 seconds. That makes our current range look much less arbitrary and gives us a stronger reason to test roughly 1 to 1.5 seconds instead of inheriting the much shorter values used by telephony systems.

At the same time, the research makes clear that we still need our own field-specific evaluation. None of these papers test the exact combination Sage cares about: outdoor environmental audio, incidental human speech, natural pauses, bird and wildlife sounds we want to preserve, and privacy measured by how much understandable speech actually survives redaction.

The legal research is also still incomplete. There are plenty of examples showing redaction used to protect privacy in voice recordings, but I did not find a rule that directly maps onto passive environmental recording in a U.S. national park.

Finally, the architecture comparison gives a clearer reason for using presence-based redaction. Many privacy systems first transcribe speech and then decide whether the content is sensitive. For Sage, that creates extra complexity and requires processing information we do not actually need. If the goal is simply to prevent human conversations from being stored while keeping useful environmental audio, detecting that speech exists is enough. We do not need to know what was said.

---

## Important Numbers

| Claim | Value | Source |
|---|---|---|
| WebRTC VAD hangover range | 60 to 150ms | [doc 05](05-vad-hangover-research.md) |
| Silero/Riva default post-utterance guard | ~580ms (80ms pad + 500ms min_duration_off) | [doc 05](05-vad-hangover-research.md) |
| 3GPP AMR "complex hangover" | 2000ms | [doc 05](05-vad-hangover-research.md) |
| Doc 05's recommended guard for Sage | ~1.05s (0.8s + 0.25s), optional 2s ceiling | [doc 05](05-vad-hangover-research.md) |
| Ramirez et al. hangover | 80ms (8 frames at 10ms), disabled above 25dB LTSD | [Ramirez et al. 2004](https://doi.org/10.1016/j.specom.2003.10.002) |
| Lezzoum 2014 (smart earphones) hangover | 1.26s, genetic-algorithm optimized | [Source: Lezzoum et al. 2014, URL not verified] |
| Lezzoum 2013 (hyperacusis) hangover | 1.25s (250 frames at 5ms), genetic-algorithm optimized | [Lezzoum et al. 2013](https://doi.org/10.21437/Interspeech.2013-202) |
| WIGVO Silero hysteresis | onset 96ms / offset 480ms; 960ms offset adds ~380ms latency | [WIGVO](https://github.com/wigtn/wigvo) |
| Doc 12 default-gate recall/leak | 75.3% recall, 1340ms mean leak, 7781ms worst leak | [doc 12](12-evaluation-recall-and-leak.md) |
| Doc 12 speech-free false-positive rate | 0.77% | [doc 12](12-evaluation-recall-and-leak.md) |
| ecoVAD playback F1 vs. field precision | 0.917 F1 (playback) vs. 0.14 to 0.32 precision (field) | [doc 09](09-corpus-check-datasets.md) |
| ecoVAD intelligibility distance | ~10m confident, ~20m barely audible and not intelligible | [doc 09](09-corpus-check-datasets.md) |
| Kim et al. unified false-negative rate | ~3% best config; 3.26% to 7% across 7 configs | [Source: Kim et al. 2026, URL not verified] |
| Roy & Vu redaction success rate (Whisper-small) | 99.47% utterance-level, 97.7% phrase-level | [Roy & Vu 2026](https://doi.org/10.1109/ICASSP55912.2026.11461572) |

---

## Sources

- [doc 05](05-vad-hangover-research.md), [doc 09](09-corpus-check-datasets.md), and [doc 12](12-evaluation-recall-and-leak.md), project-sage-notes.
- Ramirez, J., Segura, J.C., Benitez, C., de la Torre, A., and Rubio, A. (2004). "Efficient voice activity detection algorithms using long-term speech information." *Speech Communication*, 42(4), 271-287. [DOI: 10.1016/j.specom.2003.10.002](https://doi.org/10.1016/j.specom.2003.10.002)
- Lezzoum, N., Gagnon, G., and Voix, J. (2014). "Voice Activity Detection System for Smart Earphones." *IEEE Transactions on Consumer Electronics*, 60(4). [Source: URL not verified]
- Lezzoum, N., Gagnon, G., and Voix, J. (2013). "A Low-Complexity Voice Activity Detector for Smart Hearing Protection of Hyperacusic Persons." Interspeech 2013. [DOI: 10.21437/Interspeech.2013-202](https://doi.org/10.21437/Interspeech.2013-202)
- Kim, H., Son, S.-W., Cho, H., Kim, H., and Kim, J. (2026). "WIGVO: Real-Time Bidirectional Speech Translation over Legacy PSTN Calls via Dual-Session Echo Gating." ACL 2026 System Demonstrations. [github.com/wigtn/wigvo](https://github.com/wigtn/wigvo)
- Kim, K., Park, S.-W., Lee, H.-J., Choi, H., and Buu, S.-J. (2026). "A Multimodal Privacy Filtering System Using Deep Learning for Visual-Audio Input Streams." *IEEE Access*, 14. [Source: URL not verified]
- Roy, T., and Vu, N.T. (2026). "Listen, But Don't Leak: Sensitive Data Protection for Privacy Aware Automatic Speech Recognition with Acoustic Triggers." ICASSP 2026. [DOI: 10.1109/ICASSP55912.2026.11461572](https://doi.org/10.1109/ICASSP55912.2026.11461572)
- Fu, X., et al. (2026). "Trust the Voice, Hide the Source: Anonymous Provenance for Verifiably Edited Audio." [Source: URL not verified], cited here only for its reference to Miller, L., and Toliver, J. (2014), "Implementing a Body-Worn Camera Program: Recommendations and Lessons Learned," U.S. DOJ Office of Community Oriented Policing Services. [Source: URL not verified]
- Gadi Parthi, A., Kodali, R.K., Sankiti, S.R., Punniyamoorthy, V., Pothineni, B., Veerapaneni, P.K., Palanigounder, M., and Maruthavanan, D. (2025). "Scalable AI-Powered Speech Redaction: Evolving from Cloud Pipelines to LLM-Driven Architectures." 2025 IEEE International Symposium on Smart Electronic Systems (iSES). [DOI: 10.1109/iSES67504.2025.00089](https://doi.org/10.1109/iSES67504.2025.00089)
- Wattanapornprom, W., Wandee, P., Bhundularp, M., Susutti, W., Srisuk, P., and Chomchaiya, S. (2025). "User-Centric Video Privacy Preservation: Automated Face Detection, Recognition, and Blurring for PDPA and Beyond." 2025 9th International Conference on Information Technology (InCIT). [DOI: 10.1109/INCIT66780.2025.11276022](https://doi.org/10.1109/INCIT66780.2025.11276022)
- National Park Service. "Natural Sounds Program" brochure. [npshistory.com/brochures/acoustic-mon.pdf](https://www.npshistory.com/brochures/acoustic-mon.pdf)
- National Park Service. "Reference Manual 47, Chapter 2: Acoustical Monitoring." https://www.nps.gov/subjects/sound/rm47-part-2-data.htm [Source: URL not independently verified]
- National Park Service. "Sound Gallery." [nps.gov/subjects/sound/gallery.htm](https://www.nps.gov/subjects/sound/gallery.htm)
- National Park Service. "Filming, Still Photography, and Audio Recording." [nps.gov/aboutus/news/film-and-photo-permits.htm](https://www.nps.gov/aboutus/news/film-and-photo-permits.htm)
