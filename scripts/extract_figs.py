"""Figure extraction, second attempt.

What the first version got wrong: it clipped the crop to the CAPTION's
horizontal extent. In a two-column paper the caption sits in one column while
the figure often spans both, so half of every wide figure was cut off. It also
trusted drawing bboxes that can run far outside the page.

This version finds the caption, then measures the actual graphic content above
it and crops to THAT bounding box.
"""
import re
import pymupdf

CAP = re.compile(r"^\s*(FIG\.?|Figure|Fig\.)\s*\.?\s*(\d+)\b", re.I)
REF = re.compile(r"^\s*(Figure|Fig\.)\s*\d+\s*(\([a-z]\))?\s*"
                 r"(shows|presents|illustrates|displays|summarizes|depicts|plots)", re.I)


def _elements(page):
    """Graphic boxes on the page, clamped to it. A drawing's rect can be
    absurd (one page reported x1 = 3473 on a 612pt page); unclamped it poisons
    both the area test and the bounding box."""
    pr = page.rect
    out = []
    for i in page.get_image_info():
        r = pymupdf.Rect(i["bbox"]) & pr
        if not r.is_empty and r.width > 8 and r.height > 8:
            out.append(("img", r))
    for d in page.get_drawings():
        r = pymupdf.Rect(d["rect"]) & pr
        if r.is_empty:
            continue
        # Clip paths and invisible containers come back as page-height boxes.
        # One PRB page carried four of them, (0,0,535,792) and friends, which
        # made every band's union the whole page. A figure whose caption sits
        # on the same page cannot be that tall.
        if r.height > 0.72 * pr.height:
            continue
        out.append(("vec", r))
    return out


def _cluster_above(hits, cap_y, bridges=(), gap=26, bridged_gap=70):
    """Group boxes into vertical bands and return the one nearest the caption.

    A page often carries several figures. Taking the union of everything above
    a caption merged a figure with its neighbour and swept in the running head.
    Walking up from the caption and stopping at the first real gap of
    whitespace keeps one figure.

    The gap is measured on graphics alone, and axis labels are text, so the
    space between two rows of panels can read as 40pt of whitespace when it is
    really full of tick numbers. A gap that a short text block spans is not a
    gap -- that is what cut Guo Fig. 3 in half, dropping panels a-c.
    """
    if not hits:
        return []
    rows = sorted(hits, key=lambda kr: -kr[1].y1)     # nearest the caption first
    cluster = [rows[0]]
    edge = rows[0][1].y0
    for k, r in rows[1:]:
        d = edge - r.y1
        if d > gap:
            filled = any(b.y0 < edge - 2 and b.y1 > r.y1 + 2 and
                         min(b.y1, edge) - max(b.y0, r.y1) > 0.35 * d
                         for b in bridges)
            if not filled or d > bridged_gap:
                break
        cluster.append((k, r))
        edge = min(edge, r.y0)
    return cluster


def _trim_side_strays(cluster, span, gap=18, frac=0.06):
    """Drop a thin strip at the left or right edge that belongs to the figure
    next door. Vertical clustering cannot see it: the neighbour's plot frame
    sits at the same height, so it joins the band and pushes the crop sideways.
    Only a group that is both separated by clear whitespace and negligible in
    area is removed, so a genuine narrow panel survives.
    """
    for _ in range(2):
        rs = sorted((r for _, r in cluster if not (r & span).is_empty),
                    key=lambda r: r.x0)
        if len(rs) < 2:
            break
        total = sum(r.get_area() for r in rs)
        cut = None
        reach = rs[0].x1
        for i, r in enumerate(rs[1:], 1):
            if r.x0 - reach > gap:
                left = sum(x.get_area() for x in rs[:i])
                right = total - left
                if left < frac * total:
                    cut = ("l", rs[i].x0)
                elif right < frac * total:
                    cut = ("r", reach)
                break
            reach = max(reach, r.x1)
        if cut is None:
            break
        side, x = cut
        span = pymupdf.Rect(x if side == "l" else span.x0, span.y0,
                            span.x1 if side == "l" else x, span.y1)
    return span


def _absorb_labels(page, span, cap_rect, grow=13):
    """Grow the box to take in axis ticks and panel letters.

    Those are TEXT, not drawings, so they sit outside every graphic bbox: the
    first crops of a full-page Nature figure cut the y-axis numbers off the left
    edge and the x-axis numbers off the bottom. Only short blocks that already
    touch the figure are taken, so body text in a neighbouring column stays out.
    """
    blocks = [b for b in page.get_text("blocks") if len(b[4].strip()) <= 100]
    # Bound the total growth. Absorbing iteratively let each newly widened box
    # reach one line further into the neighbouring column, and Guo Fig. 3 came
    # back with a strip of body text down its left edge.
    # Sideways is where the neighbouring column's text lives, so growth there is
    # kept tight; upward there is only the figure's own panel letters and colour
    # bars, so it gets more room.
    limit = pymupdf.Rect(span.x0 - 24, span.y0 - 46, span.x1 + 24, span.y1 + 24)
    head = page.rect.y0 + 0.045 * page.rect.height     # running head / folio
    for _ in range(3):
        near = pymupdf.Rect(span.x0 - grow, span.y0 - grow,
                            span.x1 + grow, span.y1 + grow)
        grew = False
        for x0, y0, x1, y1, txt, *_ in blocks:
            r = pymupdf.Rect(x0, y0, x1, y1)
            if r.y1 < head:
                continue
            if r.y1 > cap_rect.y0 - 1 or (r & near).is_empty or r in span:
                continue
            u = span | r
            # a block that would balloon the box is a paragraph, not a tick label
            if u.get_area() > 1.35 * span.get_area():
                continue
            span, grew = u, True
        if not grew:
            break
    return span & limit


def crop_for(page, cap_rect, els, look=470, pad=5):
    """The box to render for a caption, or None when there is no figure above.

    Searches the full page width, not the caption's width -- clipping to the
    caption cut every two-column-spanning figure in half -- then tightens to the
    cluster of graphics immediately above.
    """
    top = max(page.rect.y0, cap_rect.y0 - look)
    search = pymupdf.Rect(page.rect.x0, top, page.rect.x1, cap_rect.y0 - 2)
    if search.height < 50:
        return None

    hits = []
    for k, r in els:
        c = r & search
        if c.is_empty:
            continue
        # A running head's rule is page-wide and hairline; it is not a figure.
        if c.width > 0.8 * page.rect.width and c.height < 6:
            continue
        hits.append((k, c))
    if not hits:
        return None

    bridges = [pymupdf.Rect(b[0], b[1], b[2], b[3]) & search
               for b in page.get_text("blocks")
               if len(b[4].strip()) <= 100]
    bridges = [b for b in bridges if not b.is_empty]
    cluster = _cluster_above(hits, cap_rect.y0, bridges)
    img_area = sum(r.get_area() for k, r in cluster if k == "img")
    n_vec = sum(1 for k, r in cluster if k == "vec")
    span = cluster[0][1]
    for _, r in cluster[1:]:
        span |= r
    if img_area / max(span.get_area(), 1) < 0.05 and n_vec < 40:
        return None

    # Two figures can sit side by side with a caption under each, and vertical
    # clustering cannot separate them. When the caption is narrow -- i.e. it
    # belongs to one column -- keep only the part of the cluster in that column,
    # but only if a real figure survives. A figure that genuinely spans both
    # columns carries a full-width caption, so this leaves it alone.
    W = page.rect.width
    if (cap_rect.width < 0.65 * W) and span.width > 0.7 * W:
        col = pymupdf.Rect(cap_rect.x0 - 0.06 * W, span.y0,
                           cap_rect.x1 + 0.06 * W, span.y1)
        keep = [(k, r & col) for k, r in cluster if not (r & col).is_empty]
        if keep:
            sub = keep[0][1]
            for _, r in keep[1:]:
                sub |= r
            if sub.get_area() >= 0.3 * span.get_area() and sub.width > 80:
                span = sub

    span = _trim_side_strays(cluster, span)
    span = _absorb_labels(page, span, cap_rect)
    box = pymupdf.Rect(span.x0 - pad, span.y0 - pad,
                       span.x1 + pad, span.y1 + pad) & page.rect
    box.y1 = min(box.y1, cap_rect.y0 - 2)

    # The padding can bite into the body text of the neighbouring column: a few
    # points is enough to leave a column of half-letters down the edge. Pull the
    # edge back off any paragraph it clips.
    for x0, y0, x1, y1, txt, *_ in page.get_text("blocks"):
        if len(txt.strip()) <= 100:
            continue
        if y1 <= box.y0 or y0 >= box.y1:
            continue
        if x0 < box.x0 < x1 < box.x1:
            box.x0 = x1 + 1
        elif box.x0 < x0 < box.x1 < x1:
            box.x1 = x0 - 1

    return box if box.width > 60 and box.height > 50 else None


def extract(path, outdir, dpi=150):
    import os
    os.makedirs(outdir, exist_ok=True)
    doc = pymupdf.open(path)
    best = {}
    for pno in range(doc.page_count):
        page = doc[pno]
        els = _elements(page)
        for x0, y0, x1, y1, txt, *_ in page.get_text("blocks"):
            m = CAP.match(txt)
            if not m or REF.match(txt):
                continue
            box = crop_for(page, pymupdf.Rect(x0, y0, x1, y1), els)
            if box is None:
                continue
            n = int(m.group(2))
            score = box.get_area()
            if n in best and best[n]["score"] >= score:
                continue
            best[n] = {"score": score, "page": pno, "box": box,
                       "caption": " ".join(txt.split())}
    figs = []
    for n in sorted(best):
        b = best[n]
        fn = f"{outdir}/fig{n:02d}.png"
        doc[b["page"]].get_pixmap(clip=b["box"], dpi=dpi).save(fn)
        figs.append({"n": n, "page": b["page"] + 1, "file": fn,
                     "caption": b["caption"], "box": tuple(round(v) for v in b["box"])})
    text = "\n".join(p.get_text() for p in doc)
    open(f"{outdir}/fulltext.txt", "w", encoding="utf-8").write(text)
    return figs, text
