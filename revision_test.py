"""Controlled edits to copies for document-integrity testing."""
from io import BytesIO

import fitz
from PIL import Image, ImageDraw, ImageFont

import pdf_redaction as core


def printable(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 120 or not value.strip() or not value.isprintable():
        raise ValueError("Enter a single non-empty value of up to 120 printable characters.")
    return value


def edit_pdf(raw, page_number, old_value, replacement, box=None):
    replacement = printable(replacement)
    if not replacement.isascii():
        raise ValueError("The test editor supports ASCII replacement text.")
    pages = core.render_source(raw)
    if type(page_number) is not int or not 1 <= page_number <= len(pages):
        raise ValueError("Choose an existing page.")
    index = page_number - 1
    if box is None:
        old_value = printable(old_value)
        if old_value == replacement:
            raise ValueError("Enter a different replacement value.")
        with fitz.open(stream=raw, filetype="pdf") as doc:
            page = doc[index]
            hits = page.search_for(old_value)
            if len(hits) != 1:
                raise ValueError("The original value must occur exactly once on the selected page.")
            bounds = hits[0]
            if page.get_textbox(bounds).strip() != old_value:
                raise ValueError("Select a complete extractable text value with matching capitalization.")
            font_size = min(12, bounds.height * 0.7, bounds.width / fitz.get_text_length(replacement, fontsize=1))
            if font_size < 4:
                raise ValueError("The replacement is too long for the original field.")
            page.add_redact_annot(bounds, text=replacement, fontname="helv", fontsize=font_size,
                                  fill=(1, 1, 1), text_color=(0, 0, 0))
            page.apply_redactions(images=0, graphics=0, text=0)
            if replacement not in page.get_textbox(bounds):
                raise ValueError("The replacement could not be placed in the field.")
            return doc.tobytes(garbage=4, deflate=True)

    w, h, pixels = pages[index]
    if (not isinstance(box, list) or len(box) != 4 or any(type(v) is not int for v in box)
            or not (0 <= box[0] < box[2] <= w and 0 <= box[1] < box[3] <= h)):
        raise ValueError("Select a rectangle inside the page.")
    x, y, right, bottom = box
    image = Image.frombytes("RGB", (w, h), pixels)
    area = image.crop((x, y, right, bottom))
    # The most common edge color represents the cell background on solid fills.
    edge = Image.new("RGB", (area.width, 2))
    edge.paste(area.crop((0, 0, area.width, 1)), (0, 0))
    edge.paste(area.crop((0, area.height - 1, area.width, area.height)), (0, 1))
    colors = edge.getcolors(edge.width * edge.height)
    background = max(colors)[1]
    patch = Image.new("RGB", area.size, background)
    draw = ImageDraw.Draw(patch)
    for size in range(min(20, patch.height), 5, -1):
        font = ImageFont.load_default(size=size)
        left, top, width, height = draw.textbbox((0, 0), replacement, font=font)
        text_width, text_height = width - left, height - top
        if text_width <= patch.width - 2 and text_height <= min(patch.height - 2, patch.height * 0.7):
            text_x = (patch.width - text_width) // 2 - left
            text_y = (patch.height - text_height) // 2 - top
            fill = "black" if sum(background) >= 384 else "white"
            draw.text((text_x, text_y), replacement, fill=fill, font=font)
            break
    else:
        raise ValueError("Select a larger rectangle or enter a shorter value.")
    # Replace pixels in the raster itself before building a fresh PDF.
    image.paste(patch, (x, y))
    pages[index] = (w, h, image.tobytes())
    return core.render_export(pages)


def page_preview(raw, page_number):
    pages = core.render_source(raw)
    if not 1 <= page_number <= len(pages):
        raise ValueError("Choose an existing page.")
    w, h, pixels = pages[page_number - 1]
    buffer = BytesIO()
    Image.frombytes("RGB", (w, h), pixels).save(buffer, format="PNG")
    return buffer.getvalue()
