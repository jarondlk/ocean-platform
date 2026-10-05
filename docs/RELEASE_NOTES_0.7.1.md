# v0.7.1 — Source-aware retrieval and evidence coverage

Candidate notes; publication and deployment are pending acceptance.

Chat searches selected sources individually and combines their ranked evidence
within the existing total document budget. A dominant source can no longer
consume every slot when the budget can represent all nonempty selected sources.
Prompt packing preserves source representation and reports its final omissions.

Answers and the evidence workbench show per-source coverage, including source
search failures, unavailable publications and budget limitations. Saved feedback
history retains the exact final evidence and diagnostics; older histories keep
their original content.

Explicit supported cross-source comparisons abstain when required evidence is
missing or unchecked. Date/location overlap remains unverified without an
approved matching result even when both sources retrieve evidence. These
responses skip the language model and retain the available evidence; retrieval
omission cannot establish absent data or non-overlap.

This patch does not perform historical SST acquisition or approve ANEMONE
physical sampling, environmental classifications, areas or the six real-data
research demonstrations. Those remain tracked in #102, #103 and #89. Normal
viewer/researcher acceptance passed using explicitly approved role switches only
in an isolated QA copy; all original identities/roles were restored. Container
maintenance (#104) remains open for the retained OS findings.

Migration 0016 only extends saved Chat abstention reasons. Keep that additive
constraint during application rollback; do not erase new histories to downgrade.
See [implementation evidence](RELEASE_0.7.1_IMPLEMENTATION.md) and the
[accepted patch plan](RELEASE_0.7.1_PLAN.md).

Ordinary summaries naming multiple source families now reach retrieval instead of
being mistaken for an exact eDNA catalogue count. Explicit count requests and
single-source catalogue summaries retain their bounded exact-count routing.
Linked-search failures return a safe diagnostic code rather than raw exception
text.

The user explicitly deferred live mobile layout acceptance. Desktop/keyboard,
mounted UI and static CSS checks passed; no live mobile pass is claimed.
