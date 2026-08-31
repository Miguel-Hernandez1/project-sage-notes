# Iron Horse Node and Output Naming

**Miguel Hernandez, August 29, 2026**

A working note on two things that came up today: a new node assignment, and two
corrections to how my plugin names and organizes its output.

## Iron Horse

Pete assigned a new task. The Iron Horse node needs the new WES plus
media-sampler3, bioclip, yolo, and the other pieces from the flint-pete repo
working. The site wants to study spotted lanternfly, an invasive planthopper
whose most economically damaging host is grapevines, and they have several
cameras. My part is to work with Peter Lebiedzinski on getting the core pieces in
place, and to check whether audio can be pulled from one of the cameras.

I found the node in the Sage portal by searching "iron": it's IHV, node H02A, in
Santa Rosa California, rural focus, three cameras. IHV is almost certainly Iron
Horse Vineyard, since the location and camera count match. I'm waiting on Pete to
confirm and to introduce me to the Iron Horse folks so I can get the RTSP feed
names, which is what tells us whether the cameras expose audio at all.

Sean Shahkarami joined the thread for the WES and ansible side. Nobody has yet
explained what "new WES" refers to specifically, so that's still open.

The part that's relevant to my work: media-sampler3 already captures both stills
and audio into the same v2 cache, and my consumer already speaks that format, so
if those cameras carry audio the plugin should drop in without changes.

## Output naming, two corrections

Sean suggested organizing my output as a `redacted_audio/<source>/` tree rather
than a single flat output directory, so it mirrors how media-sampler3 organizes
its own streams. He said the current flat approach is fine for a proof of concept,
but the tree is the better shape.

Pete pointed out that `hummingcam_mic` is just his personal nickname for his home
rig so he could find it, not a convention. Stream names should be chosen
appropriately per site rather than copied from H00F.

Also worth recording from that thread: Sean confirmed there's currently no
standard way to advertise a cache stream so consumers can discover it without
hardcoding the path. My output path is a convention passed in as `--output-cache`.
That's a known gap in the v2 pattern, not something I skipped.

## TODO

- Switch the producer to a `redacted_audio/<source>/` tree.
