# Repository preparation validation

## 14 October 2026

- Copied and verified all 37 original project, executable, archive, and scratch
  files by SHA-256. Application code and tests are unchanged.
- Passed all 71 tests from the new location on Windows with Python 3.12.14,
  including real Tk integration and native corner-region checks.
- Passed Ruff 0.16.10 lint and formatting checks for all eight Python files.
- The first test run encountered sandbox temporary-directory permission errors.
  Rerunning with `TEMP` and `TMP` pointing to a writable local test directory
  passed the entire suite without modifying or skipping tests.
- Added MIT licensing, repository documentation, pinned development requirements,
  and Git exclusions for local preferences, binaries, archives, and scratch work.
- Preserved the existing executable unchanged. Its SHA-256 is
  `c27a7d13cdf6f457d528e49fab17202c20242f684403240cbc93d492832c2656`.
  No new executable build or executable smoke test was performed for this
  documentation and relocation change.
- The repository has no remote configured and has not been published. The
  existing executable/archive still needs dependency notices assembled before
  public redistribution; see [release instructions](CONTRIBUTING.md).

The [original validation record](source/VALIDATION.txt) describes the earlier
application build, manual checks, and hardware/platform limitations.
