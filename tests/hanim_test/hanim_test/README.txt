H-Anim export safety net (Day 95)
=================================
Runs the REAL hanim_export()/hanim_joints() endpoints (Flask test client) and the REAL
mccf_character_creator.html (jsdom) against a scratch copy of Anna.x3d. Nothing here touches your
live files: every scenario works on a temp copy.

  audit_x3d.py          structural audit of any avatar .x3d (resume section 8): counts, dangling ROUTEs,
                        duplicate/whitespace DEFs, routed-timer attributes.   python3 audit_x3d.py Anna.x3d
  diff_x3d.py           what changed between two .x3d files (nodes, ROUTEs, attributes).
  run_scenarios.py      9 server scenarios / 36 checks (first-click export, C1-style payload, authored clip,
                        loop edit, keyframes on a real clip, integrity gate, backups, camera rig, discovery).
  client_test.js        20 client checks (C1/C2/C3, discovery filter, rig guard) in jsdom.
  e2e.py                client x server matrix for "load Anna, tick Loop on Bow, Export".
  fake_cultivar_lambda  stand-in for CultivarDefinition (the real mccf_cultivar_lambda.py wasn't available).
  *.diff                the exact changes vs. the files uploaded 2026-09-19.

Run:  ANNA_X3D=/path/to/Anna.x3d bash run_all.sh <mccf_hanim_api.py> <mccf_character_creator.html>
ASSUMPTION: Anna's cultivar is reconstructed from the resume (12 clips: Bow->BowTimer, Fold Arms->Timer2,
Idle->Timer3, Look Around->Timer4, Sit->Timer5, Wait->Timer6, Walk->Timer7, + five whitespace '... 2Timer'
stubs). If the real cultivar_anna.xml differs, edit ANNA_CLIPS in harness.py.
