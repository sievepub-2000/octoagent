# generate_word_cloud_chart - Word Cloud Chart

## Overview
Show weighted terms where larger words indicate higher importance or frequency.

## Input Fields
### Required
- `data`: array of records with `text` (string) and `value` (number).

### Optional
- `style.backgroundColor`, `style.palette`, `style.texture`.
- `theme`, `width`, `height`, `title`.

## Usage Notes
Normalize casing and remove stop words before rendering so the word cloud remains meaningful.

## Return Value
- Returns a rendered chart asset URL and keeps the effective configuration in `_meta.spec` for downstream reuse or tracing.
