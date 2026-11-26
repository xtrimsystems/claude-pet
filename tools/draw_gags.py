import math
import random

import cairo

from draw_extras import ONE_SHOT, SITTING, STANDING
from sprite_kit import *


KICK = 37
STANDING_FEET_X = 68
IMPACT = (24, 94)
GLASS = (0.92, 0.97, 1.0)
WHISTLE = (1.0, 0.62, 0.80)
LIPS = (88, 66)
LIP_SHADOW = (0.30, 0.0, 0.0)
LIP_SHINE = (0.62, 0.12, 0.12)
MOUTH_HOLE = (0.12, 0.0, 0.0)
NOTE_EVERY = 5
HANDS_AT_CHEEKS = 50
TORTILLA = (0.91, 0.64, 0.27)
CRISP = (0.74, 0.45, 0.15)
TORTILLA_SHINE = (1.0, 0.85, 0.52)
FILLING = (0.66, 0.30, 0.13)
CHEESE = (1.0, 0.84, 0.28)
SALSA = (0.85, 0.16, 0.10)
CHIMI_LENGTH, CHIMI_THICK, BITE = 38, 12, 7
CHIMI_HELD = (86, 59)
CHIMI_TILT = -14
CHIMI_ON_BELT = (56, 86)
MOUTH = (50, 66)


def crack_paths(seed=7):
    rng = random.Random(seed)
    rays = []
    for k in range(9):
        a = math.radians(k * 40 + rng.uniform(-12, 12))
        length = rng.uniform(14, 26) if math.cos(a) > 0.3 else rng.uniform(18, 30)
        points, r = [(0, 0)], 0
        while r < length:
            r += rng.uniform(5, 9)
            a += rng.uniform(-0.35, 0.35)
            points.append((r * math.cos(a), r * math.sin(a)))
        rays.append(points)
    rings = []
    for radius in (6, 12):
        ring = []
        for k in range(9):
            a = math.radians(k * 40 + rng.uniform(-8, 8))
            r = radius * rng.uniform(0.8, 1.2)
            ring.append((r * math.cos(a), r * math.sin(a)))
        rings.append(ring)
    return rays, rings


RAYS, RINGS = crack_paths()


def crack(ctx, growth=1.0, alpha=1.0):
    ctx.save()
    ctx.translate(*IMPACT)
    ctx.push_group()
    for width, color in ((2.6, OUTLINE), (1.1, GLASS)):
        ctx.set_line_width(width)
        ctx.set_source_rgb(*color)
        for ray in RAYS:
            visible = ray[:max(2, round(len(ray) * growth))]
            ctx.move_to(*visible[0])
            for x, y in visible[1:]:
                ctx.line_to(x * growth ** 0.5, y * growth ** 0.5)
            ctx.stroke()
        for ring in RINGS[:1 if growth < 0.6 else 2]:
            for k in range(0, len(ring), 2):
                ctx.move_to(*ring[k])
                ctx.line_to(*ring[(k + 1) % len(ring)])
            ctx.stroke()
    ctx.set_source_rgba(1, 1, 1, 0.9)
    ctx.arc(0, 0, 2.5, 0, 2 * math.pi)
    ctx.fill()
    ctx.pop_group_to_source()
    ctx.paint_with_alpha(alpha)
    ctx.restore()


def shards(ctx, t):
    for k, (vx, vy) in enumerate(((-1, -1.4), (-1.6, 0.2), (-0.8, 1.2), (0.6, -1.8))):
        x, y = IMPACT[0] + vx * 14 * t, IMPACT[1] + vy * 14 * t + 10 * t * t
        filled(ctx, GLASS, lambda c, x=x, y=y, k=k: (c.move_to(x, y - 2.5), c.line_to(x + 2 + k % 2, y + 1.5),
                                                     c.line_to(x - 2, y + 2), c.close_path()), 1.0)


def whistle(ctx, phase):
    for k, glyph in enumerate(("♪", "♫")):
        t = (phase + k / 2) % 1.0
        alpha = 1.0 if t < 0.7 else (1 - t) / 0.3
        outlined_text(ctx, glyph, 100 + 14 * t - 2 * math.sin(t * 8), 62 - 40 * t, 13 + 3 * t,
                      fill=WHISTLE, width=2.4, alpha=alpha)


def puckered_lips(ctx, size):
    x, y = LIPS
    ctx.save()
    ctx.set_operator(cairo.OPERATOR_ATOP)
    ctx.set_source_rgb(*LIP_SHADOW)
    ellipse(x, y, 3.2 * size, 2.8 * size)(ctx)
    ctx.fill()
    ctx.set_source_rgb(*MOUTH_HOLE)
    ellipse(x + 0.3, y, 1.4 * size, 1.2 * size)(ctx)
    ctx.fill()
    ctx.set_source_rgb(*LIP_SHINE)
    ctx.set_line_width(1)
    ctx.arc(x, y, 2.6 * size, 3.6, 5.2)
    ctx.stroke()
    ctx.restore()


def fourth_wall(kit):
    stand = kit.sprite(STANDING)
    kick = kit.sprite(KICK)
    frames = [(STANDING, 500), (shear(stand, -0.04), 160),
              (frame_of(kick, lambda c: burst(c, *IMPACT, 4, 11, range(90, 280, 30), GOLD, 2)), 70),
              (frame_of(kick, lambda c: (crack(c, 0.4), shards(c, 0.3))), 60),
              (frame_of(kick, lambda c: (crack(c, 0.8), shards(c, 0.7))), 60),
              (frame_of(kick, lambda c: (crack(c), shards(c, 1.1))), 70),
              (frame_of(kick, crack), 500),
              (frame_of(move_eyes(stand, -3, 3), crack), 500),
              (frame_of(close_eyes(stand, 0.3), crack), 120),
              (frame_of(stand, crack), 450)]
    back_to_crack = mirrored(stand, STANDING_FEET_X)
    innocent = close_eyes(move_eyes(back_to_crack, 2, -3), 0.45)
    frames.append((frame_of(back_to_crack, crack), 300))
    frames += [(frame_of(innocent, lambda c, k=k: (puckered_lips(c, 1.35 if k % NOTE_EVERY == 0 else 1.2),
                                                   crack(c), whistle(c, k / 10))), 200) for k in range(10)]
    frames += [(frame_of(innocent, lambda c, a=alpha: crack(c, alpha=a)), 140) for alpha in (0.7, 0.45, 0.2)]
    frames += [(back_to_crack, 400), (STANDING, 500)]
    return [("fourth_wall", "states", frames, ONE_SHOT)]


AURA = (0.60, 0.95, 0.85)


def zen(kit):
    sit = kit.sprite(SITTING)
    calm = close_eyes(sit, 0.85)

    def floating(lift, phase, glow=1.0):
        surface, ctx = blank()
        ctx.set_source_rgba(0, 0, 0, 0.25 * (1 - lift / 30))
        ellipse(68, 124, 30 - lift * 0.6, 3.5)(ctx)
        ctx.fill()
        for r, a in ((52, 0.10), (46, 0.14), (40, 0.18)):
            ctx.set_source_rgba(*AURA, a * glow)
            ellipse(68, 76 - lift, r + 2 * math.sin(phase * 2 * math.pi), r + 6)(ctx)
            ctx.fill()
        paint(surface, calm, dy=-round(lift))
        ctx = context(surface)
        for k in range(4):
            a = phase * 2 * math.pi + k * math.pi / 2
            sparkle(ctx, 68 + 50 * math.cos(a), 70 - lift + 18 * math.sin(a),
                    3.5 if math.sin(a) > 0 else 2.5, GOLD if k % 2 else MINT_SHINE)
        return surface

    frames = [(SITTING, 400), (close_eyes(sit, 0.5), 250), (calm, 400)]
    frames += [(floating(lift, k / 16, k / 4), 110) for k, lift in enumerate((2, 4, 6, 8))]
    frames += [(floating(10 + 3 * math.sin(k / 16 * 2 * math.pi), k / 16), 120) for k in range(32)]
    frames += [(floating(lift, k / 16, 1 - k / 4), 110) for k, lift in enumerate((8, 6, 4, 2))]
    frames += [(calm, 300), (close_eyes(sit, 0.5), 150), (SITTING, 500)]
    return [("zen", "states", frames, ONE_SHOT)]


DISCO_LIGHTS = ((1.0, 0.35, 0.70), (0.35, 0.85, 1.0), (1.0, 0.85, 0.25), (0.55, 1.0, 0.55), (0.75, 0.50, 1.0))
DISCO_BALL = (112, 15)


def disco_ball(ctx, cx, cy, phase):
    ctx.set_source_rgb(0.2, 0.2, 0.2)
    ctx.set_line_width(1)
    ctx.move_to(cx, 0)
    ctx.line_to(cx, cy - 9)
    ctx.stroke()
    filled(ctx, (0.62, 0.64, 0.70), circle(cx, cy, 9.5), 2)
    ctx.save()
    circle(cx, cy, 9.5)(ctx)
    ctx.clip()
    rng = random.Random(phase)
    for row in range(-3, 3):
        for col in range(-3, 3):
            shade = rng.choice((0.55, 0.7, 0.85, 1.0))
            ctx.set_source_rgb(shade, shade, min(1, shade + 0.08))
            ctx.rectangle(cx + col * 3.4 + 0.4 + (phase % 2) * 1.7, cy + row * 3.4 + 0.4, 2.8, 2.8)
            ctx.fill()
    ctx.restore()
    ctx.set_source_rgb(*OUTLINE)
    ctx.set_line_width(2)
    ctx.arc(cx, cy, 9.5, 0, 2 * math.pi)
    ctx.stroke()
    sparkle(ctx, cx - 4, cy - 4, 3, (1, 1, 1))


def club_lights(surface, phase):
    ctx = cairo.Context(surface)
    ctx.set_operator(cairo.OPERATOR_ATOP)
    ctx.set_source_rgba(*DISCO_LIGHTS[phase % len(DISCO_LIGHTS)], 0.10)
    ctx.paint()
    rng = random.Random(100 + phase)
    for k in range(5):
        x, y = rng.uniform(40, 96), rng.uniform(16, 120)
        ctx.set_source_rgba(*DISCO_LIGHTS[(k + phase) % len(DISCO_LIGHTS)], 0.85)
        ctx.arc(x, y, 2.4, 0, 2 * math.pi)
        ctx.fill()
        ctx.set_source_rgba(1, 1, 1, 0.8)
        ctx.arc(x - 0.6, y - 0.6, 0.9, 0, 2 * math.pi)
        ctx.fill()


def disco(kit):
    stand = kit.sprite(STANDING)
    groovy = close_eyes(stand, 0.4)

    def dancer(base, lean, phase, drop=0):
        body = shear(base, lean) if lean else copy(base)
        surface, ctx = blank()
        if drop == 0:
            club_lights(body, phase)
            rng = random.Random(200 + phase)
            for k in range(6):
                ctx.set_source_rgba(*DISCO_LIGHTS[(k + 2 * phase) % len(DISCO_LIGHTS)], 0.8)
                ctx.arc(rng.uniform(2, 126), rng.uniform(4, 124), 1.8, 0, 2 * math.pi)
                ctx.fill()
        paint(surface, body)
        disco_ball(context(surface), DISCO_BALL[0], DISCO_BALL[1] - drop, phase)
        return surface

    frames = [(dancer(stand, 0, 0, drop), 70) for drop in (30, 20, 10, 4, 0)]
    frames.append((dancer(move_eyes(stand, 3, -3), 0, 0), 500))
    frames += [(dancer(groovy, lean, k), 190) for k, lean in enumerate((0, -0.06, 0, 0.06) * 6)]
    frames.append((dancer(stand, 0, 0), 300))
    frames += [(dancer(stand, 0, 0, drop), 70) for drop in (4, 10, 20, 30)]
    frames.append((STANDING, 400))
    return [("disco", "states", frames, ONE_SHOT)]


NEON = (1.0, 0.27, 0.71)
NEON_FILL = (0.24, 0.06, 0.17)
NEON_TEXT = (1.0, 0.94, 0.99)
NEON_GLOW = (0.77, 0.50, 0.67)
HOLDING_SIGN = (51, 52, 53)
OLD_SIGN_BOX = (20, 79, 66, 36)
SIGN_FLICKER = ((51, 1.0), (51, 0.2), (51, 1.0), (52, 1.0), (53, 1.0), (52, 1.0), (53, 1.0), (51, 0.4), (51, 1.0), (51, 1.0))


def neon_sign(ctx, lines, box, lit=1.0):
    x, y, w, h = box
    ctx.save()
    rounded_rect(x - 1.5, y - 1.5, w + 3, h + 3, 4.5)(ctx)
    ctx.set_source_rgba(*NEON, 0.35 * lit)
    ctx.set_line_width(3)
    ctx.stroke()
    rounded_rect(x, y, w, h, 3.5)(ctx)
    ctx.set_source_rgb(*NEON_FILL)
    ctx.fill_preserve()
    ctx.set_source_rgba(*NEON, 0.5 + 0.5 * lit)
    ctx.set_line_width(2)
    ctx.stroke()
    ctx.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    ctx.set_font_size(11)
    line_height = h / len(lines)
    for n, text in enumerate(lines):
        extents = ctx.text_extents(text)
        ctx.save()
        text_at(ctx, text, x + (w - extents.width) / 2 - extents.x_bearing,
                y + line_height * n + (line_height - extents.height) / 2 - extents.y_bearing)
        ctx.set_source_rgba(*NEON_GLOW, 0.8 * lit)
        ctx.set_line_width(2.2)
        ctx.stroke_preserve()
        ctx.set_source_rgba(*NEON_TEXT, 0.55 + 0.45 * lit)
        ctx.fill()
        ctx.restore()
    ctx.restore()


def signs(kit):
    bare = {}
    for index in HOLDING_SIGN:
        bare[index] = copy(kit.sprite(index))
        erase(bare[index], sign_pixels(kit.sprite(index), OLD_SIGN_BOX))

    def holding(lines, box):
        return [(frame_of(bare[index], lambda c, lit=lit: neon_sign(c, lines, box, lit)), 110)
                for index, lit in SIGN_FLICKER] * 2

    return [("sign_effort", "states", holding(("MAXIMUM", "EFFORT!"), (14, 81, 80, 34)), ONE_SHOT),
            ("sign_nailed", "states", holding(("NAILED", "IT!"), (19, 81, 70, 34)), ONE_SHOT)]


def chimichanga(ctx, right_x, right_y, length=CHIMI_LENGTH, angle=CHIMI_TILT, bitten=False):
    r = CHIMI_THICK / 2
    left = -length
    tip = left if bitten else left + r

    def body(c):
        c.new_sub_path()
        c.move_to(tip, -r)
        c.curve_to(left + length * 0.4, -r - 1.2, -length * 0.4, -r - 1.2, -r, -r)
        c.arc(-r, 0, r, -math.pi / 2, math.pi / 2)
        c.curve_to(-length * 0.4, r + 1.2, left + length * 0.4, r + 1.2, tip, r)
        if bitten:
            c.arc_negative(left, r / 2, r / 2, math.pi / 2, -math.pi / 2)
            c.arc_negative(left + 0.5, -r / 2, r / 2 - 0.3, math.pi / 2, -math.pi / 2)
        else:
            c.arc(left + r, 0, r, math.pi / 2, 3 * math.pi / 2)
        c.close_path()

    ctx.save()
    ctx.translate(right_x, right_y)
    ctx.rotate(math.radians(angle))
    ctx.save()
    body(ctx)
    ctx.clip()
    ctx.set_source_rgb(*TORTILLA)
    ctx.paint()
    ctx.set_source_rgb(*CRISP)
    for x, y, rx in ((0.25, 2.2, 1.6), (0.45, -1.0, 1.2), (0.62, 2.6, 1.4), (0.8, 0.2, 1.1), (0.33, -3.3, 1.0)):
        ellipse(-length * x, y, rx, rx * 0.6)(ctx)
        ctx.fill()
    ctx.set_source_rgb(*TORTILLA_SHINE)
    ctx.set_line_width(1.6)
    ctx.move_to(left + 4, -r + 2)
    ctx.line_to(-r - 1, -r + 2)
    ctx.stroke()
    ctx.set_source_rgb(*CRISP)
    ctx.set_line_width(1.3)
    for x in (-r - 3, -r + 0.5):
        ctx.move_to(x, -r)
        ctx.curve_to(x - 2.5, -1, x - 2.5, 1, x, r)
        ctx.stroke()
    if bitten:
        ctx.set_source_rgb(*FILLING)
        ctx.rectangle(left - 1, -r, r / 2 + 4.5, CHIMI_THICK)
        ctx.fill()
        for color, x, y, size in ((CHEESE, 2.6, -2.8, 1.3), (CHEESE, 3.4, 1.0, 1.2), (SALSA, 1.6, -0.6, 1.0),
                                  (CHEESE, 2.0, 3.6, 1.0)):
            ctx.set_source_rgb(*color)
            circle(left + x + 1, y, size)(ctx)
            ctx.fill()
    ctx.restore()
    body(ctx)
    ctx.set_source_rgb(*OUTLINE)
    ctx.set_line_width(2)
    ctx.stroke()
    ctx.restore()


def crumbs(ctx, cx, cy, spread, seed):
    rnd = random.Random(seed)
    for _ in range(6):
        a = rnd.uniform(math.pi * 0.9, math.pi * 2.1)
        d = rnd.uniform(4, spread)
        filled(ctx, rnd.choice((TORTILLA, CRISP)), circle(cx + d * math.cos(a), cy + d * math.sin(a),
                                                         rnd.uniform(0.9, 1.6)), 0.8)


def chimichanga_snack(kit):
    stand = kit.sprite(STANDING)
    cheeks = without_confetti(kit.sprite(HANDS_AT_CHEEKS))

    def munching(bites, draw=None, bounce=0):
        surface = copy(cheeks)
        if bites <= 3:
            chimichanga(context(surface), CHIMI_HELD[0], CHIMI_HELD[1] + bounce, CHIMI_LENGTH - BITE * bites,
                        bitten=bites > 0)
        return frame_of(surface, draw)

    def treasure(ctx, size):
        burst(ctx, *CHIMI_ON_BELT, 8 + 6 * size, 14 + 8 * size, range(0, 360, 30), GOLD, 2)
        chimichanga(ctx, CHIMI_ON_BELT[0] + 19 * size, CHIMI_ON_BELT[1] - 7 * size, CHIMI_LENGTH * size, -20)
        sparkle(ctx, 22, 80, 3 + 2 * size)
        sparkle(ctx, 54, 104, 2 + 2 * size)

    frames = [(STANDING, 300),
              (frame_of(move_eyes(stand, -2, 3), lambda c: treasure(c, 0.6)), 250),
              (frame_of(move_eyes(stand, -2, 2), lambda c: (treasure(c, 1.0), exclamation(c, 26, 16))), 450),
              (munching(0), 350)]
    for bite in range(1, 4):
        at = (MOUTH[0] + 4 * bite, MOUTH[1])
        frames += [(munching(bite, lambda c, b=bite, at=at: (outlined_text(c, "NOM!", 2 + 4 * b, 36 - 3 * b, 11),
                                                              crumbs(c, *at, 14, b))), 220),
                   (munching(bite, lambda c, b=bite, at=at: crumbs(c, at[0], at[1] + 10, 10, b + 10), 1), 180),
                   (munching(bite, lambda c, b=bite, at=at: crumbs(c, at[0], at[1] + 18, 8, b + 20)), 180)]
    content = close_eyes(stand, 0.6)
    frames += [(munching(4, lambda c: (outlined_text(c, "GULP!", 4, 30, 11), crumbs(c, MOUTH[0] + 8, MOUTH[1] + 14, 12, 40))), 350),
               (frame_of(content, lambda c: outlined_text(c, "BURP!", 2, 30, 12)), 700),
               (content, 400),
               (STANDING, 300)]
    return [("chimichanga", "states", frames, ONE_SHOT)]


def animations(kit):
    return [*fourth_wall(kit), *zen(kit), *disco(kit), *chimichanga_snack(kit), *signs(kit)]
