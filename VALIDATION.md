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
- At the time of this preparation, the repository had no remote configured and
  had not been published. The
  existing executable/archive still needs dependency notices assembled before
  public redistribution; see [release instructions](CONTRIBUTING.md).

The [original validation record](source/VALIDATION.txt) describes the earlier
application build, manual checks, and hardware/platform limitations.

## GitHub Pages landing page — 14 October 2026

- Added a buildless landing page under `site/`, using actual app screenshots,
  source-download instructions, and a clearly labeled illustrative Mini preview.
- Passed 6 Python website checks and 8 Node interaction tests. These cover
  project-relative assets, links and IDs, accessibility labels, metadata,
  publication contents, theme preferences, unavailable browser storage,
  radius limits, dragging and cancellation, keyboard movement, resizing,
  and clipboard success/failure behavior.
- Passed JavaScript syntax checking, Ruff checks for the new Python tests,
  Prettier checks for website/JavaScript/workflow files, and `git diff --check`.
- Inspected the rendered page in both themes on a desktop viewport and at
  768 px, 390 px, and 320 px widths. No horizontal document overflow was found.
  Browser checks verified page-theme persistence after reload, independent widget
  themes, dragging against boundaries, reset, keyboard movement, square and
  rounded corners, copy-command feedback, FAQ expansion, and loaded screenshots.
  No browser console warnings or errors were observed during those checks.
- The local preview required an unsandboxed loopback server; the original
  sandboxed server could not be reached. Browser checks above were completed
  against the working local preview.
- The public source repository was confirmed at `aswin-blix/NetPulse`, with
  no packaged releases and Pages disabled at inspection time. The new workflow
  runs the website tests before uploading only `site/` to GitHub Pages.
- Application source and executable files are unchanged. Application tests and
  executable packaging were not rerun for this isolated website change.
- Deployment remains separate from this local commit. These changes have not
  been pushed, and GitHub Pages has not been enabled or deployed. Remote workflow
  execution and the public URL remain unverified until deployment; follow
  [WEBSITE.md](WEBSITE.md).
