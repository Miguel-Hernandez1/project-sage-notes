# 03 - Setting Up Hermes Agent on a Sage Thor Node

**Goal:** install [Hermes Agent](https://hermes-agent.nousresearch.com) (Nous Research) on a Sage Thor node and wire it to a local Ollama model, so the agent runs entirely on the node with no external API keys and nothing leaving the hardware. The end result is a working agent that can execute shell commands and read/write files, driven by a local LLM.

These notes also cover two issues specific to the Thors (ARM64 / Podman / Ollama context) and how I got around them. Assumes Docker/Podman and Ollama are already installed (Ollama is deployed fleet-wide) and no sudo for the core setup.

## 1. Prerequisites and pre-flight checks

SSH into the Thor. On the Sage gateway the Thors are the H-series VSNs (e.g. `H00F`). The gateway knows the VSN, not the portal's ANLT label:

```bash
ssh waggle-dev-node-H00F        # use your assigned node, NOT 'ANLT1'
```

Run these and confirm each:

```bash
uname -m                        # expect: aarch64 (ARM)
free -h                         # Thors have ~122 GB
df -h ~                         # confirm free disk (models are 5-20 GB)
ollama --version                # expect 0.30.11 or newer
docker ps                       # should return a table with no permission error
curl -sI https://hermes-agent.nousresearch.com | head -1   # expect HTTP/2 200
```

> If `docker ps` gives a permission error, your user isn't in the docker group (ask the help desk). If the curl check fails, the node can't reach the internet.

## 2. Start a logged tmux session (recommended)

Do the whole setup inside tmux with logging on (see [guide 02](02-tmux-logging.md)):

```bash
mkdir -p ~/logs
tmux new -s hermes
tmux pipe-pane -o "cat >> ~/logs/hermes-$(date +%Y%m%d).log"
```

## 3. Install Hermes

No sudo needed. It installs to `~/.hermes/` with its own managed environment:

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
source ~/.bashrc                # so the `hermes` command is on PATH
hermes --version
```

> Non-sudo side effects (harmless): the installer skips system browser libraries and installs Chromium into your user cache, and notes `ripgrep` is missing (file search falls back to grep). Neither blocks the core agent.

## 4. First-run configuration

Launch `hermes` and it walks you through setup. Choose:

### 4.1 Setup profile: Blank Slate
At "How would you like to set up Hermes?" choose **Blank Slate** (everything off). Avoid Quick Setup, which uses Nous Portal (OAuth account plus cloud routing) that we don't want on shared lab hardware. The profile only sets which features start enabled; everything is reconfigurable later.

### 4.2 Model provider: Custom endpoint (local Ollama)
Scroll the provider list to the bottom and pick **Custom endpoint (enter URL manually)**. Don't pick "Ollama Cloud", which is the hosted ollama.com service rather than your local server.

- **API base URL:** `http://localhost:11434/v1`
- **API compatibility mode:** Auto-detect (Ollama's `/v1` API is OpenAI-compatible)
- **API key:** leave blank (or dummy value `ollama` if it refuses empty)
- **Model:** `gemma4:31b` (largest general model, same one sage-agent uses; the Thor has the memory for it)
- **Context length:** see [section 7](#7-issue-b-slow-first-inference-context-size); leaving it blank auto-detects the 262k max and is slow
- **Display name:** e.g. `Ollama H00F (local)`

### 4.3 Terminal backend: see [section 6](#6-issue-a-docker-sandbox-fails-exit-125)
Docker is the safe, sandboxed choice, but on the Thors it needs a one-time fix first. To test immediately, choose Local and switch to Docker once the fix is in.

### 4.4 Finish
Choose "Start with everything disabled, finish now."

## 5. Confirm it works

Start the agent and give it a task that forces real tool use:

```
hermes

# then type:
Run uname -a, then create a file called hello.txt with the
text "sage test", and read it back to me.
```

Expected: the agent runs `uname -a` (returns the aarch64 kernel string), writes `hello.txt`, and reads back "sage test."

> First response is slow (~30-60s) while the 31b model loads into memory. That's normal, and later responses are faster. Watch progress from another window with `ollama ps`.

## 6. Issue A: Docker sandbox fails (exit 125)

**Symptom:** with the Docker backend, every tool call fails instantly with `Docker exit status 125`.

**Root cause:** on the Thors, the `docker` command is actually Podman. Hermes launches its sandbox with Podman's `--init` flag, which requires the `catatonit` binary, and it isn't installed. Podman also refuses short (unqualified) image names.

**Diagnosis:** run the failing command by hand to see the real error:

```
Error: lookup init binary: exec: "catatonit":
executable file not found in $PATH
```

**Fixes:**

1. Pre-pull the sandbox image with its full name (fixes Podman's short-name refusal):
   ```bash
   docker pull docker.io/nikolaik/python-nodejs:python3.11-nodejs20
   ```

2. Install catatonit. Upstream ships no arm64 binary, and the source needs autotools (which needs sudo), so the clean fix is a distro package, which is a help-desk request:
   ```bash
   sudo apt install catatonit      # ask the help desk to run this
   ```

Once `catatonit` is installed, switch the backend back to Docker:

```bash
hermes config set terminal.backend docker
```

> Work-around until then: run on the **local** backend (`hermes config set terminal.backend local`). Commands run directly on the node without a sandbox, which is fine for read-only testing on your own account but not for autonomous or destructive tasks.

## 7. Issue B: slow first inference (context size)

**Symptom:** first response takes 4+ minutes. The Hermes status bar shows a context like `6.8K/262.1K`.

**Root cause:** with context on auto-detect, Ollama allocates gemma4:31b's full 262,144-token window, creating a huge KV cache that bloats memory and slows the first prompt.

**Diagnosis:**

```bash
ollama ps       # CONTEXT column shows 262144
```

**Fix (self-serve, no sudo):** create a derived Ollama model that bakes in a smaller context. This runs entirely in your own model store:

```bash
cat > /tmp/gemma-64k.modelfile << 'EOF'
FROM gemma4:31b
PARAMETER num_ctx 65536
EOF

ollama create gemma4-64k -f /tmp/gemma-64k.modelfile
ollama run gemma4-64k "hi"      # loads it once
ollama ps                        # confirm CONTEXT shows 65536
```

Then point Hermes at the new model:

```bash
hermes model      # select gemma4-64k instead of gemma4:31b
```

> Two notes: (1) Setting `context_length` under `model:` in Hermes' own config only changes the displayed number. Hermes does not forward `num_ctx` to Ollama, so the Modelfile is what actually caps the allocation. Verify with `ollama ps`, not the status bar. (2) The first response after the model is idle still pays a ~25-30s model-load cost, which is the load tax rather than the context.

A fleet-wide alternative (needs sudo, help-desk) is setting `Environment="OLLAMA_CONTEXT_LENGTH=65536"` in the Ollama service override, but the Modelfile above is the fix you can do yourself right now.

## 8. Reconnecting on a later day

```bash
ssh waggle-dev-node-H00F
tmux ls                         # find your session
tmux attach -t hermes           # reattach, or 'tmux new -s hermes' if gone

# resume a specific Hermes conversation:
hermes --resume <SESSION_ID>    # ID printed when you exit Hermes
# or just start fresh:
hermes
```

## 9. Quick command reference

| Task | Command |
|---|---|
| Install Hermes | `curl -fsSL https://hermes-agent.nousresearch.com/install.sh \| bash` |
| Start agent | `hermes` |
| Resume session | `hermes --resume <id>` |
| Change model / provider | `hermes model` |
| Show config | `hermes config show` |
| Set a config value | `hermes config set <key> <value>` |
| Switch backend | `hermes config set terminal.backend local\|docker` |
| Check loaded model + context | `ollama ps` |
| List local models | `ollama list` |

*Status at time of writing: Hermes working end-to-end on H00F (local Ollama, gemma4-64k). Docker sandbox fix noted for the help desk; context fix applied via Modelfile.*
