# ghap — GitHub Actions Progress Monitor

Live terminal monitor for GitHub Actions. Select which repositories to watch, then track active, queued, and completed workflows in real time.

```
⚡ ghap v1.0.0  @sindus  ·  14:23:05  ·  next 12s  ████████░░░░  ·  API 4990/5000

 ▶ sindus/my-api  CI/CD Pipeline  ·  branch: main  ·  3m 42s
      ✓ lint    (2m 10s)
      ▶ test    (1m 32s)
         └─ step 4/7: Run unit tests
      ○ deploy  (queued)

 ⏳ sindus/frontend  Tests  ·  branch: feature/x  ·  waiting for a runner…
```

## Requirements

- Python 3.7+
- A GitHub [Personal Access Token](https://github.com/settings/tokens/new) with scope **`repo`** (or `public_repo` for public repositories only)

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/sindus/term/main/github-action-progress/install.sh | bash
```

This will:
1. Check for Python 3.7+
2. Install the Python dependencies (`requests`, `rich`)
3. Download `ghap` to `~/.ghap/ghap.py`
4. Create a launcher at `~/.local/bin/ghap`

If `~/.local/bin` is not in your `PATH`, the installer will print the line to add to your shell config.

## Usage

```bash
ghap                 # start the monitor
ghap -i 30           # refresh every 30 seconds (default: 15)
ghap --reset-token   # replace your saved GitHub token
```

### First launch

On first run, `ghap` will ask for your GitHub token if none is found:

```
No GitHub token found.

To create one:
  1. Open  https://github.com/settings/tokens/new
  2. Give it a name  (e.g. ghap)
  3. Select scope:   repo
  4. Click Generate token and copy it

Paste your GitHub token:
```

The token is saved to `~/.config/ghap/token` (mode `600`, readable only by you).

### Selecting repositories

After authentication, an interactive list of all your repositories appears:

```
↑ ↓  navigate    SPACE  select / deselect    ENTER  confirm    A  select all    Ctrl-C  quit

  Type to filter  ·  0 selected

 ▶ [ ]  sindus/frontend        public   pushed 2h ago
   [x]  sindus/my-api          private  pushed 5h ago
   [ ]  sindus/docs            public   pushed 3d ago
```

### Updates

Each launch silently checks for a new version. If one is available:

```
Update available: 1.0.0 → 1.0.1
Update now? [Y/n]
```

Choosing **Y** downloads the new version and restarts automatically.

## Uninstall

```bash
rm -rf ~/.ghap              # app files
rm -f  ~/.local/bin/ghap   # launcher
rm -rf ~/.config/ghap      # saved token
```
