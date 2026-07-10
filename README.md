# HD2 Shot Placement Assessor

A framework-free Helldivers 2 shot-placement assistant with locally bundled anatomy images.

The interface includes three task-focused modes:

- **Recommend** ranks aim points or weapons using practical lethality.
- **Inspect** explains one exact enemy/body-part/weapon interaction.
- **Compare** evaluates two weapons across every body part.

Selections, favorites, and recent items stay on the device. The current result can also be copied, linked, or exported as a PNG card.

## Run locally

```powershell
python -m http.server 8765 --bind 127.0.0.1
```

Then open `http://127.0.0.1:8765/shot-placement-assessor.html`.

## Refresh from the original assessor

The builder preserves the original data/calculation section and replaces its UI shell:

```powershell
python tools/build_assessor.py "C:\path\to\shot-placement-assessor.html"
python tools/sync_images.py
python tools/verify_project.py --original "C:\path\to\shot-placement-assessor.html"
node tests/ranking.test.mjs
```

The image sync requires Pillow and downloads each unique wiki anatomy image, resizes it to at most 300 px, and stores it as WebP under `assets/anatomy/`.
