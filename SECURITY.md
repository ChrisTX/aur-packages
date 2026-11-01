# Security policy

## What to report here

Security problems of the packaging: a PKGBUILD that downloads sources without verifying them (missing checksums or signature checks), install scripts, permissions or default configurations that leave a system open, or sources taken from somewhere they shouldn't be.

Vulnerabilities of the packaged software itself belong upstream: see the project's own security policy, at the `url` of the PKGBUILD. If upstream has released a fix and the package is still on an affected version, open an issue or flag the package out of date on the AUR.

Only the current version of each package on the AUR is supported.

## How to report

Please report privately, not in a public issue or AUR comment:

- with GitHub's [private vulnerability reporting](https://github.com/ChrisTX/aur-packages/security/advisories/new), or
- by email to cpfeiffer at rev-crew dot info.

Say which package and version is affected, and how. You'll get an answer within a week; once a fix is published to the AUR, the report can be disclosed.
