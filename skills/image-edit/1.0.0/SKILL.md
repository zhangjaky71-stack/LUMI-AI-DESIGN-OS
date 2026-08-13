---
name: image-edit
description: Plan bounded image edits that preserve protected regions and make only explicitly requested visual changes.
---
# Image Edit
## When to use
Use when the user has an existing image and requests targeted changes while other regions remain stable.
## Required inputs
Source asset, requested changes, protected regions, output size, and asset-rights context.
## Step sequence
1. Identify protected content. 2. Define edit regions and intent. 3. Preserve untouched geometry and identity. 4. Execute bounded edit. 5. Compare against source constraints.
## Design heuristics
Prefer the smallest edit that achieves the requested result and keeps source characteristics stable.
## Constraints
Do not alter logos, people, products, text, or layout marked as unchanged.
## Verification checklist
Compare protected regions, requested changes, dimensions, edge artifacts, and unintended drift.
## Failure modes
Global restyling, geometry drift, accidental text changes, and loss of source identity.
## Examples
Synthetic example: replace only a fictional product scene background while preserving product shape, label, and camera angle.
## What not to do
Do not reinterpret the whole image when the request is local.