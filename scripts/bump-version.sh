#!/bin/bash
# SPDX-License-Identifier: LGPL-3.0-or-later
# Version bump script for hyper2kvm

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_step() {
    echo -e "${GREEN}==>${NC} $1"
}

# Get current version
CURRENT_VERSION=$(grep -Po '(?<=^version = ")[^"]*' pyproject.toml)

echo "Current version: $CURRENT_VERSION"
echo ""

# Parse new version from argument or ask
if [[ -n "$1" ]]; then
    NEW_VERSION="$1"
else
    read -p "Enter new version (e.g., 0.0.2): " NEW_VERSION
fi

# Validate version format
if ! [[ "$NEW_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+(a[0-9]+|b[0-9]+|rc[0-9]+|\.post[0-9]+)?$ ]]; then
    echo "Invalid version format: $NEW_VERSION"
    echo "Expected format: X.Y.Z or X.Y.Za1 or X.Y.Zb1 or X.Y.Zrc1 or X.Y.Z.post1"
    exit 1
fi

echo "Bumping version from $CURRENT_VERSION to $NEW_VERSION"
echo ""

# Files to update
FILES=(
    "pyproject.toml"
    "hyper2kvm/__init__.py"
    "setup.py"
    "hyper2kvm.spec"
)

# Update each file
for file in "${FILES[@]}"; do
    if [[ ! -f "$file" ]]; then
        echo "⚠ Skipping $file (not found)"
        continue
    fi

    print_step "Updating $file"

    case "$file" in
        pyproject.toml)
            sed -i "s/^version = \".*\"/version = \"$NEW_VERSION\"/" "$file"
            ;;
        hyper2kvm/__init__.py)
            sed -i "s/__version__ = \".*\"/__version__ = \"$NEW_VERSION\"/" "$file"
            ;;
        setup.py)
            sed -i "s/version=\".*\"/version=\"$NEW_VERSION\"/" "$file"
            ;;
        hyper2kvm.spec)
            sed -i "s/^Version:.*$/Version:        $NEW_VERSION/" "$file"
            ;;
    esac

    # Show diff
    if git diff --quiet "$file"; then
        echo "  No changes"
    else
        echo "  Changed:"
        git diff "$file" | grep -E "^[-+].*version" || true
    fi
done

echo ""
print_step "Version bump complete!"
echo ""
echo "Review changes:"
echo "  git diff"
echo ""
echo "Commit changes:"
echo "  git add ${FILES[*]}"
echo "  git commit -m \"chore: Bump version to $NEW_VERSION\""
echo ""
echo "Next steps:"
echo "  1. Review and test"
echo "  2. Commit version bump"
echo "  3. Build and publish: ./scripts/publish.sh test"
echo "  4. If tests pass: ./scripts/publish.sh prod"
