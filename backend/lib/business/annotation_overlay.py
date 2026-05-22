def generate_annotation_svg(annotation: dict) -> str:
    """
    Generate an SVG overlay from annotation hints.
    Uses viewBox="0 0 100 100" with percentage-based coordinates so it
    scales over any image size.
    """
    if not annotation:
        return ""

    ann_type = annotation.get("type", "circle")
    x = float(annotation.get("position_x_pct", 50))
    y = float(annotation.get("position_y_pct", 50))
    color = annotation.get("color", "#f59e0b")
    label = annotation.get("label", "")

    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'viewBox="0 0 100 100" preserveAspectRatio="none" '
        'style="position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none">'
    ]

    if ann_type == "circle":
        parts.append(
            f'<circle cx="{x}" cy="{y}" r="7" fill="{color}" fill-opacity="0.18" '
            f'stroke="{color}" stroke-width="1.5"/>'
        )
        parts.append(
            f'<circle cx="{x}" cy="{y}" r="11" fill="none" '
            f'stroke="{color}" stroke-width="0.8" opacity="0.5"/>'
        )

    elif ann_type == "arrow":
        ax, ay = x - 14, y - 14
        parts.append(
            '<defs><marker id="ah" markerWidth="6" markerHeight="4" '
            'refX="5" refY="2" orient="auto">'
            f'<polygon points="0 0,6 2,0 4" fill="{color}"/></marker></defs>'
        )
        parts.append(
            f'<line x1="{ax}" y1="{ay}" x2="{x}" y2="{y}" '
            f'stroke="{color}" stroke-width="1.4" marker-end="url(#ah)"/>'
        )

    elif ann_type == "highlight":
        parts.append(
            f'<rect x="{x - 14}" y="{y - 4}" width="28" height="8" '
            f'fill="{color}" fill-opacity="0.35" rx="2"/>'
        )

    if label:
        lx = min(x + 9, 82)
        ly = y - 6
        char_w = 2.8
        box_w = len(label) * char_w + 5
        parts.append(
            f'<rect x="{lx}" y="{ly - 4.5}" width="{box_w}" height="6.5" '
            f'fill="{color}" rx="1.5"/>'
        )
        parts.append(
            f'<text x="{lx + 2.5}" y="{ly}" font-size="4" fill="white" '
            f'font-family="sans-serif">{label}</text>'
        )

    parts.append("</svg>")
    return "".join(parts)
