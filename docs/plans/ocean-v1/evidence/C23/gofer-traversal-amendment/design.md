# Gofer search boundary — profile v5

Actual diagnostic smoke20261026-01 failed before analysis: gofer could not bind
the verified rootfs because its mapped host UID100000 cannot search root-owned
0700 ancestors. Sentry then received an empty mount description and exited.
The prior profile, adapter and tests are retained in prior-source/. No resource
limit or host-root mapping is changed to address this DAC failure.

The operator stages inputs under the original strict0700 rules first. It then
permits ONLY named host UID100000 to search five exact ancestor directories:
the fixed operator root, attempt collection, selected attempt, worker and job.
All remain root-owned, with no group/other permissions and no named read/write
permissions. The Linux access ACL has exactly five entries: user_obj=rwx,
user100000=x, group_obj=none, mask=x, other=none. Its mode is0710 because the
group mode bits represent the ACL mask; accepting0710 alone is forbidden.
Unknown/default ACLs, owners, symlinks, directory swaps and broader entries
must fail closed. Mutation and readback use the same nofollow directory FD.

Search allows stat of a known child name. It does not hide all known-name
metadata. The journal, runtime state and diagnostic descendants retain0700;
control/configuration/canary files retain their private modes. No default ACL
is installed, so new descendants do not inherit the search permission. The
analysis host UID100001 receives no new ACL. Original files.py and its staging
rules remain unchanged. The profile and adapter accept exact search ACLs only
at worker/job boundaries; diagnostics and state remain strict.

An alternative separate rootfs bind alias would require another mounted
resource and absolute-path lifecycle. The exact search ACL is selected for
this dedicated operator worker because it preserves the existing mount path
and cleanup proofs while granting no read/write to control storage. No general
production-worker activation is implied. Every actual guest test must still
verify private canary denial, input readability, readonly image, namespace
restriction and cleanup. Local byte-policy tests are not containment evidence.

The trusted host permission probe creates a new synthetic temporary directory,
tests known-name search plus denied listing/private-read/journal/create under
UID100000, removes its ACL and deletes that probe. It runs no generated analysis
and is not a host execution fallback. Actual gofer startup and all original
containment gates remain required after this narrow preparation.
