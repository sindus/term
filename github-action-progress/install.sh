#!/usr/bin/env bash
set -euo pipefail

OWNER="sindus"
REPO="term"
BRANCH="main"
FOLDER="github-action-progress"
APP_DIR="$HOME/.ghap"
BIN_DIR="$HOME/.local/bin"
RAW_BASE="https://raw.githubusercontent.com/$OWNER/$REPO/$BRANCH/$FOLDER"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[1;34m'; BOLD='\033[1m'; NC='\033[0m'

ok()   { echo -e "  ${GREEN}✓${NC}  $*"; }
warn() { echo -e "  ${YELLOW}⚠${NC}  $*"; }
err()  { echo -e "  ${RED}✗${NC}  $*" >&2; exit 1; }

echo ""
echo -e "${BOLD}${BLUE}⚡ Installing ghap${NC} — GitHub Actions Progress Monitor"
echo -e "   ${BLUE}https://github.com/$OWNER/$REPO${NC}"
echo ""

# ─── Python 3 check ──────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    err "Python 3 is required but not found. Install it from https://python.org"
fi
PY=$(command -v python3)
PY_VER=$($PY -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
MAJOR=$(echo "$PY_VER" | cut -d. -f1)
MINOR=$(echo "$PY_VER" | cut -d. -f2)
if [ "$MAJOR" -lt 3 ] || { [ "$MAJOR" -eq 3 ] && [ "$MINOR" -lt 7 ]; }; then
    err "Python 3.7+ required (found $PY_VER). Please upgrade Python."
fi
ok "Python $PY_VER"

# ─── pip dependencies ─────────────────────────────────────────────────────────
echo -n "  Installing dependencies (requests, rich)…"
if $PY -m pip install -q --user requests rich 2>/dev/null \
   || $PY -m pip install -q requests rich 2>/dev/null; then
    echo -e "  ${GREEN}✓${NC}"
else
    echo ""
    warn "Could not install dependencies automatically."
    warn "Run manually: pip3 install requests rich"
fi

# ─── Download app ─────────────────────────────────────────────────────────────
mkdir -p "$APP_DIR"
echo -n "  Downloading ghap…"
if curl -fsSL "$RAW_BASE/ghap.py" -o "$APP_DIR/ghap.py"; then
    chmod +x "$APP_DIR/ghap.py"
    echo -e "          ${GREEN}✓${NC}"
else
    echo ""
    err "Download failed. Check your internet connection and try again."
fi

# ─── Create launcher ──────────────────────────────────────────────────────────
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/ghap" << 'LAUNCHER'
#!/usr/bin/env bash
exec python3 "$HOME/.ghap/ghap.py" "$@"
LAUNCHER
chmod +x "$BIN_DIR/ghap"
ok "Launcher created at $BIN_DIR/ghap"

# ─── PATH check ───────────────────────────────────────────────────────────────
echo ""
if [[ ":$PATH:" == *":$BIN_DIR:"* ]]; then
    echo -e "${GREEN}${BOLD}✓ Installation complete!${NC}"
    echo ""
    echo -e "  Run: ${BOLD}ghap${NC}"
else
    echo -e "${YELLOW}${BOLD}Almost done!${NC}  Add ~/.local/bin to your PATH."
    echo ""
    echo "  For zsh:"
    echo -e "    ${BOLD}echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.zshrc && source ~/.zshrc${NC}"
    echo ""
    echo "  For bash:"
    echo -e "    ${BOLD}echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc && source ~/.bashrc${NC}"
    echo ""
    echo "  Then run: ghap"
fi
echo ""
