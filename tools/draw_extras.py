import math

import cairo

import draw_finger_gun as finger_gun
from sprite_kit import *

STANDING = 1
SITTING = 11
DANGLING = 5
TYPING = (47, 48)
SITTING_NECK = 92
STANDING_NECK = 74
ONE_SHOT = {"loop": False, "loops": 1, "next": "idle"}
LOOK_X = {-1: -3, 0: 0, 1: 3}
LOOK_Y = {-1: -3, 0: 0, 1: 2}
LOOK_DIRECTIONS = tuple((dx, dy) for dy in (-1, 0, 1) for dx in (-1, 0, 1))


def head_nod(base, neck_y, drop):
    surface, _ = blank()
    paint(surface, crop_rows(base, neck_y, SIZE))
    paint(surface, crop_rows(base, 0, neck_y), dx=-(drop // 2), dy=drop)
    return surface


def nap(kit):
    sit = kit.sprite(SITTING)
    sleepy = close_eyes(sit, 0.85)
    nods = [head_nod(sleepy, SITTING_NECK, drop) for drop in (0, 1, 2)]
    nose = [(40, 83), (40, 84), (40, 85)]
    falling_asleep = [(SITTING, 400), (close_eyes(sit, 0.5), 450), (sleepy, 500)]

    breathing = []
    for step, (pose, radius) in enumerate(((0, 2), (1, 3.5), (2, 5), (2, 6), (1, 4.5), (0, 3)) * 2):
        def draw(ctx, pose=pose, radius=radius, phase=step / 12):
            nose_bubble(ctx, *nose[pose], radius)
            zzz(ctx, (46, 34), phase)
        breathing.append((frame_of(nods[pose], draw), 300))

    def startled(ctx):
        exclamation(ctx, 26, 16)
        burst(ctx, 72, 40, 40, 46, (240, 270, 300, 330), MARK_RED, 2)
    jump, _ = blank()
    paint(jump, sit, dy=-6)
    waking = [
        (frame_of(nods[2], lambda c: (nose_bubble(c, *nose[2], 8.5), zzz(c, (46, 34), 0.0))), 350),
        (frame_of(nods[2], lambda c: burst(c, 40, 85, 6, 11, range(0, 360, 45))), 110),
        (frame_of(jump, startled), 160),
        (frame_of(sit, lambda c: exclamation(c, 30, 22)), 450),
        (SITTING, 500),
    ]
    return [
        ("nap_start", "states", falling_asleep, {"loop": False, "loops": 1, "next": "napping"}),
        ("napping", "states", breathing, {}),
        ("nap_wake", "states", waking, ONE_SHOT),
    ]


def laptop_doze(kit):
    typing = [kit.sprite(index) for index in TYPING]
    heavy = close_eyes(typing[0], 0.5)
    sleepy = close_eyes(typing[0], 0.85)
    frames = [(TYPING[0], 300), (heavy, 500), (TYPING[0], 250), (heavy, 400), (sleepy, 500)]
    for step, drop in enumerate((1, 2, 1, 2, 3, 2, 3, 4)):
        frames.append((frame_of(head_nod(sleepy, SITTING_NECK, drop), lambda c, s=step: zzz(c, (46, 34), s / 8)), 320))
    bonk = head_nod(sleepy, SITTING_NECK, 6)
    frames.append((frame_of(bonk, lambda c: (star(c, 30, 84, 4.5), star(c, 22, 76, 3, spin=20))), 160))
    frames.append((frame_of(head_nod(typing[0], SITTING_NECK, -3), lambda c: exclamation(c, 30, 16)), 220))
    frames.append((frame_of(typing[0], lambda c: exclamation(c, 30, 16)), 250))
    frames += [(TYPING[step % 2], 110) for step in range(8)]
    frames.append((TYPING[0], 600))
    return [("laptop_doze", "states", frames, {"loop": False, "loops": 1, "next": "working"})]


def fly_sprite(ctx, x, y, flap):
    ctx.save()
    ctx.translate(x, y)
    ctx.scale(1.35, 1.35)
    ctx.translate(-x, -y)
    for side in (-1, 1):
        ctx.save()
        ctx.translate(x + side * 1.2, y - 2.2)
        ctx.rotate(math.radians(side * (40 if flap else 12)))
        ctx.scale(2.0, 3.4)
        ctx.arc(0, -0.7, 1, 0, 2 * math.pi)
        ctx.restore()
        ctx.set_source_rgba(0.85, 0.95, 1.0, 0.9)
        ctx.fill_preserve()
        ctx.set_source_rgb(0.15, 0.15, 0.15)
        ctx.set_line_width(0.8)
        ctx.stroke()
    filled(ctx, (0.12, 0.12, 0.14), ellipse(x, y, 2.6, 2.0), 1.0)
    filled(ctx, (0.12, 0.12, 0.14), circle(x - 2.6, y - 0.4, 1.3), 0.8)
    ctx.restore()


def gaze(base, target, ref, reach=(3, 4)):
    vx, vy = target[0] - ref[0], target[1] - ref[1]
    norm = math.hypot(vx, vy) or 1
    return move_eyes(base, round(reach[0] * vx / norm), round(reach[1] * vy / norm))


def bezier(start, control, end, steps):
    return [((1 - t) ** 2 * start[0] + 2 * (1 - t) * t * control[0] + t ** 2 * end[0],
             (1 - t) ** 2 * start[1] + 2 * (1 - t) * t * control[1] + t ** 2 * end[1])
            for t in (k / steps for k in range(1, steps + 1))]


def fly_gag(kit):
    sit = kit.sprite(SITTING)
    gun = finger_gun.build(kit.img_dir)
    shift_x, shift_y = finger_gun.HEAD_SHIFT

    def open_eyes(frame):
        surface = copy(frame)
        paint(surface, crop_rects(sit, finger_gun.EYE_PATCHES), dx=-shift_x, dy=-shift_y)
        return surface

    def with_fly(base, fly, ms, extra=None):
        return frame_of(base, lambda c: (fly(c), extra and extra(c))), ms, frame_of(blank()[0], fly)

    def buzz(base, ref, positions, ms, first_flap=0):
        return [with_fly(gaze(base, p, ref), lambda c, p=p, k=k: fly_sprite(c, *p, (k + first_flap) % 2), ms)
                for k, p in enumerate(positions)]

    eye_ref = (70, 66)
    gun_eye_ref = (eye_ref[0] - shift_x, eye_ref[1] - shift_y)
    loop = [(68 + 48 * math.cos(t), 30 + 16 * math.sin(2 * t)) for t in (k / 26 * 2 * math.pi for k in range(26))]
    hover = (16, 74)
    frames = buzz(sit, eye_ref, bezier((140, -6), (132, 14), loop[0], 4), 75)
    frames += buzz(sit, eye_ref, loop, 75)
    frames += buzz(sit, eye_ref, bezier(loop[-1], (64, -12), hover, 10), 75)
    frames += buzz(sit, eye_ref, [(hover[0] + k % 2, hover[1] - k % 3) for k in range(5)], 90)
    for k, (name, ms) in enumerate((("draw_low", 80), ("draw_mid", 70), ("aimed", 500), ("flag_peek", 60), ("flag_half", 60))):
        frames += buzz(open_eyes(gun[name]), gun_eye_ref, [(hover[0], hover[1] - k % 2)], ms, k)
    popped = gaze(open_eyes(gun["flag_pop"]), (14, 60), gun_eye_ref)
    frames.append(with_fly(popped, lambda c: fly_sprite(c, 14, 62, 1), 200,
                           lambda c: outlined_text(c, "!", 10, 56, 9, width=2.4)))
    flag = open_eyes(gun["flag"])
    landing = (78, 26)
    frames += buzz(flag, gun_eye_ref, bezier((14, 62), (30, 0), landing, 8), 110)
    unimpressed = close_eyes(move_eyes(flag, 1, -4), 0.45)
    frames += [with_fly(unimpressed, lambda c, k=k: fly_sprite(c, *landing, k in (2, 3)), 280) for k in range(6)]
    frames += buzz(close_eyes(flag, 0.45), gun_eye_ref, bezier(landing, (100, 0), (140, -8), 5), 90)
    frames.append((flag, 400))
    return [("fly_gag", "states", frames, ONE_SHOT)]


HEADPHONE_BAND = (0.18, 0.18, 0.20)
HEADPHONE_CUP = (0.32, 0.32, 0.36)
HEADPHONE_SHINE = (0.58, 0.58, 0.64)
NOTE_COLORS = (MINT, (1.0, 0.62, 0.80), GOLD)
CABLE = (0.30, 0.30, 0.34)
CABLE_PATH = ((76, 95), (90, 91), (104, 76), (102, 56))
WALKMAN_ON_BELT = (64, 93)
WALKMAN_SILVER = (0.80, 0.83, 0.88)
WALKMAN_BLUE = (0.24, 0.42, 0.78)
WALKMAN_BUTTON = (1.0, 0.55, 0.15)
CASSETTE_WINDOW = (0.12, 0.12, 0.14)
TAPE = (0.50, 0.30, 0.18)


def walkman(ctx, x, y):
    filled(ctx, WALKMAN_SILVER, rounded_rect(x, y, 13, 17, 2.2), 2.2)
    ctx.set_source_rgb(*WALKMAN_BLUE)
    ctx.rectangle(x + 1.5, y + 10.5, 10, 5)
    ctx.fill()
    filled(ctx, CASSETTE_WINDOW, rounded_rect(x + 2.5, y + 3.5, 8, 5, 1), 0.8)
    ctx.set_source_rgb(*TAPE)
    ctx.rectangle(x + 3.2, y + 5.2, 6.6, 1.6)
    ctx.fill()
    ctx.set_source_rgb(*WALKMAN_BUTTON)
    for button_x in (x + 1.6, x + 5.6):
        ctx.rectangle(button_x, y - 1.8, 2.6, 2)
    ctx.fill()


def headphone_cable(ctx):
    start, bend_low, bend_high, end = CABLE_PATH
    for width, color in ((2.6, OUTLINE), (1.0, CABLE)):
        ctx.set_source_rgb(*color)
        ctx.set_line_width(width)
        ctx.move_to(*start)
        ctx.curve_to(*bend_low, *bend_high, *end)
        ctx.stroke()


def listening_gear(base):
    surface, _ = blank()
    filled(context(surface), HEADPHONE_CUP, ellipse(36, 44, 5, 8, -10))
    paint(surface, base)
    ctx = context(surface)
    headphone_cable(ctx)
    for width, color in ((7, OUTLINE), (3, HEADPHONE_BAND)):
        ctx.set_source_rgb(*color)
        ctx.set_line_width(width)
        ctx.arc(68, 44, 35, math.radians(196), math.radians(338))
        ctx.stroke()
    filled(ctx, HEADPHONE_BAND, ellipse(100, 46, 5, 10, 8))
    filled(ctx, HEADPHONE_CUP, ellipse(102, 46, 5, 10, 8))
    ctx.set_source_rgb(*HEADPHONE_SHINE)
    ctx.set_line_width(1.6)
    ctx.arc(102, 46, 5.5, math.radians(200), math.radians(250))
    ctx.stroke()
    walkman(ctx, *WALKMAN_ON_BELT)
    return surface


def music_notes(ctx, phase):
    for k, glyph in enumerate(("♪", "♫", "♪")):
        t = (phase + k / 3) % 1.0
        alpha = 1.0 if t < 0.7 else (1 - t) / 0.3
        outlined_text(ctx, glyph, 104 + 12 * t + 3 * math.sin(t * 9), 44 - 38 * t, 12 + 3 * t,
                      fill=NOTE_COLORS[k], width=2.4, alpha=alpha)


def vibing(kit):
    dressed = listening_gear(kit.sprite(STANDING))
    leans = {-1: shear(dressed, -0.06), 0: dressed, 1: shear(dressed, 0.06)}
    bob, _ = blank()
    paint(bob, dressed, dy=1)
    frames = []
    for k, lean in enumerate((0, -1, 0, 1) * 4):
        base = bob if k % 4 == 2 else leans[lean]
        frames.append((frame_of(base, lambda c, k=k: music_notes(c, k / 16)), 210))
    return [("vibing", "states", frames, {"loop": False, "loops": 3, "next": "idle"})]


UNICORN_WHITE = (0.99, 0.98, 1.0)
UNICORN_SHADE = (0.86, 0.84, 0.95)
MANE = ((1.0, 0.55, 0.78), (0.72, 0.55, 1.0), (0.55, 0.80, 1.0))
HOOF = (0.70, 0.62, 0.92)
BLUSH = (1.0, 0.62, 0.72)
RIDER_SHIFT = (2, -7)
RIDER_FRONT_LEG = ((0, 100, 70, 14), (0, 114, 62, 14))
RIDER_BACK_FOOT = (62, 114, 66, 14)


def unicorn_leg(x, top, angle, length=13):
    def shape(c):
        c.save()
        c.translate(x, top)
        c.rotate(math.radians(angle))
        c.move_to(-3.5, 0)
        c.line_to(-3.5, length - 3)
        c.arc(0, length - 3, 3.5, math.pi, 0)
        c.line_to(3.5, 0)
        c.close_path()
        c.restore()
    return shape


def hoof(ctx, x, top, angle, length=13):
    ctx.save()
    ctx.translate(x, top)
    ctx.rotate(math.radians(angle))
    ctx.rectangle(-3.5, length - 4, 7, 4)
    ctx.restore()
    ctx.set_source_rgb(*HOOF)
    ctx.fill()


def unicorn_tail(ctx, by, sway):
    for i, color in enumerate(MANE):
        start = (97, by - 7 + i * 3)
        controls = ((108, by - 15 + i * 4), (118, by - 3 + i * 3 + sway))
        tip = (116, by + 9 + i * 4 + sway)
        for width, shade in ((7.5, OUTLINE), (4.5, color)):
            ctx.set_source_rgb(*shade)
            ctx.set_line_width(width)
            ctx.move_to(*start)
            ctx.curve_to(*controls[0], *controls[1], *tip)
            ctx.stroke()


def unicorn_face(ctx, by):
    mane = [circle(34 + i * 3.4, by - 33 + i * 5.2, 5.2) for i in range(6)]
    silhouette(ctx, mane, MANE[0], 1.3)
    ctx.set_source_rgb(*MANE[1])
    for i in range(0, 6, 2):
        ctx.arc(34 + i * 3.4, by - 33 + i * 5.2, 3, 0, 2 * math.pi)
        ctx.fill()
    filled(ctx, MANE[1], circle(29, by - 33, 4.5), 1.3)
    filled(ctx, GOLD, lambda c: (c.move_to(21, by - 32), c.line_to(13, by - 52), c.line_to(27, by - 33), c.close_path()), 1.8)
    ctx.set_source_rgb(0.85, 0.6, 0.1)
    ctx.set_line_width(1.2)
    for k in range(2):
        ctx.move_to(17 + k * 2.2, by - 38 - k * 6)
        ctx.line_to(24 - k * 1.2, by - 36 - k * 6)
    ctx.stroke()
    filled(ctx, (0.08, 0.08, 0.1), ellipse(20, by - 22, 2.3, 3.3), 0.6)
    ctx.set_source_rgb(1, 1, 1)
    ctx.arc(19.2, by - 23.4, 1, 0, 2 * math.pi)
    ctx.fill()
    ctx.set_source_rgba(*BLUSH, 0.85)
    ellipse(24, by - 15, 3.4, 2)(ctx)
    ctx.fill()
    ctx.set_source_rgb(*OUTLINE)
    ctx.arc(7, by - 16, 0.9, 0, 2 * math.pi)
    ctx.fill()
    ctx.set_line_width(1.1)
    ctx.arc(12, by - 13, 3, math.radians(30), math.radians(110))
    ctx.stroke()


def saddle(ctx, by):
    filled(ctx, SUIT_RED, lambda c: (c.move_to(60, by - 11), c.line_to(90, by - 11),
                                     c.curve_to(93, by - 2, 91, by + 4, 87, by + 5),
                                     c.line_to(64, by + 5), c.curve_to(60, by + 4, 58, by - 2, 60, by - 11),
                                     c.close_path()), 1.8)
    filled(ctx, SUIT_RED, circle(82, by - 3, 4.5), 1.4)
    ctx.set_source_rgb(*OUTLINE)
    ctx.arc(82, by - 3, 2.4, 0, 2 * math.pi)
    ctx.fill()
    ctx.rectangle(81.3, by - 7, 1.4, 8)
    ctx.fill()


def unicorn_frame(kit, stride):
    lift = (0, 2, 0)[stride]
    front, back = ((22, -22), (0, 0), (-18, 18))[stride]
    by = 106 - lift
    rider = copy(kit.sprite(DANGLING))
    rider_ctx = cairo.Context(rider)
    rider_ctx.set_operator(cairo.OPERATOR_CLEAR)
    rider_ctx.rectangle(*RIDER_BACK_FOOT)
    rider_ctx.fill()
    front_leg = crop_rects(kit.sprite(DANGLING), RIDER_FRONT_LEG)

    surface, _ = blank()
    ctx = context(surface)
    ctx.set_line_width(2)
    ctx.set_source_rgba(1, 1, 1, 0.85)
    for y, length in ((40, 12), (52, 18), (64, 10)):
        x = 108 + stride * 2
        ctx.move_to(x, y)
        ctx.line_to(min(x + length, 126), y)
    ctx.stroke()
    unicorn_tail(ctx, by, (0, 4, -2)[stride])
    for x, angle in ((54, front), (88, back)):
        silhouette(ctx, [unicorn_leg(x, by + 6, -angle)], UNICORN_SHADE, 1.3)
        hoof(ctx, x, by + 6, -angle)
    paint(surface, rider, dx=RIDER_SHIFT[0], dy=RIDER_SHIFT[1] - lift)

    ctx = context(surface)
    body = [ellipse(74, by, 26, 11.5),
            ellipse(46, by - 8, 9, 13, 30),
            ellipse(25, by - 22, 14, 11.5),
            ellipse(13, by - 15, 8.5, 7, 10),
            lambda c: (c.move_to(29, by - 32), c.line_to(36, by - 40), c.line_to(37, by - 29), c.close_path())]
    body += [unicorn_leg(x, by + 6, angle) for x, angle in ((62, front), (94, back))]
    silhouette(ctx, body, UNICORN_WHITE, 1.3)
    for x, angle in ((62, front), (94, back)):
        hoof(ctx, x, by + 6, angle)
    unicorn_face(ctx, by)
    saddle(ctx, by)
    paint(surface, front_leg, dx=RIDER_SHIFT[0], dy=RIDER_SHIFT[1] - lift)

    ctx = context(surface)
    ctx.set_source_rgba(0.85, 0.85, 0.85, 0.9)
    for i in range(stride + 1):
        ctx.arc(122 - i, 124 - i * 2, 2 + 0.8 * i, 0, 2 * math.pi)
        ctx.fill()
    return surface


def unicorn(kit):
    return [("unicorn", "moves", [(unicorn_frame(kit, stride), 110) for stride in range(3)], {})]


def head_pop(kit):
    stand = kit.sprite(STANDING)
    body = crop_rows(stand, STANDING_NECK, SIZE)
    head = crop_rows(stand, 0, STANDING_NECK)
    pivot = (68, 42)

    def pose(lift, spin=0, dx=0, squash=1.0, extra=None):
        surface, _ = blank()
        paint(surface, body)
        if squash != 1.0:
            ctx = cairo.Context(surface)
            ctx.translate(pivot[0], STANDING_NECK)
            ctx.scale(2 - squash, squash)
            ctx.translate(-pivot[0], -STANDING_NECK)
            ctx.set_source_surface(head, 0, 0)
            ctx.paint()
        else:
            paint(surface, head, dx=dx, dy=-lift, rotate=spin, pivot=pivot, smooth=spin % 360 != 0)
        if extra:
            extra(context(surface))
        return surface

    def dizzy(phase):
        def draw(ctx):
            for k in range(3):
                a = phase + k * 2 * math.pi / 3
                star(ctx, 68 + 26 * math.cos(a), 8 + 5 * math.sin(a), 4 if math.sin(a) > 0 else 3, spin=phase * 50)
        return draw

    frames = [(STANDING, 300)]
    frames += [(pose(0, dx=dx), 60) for dx in (1, -1, 1, -1)]
    frames.append((pose(4, extra=lambda c: burst(c, 68, 76, 6, 12, (200, 230, 310, 340))), 90))
    frames += [(pose(lift, spin), 65) for lift, spin in ((8, 40), (10, 100), (10, 170), (10, 240), (8, 300), (4, 345))]
    frames.append((pose(0, squash=0.92), 90))
    frames += [(frame_of(stand, dizzy(k * 0.6)), 120) for k in range(10)]
    frames.append((STANDING, 400))
    return [("head_pop", "states", frames, ONE_SHOT)]


TELEPORT_GLOW = (0.6, 0.95, 1.0)
BUCKLE = (64, 100)


def teleport(kit):
    stand = kit.sprite(STANDING)

    def scene(visible=True, draw=None):
        surface, _ = blank()
        if visible:
            paint(surface, stand)
        if draw:
            draw(context(surface))
        return surface

    def puff(size, spread=1.0, shrink=1.0, alpha=1.0, rise=0):
        def draw(c):
            c.push_group()
            cloud(c, 66, 72 - rise, size, spread, shrink)
            c.pop_group_to_source()
            c.paint_with_alpha(alpha)
        return draw

    def beep(size):
        return lambda c: (sparkle(c, *BUCKLE, size, TELEPORT_GLOW),
                          burst(c, *BUCKLE, 6, 9, (200, 250, 290, 340), TELEPORT_GLOW, 1.4))

    vanish = [(STANDING, 300)] + [(scene(draw=beep(size)), 120) for size in (5, 3, 5)]
    vanish += [(scene(draw=puff(14)), 70), (scene(False, puff(26)), 90),
               (scene(False, puff(30, 1.1, 0.95, 0.9, 4)), 90),
               (scene(False, puff(30, 1.25, 0.8, 0.65, 10)), 90),
               (scene(False, puff(30, 1.4, 0.6, 0.35, 16)), 300)]
    appear = [(scene(False, puff(14)), 70), (scene(False, puff(28)), 90),
              (scene(draw=puff(30, 1.1, 0.95, 0.9, 4)), 90),
              (scene(draw=puff(30, 1.25, 0.8, 0.6, 10)), 90),
              (scene(draw=puff(30, 1.4, 0.6, 0.3, 16)), 90),
              (scene(draw=lambda c: (sparkle(c, 28, 30, 5), sparkle(c, 104, 52, 4))), 250),
              (STANDING, 300)]
    return [
        ("teleport_out", "states", vanish, {"loop": False, "loops": 1, "next": "teleport_in"}),
        ("teleport_in", "states", appear, ONE_SHOT),
    ]


def looks(kit):
    poses = {}
    for pose in (STANDING, SITTING):
        base = kit.sprite(pose)
        blobs = eye_blobs(base)
        eyes = (sum(b[0] + b[2] for b in blobs) / (2 * len(blobs)), sum(b[1] + b[3] for b in blobs) / (2 * len(blobs)))
        frames = [pose if (dx, dy) == (0, 0) else move_eyes(base, LOOK_X[dx], LOOK_Y[dy], blobs)
                  for dx, dy in LOOK_DIRECTIONS]
        poses[pose] = {"eyes": eyes, "frames": frames}
    return poses


def animations(kit):
    return [*nap(kit), *laptop_doze(kit), *fly_gag(kit), *vibing(kit), *unicorn(kit), *head_pop(kit), *teleport(kit)]
