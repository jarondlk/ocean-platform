# C26 hosted timeout amendment — 2026-11-01 JST

The user changed only the backend job timeout from60to90minutes in `afe9cb2`. The preceding `55d6e72` run reached its60minute job limit and was cancelled. The accepted run41175282249 completes in about73minutes. Its first covered17cases take20m43s; remaining6694cases take50m00s. Both covered processes pass and combined coverage is83.64% against the unchanged70% gate.

Original local e087/0345 reports and all843non-workflow source paths are preserved. The first scheduled diagnostic dump remains0, remaining-suite dump120s, fatal fault handling enabled; all17/rest tests, eight coverage targets, sysmon and coverage append remain. This observed passing configuration does not establish the cause of the earlier three native Python crashes.

`workflow-before.yml` is the exact55d6workflow, `workflow-after.yml` the exact acceptedafe9workflow. `plan.json` also names the original functional workflow SHA for one-path composition; no original receipt is retargeted.
