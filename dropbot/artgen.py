"""Art generation agent: procedural pixel-art sprites for every pet.

Each sprite is generated deterministically from (species id, evolution stage),
so the same pet always gets the same art — no external image API needed.
Sprites use mirrored-symmetry noise (the classic "invader" technique) with an
element-based palette; later evolution stages get bigger, denser, spikier art.

Run `python -m dropbot.artgen` to pre-render every sprite plus a contact sheet
into assets/pets/.
"""

from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageDraw

from .pets import PET_CATALOG, Species

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets" / "pets"
SCALE = 12  # nearest-neighbour upscale factor

# body ramp (dark -> light) and accent per element
PALETTES = {
    "earth":  {"body": ["#3e5622", "#5e7c33", "#87a24c", "#b4c47a"], "accent": "#8b5a2b"},
    "flame":  {"body": ["#7f1d1d", "#c2410c", "#f97316", "#fbbf24"], "accent": "#fde68a"},
    "aqua":   {"body": ["#0c4a6e", "#0369a1", "#0ea5e9", "#7dd3fc"], "accent": "#e0f2fe"},
    "storm":  {"body": ["#3b0764", "#6d28d9", "#8b5cf6", "#facc15"], "accent": "#fef08a"},
    "spirit": {"body": ["#312e81", "#6366f1", "#a5b4fc", "#e9d5ff"], "accent": "#f5f3ff"},
}

# grid size and fill density per evolution stage
STAGE_GRID = (12, 14, 16)
STAGE_DENSITY = (0.42, 0.48, 0.55)


def _hex(color: str) -> tuple[int, int, int, int]:
    color = color.lstrip("#")
    return (int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16), 255)


def generate_sprite(species: Species, stage: int) -> Image.Image:
    rng = random.Random(f"{species.id}:{stage}")
    palette = PALETTES[species.element]
    grid = STAGE_GRID[stage]
    density = STAGE_DENSITY[stage]
    half = grid // 2

    # Mirrored body mask: draw the left half, mirror to the right.
    mask = [[False] * grid for _ in range(grid)]
    for y in range(1, grid - 1):
        # Bias toward a fat torso in the middle rows.
        row_bias = 1.0 - abs((y / grid) - 0.55) * 1.3
        for x in range(1, half):
            if rng.random() < density * max(0.25, row_bias):
                mask[y][x] = mask[y][grid - 1 - x] = True

    # Grow one connective pass so bodies aren't scattered dust.
    for y in range(1, grid - 1):
        for x in range(1, half):
            neighbours = sum(
                mask[y + dy][x + dx]
                for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                if not (dx == dy == 0)
            )
            if neighbours >= 4:
                mask[y][x] = mask[y][grid - 1 - x] = True

    # Horns: guaranteed on the top corners (it's an ox after all).
    horn_y = 1 + (stage > 0)
    for dy in range(1 + stage):
        mask[horn_y + dy][2] = mask[horn_y + dy][grid - 3] = True

    img = Image.new("RGBA", (grid, grid), (0, 0, 0, 0))
    px = img.load()
    body = [_hex(c) for c in palette["body"]]
    accent = _hex(palette["accent"])

    for y in range(grid):
        for x in range(grid):
            if not mask[y][x]:
                continue
            # Shade by height, with mirrored per-pixel noise for texture.
            shade_rng = random.Random(f"{species.id}:{stage}:{y}:{min(x, grid - 1 - x)}")
            idx = min(len(body) - 1, int(y / grid * len(body)) + shade_rng.choice((-1, 0, 0, 1)))
            px[x, y] = accent if shade_rng.random() < 0.06 else body[max(0, idx)]

    # Eyes: symmetric, on an upper body row.
    eye_row = next(
        (y for y in range(grid // 4, grid) if sum(mask[y]) >= 4),
        grid // 3,
    )
    eye_x = next((x for x in range(2, half) if mask[eye_row][x]), 3)
    dark = _hex(palette["body"][0])
    for ex in (eye_x, grid - 1 - eye_x):
        px[ex, eye_row] = (255, 255, 255, 255)
        px[ex, eye_row + 1] = dark

    return img.resize((grid * SCALE, grid * SCALE), Image.NEAREST)


def sprite_path(species: Species, stage: int) -> Path:
    return ASSETS_DIR / f"{species.id}_{stage}.png"


def ensure_sprite(species: Species, stage: int) -> Path:
    """Generate the sprite on first use; cached on disk afterwards."""
    path = sprite_path(species, stage)
    if not path.exists():
        ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        generate_sprite(species, stage).save(path)
    return path


def render_all() -> Path:
    """Pre-render every sprite and build a labelled contact sheet."""
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    species_list = list(PET_CATALOG.species.values())
    cell = 16 * SCALE + 8
    label_h = 18
    sheet = Image.new(
        "RGBA",
        (3 * cell, len(species_list) * (cell + label_h)),
        (24, 24, 32, 255),
    )
    draw = ImageDraw.Draw(sheet)
    for row, species in enumerate(species_list):
        for stage in range(3):
            sprite = generate_sprite(species, stage)
            sprite.save(sprite_path(species, stage))
            x = stage * cell + (cell - sprite.width) // 2
            y = row * (cell + label_h) + (cell - sprite.height) // 2
            sheet.alpha_composite(sprite, (x, y))
            draw.text(
                (stage * cell + 6, row * (cell + label_h) + cell + 2),
                species.stages[stage],
                fill=(220, 220, 230, 255),
            )
    sheet_path = ASSETS_DIR / "contact_sheet.png"
    sheet.save(sheet_path)
    return sheet_path


if __name__ == "__main__":
    path = render_all()
    print(f"Rendered {len(PET_CATALOG.species) * 3} sprites -> {ASSETS_DIR}")
    print(f"Contact sheet -> {path}")
