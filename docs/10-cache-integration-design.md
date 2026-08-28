# Cache Integration: Consumer and Producer Design

**Miguel Hernandez, August 25, 2026**

This is the design record for turning the speech redaction plugin into a v2-style
cache consumer and producer. Everything in the "Verified" section was checked
against the live node today, not inferred from docs.

## The workflow Pete confirmed

```
media-sampler3  ->  raw audio cache  ->  redaction plugin  ->  redacted cache  ->  BirdNET
```

media-sampler3 isn't mine. It runs on the node and fills a local cache with FLAC
clips. My plugin wakes periodically, consumes the unseen clips, redacts speech,
and writes the redacted product into a separate cache area. A modified BirdNET
then pulls from the redacted cache instead of the raw one, so nothing downstream
ever sees unredacted audio.

The plugin runs as a batch job and exits. It doesn't loop. WES schedules the
cadence.

The plugin knows nothing about BirdNET or any other consumer. It takes clips in
and produces clips out.

## Verified on H00F

media-sampler3 lives at github.com/flint-pete/media-sampler3 and runs on H00F,
which is Pete's hummingbird feeder rig. I couldn't find it earlier because
consumers never call it by name, they just read the cache it fills.

Host path is `/media/plugin-data/local-cache`, mounted into the plugin pod as
`/local-cache`. The audio stream is at
`/local-cache/hummingcam-audio/hummingcam_mic/`.

Clip format, confirmed with ffprobe:

- FLAC, 16 kHz, mono, 24-bit (PCM_24)
- 15 seconds long, produced every 60 seconds

16 kHz mono is exactly what YAMNet wants, so no resampling or downmixing is
needed on this path.

Each logical frame is two files:

```
<capture_ts_ns>-v2-<vsn>-<source>.flac
<capture_ts_ns>-v2-<vsn>-<source>.flac.json
```

Sidecar schema is `sage-media-1` with these fields: `acquisition_path`,
`camera`, `capture_timestamp_ns`, `job`, `lat`, `lon`, `media_type`, `node_id`,
`object_name`, `plugin`, `schema_version`, `source`, `source_type`, `task`,
`unique_id`, `upload_timestamp_ns`, `vsn`.

Two properties of the cache that shape the design:

**Producer contract.** The sidecar is written first, then the clip. That means
any consumer that sees a clip is guaranteed its sidecar already exists. My
producer has to do the same.

**The ring evicts.** Oldest first, bounded by count or megabytes. A clip can
disappear between the moment you list the directory and the moment you open it.
I hit this today, a file I was copying vanished mid-operation. The consumer has
to handle it without crashing.

## Design decisions

**Filenames keep the original `capture_ts_ns`.** BirdNET anchors its detections
to the timestamp parsed out of the filename. If the redacted clip got a new
timestamp, every bird detection would be stamped with when I redacted it rather
than when the bird sang. Only the source label changes, so
`hummingcam_mic` becomes `hummingcam_mic_redacted`.

**Sidecar `source` matches the new filename.** Having `object_name` and `source`
disagree is a latent bug. The original stream is still recoverable through the
provenance field.

**Provenance.** The output sidecar carries `source_unique_id` pointing at the
input clip's `unique_id`, plus `redaction_windows` as a list of
`[start_s, duration_s]`, `redaction_fail_closed` as a bool, and
`redaction_fail_closed_reason` as a string that's null on the normal path. The
reason matters: a run of empty clips reads very differently if you can see the
model failed to load rather than assuming genuine silence.

**Seen-store keyed on `unique_id`**, durable across runs, bounded, kept under
`<cache-root>/.state/` to match the rest of the v2 family.

**Atomic writes.** Everything goes to a temp name and gets renamed into place, so
a consumer never sees a half-written file.

**Output ring caps.** The producer takes `--cache-max-count` and
`--cache-max-mb` with the same evict-oldest semantics as media-sampler3. Nothing
in WES bounds a plugin's own output subtree except a hard-quota backstop, which
is a last resort rather than a design. Without caps the redacted cache would grow
until the disk filled.

**Subtype preservation.** The FLAC writer used to hardcode PCM_16, which silently
dropped 8 bits from every 24-bit source clip. It now reads the source subtype
with `sf.info(path).subtype` and writes the same.

## Bugs caught before building

**Filename regex was wrong.** The old `main.py` expected
`<ts>-v2-<40-hex>.<ext>`. The real naming is `<ts>-v2-<vsn>-<source>.flac`. That
regex was written against a guess and would have matched nothing on the node.

**Double redaction.** `write_redacted_flac` already calls `redact_speech`
internally. Calling `redact_speech` first and then passing the result in would
have redacted twice, and the second pass over already-zeroed audio returns empty
windows, which would have wiped the real redaction metadata. The fix is to call
`write_redacted_flac` once and take the windows from its return.

## Correcting the privacy claim

The README and the ECR science description both said raw unredacted audio is
never written to disk. That was true of the earlier mic-path fork, where speech
was zeroed in memory before anything was written. It isn't true in the cache
architecture, because media-sampler3 writes raw clips to the SSD and my plugin
reads them from there.

Both files now say what's actually true: this plugin never writes unredacted
audio, and only the redacted product is available to downstream consumers and for
upload. Raw clips currently reach the node's SSD via the producer.

The ECR science description is what renders on the public Sage App Catalog page,
so the live page will need a re-register to pick up the correction.

## Open

**Ramdisk.** Pete wants a version of media-sampler3 that writes raw clips to
memory instead of the SSD, so unredacted speech never touches persistent storage.
Pull a node off a pole and reboot it and no speech survives. That closes the gap
above. Peter suggested an in-memory store with persistence disabled rather than a
filesystem-level tmpfs mount, and mentioned redis. Still deciding between that and
plain tmpfs, since tmpfs would need no code change in media-sampler3 at all.

**Output cache bounding** is designed but the caps aren't tuned. Needs a real
number based on how much redacted audio a node should retain.

**End-to-end on H00F** is the next milestone after the consumer is built.
