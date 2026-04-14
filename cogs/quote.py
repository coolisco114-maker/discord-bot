import io
import os
import textwrap
import urllib.request

import aiohttp
import discord
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont

FONTS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "fonts")

FONT_URLS = {
    "regular": "https://github.com/google/fonts/raw/main/ofl/lato/Lato-Regular.ttf",
    "bold":    "https://github.com/google/fonts/raw/main/ofl/lato/Lato-Bold.ttf",
    "italic":  "https://github.com/google/fonts/raw/main/ofl/lato/Lato-Italic.ttf",
}

W, H = 1000, 480


def _download_fonts():
    os.makedirs(FONTS_DIR, exist_ok=True)
    for name, url in FONT_URLS.items():
        path = os.path.join(FONTS_DIR, f"lato_{name}.ttf")
        if not os.path.exists(path):
            try:
                urllib.request.urlretrieve(url, path)
            except Exception as e:
                print(f"[Quote] Could not download font '{name}': {e}")


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    path = os.path.join(FONTS_DIR, f"lato_{name}.ttf")
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


async def _fetch_bytes(url: str) -> bytes:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.read()


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split()
    lines, current = [], ""
    for word in words:
        test = (current + " " + word).strip()
        if font.getbbox(test)[2] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


async def build_quote_image(
    avatar_url: str,
    display_name: str,
    username_tag: str,
    text: str,
) -> io.BytesIO:
    _download_fonts()

    AVATAR_COL_W = int(W * 0.43)   # left image column width
    FADE_SPAN    = 220              # how wide the fade-to-black gradient is
    TEXT_X       = AVATAR_COL_W + 40
    TEXT_W       = W - TEXT_X - 50

    font_quote = _font("bold",    52)
    font_name  = _font("italic",  32)
    font_tag   = _font("regular", 22)

    canvas = Image.new("RGB", (W, H), (0, 0, 0))

    avatar_raw = await _fetch_bytes(str(avatar_url) + "?size=512")
    av = Image.open(io.BytesIO(avatar_raw)).convert("RGBA")

    av_ratio = av.width / av.height
    av_h = H
    av_w = int(av_ratio * av_h)
    av = av.resize((av_w, av_h), Image.LANCZOS)

    if av_w >= AVATAR_COL_W:
        crop_left = (av_w - AVATAR_COL_W) // 2
        av = av.crop((crop_left, 0, crop_left + AVATAR_COL_W, av_h))
    else:
        padded = Image.new("RGBA", (AVATAR_COL_W, H), (0, 0, 0, 255))
        padded.paste(av, ((AVATAR_COL_W - av_w) // 2, 0))
        av = padded

    canvas.paste(av.convert("RGB"), (0, 0))

    fade_start = AVATAR_COL_W - FADE_SPAN
    fade_region_w = AVATAR_COL_W + 60
    gradient_img = Image.new("L", (fade_region_w, H), 0)
    grad_pixels = gradient_img.load()
    for x in range(fade_region_w):
        if x <= fade_start:
            alpha = 0
        elif x >= AVATAR_COL_W:
            alpha = 255
        else:
            alpha = int((x - fade_start) / (AVATAR_COL_W - fade_start) * 255)
        for y in range(H):
            grad_pixels[x, y] = alpha

    black_overlay = Image.new("RGB", (fade_region_w, H), (0, 0, 0))
    canvas.paste(black_overlay, (0, 0), gradient_img)

    draw = ImageDraw.Draw(canvas)

    lines = _wrap_text(text[:400], font_quote, TEXT_W)
    lines = lines[:5]

    LINE_H = 64
    NAME_GAP = 22
    TAG_GAP  = 10
    name_h = font_name.getbbox(f"- {display_name}")[3]
    tag_h  = font_tag.getbbox(f"@{username_tag}")[3]
    block_h = len(lines) * LINE_H + NAME_GAP + name_h + TAG_GAP + tag_h
    y = (H - block_h) // 2

    for line in lines:
        draw.text((TEXT_X, y), line, font=font_quote, fill=(255, 255, 255))
        y += LINE_H

    y += NAME_GAP
    draw.text((TEXT_X, y), f"- {display_name}", font=font_name, fill=(210, 210, 210))
    y += name_h + TAG_GAP
    draw.text((TEXT_X, y), f"@{username_tag}", font=font_tag, fill=(110, 115, 125))

    buf = io.BytesIO()
    canvas.save(buf, "PNG")
    buf.seek(0)
    return buf


class Quote(commands.Cog):
    """Quote card generator."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        _download_fonts()

    @commands.command(name="quote", aliases=["q"])
    async def quote(self, ctx: commands.Context, *, text: str = None):
        """Turn a message into a stylized quote card.

        Reply to any message and run `.quote`, or type `.quote <text>`.
        """
        author = ctx.author
        quote_text = text

        if ctx.message.reference:
            try:
                ref = await ctx.channel.fetch_message(ctx.message.reference.message_id)
                if not quote_text:
                    quote_text = ref.content
                author = ref.author
            except discord.NotFound:
                pass

        if not quote_text or not quote_text.strip():
            return await ctx.send(
                "Please provide some text, or reply to a message and run `.quote`.",
                delete_after=8,
            )

        username_tag = author.name

        async with ctx.typing():
            avatar_url = author.display_avatar.with_format("png").url
            buf = await build_quote_image(
                avatar_url,
                author.display_name,
                username_tag,
                quote_text.strip(),
            )
            await ctx.message.delete()
            await ctx.send(file=discord.File(buf, filename="quote.png"))


async def setup(bot: commands.Bot):
    await bot.add_cog(Quote(bot))
