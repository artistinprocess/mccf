#!/usr/bin/env bash
# Re-run the whole H-Anim export safety net.  Usage (from this folder):
#   ANNA_X3D=/path/to/Anna.x3d bash run_all.sh <mccf_hanim_api.py> <mccf_character_creator.html> [ORIG_api.py ORIG_creator.html]
# Needs: python3 + flask; node + `npm install jsdom` (client tests only). Exit code 0 = all green.
cd "$(dirname "$0")"
API="${1:?patched mccf_hanim_api.py}"; HTML="${2:?patched mccf_character_creator.html}"; OAPI="${3:-}"; OHTML="${4:-}"
rc=0
echo "### server scenarios (patched)";  python3 run_scenarios.py "$API" | tail -3; [ "${PIPESTATUS[0]}" -eq 0 ] || rc=1
echo "### client behaviour (patched)";  PAYLOAD_OUT=payload_patched.json node client_test.js "$HTML" | tail -1; [ "${PIPESTATUS[0]}" -eq 0 ] || rc=1
if [ -n "$OAPI" ] && [ -n "$OHTML" ]; then
  echo "### CONTROL: original code (expected to FAIL - proves the tests can fail)"
  python3 run_scenarios.py "$OAPI" | tail -1; PAYLOAD_OUT=payload_original.json node client_test.js "$OHTML" | tail -1
  echo "### client x server matrix"; python3 e2e.py "$OAPI" "$API"
fi
exit $rc
