import math
import os

import cairo

SIZE = 128
OUTLINE = (0, 0, 0)
LINE_WIDTH = 2.5
SUIT_RED = (108 / 255, 0, 0)
MARK_RED = (163 / 255, 1 / 255, 3 / 255)
MINT = (0.56, 0.87, 0.78)
MINT_SHINE = (0.80, 0.97, 0.92)
GOLD = (1.0, 0.82, 0.30)
SMOKE = (0.94, 0.94, 0.95)

_text_mirrored = False


def mirror_text(enabled):
    global _text_mirrored
    _text_mirrored = enabled


def text_at(ctx, text, x, y):
    if _text_mirrored:
        extents = ctx.text_extents(text)
        center = x + extents.x_bearing + extents.width / 2
        ctx.translate(2 * center, 0)
        ctx.scale(-1, 1)
    ctx.move_to(x, y)
    ctx.text_path(text)


class Kit:
    def __init__(self, img_dir):
        self.img_dir = img_dir
        self._cache = {}

    def path(self, index):
        return os.path.join(self.img_dir, f"shime{index}.png")

    def sprite(self, index):
        if index not in self._cache:
            self._cache[index] = cairo.ImageSurface.create_from_png(self.path(index))
        return self._cache[index]


def rotate_point(point, pivot, degrees):
    a = math.radians(degrees)
    x, y = point[0] - pivot[0], point[1] - pivot[1]
    return pivot[0] + x * math.cos(a) - y * math.sin(a), pivot[1] + x * math.sin(a) + y * math.cos(a)


def blank(width=SIZE, height=SIZE):
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    return surface, cairo.Context(surface)


def copy(source):
    surface, ctx = blank(source.get_width(), source.get_height())
    ctx.set_source_surface(source, 0, 0)
    ctx.paint()
    return surface


def frame_of(base, draw=None):
    surface = copy(base)
    if draw:
        draw(context(surface))
    return surface


def context(surface):
    ctx = cairo.Context(surface)
    ctx.set_line_join(cairo.LINE_JOIN_ROUND)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    return ctx


def paint(target, source, dx=0, dy=0, rotate=0, pivot=(64, 64), scale=1.0, smooth=False):
    ctx = cairo.Context(target)
    ctx.translate(dx, dy)
    ctx.translate(*pivot)
    ctx.rotate(math.radians(rotate))
    ctx.scale(scale, scale)
    ctx.translate(-pivot[0], -pivot[1])
    ctx.set_source_surface(source, 0, 0)
    ctx.get_source().set_filter(cairo.FILTER_GOOD if smooth else cairo.FILTER_NEAREST)
    ctx.paint()


def crop_rows(source, top, bottom):
    surface, ctx = blank()
    ctx.rectangle(0, top, SIZE, bottom - top)
    ctx.clip()
    ctx.set_source_surface(source, 0, 0)
    ctx.paint()
    return surface


def crop_rects(source, rects, dx=0, dy=0):
    surface, ctx = blank()
    for rect in rects:
        ctx.rectangle(*rect)
    ctx.clip()
    ctx.set_source_surface(source, dx, dy)
    ctx.paint()
    return surface


def shear(source, lean, base_y=SIZE):
    surface, ctx = blank()
    for y in range(SIZE):
        ctx.save()
        ctx.rectangle(0, y, SIZE, 1)
        ctx.clip()
        ctx.set_source_surface(source, round(lean * (base_y - y)), 0)
        ctx.paint()
        ctx.restore()
    return surface


def drop_specks(surface):
    data, stride = _pixels(surface)
    solid = lambda x, y: 0 <= x < SIZE and 0 <= y < SIZE and data[y * stride + x * 4 + 3] >= 160
    keep = {(x, y) for y in range(SIZE) for x in range(SIZE)
            if solid(x, y) and sum(solid(x + dx, y + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))) >= 2}
    for y in range(SIZE):
        for x in range(SIZE):
            if (x, y) not in keep:
                data[y * stride + x * 4:y * stride + x * 4 + 4] = bytes(4)
    surface.mark_dirty()


def sign_pixels(source, box, min_blue=18):
    surface = crop_rects(source, [box])
    data, stride = _pixels(surface)
    for i in range(0, stride * SIZE, 4):
        if data[i] < min_blue:
            data[i:i + 4] = bytes(4)
    surface.mark_dirty()
    return surface


def erase(target, layer):
    ctx = cairo.Context(target)
    ctx.set_operator(cairo.OPERATOR_DEST_OUT)
    ctx.set_source_surface(layer, 0, 0)
    ctx.paint()


def _pixels(surface):
    surface.flush()
    return surface.get_data(), surface.get_stride()


def _is_light(data, i):
    return data[i + 3] > 0 and data[i + 1] > 150 and data[i + 2] > 150 and data[i] > 150


def eye_blobs(surface, top=20, bottom=95):
    data, stride = _pixels(surface)
    seen, blobs = set(), []
    for y in range(top, bottom):
        for x in range(SIZE):
            if (x, y) in seen or not _is_light(data, y * stride + x * 4):
                continue
            stack, points = [(x, y)], []
            seen.add((x, y))
            while stack:
                px, py = stack.pop()
                points.append((px, py))
                for nx, ny in ((px + 1, py), (px - 1, py), (px, py + 1), (px, py - 1)):
                    if (0 <= nx < SIZE and top <= ny < bottom and (nx, ny) not in seen
                            and _is_light(data, ny * stride + nx * 4)):
                        seen.add((nx, ny))
                        stack.append((nx, ny))
            if len(points) >= 6:
                xs, ys = [p[0] for p in points], [p[1] for p in points]
                blobs.append((min(xs), min(ys), max(xs), max(ys)))
    return sorted(blobs)


def _eye_pixels(data, stride, blob):
    x0, y0, x1, y1 = blob
    return [(x, y) for y in range(y0 - 1, y1 + 2) for x in range(x0 - 1, x1 + 2)
            if data[y * stride + x * 4 + 3] > 0 and data[y * stride + x * 4 + 1] > 12]


def close_eyes(source, fraction, blobs=None):
    surface = copy(source)
    blobs = blobs or eye_blobs(surface)
    data, stride = _pixels(surface)
    for blob in blobs:
        lid = blob[1] + (blob[3] - blob[1] + 1) * fraction
        for x, y in _eye_pixels(data, stride, blob):
            if y < lid:
                i = y * stride + x * 4
                data[i:i + 3] = bytes((0, 0, 0))
    surface.mark_dirty()
    return surface


def move_eyes(source, dx, dy, blobs=None):
    surface = copy(source)
    blobs = blobs or eye_blobs(surface)
    data, stride = _pixels(surface)
    moved = []
    for blob in blobs:
        for x, y in _eye_pixels(data, stride, blob):
            i = y * stride + x * 4
            moved.append((x + dx, y + dy, bytes(data[i:i + 4])))
            data[i:i + 3] = bytes((0, 0, 0))
    for x, y, value in moved:
        i = y * stride + x * 4
        if 0 <= x < SIZE and 0 <= y < SIZE and data[i + 3] > 200 and max(data[i:i + 3]) < 60:
            data[i:i + 4] = value
    surface.mark_dirty()
    return surface


def silhouette(ctx, shapes, fill, width=LINE_WIDTH):
    ctx.set_source_rgb(*OUTLINE)
    ctx.set_line_width(2 * width)
    for shape in shapes:
        shape(ctx)
        ctx.stroke()
    ctx.set_source_rgb(*fill)
    for shape in shapes:
        shape(ctx)
        ctx.fill()


def filled(ctx, color, shape, width=LINE_WIDTH):
    shape(ctx)
    ctx.set_source_rgb(*color)
    ctx.fill_preserve()
    ctx.set_source_rgb(*OUTLINE)
    ctx.set_line_width(width)
    ctx.stroke()


def circle(cx, cy, r):
    return lambda c: c.arc(cx, cy, max(r, 0.1), 0, 2 * math.pi)


def ellipse(cx, cy, rx, ry, angle=0):
    def shape(c):
        c.save()
        c.translate(cx, cy)
        c.rotate(math.radians(angle))
        c.scale(rx, ry)
        c.arc(0, 0, 1, 0, 2 * math.pi)
        c.restore()
    return shape


def outlined_text(ctx, text, x, y, size, fill=(1, 1, 1), width=3, alpha=1.0):
    ctx.save()
    ctx.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    ctx.set_font_size(size)
    text_at(ctx, text, x, y)
    ctx.set_source_rgba(*OUTLINE, alpha)
    ctx.set_line_width(width)
    ctx.stroke_preserve()
    ctx.set_source_rgba(*fill, alpha)
    ctx.fill()
    ctx.restore()


def burst(ctx, cx, cy, inner, outer, angles, color=(1, 1, 1), width=1.6):
    ctx.save()
    ctx.set_source_rgb(*color)
    ctx.set_line_width(width)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    for degrees in angles:
        a = math.radians(degrees)
        ctx.move_to(cx + inner * math.cos(a), cy + inner * math.sin(a))
        ctx.line_to(cx + outer * math.cos(a), cy + outer * math.sin(a))
    ctx.stroke()
    ctx.restore()


def exclamation(ctx, x, y, height=16):
    ctx.save()
    ctx.set_source_rgb(*MARK_RED)
    ctx.move_to(x - 2.6, y)
    ctx.line_to(x + 2.6, y)
    ctx.line_to(x + 1.2, y + height * 0.68)
    ctx.line_to(x - 1.2, y + height * 0.68)
    ctx.close_path()
    ctx.fill()
    ctx.arc(x, y + height * 0.9, 1.9, 0, 2 * math.pi)
    ctx.fill()
    ctx.restore()


def star(ctx, cx, cy, r, color=GOLD, spin=0):
    def shape(c):
        for k in range(10):
            a = math.radians(spin + k * 36 - 90)
            rr = r if k % 2 == 0 else r * 0.45
            (c.move_to if k == 0 else c.line_to)(cx + rr * math.cos(a), cy + rr * math.sin(a))
        c.close_path()
    filled(ctx, color, shape, 1.3)


def sparkle(ctx, x, y, size, color=GOLD):
    ctx.save()
    ctx.set_source_rgb(*color)
    for k in range(8):
        a = math.radians(k * 45)
        r = size if k % 2 == 0 else size * 0.3
        (ctx.move_to if k == 0 else ctx.line_to)(x + r * math.cos(a), y + r * math.sin(a))
    ctx.close_path()
    ctx.fill()
    ctx.restore()


CLOUD = ((0, 0, 1.0), (-0.9, 0.35, 0.75), (0.9, 0.35, 0.75), (-0.5, -0.75, 0.7),
         (0.55, -0.7, 0.75), (0, 0.85, 0.7), (-1.15, -0.35, 0.55), (1.15, -0.3, 0.55))


def cloud(ctx, cx, cy, size, spread=1.0, shrink=1.0):
    shapes = [circle(cx + dx * size * spread, cy + dy * size * spread, r * size * shrink)
              for dx, dy, r in CLOUD]
    silhouette(ctx, shapes, SMOKE, 2.0)
    ctx.set_source_rgba(1, 1, 1, 0.9)
    for dx, dy, r in CLOUD[:4]:
        ctx.arc(cx + dx * size * spread - r * size * 0.25, cy + dy * size * spread - r * size * 0.3,
                r * size * shrink * 0.35, 0, 2 * math.pi)
        ctx.fill()


def zzz(ctx, origin, phase, count=3):
    ox, oy = origin
    for k in range(count):
        t = (phase + k / count) % 1.0
        size = 7 + 6 * t
        alpha = 1.0 if t < 0.75 else (1 - t) / 0.25
        outlined_text(ctx, "z", ox - 16 * t - 4 * math.sin(t * 6), oy - 30 * t, size,
                      width=2.6, alpha=alpha)


def nose_bubble(ctx, x, y, r):
    ctx.save()
    ctx.arc(x, y, r, 0, 2 * math.pi)
    ctx.set_source_rgba(0.72, 0.90, 1.0, 0.80)
    ctx.fill_preserve()
    ctx.set_source_rgb(*OUTLINE)
    ctx.set_line_width(1.4)
    ctx.stroke()
    ctx.set_source_rgba(1, 1, 1, 0.95)
    ctx.arc(x - r * 0.35, y - r * 0.35, max(r * 0.22, 0.6), 0, 2 * math.pi)
    ctx.fill()
    ctx.restore()
