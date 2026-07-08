# 01 - Running sage-agent on a Local Ollama Model

**Goal:** switch the sage-agent reasoning LLM from a cloud API (OpenRouter) to a fully local [Ollama](https://ollama.com) model, so the agent runs entirely offline with no API keys.

These notes are for a **macOS** dev setup (Apple Silicon), which is where I first got sage-agent running. The same idea applies on a node; only the model choice changes with the hardware.

## Prerequisites

- A working sage-agent checkout (from the `sage-agent` repo) with its Python venv already set up.
- [Homebrew](https://brew.sh) (macOS).

## Step 1 - Neutralize any cloud-API override

sage-agent merges a local override file (`config/argo_proxy.local.yaml`) on top of whatever config you load. If it points at OpenRouter, it will silently keep you on the cloud API no matter what else you change. Rename it out of the way:

```bash
cd path/to/sage-agent
mv config/argo_proxy.local.yaml config/argo_proxy.local.yaml.bak
```

> This one is easy to miss. The config can look local while this file quietly overrides it, so check for it first.

Also remove any cloud key from your shell profile (`~/.zshrc` on macOS):

```bash
# comment out or delete a line like:
# export OPENROUTER_API_KEY="sk-or-..."
unset OPENROUTER_API_KEY   # clear it from the current shell too
```

> Security note: if an API key was ever pasted or committed anywhere, revoke it on the provider's site. Commenting it out is not enough.

## Step 2 - Install Ollama and pick a model sized to your hardware

```bash
brew install ollama
brew services start ollama       # runs in the background, restarts on login
curl http://127.0.0.1:11434      # should reply "Ollama is running"
```

Model choice depends on RAM. The sage-agent default (`gemma4:31b`, ~20 GB) needs roughly 24 GB+ of usable memory. Check yours:

```bash
sysctl -n hw.memsize | awk '{print $1/1073741824 " GB"}'   # macOS
```

- **32 GB or more:** you can run the full `gemma4:31b`.
- **16 GB (my Mac):** use a smaller reasoning model instead, e.g. `qwen2.5:7b`. Node hardware can run the big model later.

Pull the reasoning model plus the small vision model sage-agent uses:

```bash
ollama pull qwen2.5:7b      # or gemma4:31b on a big machine
ollama pull gemma4:e2b      # vision model for ptz_detect / ptz_caption
ollama list                 # confirm both are present
```

## Step 3 - Point sage-agent at the local config

sage-agent ships a `config/local.yaml` pre-wired for Ollama (`provider: ollama`, `argo_proxy.enabled: false`). If you downsized the model, edit that one line:

```yaml
model:
  provider: ollama
  model: qwen2.5:7b        # match what you pulled
  base_url: http://127.0.0.1:11434
```

Then select it and run the built-in health check:

```bash
source .venv/bin/activate
export PTZ_GRAPH_CONFIG=$PWD/config/local.yaml
export MSA_PTZ_BACKEND=sim
python -m ptz_node doctor
```

You want every check `[OK]`, especially:

```
[OK] ollama_reachable (agent)
[OK] ollama_model_pulled (agent) qwen2.5:7b present in ollama
```

## Step 4 - Confirm it runs fully local

```bash
python -m ptz_node run "List the devices, check detector status, and summarize node readiness."
```

The agent should call tools (`sensor_list_devices`, `detector_status`) and return a coherent summary, with no API key set and no network calls.

## Notes to self

- The `argo_proxy.local.yaml` override is the first thing to check when the backend won't switch.
- `config/local.yaml` is already Ollama-ready; usually only the model name needs changing.
- Match model size to RAM: `gemma4:31b` wants a big machine, `qwen2.5:7b` runs almost anywhere.
