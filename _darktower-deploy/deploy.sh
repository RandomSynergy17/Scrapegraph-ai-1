#!/usr/bin/env bash
#
# deploy.sh - Deploy ScrapeGraph Server to DarkTower
#
# Usage:
#   ./deploy.sh              # Deploy server source + config
#   ./deploy.sh server       # Deploy server/ source + Dockerfile.server only
#   ./deploy.sh config       # Deploy docker-compose + .env file only
#   ./deploy.sh server config  # Deploy multiple targets
#   ./deploy.sh --dry-run    # Preview changes without deploying
#   ./deploy.sh --force      # Skip git dirty check
#
set -euo pipefail

# Ensure standard paths are available
export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:$PATH"

# =============================================================================
# Configuration
# =============================================================================

REMOTE_USER="randolph"
REMOTE_HOST="darktower.lynx-alpha.ts.net"
REMOTE_BASE="/docker/appdata/scrapegraph"
CONTAINER_NAME="scrapegraph-server"

# Portainer stack reference
PORTAINER_URL="https://portainer.randomsynergy.xyz"
PORTAINER_ENV_ID=2
STACK_NAME="scrapegraph"
STACK_ID=182

# Use Homebrew rsync if available (macOS openrsync lacks --chmod support)
RSYNC_BIN="rsync"
if [ -x /opt/homebrew/bin/rsync ]; then
    RSYNC_BIN="/opt/homebrew/bin/rsync"
fi

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Source paths — all local sources live inside _darktower-deploy/
SERVER_SRC="$SCRIPT_DIR/server"
DOCKERFILE_SRC="$SCRIPT_DIR/Dockerfile.server"
CONFIG_SRC="$SCRIPT_DIR"

# Remote destination for server/ contents
SERVER_DST="$REMOTE_USER@$REMOTE_HOST:$REMOTE_BASE/server/"

# =============================================================================
# Colors
# =============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# =============================================================================
# Functions
# =============================================================================

info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
error()   { echo -e "${RED}[ERROR]${NC} $1" >&2; }

usage() {
    cat << EOF
Usage: $(basename "$0") [OPTIONS] [TARGET...]

Deploy ScrapeGraph Server to DarkTower (darktower.lynx-alpha.ts.net).

TARGETS:
  server        Deploy server/ source code + Dockerfile.server
  config        Deploy docker-compose.portainer.yml + .env.portainer
  (none)        Deploy both targets

OPTIONS:
  -d, --dry-run       Preview changes without deploying
  -f, --force         Skip git dirty check
  -h, --help          Show this help message

POST-DEPLOY:
  Trigger a stack redeploy from Portainer to rebuild the image:
  $PORTAINER_URL/#!/$PORTAINER_ENV_ID/docker/stacks/$STACK_NAME

EXAMPLES:
  $(basename "$0")                    # Deploy everything
  $(basename "$0") server            # Deploy source only
  $(basename "$0") --dry-run         # Preview all changes
  $(basename "$0") -f config         # Force deploy config only

REMOTE:
  Host: $REMOTE_HOST
  Path: $REMOTE_BASE
  Container: $CONTAINER_NAME

PORTAINER:
  Stack: $STACK_NAME (ID: $STACK_ID)
  URL: $PORTAINER_URL/#!/$PORTAINER_ENV_ID/docker/stacks/$STACK_NAME
EOF
}

check_ssh() {
    info "Checking SSH connectivity to $REMOTE_HOST..."

    if ! ssh -o ConnectTimeout=5 -o BatchMode=yes "$REMOTE_USER@$REMOTE_HOST" "echo ok" &>/dev/null; then
        error "SSH connection failed to $REMOTE_USER@$REMOTE_HOST"
        error "Check your SSH key configuration"
        return 1
    fi

    success "SSH connection OK"
}

check_git() {
    local force="$1"

    info "Checking git status..."

    cd "$PROJECT_ROOT"

    if ! git rev-parse --is-inside-work-tree &>/dev/null; then
        warn "Not a git repository, skipping git check"
        return 0
    fi

    if ! git diff --quiet || ! git diff --cached --quiet; then
        if [ "$force" = "true" ]; then
            warn "Uncommitted changes detected (--force used, continuing)"
        else
            error "Uncommitted changes detected!"
            echo ""
            git status --short
            echo ""
            error "Commit changes before deploying, or use --force to skip"
            return 1
        fi
    else
        success "Working directory clean"
    fi
}

check_sources() {
    local deploy_server="$1"
    local deploy_config="$2"

    if [ "$deploy_server" = "true" ]; then
        if [ ! -d "$SERVER_SRC" ]; then
            error "server/ not found: $SERVER_SRC"
            return 1
        fi
        if [ ! -f "$DOCKERFILE_SRC" ]; then
            error "Dockerfile.server not found: $DOCKERFILE_SRC"
            return 1
        fi
    fi

    if [ "$deploy_config" = "true" ]; then
        if [ ! -f "$CONFIG_SRC/docker-compose.portainer.yml" ]; then
            error "Compose file not found: $CONFIG_SRC/docker-compose.portainer.yml"
            return 1
        fi
        if [ ! -f "$CONFIG_SRC/.env.portainer" ]; then
            error ".env.portainer not found: $CONFIG_SRC/.env.portainer"
            error "Copy .env.portainer.example to .env.portainer and fill in values"
            return 1
        fi
    fi

    success "Source files OK"
}

ensure_remote_dir() {
    info "Ensuring remote directory exists: $REMOTE_BASE"
    ssh "$REMOTE_USER@$REMOTE_HOST" "mkdir -p $REMOTE_BASE/server"
    success "Remote directory ready"
}

deploy_server() {
    local dry_run="$1"

    info "Deploying server/ source..."

    local -a rsync_cmd=(
        "$RSYNC_BIN" -rltzv --progress
        --no-perms --no-owner --no-group
        --chmod=D755,F644
        --omit-dir-times
        --delete
        --exclude=.DS_Store
        --exclude=__pycache__/
        --exclude='*.pyc'
        --exclude='*.pyo'
        --exclude='.git/'
    )

    if [ "$dry_run" = "true" ]; then
        rsync_cmd+=(--dry-run)
        info "DRY RUN: server/ deployment preview"
    fi

    echo ""
    local rsync_output
    rsync_output=$("${rsync_cmd[@]}" "$SERVER_SRC/" "$SERVER_DST" 2>&1) || {
        local exit_code=$?
        echo "$rsync_output"
        if [ $exit_code -eq 23 ]; then
            warn "Some non-critical rsync warnings (exit 23), continuing..."
        else
            error "rsync failed with exit code $exit_code"
            return $exit_code
        fi
    }
    [ -n "$rsync_output" ] && echo "$rsync_output"
    echo ""

    if [ "$dry_run" = "true" ]; then
        info "DRY RUN: Would copy Dockerfile.server -> $REMOTE_BASE/Dockerfile.server"
        success "Server dry run complete"
    else
        info "Deploying Dockerfile.server..."
        scp -q "$DOCKERFILE_SRC" "$REMOTE_USER@$REMOTE_HOST:$REMOTE_BASE/Dockerfile.server"
        success "Server source deployed"
    fi
}

deploy_config() {
    local dry_run="$1"

    info "Deploying config files..."

    if [ "$dry_run" = "true" ]; then
        info "DRY RUN: Would copy docker-compose.portainer.yml -> $REMOTE_BASE/docker-compose.portainer.yml"
        info "DRY RUN: Would copy .env.portainer -> $REMOTE_BASE/.env"
        success "Config dry run complete"
        return
    fi

    scp -q "$CONFIG_SRC/docker-compose.portainer.yml" \
        "$REMOTE_USER@$REMOTE_HOST:$REMOTE_BASE/docker-compose.portainer.yml"
    success "Deployed docker-compose.portainer.yml"

    # .env.portainer deployed as .env — the path referenced by env_file in docker-compose
    scp -q "$CONFIG_SRC/.env.portainer" "$REMOTE_USER@$REMOTE_HOST:$REMOTE_BASE/.env"
    success "Deployed .env.portainer -> .env"
}

# =============================================================================
# Main
# =============================================================================

main() {
    local dry_run="false"
    local force="false"
    local deploy_server="false"
    local deploy_config="false"
    local targets=()

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -d|--dry-run) dry_run="true"; shift ;;
            -f|--force)   force="true";   shift ;;
            -h|--help)    usage; exit 0 ;;
            server|config) targets+=("$1"); shift ;;
            *)
                error "Unknown option: $1"
                usage
                exit 1
                ;;
        esac
    done

    # Determine what to deploy
    if [ ${#targets[@]} -eq 0 ]; then
        deploy_server="true"
        deploy_config="true"
    else
        for target in "${targets[@]}"; do
            case "$target" in
                server) deploy_server="true" ;;
                config) deploy_config="true" ;;
            esac
        done
    fi

    # Header
    echo ""
    echo "========================================"
    echo "  ScrapeGraph Server — Deployment"
    echo "========================================"
    echo ""

    if [ "$dry_run" = "true" ]; then
        warn "DRY RUN MODE — No changes will be made"
        echo ""
    fi

    info "Targets: $([ "$deploy_server" = "true" ] && echo "server ")$([ "$deploy_config" = "true" ] && echo "config")"
    info "Remote:  $REMOTE_USER@$REMOTE_HOST:$REMOTE_BASE"
    echo ""

    # Pre-flight checks
    check_ssh                                          || exit 1
    check_git "$force"                                 || exit 1
    check_sources "$deploy_server" "$deploy_config"    || exit 1

    if [ "$dry_run" = "false" ]; then
        ensure_remote_dir
    fi

    echo ""
    echo "----------------------------------------"
    echo ""

    # Deploy
    [ "$deploy_server" = "true" ] && deploy_server "$dry_run"
    [ "$deploy_config" = "true" ] && deploy_config "$dry_run"

    # Summary
    echo ""
    echo "----------------------------------------"
    if [ "$dry_run" = "true" ]; then
        success "Dry run complete"
    else
        success "Deployment complete!"
        echo ""
        info "Next: trigger a stack redeploy in Portainer to rebuild the image"
        info "Portainer: $PORTAINER_URL/#!/$PORTAINER_ENV_ID/docker/stacks/$STACK_NAME"
    fi
    echo ""
}

main "$@"
