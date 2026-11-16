import math
import random

import cairo

import draw_finger_gun as finger_gun
from draw_extras import ONE_SHOT, SITTING, STANDING
from sprite_kit import *

STRAW = (0.96, 0.82, 0.46)
STRAW_DARK = (0.78, 0.58, 0.26)
BAND_GREEN = (0.10, 0.58, 0.32)
FLASH = (1.0, 0.86, 0.30)
FLASH_CORE = (1.0, 0.98, 0.85)
NEAR_SHOULDER = finger_gun.SHOULDER
FAR_SHOULDER = (84, 101)
MUZZLE = (31, 95)
HAT = (75, 40)
GUNS_UP = 28
RECOIL = 8


def sombrero(ctx, cx, cy, squash=1.0):
    ctx.save()
    ctx.translate(cx, cy)
    ctx.rotate(math.radians(-4))
    ctx.scale(1.0 / squash ** 0.5, squash)
    filled(ctx, STRAW, ellipse(0, 0, 52, 10), 2.4)
    ctx.set_source_rgb(*STRAW_DARK)
    ctx.set_line_width(1.4)
    ellipse(0, -0.5, 44, 7)(ctx)
    ctx.stroke()
    for k in range(18):
        a = math.radians(8 + k * 9.6)
        ctx.set_source_rgb(*(MARK_RED if k % 2 else BAND_GREEN))
        ctx.arc(49 * math.cos(a), 9.4 * math.sin(a) + 1.2, 1.8, 0, 2 * math.pi)
        ctx.fill()
    crown = lambda c: (c.move_to(-29, 1), c.curve_to(-25, -12, -13, -34, 0, -34),
                       c.curve_to(13, -34, 25, -12, 29, 1), c.curve_to(10, 5, -10, 5, -29, 1), c.close_path())
    filled(ctx, STRAW, crown, 2.4)
    ctx.save()
    crown(ctx)
    ctx.clip()
    ctx.set_source_rgb(*BAND_GREEN)
    ctx.rectangle(-30, -8, 60, 9)
    ctx.fill()
    ctx.set_source_rgb(1, 1, 1)
    ctx.set_line_width(1.7)
    for k in range(13):
        x = -30 + k * 5
        ctx.move_to(x, -1.5)
        ctx.line_to(x + 2.5, -6.5)
        ctx.line_to(x + 5, -1.5)
    ctx.stroke()
    ctx.set_source_rgb(*STRAW_DARK)
    ctx.set_line_width(1.3)
    ctx.move_to(-5, -31)
    ctx.curve_to(-11, -20, -12, -14, -11, -9)
    ctx.stroke()
    ctx.restore()
    ctx.set_source_rgb(*OUTLINE)
    ctx.set_line_width(2)
    ctx.move_to(-28.5, -8.5)
    ctx.line_to(28.5, -8.5)
    ctx.stroke()
    ctx.restore()


def muzzle_flash(ctx, x, y, angle):
    ctx.save()
    ctx.translate(x, y)
    ctx.rotate(math.radians(angle))

    def spikes(c):
        for k in range(12):
            a = math.radians(k * 30)
            rx, ry = (11, 8) if k % 2 == 0 else (4.5, 3.5)
            (c.move_to if k == 0 else c.line_to)(rx * math.cos(a) - 5, ry * math.sin(a))
        c.close_path()
    filled(ctx, FLASH, spikes, 1.6)
    ctx.set_source_rgb(*FLASH_CORE)
    ellipse(-5, 0, 4, 2.6)(ctx)
    ctx.fill()
    ctx.restore()


def mariachi(kit):
    _, arm, unarmed = finger_gun.gun_layers(kit.img_dir)
    drop_specks(arm)
    far_arm, ctx = blank()
    ctx.translate(FAR_SHOULDER[0], 0)
    ctx.scale(-1, 1)
    ctx.translate(-NEAR_SHOULDER[0], 0)
    ctx.set_source_surface(arm, 0, 0)
    ctx.paint()
    sit = kit.sprite(SITTING)
    head_x, head_y = finger_gun.HEAD_SHIFT

    def pose(near=None, far=None, hat_dy=0, squash=1.0, flash_near=False, flash_far=False):
        surface, _ = blank()
        if far is not None:
            paint(surface, far_arm, rotate=-far, pivot=FAR_SHOULDER)
        paint(surface, sit if near is None else unarmed)
        if near is not None:
            paint(surface, arm, rotate=near, pivot=NEAR_SHOULDER)
        ctx = context(surface)
        hat_x, hat_y = HAT if near is None else (HAT[0] + head_x, HAT[1] + head_y)
        sombrero(ctx, hat_x, hat_y + hat_dy, squash)
        if flash_near:
            muzzle_flash(ctx, *rotate_point((MUZZLE[0] - 6, MUZZLE[1]), NEAR_SHOULDER, near), near)
        if flash_far:
            far_muzzle = (FAR_SHOULDER[0] + NEAR_SHOULDER[0] - MUZZLE[0] + 6, MUZZLE[1])
            muzzle_flash(ctx, *rotate_point(far_muzzle, FAR_SHOULDER, -far), 180 - far)
        return surface

    up = GUNS_UP
    frames = [(SITTING, 400)]
    frames += [(pose(hat_dy=dy, squash=squash), ms)
               for dy, squash, ms in ((-70, 1, 60), (-46, 1, 60), (-20, 1, 60), (1, 0.88, 80), (-1, 1.04, 80), (0, 1, 300))]
    frames += [(pose(a, a), 70) for a in (-30, 10, 40)]
    frames.append((pose(up, up), 350))
    for _ in range(3):
        frames += [(pose(up + RECOIL, up, flash_near=True), 90), (pose(up, up), 70),
                   (pose(up, up + RECOIL, flash_far=True), 90), (pose(up, up), 70)]
    frames += [(pose(up + RECOIL, up + RECOIL, flash_near=True, flash_far=True), 90), (pose(up, up), 70)] * 2
    frames.append((pose(up, up), 600))
    frames += [(pose(a, a), 70) for a in (20, -20)]
    frames += [(pose(hat_dy=dy), ms) for dy, ms in ((0, 400), (-14, 60), (-36, 60), (-70, 60))]
    frames.append((SITTING, 500))
    return [("mariachi", "states", frames, ONE_SHOT)]


KICK = 37
IMPACT = (24, 94)
GLASS = (0.92, 0.97, 1.0)
WHISTLE = (1.0, 0.62, 0.80)


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
        outlined_text(ctx, glyph, 28 - 14 * t + 2 * math.sin(t * 8), 62 - 40 * t, 13 + 3 * t,
                      fill=WHISTLE, width=2.4, alpha=alpha)


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
              (frame_of(stand, crack), 700)]
    innocent = close_eyes(move_eyes(stand, 2, -3), 0.45)
    frames += [(frame_of(innocent, lambda c, k=k: (crack(c), whistle(c, k / 10))), 200) for k in range(10)]
    frames += [(frame_of(innocent, lambda c, a=alpha: crack(c, alpha=a)), 140) for alpha in (0.7, 0.45, 0.2)]
    frames.append((STANDING, 500))
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


def rounded(ctx, x, y, w, h, r):
    ctx.new_sub_path()
    ctx.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    ctx.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    ctx.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    ctx.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    ctx.close_path()


def neon_sign(ctx, lines, box, lit=1.0):
    x, y, w, h = box
    ctx.save()
    rounded(ctx, x - 1.5, y - 1.5, w + 3, h + 3, 4.5)
    ctx.set_source_rgba(*NEON, 0.35 * lit)
    ctx.set_line_width(3)
    ctx.stroke()
    rounded(ctx, x, y, w, h, 3.5)
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


def animations(kit):
    return [*mariachi(kit), *fourth_wall(kit), *zen(kit), *disco(kit), *signs(kit)]
