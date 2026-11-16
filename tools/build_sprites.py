import hashlib
import json
import os
import re
import sys

import cairo

import draw_extras
import draw_finger_gun
import draw_gags
import draw_scooter
import draw_travel
from sprite_kit import Kit, copy, erase, mirror_text, sign_pixels

FIRST_GENERATED = 54
MIN_PNG_BYTES = 500
SPRITE_NAME = re.compile(r"shime(\d+)\.png$")
QUESTION_BOX = (10, 8, 22, 38)
HEY_BOX = (25, 93, 55, 19)
TILTED_HEY_BOX = (21, 80, 63, 32)


def fingerprint(surface):
    surface.flush()
    return hashlib.sha1(bytes(surface.get_data())).hexdigest()


def sprite_indices(img_dir):
    return {int(match.group(1)) for match in map(SPRITE_NAME.match, os.listdir(img_dir)) if match}


def flip_box(source, box):
    x, y, width, height = box
    surface = copy(source)
    ctx = cairo.Context(surface)
    ctx.rectangle(x, y, width, height)
    ctx.clip()
    ctx.set_operator(cairo.OPERATOR_SOURCE)
    ctx.translate(2 * x + width, 0)
    ctx.scale(-1, 1)
    ctx.set_source_surface(source, 0, 0)
    ctx.paint()
    return surface


def swap_sign(target, partner, box):
    x, _, width, _ = box
    surface = copy(target)
    erase(surface, sign_pixels(target, box))
    ctx = cairo.Context(surface)
    ctx.translate(2 * x + width, 0)
    ctx.scale(-1, 1)
    ctx.set_source_surface(sign_pixels(partner, box), 0, 0)
    ctx.paint()
    return surface


def pack_text_twins(kit):
    sprite = kit.sprite
    return [(43, flip_box(sprite(43), QUESTION_BOX)),
            (51, flip_box(sprite(51), HEY_BOX)),
            (52, swap_sign(sprite(52), sprite(53), TILTED_HEY_BOX)),
            (53, swap_sign(sprite(53), sprite(52), TILTED_HEY_BOX))]


def all_animations(kit, text_mirrored=False):
    mirror_text(text_mirrored)
    try:
        return [animation for module in (draw_scooter, draw_finger_gun, draw_extras, draw_gags, draw_travel)
                for animation in module.animations(kit)]
    finally:
        mirror_text(False)


def write_manifest(path, manifest):
    sections = []
    for kind, configs in manifest.items():
        entries = [f'    "{name}": {json.dumps(config)}' for name, config in configs.items()]
        sections.append(f'  "{kind}": {{\n' + ",\n".join(entries) + "\n  }")
    with open(path, "w") as f:
        f.write("{\n" + ",\n".join(sections) + "\n}\n")


def main(mascot_dir):
    img_dir = os.path.join(mascot_dir, "img")
    kit = Kit(img_dir)
    originals = sorted(i for i in sprite_indices(img_dir) if i < FIRST_GENERATED)
    index_of = {fingerprint(kit.sprite(i)): i for i in originals}
    generated = {}
    manifest = {"states": {}, "moves": {}}

    def index_for(surface):
        key = fingerprint(surface)
        if key not in index_of:
            index_of[key] = FIRST_GENERATED + len(generated)
            generated[index_of[key]] = surface
        return index_of[key]

    twins = pack_text_twins(kit)
    for (name, kind, frames, options), (_, _, mirrored, _) in zip(all_animations(kit), all_animations(kit, True)):
        sprites = []
        for (frame, _), (twin, _) in zip(frames, mirrored):
            if not isinstance(frame, int):
                has_text = fingerprint(twin) != fingerprint(frame)
                frame = index_for(frame)
                if has_text:
                    twins.append((frame, twin))
            sprites.append(frame)
        manifest[kind][name] = {"sprites": sprites, "durations": [ms for _, ms in frames], **options}
    manifest["right_facing"] = {str(index): index_for(twin) for index, twin in sorted(twins, key=lambda t: t[0])}

    for index, surface in generated.items():
        surface.write_to_png(kit.path(index))
        if os.path.getsize(kit.path(index)) < MIN_PNG_BYTES:
            sys.exit(f"{kit.path(index)} is nearly empty; the pet skips sprites under {MIN_PNG_BYTES} bytes")
    for index in sprite_indices(img_dir):
        if index >= FIRST_GENERATED and index not in generated:
            os.remove(kit.path(index))

    write_manifest(os.path.join(mascot_dir, "animations.json"), manifest)
    last = FIRST_GENERATED + len(generated) - 1
    print(f"{len(manifest['states'])} states, {len(manifest['moves'])} moves, "
          f"{len(manifest['right_facing'])} right-facing text frames, sprites {FIRST_GENERATED}-{last}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "sprites/deadpool")
