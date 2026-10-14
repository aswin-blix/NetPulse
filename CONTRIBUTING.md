# Contributing to NetPulse

Keep changes focused and reuse the existing small modules. Include a clear
description of the problem, the proposed behavior, and how it was verified.
For bugs, include Windows and Python versions, display scaling, widget mode,
and reproducible steps. Remove private adapter names and paths from reports.

## Validation

Follow the environment setup in [README.md](README.md). From `source`, run
the focused tests for the change, then the full suite and lint/format checks:

```powershell
..\.venv\Scripts\python.exe -m unittest discover -s tests -v
..\.venv\Scripts\python.exe -m ruff check .
..\.venv\Scripts\python.exe -m ruff format --check .
```

Use a Windows desktop session. UI tests create their own temporary preferences
and exercise real Tk windows. Cover changed behavior and relevant failure cases.
For UI changes, check Mini, Compact, and Comfortable sizes in dark and light themes.
Update affected documentation and record the actual validation performed.

## Preparing a public source repository

Review `git status --short` and the complete diff before committing. Keep generated
executables, ZIP archives, `.local-work`, settings, and environment files out of Git.
The source, tests, icon, previews, license, and documentation belong in the repository.
Executable releases are published manually. The landing page has a GitHub Pages
workflow; see [WEBSITE.md](WEBSITE.md) for website checks and deployment setup.

## Preparing an executable release

1. Validate the exact source revision and build on Windows using the command in
   the README. Record Python, Tcl/Tk, and PyInstaller versions.
2. Close other NetPulse instances and smoke-test the resulting executable with a
   temporary `--config` file. Check live readings, dragging, customization, and saved
   preferences after restart.
3. Assemble a portable release containing the executable, `README.txt`, the NetPulse
   `LICENSE`, and the applicable notices for the runtimes and libraries actually
   bundled by that build. Collect these from the matching build environment.
4. Include Python and Tcl/Tk notices and inspect additional bundled DLLs, including
   OpenSSL, libffi, and Microsoft runtimes. The existing local executable/archive
   predates this license preparation and has not had its dependency notices assembled.
5. Compute a SHA-256 checksum with `Get-FileHash -Algorithm SHA256`, record the tested
   platform and limitations, and publish the archive as a release asset alongside
   the corresponding source revision.

Licensing references: [Python](https://docs.python.org/3/license.html),
[Tcl/Tk](https://www.tcl-lang.org/software/tcltk/license.html), and
[PyInstaller](https://pyinstaller.org/en/stable/license.html). PyInstaller's license
exception permits distributing the bundled application under its own license;
licenses for the bundled dependencies still apply.
