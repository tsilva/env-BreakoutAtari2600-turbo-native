# Benchmark proof withdrawal

Four historical benchmark/showcase downloads were withdrawn on 2026-10-05
because their provenance included private infrastructure access details:

- Original benchmark/showcase for native 0.5.15 and TurboBench 2.0.11.
- Showcase style 3, style 4, and style 5 exports for native 0.5.15.

Their GitHub release entries and tags were retired. Original proof archives and
hashes are retained privately; public documents do not provide downloads.
The measured results, policy controls, chart and animation bytes are unchanged.
The current media's original proof and asset identities remain in
[demo-manifest.json](../demo-manifest.json).

New publications must contain hardware specifications without hostnames, IPs,
ports, SSH aliases, login names or private tracking URLs. TurboBench rejects
public exports whose underlying proof includes machine access details.

Ten affected library GitHub release entries and tags (`v0.5.6` through
`v0.5.15`) were also retired to eliminate access details from their source
history. PyPI distributions were left unchanged. Private backups preserve the
original release metadata and assets. GitHub cached views and pull-request
references require a separate GitHub Support purge.
