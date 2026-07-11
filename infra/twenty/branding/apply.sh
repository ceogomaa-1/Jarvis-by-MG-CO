#!/usr/bin/env bash
# Rue CRM branding overlay — the ONLY script that edits the Twenty source tree.
#
# Lives in the fork at jarvis-branding/apply.sh (a copy is tracked here in the Rue
# repo for review). Idempotent: safe to re-run after every upstream rebase.
#
# Run from the fork root:  ./jarvis-branding/apply.sh
#
# Strategy: keep edits content-addressed (grep/sed by string) instead of hard-coded
# paths so small upstream moves don't silently no-op. After running, do the VERIFY
# checklist in branding/README.md.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
OVERLAY="${ROOT}/jarvis-branding"
FRONT="${ROOT}/packages/twenty-front"
EMAILS="${ROOT}/packages/twenty-emails"

echo "→ Rue CRM branding overlay"

# 1. Assets: logo + favicon -----------------------------------------------------
cp -f "${OVERLAY}/logo/"*       "${FRONT}/public/images/logos/" 2>/dev/null || true
cp -f "${OVERLAY}/favicon/"*    "${FRONT}/public/"             2>/dev/null || true

# 2. Theme tokens: drop in the Rue theme + default the color scheme to Dark -----
cp -f "${OVERLAY}/jarvis-theme.ts" "${FRONT}/src/modules/ui/theme/jarvis-theme.ts"
#   (apply.sh also flips the default color scheme — see strings.map note)

# 3. String replacements (app name, login copy, email copy) ---------------------
#    strings.map is TAB-separated:  old<TAB>new
if [[ -f "${OVERLAY}/strings.map" ]]; then
  while IFS=$'\t' read -r old new; do
    [[ -z "${old}" || "${old}" == \#* ]] && continue
    grep -rl --binary-files=without-match "${old}" "${FRONT}/src" "${EMAILS}/src" 2>/dev/null \
      | while read -r f; do
          sed -i "s|${old}|${new}|g" "${f}"
        done
  done < "${OVERLAY}/strings.map"
fi

# 4. Tab title ------------------------------------------------------------------
sed -i 's|<title>.*</title>|<title>Rue CRM</title>|' "${FRONT}/index.html" || true

# 5. External links (docs/support/marketing) → ours or removed ------------------
if [[ -f "${OVERLAY}/links.map" ]]; then
  while IFS=$'\t' read -r old new; do
    [[ -z "${old}" || "${old}" == \#* ]] && continue
    grep -rl --binary-files=without-match "${old}" "${FRONT}/src" 2>/dev/null \
      | while read -r f; do sed -i "s|${old}|${new}|g" "${f}"; done
  done < "${OVERLAY}/links.map"
fi

echo "✓ overlay applied. Now: yarn nx build twenty-front  (or build the Docker image)."
echo "  Then run the VERIFY checklist in infra/twenty/branding/README.md."
