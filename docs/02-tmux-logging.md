# 02 - tmux with Persistent Terminal Logging

**Goal:** run work on remote nodes that survives SSH disconnects, and save a durable log of every command and its output.

When you SSH into a node and run something long, closing your laptop kills the session. `tmux` keeps that session alive on the node so you can reattach later. Adding `pipe-pane` writes everything to a file, which doubles as a record of what you did.

## One-time config

On the node, create `~/.tmux.conf`:

```bash
cat > ~/.tmux.conf << 'EOF'
# keep way more scrollback than the 2000-line default
set -g history-limit 100000
set -g status-interval 5
set -g base-index 1
EOF
```

> Version note: some Sage nodes ship an old tmux (e.g. 2.6). The settings above work there, but newer configs from blog posts may throw errors, so keep it minimal.

## Core workflow

```bash
mkdir -p ~/logs
tmux new -s work                 # start a named session

# turn on logging for the current pane (captures commands AND output):
tmux pipe-pane -o "cat >> ~/logs/tmux-$(date +%Y%m%d).log"

# ... do your work ...
```

Then detach and reattach as needed:

```bash
# detach (session keeps running on the node):   Ctrl-b  then  d
tmux ls                          # list running sessions
tmux attach -t work              # reattach later, even from a new SSH login
```

The payoff: start a task, close your laptop, reconnect an hour later, `tmux attach`, and everything is still running and scrolled where you left it.

## Key bindings (press `Ctrl-b`, release, then the key)

| Keys | Action |
|---|---|
| `Ctrl-b d` | Detach (leave session running) |
| `Ctrl-b w` | Visual window picker |
| `Ctrl-b c` | New window |
| `Ctrl-b 0/1/2` | Jump to window by number |
| `Ctrl-b [` | Scroll mode (arrows / PgUp; `q` to exit) |

## Gotchas I hit

- **`pipe-pane` must be run *inside* tmux.** At a normal prompt it errors ("no current client") because there's no pane to pipe.
- **Logging is per-pane.** Open a new window (`Ctrl-b c`) and it isn't logged until you run `pipe-pane` there too.
- **Don't nest tmux.** Running `tmux` inside a tmux session creates a nested session (window shows as `[tmux]`). Type `exit` to leave it.
- **Optional keybinding** to toggle logging on the current pane with `Ctrl-b P`:

  ```bash
  bind P pipe-pane -o "cat >> ~/logs/tmux-#S-%Y%m%d.log" \; display "logging toggled"
  ```

## Bonus: persistent shell history

Add to `~/.bashrc` so commands persist across sessions with timestamps:

```bash
export HISTSIZE=100000
export HISTFILESIZE=100000
shopt -s histappend
export HISTTIMEFORMAT="%F %T  "
```
