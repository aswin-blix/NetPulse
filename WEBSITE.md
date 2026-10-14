# NetPulse website

The landing page lives in `site/`. It uses plain HTML, CSS, and JavaScript.
No build step, package manager, or server-side runtime is needed to publish it.
GitHub Pages serves these files directly.

## Preview locally

From the repository root, run:

```powershell
python -m http.server 8000 --directory site --bind 127.0.0.1
```

Open <http://127.0.0.1:8000/>. Press `Ctrl+C` in the terminal to stop the preview.
Check the page at desktop and mobile widths, keyboard navigation, light and dark
themes, and the download and repository links before publishing changes.

## Checks

Run the website tests from the repository root. They use only Python's and
Node.js's built-in test tools; no packages need to be installed:

```powershell
python -B -m unittest discover -s tests -p test_site.py -v
node --test tests/site.test.cjs
node --check site/script.js
```

The Python tests check the published page and its assets; the JavaScript tests
exercise the interactive preview and browser-storage/clipboard failure paths.
The Pages workflow runs both suites before uploading the website.

## Enable GitHub Pages

The expected public address is:

<https://aswin-blix.github.io/NetPulse/>

This address is a deployment target; adding these files does not make it live.

1. In the `aswin-blix/NetPulse` repository, open **Settings > Pages**.
2. Under **Build and deployment**, set **Source** to **GitHub Actions**.
3. Commit and push the website and `.github/workflows/pages.yml` to `main`.
4. In **Actions**, open **Deploy landing page** and confirm the deployment succeeds.
   If the files were already pushed before Pages was enabled, select **Run workflow**
   on the `main` branch.
5. Open the address above and check the deployed page and links.

The workflow runs when `site/`, its tests, or its workflow file changes on `main`,
and can also be started manually. Its artifact contains only `site/`; application source,
local executables, scratch files, and development files are not uploaded to Pages.
GitHub's `github-pages` environment records deployments and their URLs.

Use relative paths for site assets so they work under the `/NetPulse/` project
path. Keep the page usable without JavaScript and avoid adding app dependencies
to the static website.

## Downloads and releases

The initial landing page offers the public source ZIP and source-running
instructions. There is no published executable release yet; do not label a
source archive as a Windows executable or link to a nonexistent release asset.

When a tested portable release is available, follow the release checklist in
[CONTRIBUTING.md](CONTRIBUTING.md), publish its runtime notices and checksum,
then update the website download links and text to match the actual release.
The existing local executable is not part of the website deployment.

## Deployment reference

The workflow uses GitHub's official checkout, Pages configuration, artifact
upload, and deployment actions. See GitHub's documentation for
[custom Pages workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).
