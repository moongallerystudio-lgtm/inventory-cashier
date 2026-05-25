#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
  cat <<'EOF'
Usage: ./deploy_render.sh [git-remote-url]

If a git remote named origin does not exist, pass the GitHub/GitLab repository URL
as the first argument.

Example:
  ./deploy_render.sh git@github.com:yourname/inventory-cashier.git
EOF
  exit 0
fi

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Error: not a git repository. Initialize a repository first."
  exit 1
fi

if [ -n "$1" ]; then
  if git remote get-url origin >/dev/null 2>&1; then
    echo "Remote origin already exists: $(git remote get-url origin)"
  else
    git remote add origin "$1"
    echo "Added remote origin: $1"
  fi
fi

if ! git remote get-url origin >/dev/null 2>&1; then
  echo "No git remote configured."
  echo "Run: git remote add origin <your-repo-url>"
  exit 1
fi

git push -u origin main

echo
cat <<'EOF'
Code pushed successfully.
Next steps:
1. Open Render and create a new Web Service from your repository.
2. Choose Docker as the environment and keep Dockerfile path as ./Dockerfile.
3. Create or attach a PostgreSQL database service.
4. Set SECRET_KEY and DATABASE_URL in Render environment variables.
5. Deploy the service and verify the HTTPS URL.

If you have RENDER_TOKEN set, you can use the render-cli to inspect your account:
  export RENDER_TOKEN=<your-render-api-token>
  ./.venv-1/bin/render-cli list
EOF
