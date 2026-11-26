import hashlib
import json
import os
import re
import sys

import cairo

import draw_extras
import draw_finger_gun
import draw_gags
import draw_hats
import draw_scooter
import draw_travel
from sprite_kit import Kit, copy, erase, mirror_text, sign_pixels

FIRST_GENERATED = 54
MIN_PNG_BYTES = 500
FRONT_DIR = "front"
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


def head_anchors(kit, finder, originals, animations):
    heads = {}
    for index in originals:
        anchor, _ = finder.anchor(kit.sprite(index))
        if finder.usable(kit.sprite(index), anchor):
            heads[index] = anchor
    for frames, indices in animations:
        surfaces = [kit.sprite(frame) if isinstance(frame, int) else frame for frame in frames]
        for index, anchor in zip(indices, draw_hats.head_anchors(finder, surfaces)):
            if anchor and index not in heads:
                heads[index] = anchor
    return heads


def write_hats(mascot_dir, hats):
    hat_dir = os.path.join(mascot_dir, "hats")
    os.makedirs(hat_dir, exist_ok=True)
    for name in os.listdir(hat_dir):
        if name.endswith(".png") and name[:-4] not in hats:
            os.remove(os.path.join(hat_dir, name))
    for name, image in hats.items():
        image.write_to_png(os.path.join(hat_dir, f"{name}.png"))


def write_fronts(mascot_dir, fronts):
    front_dir = os.path.join(mascot_dir, FRONT_DIR)
    os.makedirs(front_dir, exist_ok=True)
    files = {index: f"{FRONT_DIR}/shime{index}.png" for index in fronts}
    for name in os.listdir(front_dir):
        if f"{FRONT_DIR}/{name}" not in files.values():
            os.remove(os.path.join(front_dir, name))
    for index, surface in fronts.items():
        surface.write_to_png(os.path.join(mascot_dir, files[index]))
    return files


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
    played = []
    fronts = {}
    for (name, kind, frames, options), (_, _, mirrored, _) in zip(all_animations(kit), all_animations(kit, True)):
        sprites = []
        for (frame, _, *front), (twin, *_) in zip(frames, mirrored):
            if not isinstance(frame, int):
                has_text = fingerprint(twin) != fingerprint(frame)
                frame = index_for(frame)
                if has_text:
                    twins.append((frame, twin))
            if front:
                fronts[frame] = front[0]
            sprites.append(frame)
        manifest[kind][name] = {"sprites": sprites, "durations": [entry[1] for entry in frames], **options}
        played.append(([entry[0] for entry in frames], sprites))
    manifest["looks"] = {str(pose): {"eyes": look["eyes"],
                                     "sprites": [frame if isinstance(frame, int) else index_for(frame)
                                                 for frame in look["frames"]]}
                         for pose, look in draw_extras.looks(kit).items()}
    manifest["right_facing"] = {str(index): index_for(twin) for index, twin in sorted(twins, key=lambda t: t[0])}

    hats = draw_hats.hats()
    heads = head_anchors(kit, draw_hats.HeadFinder(kit, hats.values()), originals, played)
    for twin_of, twin in manifest["right_facing"].items():
        if int(twin_of) in heads:
            heads[twin] = heads[int(twin_of)]
    for pose, look in manifest["looks"].items():
        for index in look["sprites"]:
            if int(pose) in heads:
                heads[index] = heads[int(pose)]
    manifest["hats"] = {name: list(draw_hats.HAT_ORIGIN) for name in hats}
    manifest["heads"] = {str(index): heads[index] for index in sorted(heads)}
    write_hats(mascot_dir, hats)
    front_files = write_fronts(mascot_dir, fronts)
    for twin_of, twin in manifest["right_facing"].items():
        if int(twin_of) in front_files:
            front_files[twin] = front_files[int(twin_of)]
    manifest["fronts"] = {str(index): front_files[index] for index in sorted(front_files)}

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
          f"{len(manifest['right_facing'])} right-facing text frames, {len(heads)} frames with a head for hats, "
          f"sprites {FIRST_GENERATED}-{last}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "sprites/deadpool")
