import math

from draw_extras import DANGLING, ONE_SHOT, STANDING
from sprite_kit import *

FALLING = 4
CHEERING = 50
WALK_CYCLE = (1, 2, 1, 3)

BALLOON_OVERHANG = 100
BALLOON_BLUE = (0.18, 0.44, 0.84)
BALLOON_SHINE = (0.78, 0.88, 1.0)
BALLOON_CENTER = (86, 42)
BALLOON_RX, BALLOON_RY = 33, 39
KNOT_LENGTH = 7
STRING = (0.12, 0.12, 0.12)
STEEL = (0.66, 0.68, 0.73)
STEEL_SHINE = (0.93, 0.95, 0.98)
HOOK_SHANK, HOOK_RADIUS, HOOK_TIP = 13.8, 3.5, 3
HOOKED_SWING = 5
HOOKED_AT = (BALLOON_CENTER[0] + HOOKED_SWING - HOOK_RADIUS, BALLOON_OVERHANG + 99)
HOOK_TIE = (HOOKED_AT[0] + HOOK_RADIUS, HOOKED_AT[1] - HOOK_SHANK)
STRING_LENGTH = HOOK_TIE[1] - (BALLOON_CENTER[1] + BALLOON_RY + KNOT_LENGTH)
FAR_BEHIND_HIM = ((100, 150, 0.35), (105, 124, 0.48), (104, 98, 0.62), (99, 74, 0.76), (93, 57, 0.88))
SWEAT = (0.62, 0.85, 1.0)
SWEAT_ON_BROW = (39, BALLOON_OVERHANG + 30)
TREMBLE = ((0, 0), (1, 0), (0, 1), (-1, 0), (1, 1), (0, 0), (-1, 1), (1, -1))


def tall(overhang):
    surface, ctx = blank(SIZE, SIZE + overhang)
    ctx.set_line_join(cairo.LINE_JOIN_ROUND)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    return surface, ctx


def big_balloon(ctx, cx, cy, tilt=0, scale=1.0):
    ctx.save()
    ctx.translate(cx, cy)
    ctx.rotate(math.radians(tilt))
    ctx.scale(scale, scale)
    knot = lambda c: (c.move_to(0, BALLOON_RY - 1), c.line_to(-4.5, BALLOON_RY + KNOT_LENGTH),
                      c.line_to(4.5, BALLOON_RY + KNOT_LENGTH), c.close_path())
    silhouette(ctx, [ellipse(0, 0, BALLOON_RX, BALLOON_RY), knot], BALLOON_BLUE, 1.25)
    ctx.set_source_rgba(*BALLOON_SHINE, 0.9)
    ellipse(-BALLOON_RX * 0.55, -BALLOON_RY * 0.55, 4, 8, 32)(ctx)
    ctx.fill()
    ctx.restore()


def knot_point(cx, cy, tilt, scale=1.0):
    a = math.radians(tilt)
    reach = (BALLOON_RY + KNOT_LENGTH) * scale
    return cx - reach * math.sin(a), cy + reach * math.cos(a)


def hook(ctx, x, y, scale=1.0):
    ctx.save()
    ctx.translate(x, y)
    ctx.scale(scale, scale)
    r = HOOK_RADIUS
    shape = lambda c: (c.move_to(r, -HOOK_SHANK + 2), c.line_to(r, 0), c.arc(0, 0, r, 0, math.pi),
                       c.line_to(-r, -HOOK_TIP))
    for width, color in ((3.4, OUTLINE), (1.6, STEEL)):
        ctx.set_source_rgb(*color)
        ctx.set_line_width(width)
        shape(ctx)
        ctx.stroke()
    filled(ctx, STEEL, circle(r, -HOOK_SHANK, 2), 1.2)
    ctx.set_source_rgb(*STEEL_SHINE)
    ctx.rectangle(r - 0.5, -HOOK_SHANK + 4, 1, 5)
    ctx.fill()
    ctx.restore()


def hanging_string(ctx, knot, tie, swing):
    ctx.set_source_rgb(*STRING)
    ctx.set_line_width(1.3)
    ctx.move_to(*knot)
    ctx.curve_to(knot[0] + swing * 0.2, knot[1] + (tie[1] - knot[1]) * 0.4,
                 tie[0] - swing * 0.4, tie[1] - (tie[1] - knot[1]) * 0.3, *tie)
    ctx.stroke()


def sweat_drop(ctx, x, y):
    def drop(c):
        c.move_to(x, y - 6)
        c.curve_to(x + 1.5, y - 2, x + 4, y + 1, x + 4, y + 3.5)
        c.arc(x, y + 3.5, 4, 0, math.pi)
        c.curve_to(x - 4, y + 1, x - 1.5, y - 2, x, y - 6)
        c.close_path()
    filled(ctx, SWEAT, drop, 1.3)
    ctx.set_source_rgb(1, 1, 1)
    ellipse(x - 1.5, y + 3, 0.9, 1.4)(ctx)
    ctx.fill()


def drifting_in(base, cx, cy, scale, swing):
    surface, ctx = tall(BALLOON_OVERHANG)
    knot = knot_point(cx, cy, 0, scale)
    tie = (knot[0] + swing * scale, knot[1] + STRING_LENGTH * scale)
    hanging_string(ctx, knot, tie, swing)
    hook(ctx, tie[0] - HOOK_RADIUS * scale, tie[1] + HOOK_SHANK * scale, scale)
    big_balloon(ctx, cx, cy, scale=scale)
    paint(surface, base, dy=BALLOON_OVERHANG)
    return surface


def lifted(base, center=BALLOON_CENTER, sway=0, slack=0.0, behind=None, extra=None):
    surface, ctx = tall(BALLOON_OVERHANG)
    cx, cy = center[0] + sway, center[1]
    tilt = sway * 3
    ctx.set_source_rgb(*STRING)
    ctx.set_line_width(1.3)
    ctx.move_to(*HOOK_TIE)
    ctx.curve_to(110 + 10 * slack, BALLOON_OVERHANG + 70, 106 - 12 * slack, BALLOON_OVERHANG + 10 + 20 * slack,
                 *knot_point(cx, cy, tilt))
    ctx.stroke()
    big_balloon(ctx, cx, cy, tilt)
    hook(ctx, *HOOKED_AT)
    if behind:
        behind(ctx)
    paint(surface, base, dy=BALLOON_OVERHANG)
    if extra:
        extra(context(surface))
    return surface


def popped(base, flash=True, extra=None):
    surface, ctx = tall(BALLOON_OVERHANG)
    if flash:
        burst(ctx, *BALLOON_CENTER, 18, 40, range(0, 360, 24), GOLD, 3)
        for k in range(7):
            a = math.radians(k * 51 + 10)
            filled(ctx, BALLOON_BLUE, ellipse(BALLOON_CENTER[0] + 30 * math.cos(a), BALLOON_CENTER[1] + 30 * math.sin(a),
                                             4.5, 2.4, k * 40), 1.2)
        outlined_text(ctx, "POP!", BALLOON_CENTER[0] - 22, BALLOON_CENTER[1] + 7, 18, fill=GOLD, width=3)
    paint(surface, base, dy=BALLOON_OVERHANG)
    if extra:
        extra(context(surface))
    return surface


def balloon(kit):
    stand, dangle = kit.sprite(STANDING), kit.sprite(DANGLING)
    look_back = move_eyes(stand, 3, -3)
    swings = (-6, 4, 9, 5, 0)
    grab = [(STANDING, 300)]
    grab += [(drifting_in(stand if k < 2 else look_back, x, y, scale, swing), 120)
             for k, ((x, y, scale), swing) in enumerate(zip(FAR_BEHIND_HIM, swings))]
    grab += [(drifting_in(look_back, *BALLOON_CENTER, 1.0, swing), ms) for swing, ms in ((7, 140), (HOOKED_SWING, 140))]
    clink = lambda c: burst(c, HOOKED_AT[0] + 2, HOOKED_AT[1] - 2, 5, 10, (-40, 0, 40), (1, 1, 1), 1.6)
    alarm = lambda c: exclamation(c, 30, BALLOON_OVERHANG + 4)
    sweating = lambda c: sweat_drop(c, *SWEAT_ON_BROW)
    shocked = resize_eyes(stand, 0.45)
    round_eyed = eyes_from(dangle, stand)
    looking_down_scared = lambda dx=0, dy=0: resize_eyes(round_eyed, 0.5, dx - 1, dy + 3)
    grab += [(lifted(look_back, slack=0.8, behind=clink), 120),
             (lifted(shocked, slack=0.6, extra=alarm), 400),
             (lifted(looking_down_scared(), slack=0.0, extra=sweating), 200)]
    rising = [(lifted(looking_down_scared(*TREMBLE[k % len(TREMBLE)]), sway=sway, extra=sweating), 90)
              for k, sway in enumerate((0, 1, 2, 1, 0, -1, -2, -1) * 2)]
    look_up = move_eyes(dangle, 2, -3)
    pop = [(popped(dangle), 110),
           (popped(look_up, False, lambda c: exclamation(c, 26, BALLOON_OVERHANG + 2)), 350)]
    return [("balloon_grab", "states", grab, ONE_SHOT),
            ("balloon", "moves", rising, {}),
            ("balloon_pop", "states", pop, ONE_SHOT)]


BOX_OVERHANG = 120
CARD = (0.80, 0.60, 0.37)
CARD_SIDE = (0.66, 0.47, 0.27)
CARD_TOP = (0.88, 0.70, 0.46)
CARD_LINE = (0.55, 0.38, 0.20)
TAPE = (0.93, 0.82, 0.60)
BOX_BOTTOM = 114
CROUCH = 14
RISEN = 6
SLIT = (46, 57, 44, 16)
EYE_AREA = (38, 38, 50, 22)
EYES_IN_SLIT = (6, 17)


def cardboard_box(ctx, dy):
    ctx.save()
    ctx.translate(0, dy)
    left_flap = lambda c: (c.move_to(30, 44), c.line_to(18, 30), c.line_to(54, 28), c.line_to(64, 44), c.close_path())
    right_flap = lambda c: (c.move_to(64, 44), c.line_to(78, 26), c.line_to(116, 30), c.line_to(100, 44), c.close_path())
    filled(ctx, CARD_SIDE, left_flap, 2.2)
    filled(ctx, CARD_TOP, right_flap, 2.2)
    filled(ctx, CARD_SIDE, lambda c: (c.move_to(100, 44), c.line_to(110, 37), c.line_to(110, 106),
                                      c.line_to(100, 114), c.close_path()), 2.2)
    filled(ctx, CARD, lambda c: c.rectangle(30, 44, 70, 70), 2.4)
    ctx.set_source_rgb(*TAPE)
    ctx.rectangle(59, 45.5, 10, 12)
    ctx.fill()
    ctx.set_source_rgb(*CARD_LINE)
    ctx.set_line_width(1.2)
    for x in (59, 69):
        ctx.move_to(x, 45.5)
        ctx.line_to(x, 57.5)
    ctx.stroke()
    for x in (40, 52):
        ctx.move_to(x, 104)
        ctx.line_to(x, 92)
        ctx.move_to(x - 3.5, 96)
        ctx.line_to(x, 92)
        ctx.line_to(x + 3.5, 96)
    ctx.set_line_width(1.8)
    ctx.stroke()
    ctx.set_line_width(1.2)
    ctx.rectangle(80, 98, 12, 9)
    ctx.stroke()
    ctx.move_to(83, 101)
    ctx.line_to(89, 101)
    ctx.move_to(83, 104)
    ctx.line_to(87, 104)
    ctx.stroke()
    ctx.restore()


def eye_whites(source):
    surface = crop_rects(source, [EYE_AREA])
    surface.flush()
    data, stride = surface.get_data(), surface.get_stride()
    for i in range(0, stride * SIZE, 4):
        if data[i + 1] <= 40:
            data[i:i + 4] = bytes(4)
    surface.mark_dirty()
    return surface


def slit(ctx, dy):
    x, y, w, h = SLIT
    r = h / 2
    ctx.new_sub_path()
    ctx.arc(x + r, y + dy + r, r, math.pi / 2, 3 * math.pi / 2)
    ctx.arc(x + w - r, y + dy + r, r, -math.pi / 2, math.pi / 2)
    ctx.close_path()


def boxed(body, box_dy, eyes=None, puffs=0.0, overhang=0):
    surface, ctx = tall(overhang)
    paint(surface, crop_rows(body, max(0, min(SIZE, BOX_BOTTOM + box_dy)), SIZE), dy=overhang)
    ctx.translate(0, overhang)
    cardboard_box(ctx, box_dy)
    slit(ctx, box_dy)
    ctx.set_source_rgb(0.05, 0.03, 0.02)
    ctx.fill_preserve()
    if eyes is not None:
        ctx.save()
        ctx.clip()
        ctx.set_source_surface(eye_whites(eyes), EYES_IN_SLIT[0], EYES_IN_SLIT[1] + box_dy)
        ctx.paint()
        ctx.restore()
    slit(ctx, box_dy)
    ctx.set_source_rgb(*CARD_LINE)
    ctx.set_line_width(1.6)
    ctx.stroke()
    for x in (24, 106) if puffs else ():
        ctx.push_group()
        cloud(ctx, x, 124, 5 + 3 * puffs, 1 + 0.4 * puffs)
        ctx.pop_group_to_source()
        ctx.paint_with_alpha(1 - puffs * 0.6)
    return surface


def box_sneak(kit):
    stand = kit.sprite(STANDING)
    walk = [kit.sprite(index) for index in WALK_CYCLE]
    ahead = move_eyes(stand, -2, 0)
    cheer = without_confetti(kit.sprite(CHEERING))
    on = [(boxed(stand, -BOX_OVERHANG * 2, overhang=BOX_OVERHANG), 400),
          (boxed(move_eyes(stand, -3, 0), -BOX_OVERHANG * 2, overhang=BOX_OVERHANG), 300),
          (boxed(move_eyes(stand, 3, 0), -BOX_OVERHANG * 2, overhang=BOX_OVERHANG), 300),
          (boxed(frame_of(move_eyes(stand, 1, -3), lambda c: exclamation(c, 26, 2)), -BOX_OVERHANG * 2,
                 overhang=BOX_OVERHANG), 250)]
    on += [(boxed(stand, dy, overhang=BOX_OVERHANG), 50) for dy in (-200, -150, -100, -50, -10)]
    on += [(boxed(stand, CROUCH, puffs=0.2), 90), (boxed(stand, CROUCH, puffs=0.7), 110),
           (boxed(stand, CROUCH, stand), 350), (boxed(stand, CROUCH, close_eyes(stand, 0.6)), 90),
           (boxed(stand, CROUCH, ahead), 300), (boxed(stand, RISEN, ahead), 70)]
    sneaking = [(boxed(walk[k], k % 2, ahead), 110) for k in range(4)]
    peek = [(boxed(stand, RISEN, stand), 70)]
    peek += [(boxed(stand, CROUCH, eyes), ms) for eyes, ms in ((stand, 300), (move_eyes(stand, 3, 0), 450),
                                                               (move_eyes(stand, -3, 0), 450),
                                                               (close_eyes(stand, 0.6), 90), (stand, 400))]
    peek.append((boxed(stand, RISEN, ahead), 70))
    off = [(boxed(stand, 0, stand), 300), (boxed(stand, CROUCH, close_eyes(stand, 0.6)), 160)]
    off += [(boxed(cheer, dy, overhang=BOX_OVERHANG), 55) for dy in (-12, -50, -100, -170, -250)]
    off += [(cheer, 600), (STANDING, 500)]
    return [("box_on", "states", on, ONE_SHOT),
            ("box", "moves", sneaking, {}),
            ("box_peek", "states", peek, ONE_SHOT),
            ("box_off", "states", off, ONE_SHOT)]


def animations(kit):
    return [*balloon(kit), *box_sneak(kit)]
