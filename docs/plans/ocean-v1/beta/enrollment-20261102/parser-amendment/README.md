# Exact apply flag and proxy finalizer amendment

Independent source review found a CLI dispatch mismatch: argparse's default
long-option abbreviation could parse `--app` as `--apply`, while the finalizer's
explicit argv test recognized only the exact `--apply`. An abbreviated request
could therefore enter the applied path without its required proxy finalizer.
No actual enrollment or exposure is established by that finding.

The owning parser now sets `allow_abbrev=False`. Only the exact apply flag can
select mutation. Abbreviated flags reject before private configuration, Google
verification, database work or proxy network calls. An exact apply invocation
still requests proxy shutdown on parser/configuration failures; failed shutdown
still returns exit3 and remains unaccepted.

The sole production change is that parser option. The original41-case receipt,
checks/output and6source bytes remain unchanged or explicitly frozen beneath
`frozen-original/`. `original-receipt.json` is an exact predecessor copy; no
historical source pin is retargeted. Six new focused mocked checks cover
abbreviations and exact-apply failure/finalizer behavior, without acquiring a
token, creating a key, connecting a database, exercising native PostgreSQL or
calling GCP. The original41cases are not repeated.

Root reports the user's concrete application choice is **Administrator /
internal**, for the selected university Google account. That is an external
authorization decision, not an inferred or newly introduced role default.
Applied invocation must still explicitly choose `--role admin --account-type
internal`. The exact approved email remains a private deployment input; an
actual current Google-signed SDK user token, expected official audience and
signature/profile verification are still pending. No subject is inferred from
the email and no account is enrolled by this amendment.

```sh
.venv/bin/python docs/plans/ocean-v1/beta/enrollment-20261102/parser-amendment/verify.py
```

The read-only verifier maps the original source to its frozen bytes and checks
the new one-line supersession, six-case evidence and unchanged predecessor
artifacts. Independent review, source-bound image/job, actual Google identity,
restricted database preflight/commit/readback and successful physical
operator/proxy exits remain separate gates. No unrelated or frozen serving/
operator package is changed.
