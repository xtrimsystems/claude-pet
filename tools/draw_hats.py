import math

from sprite_kit import *

HAT_CANVAS = (84, 76)
HAT_ORIGIN = (42, 58)
SANTA_RED = (0.62, 0.04, 0.06)
SANTA_SHADE = (0.45, 0.02, 0.04)
FUR = (0.97, 0.97, 0.96)
FUR_SHADE = (0.80, 0.82, 0.86)
PUMPKIN = (0.96, 0.52, 0.10)
PUMPKIN_SHADE = (0.78, 0.36, 0.05)
PUMPKIN_SHINE = (1.0, 0.72, 0.36)
STEM = (0.40, 0.30, 0.14)
LEAF = (0.36, 0.62, 0.20)

REFERENCE_POSE = 1
HAT_ABOVE_EYE = (-5, -27)
MIN_EYE_PIXELS = 5
EYE_PAIR_DISTANCE = (16, 42)
SOCKET_REACH = 9
SOCKET_MAX_PIXELS = 700
HEAD_BELOW_HAT = 7
MAX_HEAD_DEPTH = 40
HAT_SINKS = 6
HAT_RISES = 16
FIT_SLACK = 3
EYE_GAP = 30
BAND_HEIGHT = 18
PROPS_UNDER_HAT = 300
SIDE_SLACK = 12
CLOSED_SOCKET_SIZE = (0.5, 1.6)
CLOSED_SOCKET_RIM = 0.5
STRAIGHT_WITHIN = math.radians(6)
SUIT_RED_SHARE = 0.10


def _pixel_reader(surface):
    surface.flush()
    data, stride = surface.get_data(), surface.get_stride()
    width, height = surface.get_width(), surface.get_height()

    def pixel(x, y):
        if not (0 <= x < width and 0 <= y < height):
            return 0, 0, 0, 0
        i = y * stride + x * 4
        return data[i + 2], data[i + 1], data[i], data[i + 3]
    return pixel, width, height


def _is_white(p):
    return p[3] > 200 and min(p[:3]) >= 200


def _is_grey(p):
    return p[3] > 200 and max(p[:3]) - min(p[:3]) < 25


def _is_suit(p):
    return p[3] > 200 and 80 <= p[0] <= 140 and p[1] < 30 and p[2] < 30


def _neighbours(x, y):
    return ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1))


def _white_blobs(pixel, width, height):
    seen, blobs = set(), []
    for y in range(height):
        for x in range(width):
            if (x, y) in seen or not _is_white(pixel(x, y)):
                continue
            stack, points = [(x, y)], []
            seen.add((x, y))
            while stack:
                point = stack.pop()
                points.append(point)
                for n in _neighbours(*point):
                    if n not in seen and _is_white(pixel(*n)):
                        seen.add(n)
                        stack.append(n)
            if len(points) >= MIN_EYE_PIXELS:
                blobs.append(points)
    return blobs


def _around(blob):
    xs, ys = [p[0] for p in blob], [p[1] for p in blob]
    return min(xs) - SOCKET_REACH, min(ys) - SOCKET_REACH, max(xs) + SOCKET_REACH, max(ys) + SOCKET_REACH


def _grey_region(pixel, blob, box=None, limit=None):
    inside = lambda x, y: box is None or (box[0] <= x <= box[2] and box[1] <= y <= box[3])
    seen = set(blob)
    stack = list(blob)
    while stack:
        for n in _neighbours(*stack.pop()):
            if n not in seen and inside(*n) and _is_grey(pixel(*n)):
                seen.add(n)
                stack.append(n)
        if limit and len(seen) > limit:
            return None
    return seen


def _socket(pixel, blob):
    return _grey_region(pixel, blob, limit=SOCKET_MAX_PIXELS) or _grey_region(pixel, blob, _around(blob))


def _is_eye(pixel, blob):
    x0, y0, x1, y1 = _around(blob)
    rim = {n for point in blob for n in _neighbours(*point)} - set(blob)
    if sum(_is_grey(pixel(*point)) for point in rim) < 0.8 * len(rim):
        return False
    area = [(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]
    return sum(_is_suit(pixel(*point)) for point in area) >= SUIT_RED_SHARE * len(area)


def _center(points):
    return sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points)


def _grey_components(pixel, width, height):
    seen = set()
    for y in range(height):
        for x in range(width):
            if (x, y) not in seen and _is_grey(pixel(x, y)):
                region = _grey_region(pixel, [(x, y)])
                seen |= region
                yield region


def _closed_socket(pixel, width, height, size_range):
    sockets = []
    for region in _grey_components(pixel, width, height):
        if not size_range[0] <= len(region) <= size_range[1]:
            continue
        rim = {n for point in region for n in _neighbours(*point)} - region
        if sum(_is_suit(pixel(*point)) for point in rim) >= CLOSED_SOCKET_RIM * len(rim):
            sockets.append(region)
    return _center(max(sockets, key=len)) if sockets else None


def _eye_pairs(pixel, width, height):
    eyes = sorted((blob for blob in _white_blobs(pixel, width, height) if _is_eye(pixel, blob)), key=len, reverse=True)
    pairs = []
    for near in eyes:
        near_center = _center(near)
        partners = [far for far in eyes if far is not near and len(far) < len(near)
                    and EYE_PAIR_DISTANCE[0] <= math.dist(_center(far), near_center) <= EYE_PAIR_DISTANCE[1]]
        far = min(partners, key=lambda blob: abs(math.dist(_center(blob), near_center) - EYE_GAP), default=None)
        tilt = None if far is None else math.atan2(near_center[1] - _center(far)[1], near_center[0] - _center(far)[0])
        pairs.append((_center(_socket(pixel, near)), tilt))
    return pairs


def _turned(angle, x, y):
    cos, sin = math.cos(angle), math.sin(angle)
    return x * cos - y * sin, x * sin + y * cos


def _straightened(angle):
    angle = math.atan2(math.sin(angle), math.cos(angle))
    return 0.0 if abs(angle) < STRAIGHT_WITHIN else angle


def _is_head(p):
    return _is_suit(p) or (p[3] > 200 and max(p[:3]) < 70)


def _head_depth(pixel, x, y, angle):
    ux, uy = _turned(angle, 0, -1)
    for step in range(MAX_HEAD_DEPTH):
        if not _is_head(pixel(round(x + ux * step), round(y + uy * step))):
            return step
    return None


def _head_below(pixel, x, y, angle):
    bx, by = _turned(angle, 0, HEAD_BELOW_HAT)
    return any(_is_suit(pixel(round(x + bx) + dx, round(y + by) + dy)) for dx in (-2, 0, 2) for dy in (-2, 0, 2))


class HeadFinder:
    def __init__(self, kit, hat_images):
        self._hat_band = self._band_pixels(hat_images)
        self._hat_corners = self._corners(hat_images)
        reference = kit.sprite(REFERENCE_POSE)
        pixel, width, height = _pixel_reader(reference)
        near = max((blob for blob in _white_blobs(pixel, width, height) if _is_eye(pixel, blob)), key=len)
        socket_size = len(_grey_region(pixel, near, limit=SOCKET_MAX_PIXELS))
        self._socket_sizes = (socket_size * CLOSED_SOCKET_SIZE[0], socket_size * CLOSED_SOCKET_SIZE[1])
        (sx, sy), self._tilt = _eye_pairs(pixel, width, height)[0]
        self._depth = _head_depth(pixel, sx + HAT_ABOVE_EYE[0], sy + HAT_ABOVE_EYE[1], 0.0)

    def _placed(self, pixel, socket, angle, flip):
        angle = _straightened(angle)
        dx, dy = HAT_ABOVE_EYE
        ox, oy = _turned(angle, -dx if flip else dx, dy)
        x, y = socket[0] + ox, socket[1] + oy
        depth = _head_depth(pixel, x, y, angle)
        if depth is None or not -HAT_SINKS <= depth - self._depth <= HAT_RISES:
            return None
        ux, uy = _turned(angle, 0, -1)
        x, y = x + ux * (depth - self._depth), y + uy * (depth - self._depth)
        if not _head_below(pixel, x, y, angle):
            return None
        return [round(x, 1), round(y, 1), round(math.degrees(angle), 1), int(flip)]

    def anchor(self, surface):
        pixel, width, height = _pixel_reader(surface)
        pairs = _eye_pairs(pixel, width, height)
        for socket, tilt in pairs:
            if tilt is None:
                continue
            for angle, flip in ((tilt - self._tilt, False), (tilt - math.pi + self._tilt, True)):
                placed = self._placed(pixel, socket, angle, flip)
                if placed:
                    return placed, True
        sockets = [socket for socket, _ in pairs] or [_closed_socket(pixel, width, height, self._socket_sizes)]
        for socket in filter(None, sockets):
            for flip in (False, True):
                placed = self._placed(pixel, socket, 0.0, flip)
                if placed:
                    return placed, False
        return None, False

    @staticmethod
    def _band_pixels(hat_images):
        readers = [_pixel_reader(image)[0] for image in hat_images]
        return [(x - HAT_ORIGIN[0], y - HAT_ORIGIN[1])
                for y in range(HAT_ORIGIN[1] - BAND_HEIGHT, HAT_CANVAS[1]) for x in range(HAT_CANVAS[0])
                if any(read(x, y)[3] > 128 for read in readers)]

    @staticmethod
    def _corners(hat_images):
        opaque = [(x, y) for image in hat_images for read in [_pixel_reader(image)[0]]
                  for y in range(HAT_CANVAS[1]) for x in range(HAT_CANVAS[0]) if read(x, y)[3] > 0]
        xs, ys = [x - HAT_ORIGIN[0] for x, _ in opaque], [y - HAT_ORIGIN[1] for _, y in opaque]
        return [(x, y) for x in (min(xs), max(xs)) for y in (min(ys), max(ys))]

    def _sticks_out(self, surface, anchor):
        x, y, angle, flip = anchor
        angle = math.radians(angle)
        sides = [x + _turned(angle, -hx if flip else hx, hy)[0] for hx, hy in self._hat_corners]
        return min(sides) < -SIDE_SLACK or max(sides) > surface.get_width() + SIDE_SLACK

    def usable(self, surface, anchor):
        return anchor is not None and not self.hides_props(surface, anchor) and not self._sticks_out(surface, anchor)

    def hides_props(self, surface, anchor):
        pixel, _, _ = _pixel_reader(surface)
        x, y, angle, flip = anchor
        angle = math.radians(angle)
        covered = 0
        for hx, hy in self._hat_band:
            ox, oy = _turned(angle, -hx if flip else hx, hy)
            p = pixel(round(x + ox), round(y + oy))
            covered += p[3] > 200 and not _is_head(p) and not _is_grey(p)
        return covered > PROPS_UNDER_HAT

    def fits(self, surface, anchor):
        pixel, _, _ = _pixel_reader(surface)
        x, y, angle, _ = anchor
        depth = _head_depth(pixel, x, y, math.radians(angle))
        return depth is not None and abs(depth - self._depth) <= FIT_SLACK and _head_below(pixel, x, y, math.radians(angle))


def head_anchors(finder, frames):
    found = [finder.anchor(frame) for frame in frames]
    anchors = []
    for k, frame in enumerate(frames):
        anchor, sure = found[k]
        if sure:
            anchors.append(anchor)
            continue
        nearby = sorted((abs(j - k) + (0.5 if j > k else 0), other) for j, (other, other_sure) in enumerate(found)
                        if other_sure)
        borrowed = next((other for _, other in nearby if finder.fits(frame, other)), None)
        anchors.append(borrowed or anchor)
    return [anchor if finder.usable(frame, anchor) else None for frame, anchor in zip(frames, anchors)]


def hat_canvas():
    surface, ctx = blank(*HAT_CANVAS)
    ctx.translate(*HAT_ORIGIN)
    return surface, ctx


def santa_hat():
    surface, ctx = hat_canvas()

    def cone(c):
        c.move_to(-25, -2)
        c.curve_to(-22, -24, -8, -40, 12, -44)
        c.curve_to(22, -46, 30, -40, 33, -30)
        c.curve_to(26, -34, 20, -33, 16, -28)
        c.curve_to(22, -20, 25, -10, 25, -2)
        c.close_path()
    filled(ctx, SANTA_RED, cone)
    ctx.save()
    cone(ctx)
    ctx.clip()
    ctx.set_source_rgb(*SANTA_SHADE)
    ctx.move_to(10, -2)
    ctx.curve_to(16, -14, 14, -24, 16, -28)
    ctx.curve_to(22, -20, 25, -10, 25, -2)
    ctx.close_path()
    ctx.fill()
    ctx.restore()
    filled(ctx, FUR, circle(33, -29, 6.5))
    band = rounded_rect(-28, -7, 56, 12, 6)
    filled(ctx, FUR, band)
    ctx.save()
    band(ctx)
    ctx.clip()
    ctx.set_source_rgb(*FUR_SHADE)
    ctx.rectangle(-28, 1, 56, 4)
    ctx.fill()
    ctx.restore()
    band(ctx)
    ctx.set_source_rgb(*OUTLINE)
    ctx.set_line_width(LINE_WIDTH)
    ctx.stroke()
    return surface


def pumpkin_hat():
    surface, ctx = hat_canvas()
    dome = lambda c: (c.move_to(-29, 4), c.curve_to(-32, -16, -18, -30, 0, -30),
                      c.curve_to(18, -30, 32, -16, 29, 4), c.curve_to(10, 8, -10, 8, -29, 4), c.close_path())
    filled(ctx, PUMPKIN, dome)
    ctx.save()
    dome(ctx)
    ctx.clip()
    ctx.set_source_rgb(*PUMPKIN_SHINE)
    ellipse(-14, -17, 4, 7, -0.5)(ctx)
    ctx.fill()
    ctx.set_source_rgb(*PUMPKIN_SHADE)
    ctx.set_line_width(2)
    for x, bend in ((-15, -6), (0, 0), (15, 6)):
        ctx.move_to(x * 0.35, -30)
        ctx.curve_to(x + bend, -22, x + bend, -4, x, 7)
        ctx.stroke()
    ctx.restore()
    dome(ctx)
    ctx.set_source_rgb(*OUTLINE)
    ctx.set_line_width(LINE_WIDTH)
    ctx.stroke()
    stem = lambda c: (c.move_to(-3, -28), c.curve_to(-3, -34, -1, -38, 3, -41), c.line_to(6, -38),
                      c.curve_to(3, -35, 3, -32, 4, -28), c.close_path())
    filled(ctx, STEM, stem)
    leaf = lambda c: (c.move_to(4, -33), c.curve_to(10, -42, 20, -40, 22, -35),
                      c.curve_to(16, -30, 9, -30, 4, -33), c.close_path())
    filled(ctx, LEAF, leaf, 2)
    return surface


def hats():
    return {"santa": santa_hat(), "pumpkin": pumpkin_hat()}


def wear(surface, hat, anchor):
    x, y, angle, flip = anchor
    ctx = context(surface)
    ctx.translate(x, y)
    ctx.rotate(math.radians(angle))
    if flip:
        ctx.scale(-1, 1)
    ctx.translate(-HAT_ORIGIN[0], -HAT_ORIGIN[1])
    ctx.set_source_surface(hat, 0, 0)
    ctx.paint()
    return surface
