# Research Internship @ Argonne National Laboratory Notes

Notes, setup guides, and project work from my summer internship at Argonne National Laboratory, working with the Sage / Waggle edge-AI stack.

## The project

**[project.md](project.md)** — Speech Redaction at the Edge: automatic redaction of human speech on a Sage node so BirdNET can keep running at Haleakalā National Park without recording park visitors. The tested redaction modules (hysteresis gate, verified YAMNet speech classes, YAMNet wrapper) live in [code/redaction/](code/redaction/).

## Setup guides and working notes

| Guide | What it covers |
|---|---|
| [01 - sage-agent on local Ollama](docs/01-sage-agent-ollama.md) | Switching the sage-agent LLM backend from a cloud API to a local Ollama model. |
| [02 - tmux with persistent logging](docs/02-tmux-logging.md) | Keeping remote sessions alive across disconnects and saving terminal history to disk. |
| [03 - Hermes Agent on a Thor node](docs/03-hermes-on-thor.md) | Installing Hermes Agent on a Sage Thor node wired to local Ollama, plus notes on a couple of issues I ran into. |
| [04 - Audio privacy redaction](docs/04-audio-redaction.md) | Working notes for the redaction project: pipeline persistence analysis, RedactionGate design, open questions, hardware. |
| [05 - VAD hangover research](docs/05-vad-hangover-research.md) | Sourced post-speech padding numbers from WebRTC VAD, Silero/Riva, and 3GPP AMR, mapped onto the privacy-redaction cost model. |

## Context

Sage is a distributed edge-AI platform built on Waggle nodes. The "Thor" nodes are NVIDIA Jetson AGX Thor devices (ARM64). Most of these notes are about getting AI agents running locally on that hardware using local models, so nothing has to leave the node.

## Tools

Ollama, Hermes Agent (Nous Research), Podman/Docker, tmux, Python, NumPy, YAMNet (TF Hub / LiteRT on-node), BirdNET, pywaggle, Jetson AGX Thor (ARM64), Sage / Waggle nodes, gemma4 / qwen2.5 local models, glm-5.2 via NVIDIA Build.
