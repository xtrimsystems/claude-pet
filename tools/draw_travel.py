import math

from draw_extras import DANGLING, ONE_SHOT, STANDING
from sprite_kit import *

FALLING = 4
CHEERING = 50
WALK_CYCLE = (1, 2, 1, 3)

BALLOON_OVERHANG = 100
BALLOON_RED = (0.86, 0.12, 0.14)
BALLOON_SHINE = (1.0, 0.75, 0.75)
BALLOON_CENTER = (86, 42)
BALLOON_RX, BALLOON_RY = 33, 39
STRING = (0.12, 0.12, 0.12)
BACK = (80, BALLOON_OVERHANG + 92)


def tall(overhang):
    surface, ctx = blank(SIZE, SIZE + overhang)
    ctx.set_line_join(cairo.LINE_JOIN_ROUND)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    return surface, ctx


def big_balloon(ctx, cx, cy, tilt=0):
    ctx.save()
    ctx.translate(cx, cy)
    ctx.rotate(math.radians(tilt))
    knot = lambda c: (c.move_to(0, BALLOON_RY - 1), c.line_to(-4.5, BALLOON_RY + 7), c.line_to(4.5, BALLOON_RY + 7),
                      c.close_path())
    silhouette(ctx, [ellipse(0, 0, BALLOON_RX, BALLOON_RY), knot], BALLOON_RED, 1.25)
    ctx.set_source_rgba(*BALLOON_SHINE, 0.9)
    ellipse(-BALLOON_RX * 0.48, -BALLOON_RY * 0.45, 5, 10, 28)(ctx)
    ctx.fill()
    ctx.set_source_rgba(1, 1, 1, 0.9)
    ellipse(-BALLOON_RX * 0.62, -BALLOON_RY * 0.1, 2, 3.2, 20)(ctx)
    ctx.fill()
    ctx.set_source_rgb(*OUTLINE)
    ctx.arc(3, 6, 13, 0, 2 * math.pi)
    ctx.fill()
    ctx.set_source_rgb(*BALLOON_RED)
    ctx.arc(3, 6, 9, 0, 2 * math.pi)
    ctx.fill()
    ctx.set_source_rgb(*OUTLINE)
    ctx.rectangle(1, -5, 4, 22)
    ctx.fill()
    ctx.restore()


def knot_point(cx, cy, tilt):
    a = math.radians(tilt)
    return cx - (BALLOON_RY + 7) * math.sin(a), cy + (BALLOON_RY + 7) * math.cos(a)


def lifted(base, center=BALLOON_CENTER, sway=0, slack=0.0, extra=None):
    surface, ctx = tall(BALLOON_OVERHANG)
    cx, cy = center[0] + sway, center[1]
    tilt = sway * 3
    ctx.set_source_rgb(*STRING)
    ctx.set_line_width(1.3)
    ctx.move_to(*BACK)
    ctx.curve_to(114 + 10 * slack, BALLOON_OVERHANG + 80, 108 - 12 * slack, BALLOON_OVERHANG + 10 + 20 * slack,
                 *knot_point(cx, cy, tilt))
    ctx.stroke()
    big_balloon(ctx, cx, cy, tilt)
    paint(surface, base, dy=BALLOON_OVERHANG)
    if extra:
        extra(context(surface))
    return surface


def popped(base, flash=True, extra=None):
    surface, ctx = tall(BALLOON_OVERHANG)
    ctx.set_source_rgb(*STRING)
    ctx.set_line_width(1.3)
    ctx.move_to(*BACK)
    ctx.curve_to(104, BALLOON_OVERHANG + 88, 112, BALLOON_OVERHANG + 70, 106, BALLOON_OVERHANG + 58)
    ctx.stroke()
    if flash:
        burst(ctx, *BALLOON_CENTER, 18, 40, range(0, 360, 24), GOLD, 3)
        for k in range(7):
            a = math.radians(k * 51 + 10)
            filled(ctx, BALLOON_RED, ellipse(BALLOON_CENTER[0] + 30 * math.cos(a), BALLOON_CENTER[1] + 30 * math.sin(a),
                                             4.5, 2.4, k * 40), 1.2)
        outlined_text(ctx, "POP!", BALLOON_CENTER[0] - 22, BALLOON_CENTER[1] + 7, 18, fill=GOLD, width=3)
    paint(surface, base, dy=BALLOON_OVERHANG)
    if extra:
        extra(context(surface))
    return surface


def balloon(kit):
    stand, dangle = kit.sprite(STANDING), kit.sprite(DANGLING)
    look_up = move_eyes(stand, 1, -3)
    grab = [(lifted(stand, (BALLOON_CENTER[0], -100)), 400), (lifted(look_up, (BALLOON_CENTER[0], -100)), 300)]
    grab += [(lifted(look_up, (BALLOON_CENTER[0], y), slack=1 - k / 6), 90) for k, y in enumerate((-70, -40, -12, 14, 34, 42))]
    grab += [(lifted(look_up, slack=0.3), 300),
             (lifted(stand, extra=lambda c: exclamation(c, 30, BALLOON_OVERHANG + 4)), 250)]
    looking_down = move_eyes(dangle, -2, 2)
    rising = [(lifted(dangle if k < 8 else looking_down, sway=sway), 90)
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
BELT_ROWS = range(94, 104)


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


def is_confetti(r, g, b, y):
    suit = r <= 140 and g <= 45 and b <= 45
    grey = abs(r - g) < 28 and abs(g - b) < 28
    belt = y in BELT_ROWS and r > g > b >= 16 and r < 120 and g < 90
    return not (suit or grey or belt)


def without_confetti(source):
    surface = copy(source)
    surface.flush()
    data, stride = surface.get_data(), surface.get_stride()
    original = bytes(data)
    alpha = lambda x, y: original[y * stride + x * 4 + 3] if 0 <= x < SIZE and 0 <= y < SIZE else 0
    near = lambda x, y: [(x + dx, y + dy) for dx in range(-2, 3) for dy in range(-2, 3)]
    confetti = set()
    for y in range(SIZE):
        for x in range(SIZE):
            b, g, r, a = original[y * stride + x * 4:y * stride + x * 4 + 4]
            if a and is_confetti(r * 255 // a, g * 255 // a, b * 255 // a, y):
                confetti.add((x, y))
            elif a and a < 120 and sum(alpha(*p) > 200 for p in near(x, y)) < 4:
                confetti.add((x, y))
    for x, y in confetti:
        body = sum(p not in confetti and alpha(*p) > 200 for p in near(x, y))
        i = y * stride + x * 4
        data[i:i + 4] = bytes((0, 0, 108, 255)) if body >= 12 else bytes(4)
    surface.mark_dirty()
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
