import hashlib
import json
import os
import re
import sys

import draw_extras
import draw_finger_gun
import draw_scooter
from sprite_kit import Kit

FIRST_GENERATED = 54
MIN_PNG_BYTES = 500
SPRITE_NAME = re.compile(r"shime(\d+)\.png$")


def fingerprint(surface):
    surface.flush()
    return hashlib.sha1(bytes(surface.get_data())).hexdigest()


def sprite_indices(img_dir):
    return {int(match.group(1)) for match in map(SPRITE_NAME.match, os.listdir(img_dir)) if match}


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

    animations = draw_scooter.animations(kit) + draw_finger_gun.animations(kit) + draw_extras.animations(kit)
    for name, kind, frames, options in animations:
        sprites = []
        for frame, _ in frames:
            if not isinstance(frame, int):
                key = fingerprint(frame)
                if key not in index_of:
                    index_of[key] = FIRST_GENERATED + len(generated)
                    generated[index_of[key]] = frame
                frame = index_of[key]
            sprites.append(frame)
        manifest[kind][name] = {"sprites": sprites, "durations": [ms for _, ms in frames], **options}

    for index, surface in generated.items():
        surface.write_to_png(kit.path(index))
        if os.path.getsize(kit.path(index)) < MIN_PNG_BYTES:
            sys.exit(f"{kit.path(index)} is nearly empty; the pet skips sprites under {MIN_PNG_BYTES} bytes")
    for index in sprite_indices(img_dir):
        if index >= FIRST_GENERATED and index not in generated:
            os.remove(kit.path(index))

    write_manifest(os.path.join(mascot_dir, "animations.json"), manifest)
    last = FIRST_GENERATED + len(generated) - 1
    print(f"{len(manifest['states'])} states, {len(manifest['moves'])} moves, sprites {FIRST_GENERATED}-{last}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "sprites/deadpool")
