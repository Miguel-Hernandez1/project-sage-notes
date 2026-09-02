# Deploying media-sampler3 on a New Node (H02A)

**Miguel Hernandez**

These are my notes from getting the media-sampler3 audio producer running on H02A, the Iron Horse node. I did all of this directly on the node, and I wanted to write down the steps because the setup on H02A was different from H00F in a few important ways.

The short version is that everything up to the actual audio capture is working. The image runs, the cache mounts, the plugin starts its capture loop, and the heartbeat keeps reporting status, but H02A does not currently have an audio source that I can use to finish testing the write path.

## Starting state

H02A already had the WES base stack running, with roughly 19 pods in `default`, but it did not have the flint-pete pieces that are running on H00F, including media-sampler3, YOLO, and BioCLIP.

Two pods, `wes-audio-server` and `wes-gps-server`, were sitting in Pending. Sean confirmed that this is expected because those services were built for a hardware setup that no longer applies to the Thor, while the WES deploy script is not hardware-aware yet, so they still get deployed even though this node cannot run them. I left those alone since they are not blocking media-sampler3.

I also checked `/media/plugin-data/` and found `docker_registry` and `uploads`, but there was no `local-cache` directory.

## Setting up the cache directory

media-sampler3 expects `/local-cache` to exist and fails instead of writing somewhere else when that path is missing.

On H00F, that path comes from `wes-local-cache-manager`, but I could not find that component in the public `waggle-edge-stack` repo and there was no cache daemonset running on H02A. `wes-app-meta-cache` is running on the node, but that is a separate component and does not provide this directory.

Instead of creating the directory and assuming that was the right setup, I checked with Peter first, and he confirmed that creating it manually was fine for testing:

```bash
sudo mkdir -p /media/plugin-data/local-cache
sudo chmod 755 /media/plugin-data/local-cache
```

This is only a normal directory and is not the same as having the managed local-cache component running. It is enough for the current testing, but the final setup for this node still needs to be decided.

## Getting the image onto the node

I first tried the registry reference from `jobs/producer-audio-continuous.yaml`:

```bash
sudo k3s crictl pull registry.sagecontinuum.org/beckman/media-sampler3:0.1.0
# not found
```

Since that image did not resolve, I followed the build path described in the repo notes and built the image directly on H02A:

```bash
git clone https://github.com/flint-pete/media-sampler3.git
cd media-sampler3
make image RELEASE=0.1.0
```

The Makefile calls `docker buildx build`, and on the Thor `docker` is actually using podman, but the build completed successfully. The image is tagged as `localhost/waggle/plugin-media-sampler:0.1.0`, which is worth noting because the image name comes from the Makefile's `IMAGE` variable and is not called `media-sampler3`.

The next issue is that podman and k3s/containerd do not use the same image store, so building the image is not enough by itself. I exported the image from podman and then imported it into k3s:

```bash
podman save localhost/waggle/plugin-media-sampler:0.1.0 -o /tmp/ms3.tar
sudo k3s ctr images import /tmp/ms3.tar
sudo k3s crictl images | grep -i sampler
```

`podman save` should be run without `sudo`. Running it with `sudo` looks in root's separate podman image store, so it can report that the image is unknown even when the same image shows up under the normal user's `podman images`.

## Running the plugin

My first `pluginctl` attempt failed because I mounted a volume without giving it a node selector:

```text
Error: volume mounting requires nodeSelector.
Please specify the node by --selector or --node
```

`pluginctl` requires a selector or node when mounting a host volume. Using `--selector zone=core` worked, and that is also the selector used by the H00F runs.

For testing the USB microphone path, I used:

```bash
sudo pluginctl run --name ms3-test --selector zone=core \
  -v /media/plugin-data/local-cache:/local-cache \
  localhost/waggle/plugin-media-sampler:0.1.0 -- \
  --media audio --source-type usb_mic --audio-source hw:0,0 \
  --continuous 60 --clip-seconds 15 --audio-format flac \
  --stream test_mic --cache-name test-audio \
  --cache-max-count 5 --max-runtime 60
```

`--max-runtime` is useful while testing because the pod exits on its own after the requested time instead of continuing indefinitely. One thing to keep in mind is that the pod can disappear before there is much time to inspect its logs, so it helps to watch the run while it is active.

## What I verified on H02A

I first tried `--source-type camera_mic` without credentials, and the plugin stopped during configuration:

```text
config error: --source-type camera_mic needs CAMERA_USER and CAMERA_PASSWORD
in the environment (credentials are never passed as flags)
```

The plugin checks for the camera credentials before it tries to connect, so the camera path cannot be tested further without them. The credentials are provided through the environment rather than command-line flags, using `--env-from` with a mode 600 file.

I then tested `--source-type usb_mic`, which got through configuration and into the capture loop:

```text
media-sampler3 config OK: mode=continuous media=audio(src=hw:0,0, type=usb_mic,
  fmt=flac) interval=60s streams=['test_mic'] cache_name=test-audio
  caps=[max_count=5] heartbeat=60s bounds=[max_runtime=60s]
node VSN not resolvable at runtime; using PLACEHOLDER vsn='NODE'.
node GPS not resolvable at runtime; omitting EXIF GPS (not faking coordinates).
STAGE 4: continuous -> ring /local-cache/test-audio/test_mic
STAGE 5: heartbeat count=0 bytes=0 written=0 evicted=0 status=none
capturing 15s clip: hw:0,0 (subprocess timeout 30.0s)
STAGE 4: capture skipped: ffmpeg exit 251: cannot open audio device hw:0,0
STAGE 5: heartbeat count=0 bytes=0 written=0 evicted=0 status=skip
```

From these runs, I verified that the image starts correctly on H02A, the host cache mounts into the container, the configuration is accepted, the ring directory is created, the capture loop runs on its configured timing, and the heartbeat continues to report status separately from the capture attempts.

The heartbeat behavior was also useful to confirm because every capture attempt failed, but the plugin stayed alive and continued reporting `count=0 status=skip` instead of going silent. This means a plugin that is running but not producing clips is still visible through its heartbeat, which matches the behavior described in the repo notes for a dead camera on H00F.

**Not verified on H02A:** anything after a successful capture. No audio clip was encoded, no sidecar was written, and no cache eviction was triggered because the node never provided a usable audio source. The write path has been used on H00F, but I have not verified it on H02A yet.

## Testing a synthetic audio source

Since H02A did not have a working local audio device, I tried using an ffmpeg lavfi source to generate audio and see whether I could test the rest of the path without hardware:

```text
--audio-source "anullsrc=r=16000:cl=mono"
```

That did not work because media-sampler3 forces `-f alsa` when the source type is `usb_mic`, which makes ffmpeg interpret the lavfi string as an ALSA device name. For `camera_mic` and RTSP sources the plugin lets ffmpeg detect the format from the URL, so this restriction only applies to the ALSA path.

```text
ALSA lib pcm.c:2722: (snd_pcm_open_noupdate) Unknown PCM anullsrc=r=16000:cl=mono
```

So this particular way of generating a synthetic source cannot be passed through `--audio-source`. Testing past the capture step on H02A still requires a source that media-sampler3 supports, such as a real ALSA audio device or a camera audio stream.

## What is still needed

Running `arecord -l` returned no sound cards on H02A, so there is no local ALSA audio device available in the current setup. Because of that, the next source to test is one of the Iron Horse cameras if it has a microphone.

For that test I still need the RTSP host, port, and channel for one of the cameras, along with the camera login credentials provided through the environment. I asked the Iron Horse site contacts for those details, but none of the actual credentials or private connection information are included in these notes.

## Cleanup

After testing, I removed the test pod and the test cache directory:

```bash
sudo pluginctl rm ms3-test 2>/dev/null
sudo rm -rf /media/plugin-data/local-cache/test-audio
ls -la /media/plugin-data/local-cache/
```

This keeps the manually created local cache directory in place while removing the `test-audio` data created during these runs.

## Other things I learned

Sudo access on H02A did not start working until I reconnected after Peter granted it. `sudo -n true` is a useful way to check whether sudo is working without opening a password prompt, especially because these accounts use SSH key login and do not have a normal password to enter.

The plugin also logs `vsn=NODE` when it cannot resolve the node VSN at runtime, while Beehive attaches the real VSN downstream. This appears to be a WES runtime identity issue rather than something specific to media-sampler3.

Finally, `hummingcam_mic` is a name from Pete's home setup and is not a required naming convention, so the stream and cache names should be chosen based on the site where media-sampler3 is being deployed.
