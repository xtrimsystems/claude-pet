import math
import os

import cairo

SIZE = 128
SITTING = 11
GUN_POSE = 15
BUBBLE_BOX = (0, 0, 43, 62)
BUBBLE_TAIL = (30, 58)
HEAD_SHIFT = (2, -1)
EYE_PATCHES = ((38, 48, 20, 36), (66, 44, 30, 42))
ARM_REGIONS = ((0, 92, 48, 20), (48, 94, 12, 18))
SHOULDER = (60, 102)
FLAG_BOX = (0, 90, 30, 12)
FLAG_CENTER = (24, 97)
EYE_BOXES = ((44, 56, 13, 21), (70, 54, 21, 23))
BURST = (240 / 255, 165 / 255, 35 / 255)


def load(img_dir, index):
    return cairo.ImageSurface.create_from_png(os.path.join(img_dir, f"shime{index}.png"))


def blank():
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, SIZE, SIZE)
    return surface, cairo.Context(surface)


def copy(source):
    surface, ctx = blank()
    ctx.set_source_surface(source, 0, 0)
    ctx.paint()
    return surface


def clear(surface, x, y, w, h):
    ctx = cairo.Context(surface)
    ctx.set_operator(cairo.OPERATOR_CLEAR)
    ctx.rectangle(x, y, w, h)
    ctx.fill()


def paint_clipped(target, source, rects, dx=0, dy=0):
    ctx = cairo.Context(target)
    for rect in rects:
        ctx.rectangle(*rect)
    ctx.clip()
    ctx.set_source_surface(source, dx, dy)
    ctx.paint()


def crop(source, rect):
    surface, _ = blank()
    paint_clipped(surface, source, [rect])
    return surface


def inside(x, y, rects):
    return any(rx <= x < rx + rw and ry <= y < ry + rh for rx, ry, rw, rh in rects)


def pixels_that_differ(source, reference, regions):
    surface = copy(source)
    surface.flush()
    reference.flush()
    stride = surface.get_stride()
    out, ref = surface.get_data(), reference.get_data()
    for y in range(SIZE):
        for x in range(SIZE):
            i = y * stride + x * 4
            if not inside(x, y, regions) or out[i:i + 4] == ref[i:i + 4]:
                out[i:i + 4] = b"\x00\x00\x00\x00"
    surface.mark_dirty()
    return surface


def erase_pixels(surface, layer):
    surface.flush()
    layer.flush()
    stride = surface.get_stride()
    out, mask = surface.get_data(), layer.get_data()
    for y in range(SIZE):
        for x in range(SIZE):
            i = y * stride + x * 4
            if mask[i + 3]:
                out[i:i + 4] = b"\x00\x00\x00\x00"
    surface.mark_dirty()


def underpaint(surface, source, rects):
    ctx = cairo.Context(surface)
    for rect in rects:
        ctx.rectangle(*rect)
    ctx.clip()
    ctx.set_operator(cairo.OPERATOR_DEST_OVER)
    ctx.set_source_surface(source, 0, 0)
    ctx.paint()


def lower_eyelids(source, closed_fraction):
    surface = copy(source)
    surface.flush()
    stride = surface.get_stride()
    data = surface.get_data()
    for bx, by, bw, bh in EYE_BOXES:
        rows = [y for y in range(by, by + bh)
                if any(data[y * stride + x * 4 + 1] > 120 for x in range(bx, bx + bw))]
        if not rows:
            continue
        lid = rows[0] + (rows[-1] - rows[0] + 1) * closed_fraction
        for y in range(rows[0], math.ceil(lid)):
            for x in range(bx, bx + bw):
                i = y * stride + x * 4
                if data[i + 1] > 60 and data[i + 3] > 0:
                    data[i:i + 3] = bytes((0, 0, 0))
    surface.mark_dirty()
    return surface


def paint_rotated(target, layer, pivot, degrees):
    ctx = cairo.Context(target)
    ctx.translate(*pivot)
    ctx.rotate(math.radians(degrees))
    ctx.translate(-pivot[0], -pivot[1])
    ctx.set_source_surface(layer, 0, 0)
    ctx.paint()


def paint_scaled(target, layer, pivot, scale):
    ctx = cairo.Context(target)
    ctx.translate(*pivot)
    ctx.scale(scale, scale)
    ctx.translate(-pivot[0], -pivot[1])
    ctx.set_source_surface(layer, 0, 0)
    ctx.get_source().set_filter(cairo.FILTER_NEAREST if scale >= 1 else cairo.FILTER_GOOD)
    ctx.paint()


def burst(target):
    ctx = cairo.Context(target)
    ctx.set_source_rgb(*BURST)
    ctx.set_line_width(1.3)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    cx, cy = FLAG_CENTER
    for degrees in (150, 180, 210, 245, 115):
        a = math.radians(degrees)
        ctx.move_to(cx + 7 * math.cos(a), cy + 7 * math.sin(a))
        ctx.line_to(cx + 11 * math.cos(a), cy + 11 * math.sin(a))
    ctx.stroke()


def gun_layers(img_dir):
    sitting = load(img_dir, SITTING)
    aimed_bare = copy(load(img_dir, GUN_POSE))
    clear(aimed_bare, *BUBBLE_BOX)
    clear(aimed_bare, *FLAG_BOX)
    arm = pixels_that_differ(aimed_bare, sitting, ARM_REGIONS)
    unarmed = copy(aimed_bare)
    erase_pixels(unarmed, arm)
    underpaint(unarmed, sitting, ARM_REGIONS)
    return aimed_bare, arm, unarmed


def build(img_dir):
    sitting = load(img_dir, SITTING)
    gun_pose = load(img_dir, GUN_POSE)

    bubble = crop(gun_pose, BUBBLE_BOX)
    flag = crop(gun_pose, FLAG_BOX)
    aimed_bare, arm, unarmed = gun_layers(img_dir)

    smirk = copy(sitting)
    paint_clipped(smirk, gun_pose, EYE_PATCHES, *HEAD_SHIFT)

    def with_arm(degrees):
        frame = copy(unarmed)
        paint_rotated(frame, arm, SHOULDER, degrees)
        return frame

    def with_flag(shift, popped=False):
        frame = copy(aimed_bare)
        paint_clipped(frame, flag, [FLAG_BOX], dx=shift)
        if popped:
            burst(frame)
        return frame

    def with_bubble(scale):
        frame = with_flag(0)
        paint_scaled(frame, bubble, BUBBLE_TAIL, scale)
        return frame

    return {
        "half_lids": lower_eyelids(sitting, 0.5),
        "smirk": smirk,
        "draw_low": with_arm(-38),
        "draw_mid": with_arm(-14),
        "aimed": aimed_bare,
        "flag_peek": with_flag(6),
        "flag_half": with_flag(3),
        "flag_pop": with_flag(0, popped=True),
        "flag": with_flag(0),
        "bubble_small": with_bubble(0.55),
        "bubble_big": with_bubble(1.15),
        "bubble_beat": with_bubble(1.08),
    }


def animations(kit):
    steps = build(kit.img_dir)
    timeline = [
        (SITTING, 700), (steps["half_lids"], 280), (steps["smirk"], 490),
        (steps["draw_low"], 70), (steps["draw_mid"], 70), (steps["aimed"], 420),
        (steps["flag_peek"], 70), (steps["flag_half"], 70), (steps["flag_pop"], 140), (steps["flag"], 420),
        (steps["bubble_small"], 70), (steps["bubble_big"], 70), (GUN_POSE, 350),
        (steps["bubble_beat"], 140), (GUN_POSE, 140), (steps["bubble_beat"], 140), (GUN_POSE, 1470),
    ]
    return [("finger_gun", "states", timeline, {"loop": False, "loops": 1, "next": "idle"})]
