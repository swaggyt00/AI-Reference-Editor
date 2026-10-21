"""Measured reference effects: high-confidence white side panels and bright flashes.

These functions transfer shapes at the same reference FRAMES, not hallucinated VFX.
More involved tracking, perspective doors, blur and transitions are not yet handled.
"""
import cv2
import numpy as np


def white_edge_bounds(frame, width=320):
    """Normalized visible opening if flat white columns occlude image edges.

    False positives are reduced by requiring mostly-white outer columns,
    substantial nonwhite center content, and minimum mask width. Returns
    [0,1] when there is no obvious white side-panel overlay.
    """
    height, original_width = frame.shape[:2]
    if height < 8 or original_width < 8:
        return [0., 1.]
    small = cv2.resize(frame, (width, max(30, int(height*width/original_width))),
                       interpolation=cv2.INTER_AREA)
    # Require all three RGB/BGR channels very bright to reject tinted walls.
    is_white = (small.min(axis=2) >= 239).mean(axis=0) > .975
    left, right = 0, width-1
    while left < width-1 and is_white[left]:
        left += 1
    while right > 0 and is_white[right]:
        right -= 1
    if left < 4 and right > width-5:
        return [0., 1.]
    if right <= left or right-left < width*.12:
        return [0., 1.]
    # A washed-out reference shot is not itself a two-sided white wipe.
    center = small[:, max(left, width//3):min(right, width*2//3)]
    if not center.size or float((center.min(axis=2) < 210).mean()) < .04:
        return [0., 1.]
    return [round(left/width, 6), round((right+1)/width, 6)]


def apply_white_panels(frame, bounds):
    if not bounds or len(bounds) != 2:
        return frame
    width = frame.shape[1]
    left = int(round(max(0., min(1., float(bounds[0])))*width))
    right = int(round(max(0., min(1., float(bounds[1])))*width))
    if left:
        frame[:, :left, :] = 255
    if right < width:
        frame[:, right:, :] = 255
    return frame


def apply_reference_flash(frame, frame_number, events):
    """Only flash at confirmed measured frames, never generic transition FX."""
    for event in events or []:
        dt = abs(frame_number-int(event["frame"]))
        if dt > 2:
            continue
        strength = max(0., min(.8, float(event.get("strength", .4))))
        strength *= max(0, 1. - dt/3.)
        frame = np.clip(frame.astype(np.float32)*(1-strength)+255*strength, 0, 255).astype(np.uint8)
    return frame
