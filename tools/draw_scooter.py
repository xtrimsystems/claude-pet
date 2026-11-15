import math
import os
import sys

import cairo

FIRST_INDEX = 54
FRAME_COUNT = 3
RIDER_SPRITE = 11
RIDER_LIFT = 18

OUTLINE = (0, 0, 0)
SUIT_RED = (108 / 255, 0, 0)
MINT = (0.56, 0.87, 0.78)
MINT_SHINE = (0.80, 0.97, 0.92)
TIRE = (0.13, 0.13, 0.13)
HUB = (0.75, 0.75, 0.78)
HEADLIGHT = (1.0, 0.93, 0.55)
LINE_WIDTH = 2.5


def filled(ctx, color, trace, width=LINE_WIDTH):
    trace(ctx)
    ctx.set_source_rgb(*color)
    ctx.fill_preserve()
    ctx.set_source_rgb(*OUTLINE)
    ctx.set_line_width(width)
    ctx.stroke()


def circle(cx, cy, r):
    return lambda c: c.arc(cx, cy, r, 0, 2 * math.pi)


def wheel(ctx, cx, cy, angle):
    filled(ctx, TIRE, circle(cx, cy, 9))
    filled(ctx, HUB, circle(cx, cy, 4.5), 1.5)
    ctx.set_source_rgb(*OUTLINE)
    ctx.set_line_width(1.5)
    for spoke in range(3):
        a = angle + spoke * 2 * math.pi / 3
        ctx.move_to(cx, cy)
        ctx.line_to(cx + 4.5 * math.cos(a), cy + 4.5 * math.sin(a))
    ctx.stroke()


def rear_cowl(c):
    c.move_to(54, 104)
    c.curve_to(62, 96, 100, 94, 112, 104)
    c.curve_to(118, 110, 116, 118, 108, 119)
    c.line_to(60, 119)
    c.curve_to(54, 119, 50, 110, 54, 104)
    c.close_path()


def floorboard(c):
    c.rectangle(30, 110, 32, 8)


def leg_shield(c):
    c.move_to(36, 118)
    c.curve_to(30, 104, 28, 92, 32, 82)
    c.line_to(24, 82)
    c.curve_to(19, 94, 20, 108, 26, 118)
    c.close_path()


def front_fender(c):
    c.move_to(12, 113)
    c.curve_to(14, 103, 32, 103, 34, 113)
    c.line_to(28, 113)
    c.curve_to(26, 108, 20, 108, 18, 113)
    c.close_path()


def handlebar(c):
    c.move_to(20, 76)
    c.line_to(38, 76)
    c.curve_to(41, 76, 41, 84, 38, 84)
    c.line_to(20, 84)
    c.close_path()


def cowl_shine(ctx):
    ctx.set_source_rgb(*MINT_SHINE)
    ctx.set_line_width(2)
    ctx.move_to(66, 101)
    ctx.curve_to(78, 98, 92, 98, 102, 101)
    ctx.stroke()


def deadpool_logo(ctx, cx, cy):
    filled(ctx, SUIT_RED, circle(cx, cy, 5.5), 1.5)
    ctx.set_source_rgb(*OUTLINE)
    ctx.arc(cx, cy, 3, 0, 2 * math.pi)
    ctx.fill()
    ctx.rectangle(cx - 0.75, cy - 5, 1.5, 10)
    ctx.fill()


def arm(ctx, shoulder, hand):
    for color, width in ((OUTLINE, 9), (SUIT_RED, 5)):
        ctx.set_source_rgb(*color)
        ctx.set_line_width(width)
        ctx.move_to(*shoulder)
        ctx.line_to(*hand)
        ctx.stroke()
    filled(ctx, SUIT_RED, circle(*hand, 3.5), 2)


def speed_lines(ctx, shift):
    ctx.set_line_width(2)
    ctx.set_source_rgba(1, 1, 1, 0.85)
    for y, length in ((64, 14), (76, 20), (90, 12)):
        x = 108 + shift
        ctx.move_to(x, y)
        ctx.line_to(min(x + length, 126), y)
    ctx.stroke()


def exhaust_puffs(ctx, count):
    for i in range(count):
        ctx.set_source_rgba(0.85, 0.85, 0.85, 0.9 - 0.25 * i)
        ctx.arc(110 + 5 * i, 121 - 2 * i, 2 + 0.8 * i, 0, 2 * math.pi)
        ctx.fill()


def draw_frame(rider, index):
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 128, 128)
    ctx = cairo.Context(surface)
    ctx.set_line_join(cairo.LINE_JOIN_ROUND)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    bob = index % 2
    spin = index * 2 * math.pi / 9

    speed_lines(ctx, index * 2)
    exhaust_puffs(ctx, index + 1)
    wheel(ctx, 92, 118, spin)

    ctx.set_source_surface(rider, 0, bob - RIDER_LIFT)
    ctx.paint()

    filled(ctx, MINT, floorboard)
    filled(ctx, MINT, rear_cowl)
    cowl_shine(ctx)
    deadpool_logo(ctx, 88, 110)

    wheel(ctx, 24, 118, spin)
    filled(ctx, MINT, front_fender)
    filled(ctx, MINT, leg_shield)
    ctx.set_source_rgb(*OUTLINE)
    ctx.set_line_width(3)
    ctx.move_to(28, 84)
    ctx.line_to(28, 78)
    ctx.stroke()
    filled(ctx, MINT, handlebar)
    filled(ctx, HEADLIGHT, circle(19, 80, 4), 2)
    arm(ctx, (62, 84 + bob), (44, 80))
    return surface


def main(img_dir):
    rider = cairo.ImageSurface.create_from_png(os.path.join(img_dir, f"shime{RIDER_SPRITE}.png"))
    for index in range(FRAME_COUNT):
        target = os.path.join(img_dir, f"shime{FIRST_INDEX + index}.png")
        draw_frame(rider, index).write_to_png(target)
        print(target)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "sprites/deadpool/img")
