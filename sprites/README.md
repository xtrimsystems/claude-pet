# Mascot Sprites

Claude Pet uses the **Shimeji-ee / Shijima-Qt** sprite format. Place your mascot folders here or point to them with `--mascot`.

## Adding a mascot

1. Download or create a Shimeji-ee compatible mascot pack
2. Create a folder here (e.g. `sprites/my-mascot/`)
3. Place the sprite PNGs inside an `img/` subfolder, or directly in the folder:

```
sprites/my-mascot/
  img/
    shime1.png
    shime2.png
    ...
    shimeN.png
```

Or flat layout:

```
sprites/my-mascot/
  shime1.png
  shime2.png
  ...
```

4. Run with: `python3 main.py --mascot sprites/my-mascot`

## Where to find mascots

- **Shijima-Qt** built-in mascots and community packs: https://getshijima.app
- **Shimeji-ee** mascot collections: https://kilkakon.com/shimeji/
- **DeviantArt** has thousands of fan-made Shimeji packs

Most Shimeji-ee packs include an `img/` folder with numbered sprite PNGs — that's all Claude Pet needs.

## Sprite numbering

Sprites are loaded as `shime1.png`, `shime2.png`, etc. The sprite-to-animation mapping is defined in `sprite_character.py`. The default mapping assumes the standard Shimeji-ee 46-sprite layout:

| Sprites | Purpose |
|---------|---------|
| 1-3 | Walking |
| 4 | Falling |
| 5-10 | Dragging (various directions/speeds) |
| 11 | Sitting |
| 12-14 | Climbing |
| 15-17 | Action poses |
| 18-21 | Landing |
| 22 | Jump launch |
| 23-25 | Ceiling walk |
| 26-29 | Celebrating/working |
| 37 | Jump air |
| 38-43 | Error/thinking |
| 44-46 | Special (clone/double) |

Not all mascots use the same numbering. If animations look wrong with your mascot, you may need to adjust the mappings in `sprite_character.py`.
