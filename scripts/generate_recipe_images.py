"""Render the data pack's crafting and smithing recipes as PNG images.

Textures are read directly from a vanilla Minecraft client .jar, so the
images match the game's look (GUI, items, blocks in 3D).

usage: python scripts/generate_recipe_images.py [--mc-version 26.3] [--jar PATH] [--out DIR] [--clean]
"""
import argparse
import glob
import io
import json
import os
import zipfile

from PIL import Image, ImageChops

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECIPES = os.path.join(ROOT, "data", "bastion_recipes", "recipe")
TAGS = os.path.join(ROOT, "data", "bastion", "tags", "item")

S = 3                       # GUI scale
SLOT = 16 * S
GRASS_TINT = (0x91, 0xBD, 0x59)
FOLIAGE_TINT = (0x48, 0xB5, 0x18)

JAR = None                  # zipfile.ZipFile of the client jar, set in main()


# --- assets ------------------------------------------------------------
def has(path):
    try:
        JAR.getinfo("assets/minecraft/" + path)
        return True
    except KeyError:
        return False


def image(path):
    return Image.open(io.BytesIO(JAR.read("assets/minecraft/" + path))).convert("RGBA")


def tex(path):
    return image("textures/" + path + ".png").crop((0, 0, 16, 16))


def model_textures(name):
    path = "models/block/" + name + ".json"
    if not has(path):
        return None, {}
    m = json.loads(JAR.read("assets/minecraft/" + path))
    return m.get("parent", "").split("/")[-1], {k: v.split(":")[-1] for k, v in m.get("textures", {}).items()}


# --- item icons --------------------------------------------------------
def tint(im, rgb):
    r, g, b, a = im.split()
    col = ImageChops.multiply(Image.merge("RGB", (r, g, b)), Image.new("RGB", im.size, rgb))
    return Image.merge("RGBA", (*col.split(), a))


def shade(im, k):
    r, g, b, a = im.split()
    r, g, b = (c.point(lambda v: int(v * k)) for c in (r, g, b))
    return Image.merge("RGBA", (r, g, b, a))


def face(dst, src, origin, u, v):
    """Map texture src onto parallelogram origin + a*u + b*v (a, b in [0, 1])."""
    big = src.resize((src.width * 8, src.height * 8), Image.NEAREST)
    det = u[0] * v[1] - u[1] * v[0]
    ia, ib = v[1] / det, -v[0] / det
    ic, id_ = -u[1] / det, u[0] / det
    ox, oy = origin
    W, H = big.size
    data = (ia * W, ib * W, -(ia * ox + ib * oy) * W,
            ic * H, id_ * H, -(ic * ox + id_ * oy) * H)
    dst.alpha_composite(big.transform(dst.size, Image.AFFINE, data, resample=Image.NEAREST))


def iso(top, side, height=1.0):
    """Inventory-style isometric block. Side faces use the bottom `height` part of the texture."""
    w = SLOT
    pad = w * 0.06
    w2 = w - 2 * pad
    im = Image.new("RGBA", (w, w), (0, 0, 0, 0))
    h = w2 / 2 * height
    yoff = pad + w2 / 2 * (1 - height)
    s = side.crop((0, int(16 * (1 - height)), 16, 16)) if height < 1 else side
    face(im, shade(s, 0.8), (pad, yoff + w2 / 4), (w2 / 2, w2 / 4), (0, h))
    face(im, shade(s, 0.6), (pad + w2 / 2, yoff + w2 / 2), (w2 / 2, -w2 / 4), (0, h))
    face(im, top, (pad, yoff + w2 / 4), (w2 / 2, -w2 / 4), (w2 / 2, w2 / 4))
    return im


def flat(im):
    return im.resize((SLOT, SLOT), Image.NEAREST)


def chest():
    e = image("textures/entity/chest/normal.png")
    top = e.crop((14, 0, 28, 14)).resize((16, 16), Image.NEAREST)
    front = Image.new("RGBA", (14, 15))
    front.paste(e.crop((14, 14, 28, 19)), (0, 0))
    front.paste(e.crop((14, 33, 28, 43)), (0, 5))
    front = front.resize((16, 16), Image.NEAREST)
    lock = e.crop((1, 1, 3, 5))
    front.paste(lock, (7, 3), lock)
    return iso(top, front)


def end_rod():
    t = tex("block/end_rod")
    im = Image.new("RGBA", (16, 16))
    im.paste(t.crop((0, 0, 2, 15)), (7, 0))
    im.paste(t.crop((2, 2, 6, 3)), (6, 15))
    return flat(im.rotate(-45, resample=Image.NEAREST))


def lightning_rod():
    t = tex("block/lightning_rod")
    im = Image.new("RGBA", (16, 16))
    im.paste(t.crop((0, 4, 2, 16)), (7, 4))      # rod
    im.paste(t.crop((0, 0, 4, 4)), (6, 0))       # tip
    return flat(im.rotate(-45, resample=Image.NEAREST))


SPECIAL = {
    "grass_block": lambda: iso(tint(tex("block/grass_block_top"), GRASS_TINT),
                               Image.alpha_composite(tex("block/grass_block_side"),
                                                     tint(tex("block/grass_block_side_overlay"), GRASS_TINT))),
    "chest": chest,
    "end_rod": end_rod,
    "lightning_rod": lightning_rod,
    "shulker_box": lambda: iso(tex("block/shulker_box"), tex("block/shulker_box")),
    "snow": lambda: iso(tex("block/snow"), tex("block/snow"), height=2 / 16),
    "sculk_sensor": lambda: iso(tex("block/sculk_sensor_top"), tex("block/sculk_sensor_side"), height=0.5),
}

_cache = {}


def icon(item_id):
    name = item_id.split(":")[-1]
    if name in _cache:
        return _cache[name]
    if name in SPECIAL:
        im = SPECIAL[name]()
    elif has("textures/item/" + name + ".png"):
        im = flat(tex("item/" + name))
    else:
        parent, t = model_textures(name)
        if parent == "cube_all":
            im = iso(tex(t["all"]), tex(t["all"]))
        elif parent == "template_single_face":
            im = iso(tex(t["texture"]), tex(t["texture"]))
        elif parent == "cube_column":
            im = iso(tex(t["end"]), tex(t["side"]))
        elif parent == "cube_bottom_top":
            im = iso(tex(t["top"]), tex(t["side"]))
        elif parent == "leaves" or name.endswith("_leaves"):
            lt = tint(tex("block/" + name), FOLIAGE_TINT)
            im = iso(lt, lt)
        elif parent in ("cross", "template_torch", "rail_flat"):
            im = flat(tex(next(iter(t.values()))))
        elif has("textures/block/" + name + ".png"):
            im = flat(tex("block/" + name))
        else:
            raise SystemExit("no texture for " + item_id + " (add it to SPECIAL)")
    _cache[name] = im
    return im


# --- GUI ---------------------------------------------------------------
def panel(w, h):
    """9-slice the vanilla container background to w x h (GUI px)."""
    src = image("textures/gui/container/crafting_table.png").crop((0, 0, 176, 166))
    c = 4
    im = Image.new("RGBA", (w, h), src.getpixel((8, 8)))
    im.paste(src.crop((c, 0, c + 1, c)).resize((w - 2 * c, c)), (c, 0))
    im.paste(src.crop((c, 166 - c, c + 1, 166)).resize((w - 2 * c, c)), (c, h - c))
    im.paste(src.crop((0, c, c, c + 1)).resize((c, h - 2 * c)), (0, c))
    im.paste(src.crop((176 - c, c, 176, c + 1)).resize((c, h - 2 * c)), (w - c, c))
    im.paste(src.crop((0, 0, c, c)), (0, 0))
    im.paste(src.crop((176 - c, 0, 176, c)), (w - c, 0))
    im.paste(src.crop((0, 166 - c, c, 166)), (0, h - c))
    im.paste(src.crop((176 - c, 166 - c, 176, 166)), (w - c, h - c))
    return im


def gui(texture, box, extra_right=0):
    """Crop `box` of a container texture onto a panel; returns (image, GUI origin)."""
    x0, y0, x1, y1 = box
    p = panel(x1 - x0 + 8 + extra_right, y1 - y0 + 8)
    p.paste(image("textures/gui/container/" + texture + ".png").crop(box), (4, 4))
    return p.resize((p.width * S, p.height * S), Image.NEAREST), (x0 - 4, y0 - 4)


def draw_count(im, n, x, y):
    """Item count, right-aligned like vanilla (x, y = item top-left in GUI px)."""
    font = image("textures/font/ascii.png")
    glyphs = []
    for ch in str(n):
        code = ord(ch)
        g = font.crop(((code % 16) * 8, (code // 16) * 8, (code % 16) * 8 + 8, (code // 16) * 8 + 8))
        width = max((xx for xx in range(8) for yy in range(8) if g.getpixel((xx, yy))[3]), default=0) + 1
        glyphs.append((g.crop((0, 0, width, 8)), width + 1))
    cx = x + 17 - (sum(w for _, w in glyphs) - 1)
    for g, w in glyphs:
        a = g.split()[3]
        for col, off in (((63, 63, 63, 255), 1), ((255, 255, 255, 255), 0)):
            layer = Image.new("RGBA", g.size, col)
            layer.putalpha(a)
            big = layer.resize((g.width * S, g.height * S), Image.NEAREST)
            im.alpha_composite(big, ((cx + off) * S, (y + 9 + off) * S))
        cx += w


# --- recipes -----------------------------------------------------------
def load_tag_picks():
    """Representative item shown for each #bastion: tag ingredient (its first value)."""
    picks = {}
    for f in glob.glob(os.path.join(TAGS, "*.json")):
        picks["#bastion:" + os.path.basename(f)[:-5]] = json.load(open(f, encoding="utf-8-sig"))["values"][0]
    return picks


TAG_PICK = {}


def ing(v):
    if isinstance(v, list):
        v = v[0]
    return TAG_PICK.get(v, v)


def put(im, origin, item, x, y, count=1):
    ox, oy = origin
    im.alpha_composite(icon(item), ((x - ox) * S, (y - oy) * S))
    if count > 1:
        draw_count(im, count, x - ox, y - oy)


def render(d):
    t = d["type"].split(":")[-1]
    res = d["result"]
    if t == "smithing_transform":
        im, o = gui("smithing", (2, 42, 122, 70))
        for x, k in ((8, "template"), (26, "base"), (44, "addition")):
            if d.get(k):
                put(im, o, ing(d[k]), x, 48)
        put(im, o, res["id"], 98, 48, res.get("count", 1))
        return im
    if t == "crafting_shapeless" and len(d["ingredients"]) <= 4:
        # player inventory 2x2 grid
        im, o = gui("inventory", (90, 10, 172, 61), extra_right=6)
        for k, v in enumerate(d["ingredients"]):
            put(im, o, ing(v), 98 + 18 * (k % 2), 18 + 18 * (k // 2))
        put(im, o, res["id"], 154, 28, res.get("count", 1))
        return im
    im, o = gui("crafting_table", (22, 10, 152, 76))
    if t == "crafting_shaped":
        # trim empty rows / columns, then centre in the 3x3 grid
        rows = [r for r in d["pattern"] if r.strip()]
        w = max(len(r) for r in rows)
        rows = [r.ljust(w) for r in rows]
        cols = [i for i in range(w) if any(r[i] != " " for r in rows)]
        rows = [r[cols[0]:cols[-1] + 1] for r in rows]
        ox, oy = (3 - len(rows[0])) // 2, (3 - len(rows)) // 2
        for j, r in enumerate(rows):
            for i, ch in enumerate(r):
                if ch != " ":
                    put(im, o, ing(d["key"][ch]), 30 + 18 * (i + ox), 17 + 18 * (j + oy))
    else:
        for k, v in enumerate(d["ingredients"]):
            put(im, o, ing(v), 30 + 18 * (k % 3), 17 + 18 * (k // 3))
    put(im, o, res["id"], 124, 35, res.get("count", 1))
    return im


def main():
    global JAR, TAG_PICK
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mc-version", default="26.3", help="client version to read from the default launcher folder")
    ap.add_argument("--jar", help="path to a Minecraft client .jar (overrides --mc-version)")
    ap.add_argument("--out", default=os.path.join(ROOT, "images", "recipes"), help="output folder")
    ap.add_argument("--clean", action="store_true", help="delete PNGs in --out that no recipe produces anymore")
    args = ap.parse_args()

    jar = args.jar or os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")),
                                   ".minecraft", "versions", args.mc_version, args.mc_version + ".jar")
    if not os.path.isfile(jar):
        raise SystemExit(f"Minecraft jar not found: {jar}\nLaunch {args.mc_version} once or pass --jar.")
    JAR = zipfile.ZipFile(jar)
    TAG_PICK = load_tag_picks()

    written = set()
    for f in sorted(glob.glob(os.path.join(RECIPES, "**", "*.json"), recursive=True)):
        d = json.load(open(f, encoding="utf-8-sig"))
        t = d["type"].split(":")[-1]
        if not (t.startswith("crafting") or t == "smithing_transform"):
            continue
        dst = os.path.join(args.out, os.path.relpath(f, RECIPES)[:-5] + ".png")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        render(d).save(dst, optimize=True)
        written.add(os.path.normpath(dst))
    print(len(written), "images written to", args.out)

    stale = [p for p in glob.glob(os.path.join(args.out, "**", "*.png"), recursive=True)
             if os.path.normpath(p) not in written]
    for p in stale:
        if args.clean:
            os.remove(p)
            print("removed", p)
        else:
            print("stale (use --clean to remove):", p)


if __name__ == "__main__":
    main()
