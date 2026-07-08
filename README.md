# Research Internship @ Argonne National Laboratory Notes

Personal notes and setup guides from my summer internship at Argonne National Laboratory, working with the Sage / Waggle edge-AI stack. This isn't the internship project itself, just a place to keep track of things I set up and figured out along the way so I can reference them later.

## Contents

| Guide | What it covers |
|---|---|
| [01 - sage-agent on local Ollama](docs/01-sage-agent-ollama.md) | Switching the sage-agent LLM backend from a cloud API to a local Ollama model. |
| [02 - tmux with persistent logging](docs/02-tmux-logging.md) | Keeping remote sessions alive across disconnects and saving terminal history to disk. |
| [03 - Hermes Agent on a Thor node](docs/03-hermes-on-thor.md) | Installing Hermes Agent on a Sage Thor node wired to local Ollama, plus notes on a couple of issues I ran into. |

## Context

Sage is a distributed edge-AI platform built on Waggle nodes. The "Thor" nodes are NVIDIA Jetson AGX Thor devices (ARM64). Most of these notes are about getting AI agents running locally on that hardware using local models, so nothing has to leave the node.

## Tools

Ollama, Hermes Agent (Nous Research), Podman/Docker, tmux, Python, Jetson AGX Thor (ARM64), Sage / Waggle nodes, gemma4 / qwen2.5 local models.
