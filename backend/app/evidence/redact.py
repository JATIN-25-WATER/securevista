import cv2


def apply_redaction(frame, bboxes_normalized: list[list[float]]):
    """Gaussian-blurs each given normalized bbox region in place. Used to
    build the wide-access redacted preview from an evidence frame."""
    h, w = frame.shape[:2]
    for bbox in bboxes_normalized:
        x1, y1, x2, y2 = bbox
        px1, py1 = max(0, int(x1 * w)), max(0, int(y1 * h))
        px2, py2 = min(w, int(x2 * w)), min(h, int(y2 * h))
        if px2 <= px1 or py2 <= py1:
            continue
        region = frame[py1:py2, px1:px2]
        ksize = max(15, (min(region.shape[:2]) // 2) | 1)  # odd kernel size, scales with box
        frame[py1:py2, px1:px2] = cv2.GaussianBlur(region, (ksize, ksize), 0)
    return frame
