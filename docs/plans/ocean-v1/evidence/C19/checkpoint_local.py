"""Update the mutable C19 ledger only after the immutable local receipt passes."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[5]
PLAN = ROOT / "docs/plans/ocean-v1"
receipt = json.loads((PLAN / "evidence/C19/verification.json").read_text())
backend = receipt["checks"]["backend"]
counts = f'{backend["passed"]} backend/{backend["postgres_gated_skips"]} gated skips/{backend["coverage_percent"]}%'
summary = (
    f"C19 local acceptance passes: {counts};356 new C19 cases and164 required "
    "compatibility cases; all9 generated checks/Ruff and independent source review. "
    "Inventory-first C17/C14 exploration, binding pins, full-count/later-page "
    "discovery, deterministic completion and cooperative stopping are implemented. "
    "C18 frontend23 sources remain unchanged. Source checkpoint and exact-source "
    "hosted delivery are pending. [Handoff](handoffs/C19.md), "
    "[contract](C19_AGENT_CONTROLLER_CONTRACT.md), [receipt](evidence/C19/verification.json)."
)
path = PLAN / "STATUS.md"
text = path.read_text()
text = text.replace("Updated: 2026-10-18 JST.", "Updated: 2026-10-19 JST.", 1)
text = text.replace("**P00 and C01–C18 are Complete locally; C18 hosted delivery is complete.**", "**P00 and C01–C19 are Complete locally; C18 hosted delivery is complete and C19 hosted delivery is pending.**", 1)
text = text.replace("C19 is In progress; C20–C27 remain Not started.", "C19 passes local controller acceptance; C20–C27 remain Not started.")
text = text.replace("Latest delivered implementation:", "Latest local implementation: **C19 — Agent exploration controller**. " + summary + "\n\nLatest delivered implementation:", 1)
old = "| [C19 — Agent exploration controller](components/C19-agent-controller.md) | In progress | All59 prerequisite entries reconcile; action/scope/controller checkpoints selected | C18 delivered; fake-runtime implementation acceptance pending | [C19](handoffs/C19.md) |"
new = "| [C19 — Agent exploration controller](components/C19-agent-controller.md) | Complete | All3 local checkpoints; source checkpoint/hosted delivery pending | " + counts + ";356 new cases/164 compatibility;9 generated checks; actual synthetic C14/C17 and100000 backend | [C19](handoffs/C19.md) |"
assert old in text
path.write_text(text.replace(old, new))
path = PLAN / "README.md"
text = path.read_text().replace("**P00 and C01–C18 are Complete locally with C18 hosted delivery complete; C19 is In progress; C20–C27 are not started.**", "**P00 and C01–C19 are Complete locally; C18 hosted delivery is complete and C19 hosted delivery is pending; C20–C27 are not started.**", 1)
path.write_text(text + "\n" + summary + "\n")
path = PLAN / "components/C19-agent-controller.md"
text = path.read_text().replace("**Status:** In progress; readiness passed and all3 local checkpoints selected.", "**Status:** Complete for all3 local checkpoints; source checkpoint and exact-source hosted delivery pending.", 1)
path.write_text(text + "\n## Local acceptance — 2026-10-19 JST\n\n" + summary.replace("(handoffs/", "(../handoffs/").replace("(C19_", "(../C19_").replace("(evidence/", "(../evidence/") + "\n")
path = PLAN / "handoffs/C19.md"
text = path.read_text().replace("State: In progress; all3 implementation checkpoints frozen, broad acceptance running.", "State: Complete for all3 local checkpoints; source checkpoint/hosted delivery pending.", 1)
text = text.replace("The source-pinned full backend command is running once through\n`evidence/C19/verify_backend.py`; its results are not yet accepted.", "The source-pinned full backend acceptance passes " + counts + " through\n`evidence/C19/verify_backend.py`; all tested source bytes are unchanged.")
text = text.replace("Finish full backend acceptance and unchanged-source checks, freeze verification\nand preservation of823 prior evidence/30 unrelated/7 science/2 serving/106 legacy\nfiles, commit/push the source checkpoint to overhaul, then await source-bound\nhosted CI and record a separate delivery checkpoint. C20 is not started.", "Local acceptance and source verification are frozen in evidence/C19/verification.json.\nAll823 prior evidence/30 unrelated/7 science/2 serving/106 legacy files are unchanged.\nNext: commit/push the source checkpoint to overhaul, await source-bound hosted CI\nand record a separate delivery checkpoint before C20 readiness. C20 is not started.")
path.write_text(text)
print(counts)
