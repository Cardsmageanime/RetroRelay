# RetroRelay download tracking

This proposed workflow reports GitHub **uploaded release asset** download counts.

## How to see the numbers

After this pull request is merged to `main`, open **Actions → Release download metrics → Run workflow**. Open the completed run's **Summary** to see counts by release. The run also contains a `release-download-metrics` JSON artifact with a snapshot of the counts. A scheduled run is configured once per day (12:17 UTC); GitHub may delay or skip scheduled runs.

The workflow uses the repository's built-in read-only `GITHUB_TOKEN`, and it does not store visitor information or require third-party analytics. It does not modify releases, code, or repository settings.

## What the counts mean

- Only files **explicitly uploaded as release assets** expose `download_count` in GitHub's release API.
- GitHub's automatic **Source code (zip)** and **Source code (tar.gz)** archives do **not** expose this download count.
- Git clones, GitHub Actions artifact downloads, repository views and unique users are not counted.
- A download count is not a unique-person count; repeat downloads may increment it.
- Old downloads of source archives cannot be reconstructed retroactively from this API.
- If a release has no uploaded assets, its measurable asset count is zero, **not** proof that nobody downloaded the source.

To make future versions measurable, publish an **explicitly uploaded** downloadable file on each release (for example `RetroRelay_Source_v0.2.0.zip`, if validated and approved). The GitHub release page will show that asset and the API will track its downloads from publication onward. Do not interpret download counts as installs, active users, or secure usage.

The tracking workflow is separate from PR #2's security review and must not trigger a release or bypass release gates.
