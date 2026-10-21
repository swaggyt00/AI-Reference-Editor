"""Measured reference effects: high-confidence white side panels and bright flashes.

These functions transfer shapes at the same reference FRAMES, not hallucinated VFX.
More involved tracking, perspective doors, blur and transitions are not yet handled.
"""
import cv2
import numpy as np


def white_edge_bounds(frame, width=320):
    """Detect relatively flat light-toned sliding doors at both image edges.

    Unlike a pure-white threshold, this detects the softly lit gray gradient
    panels in real reference clips. Still a conservative heuristic: only
    high-contrast, low-texture exterior occlusions can be transferred.
    """
    h, w = frame.shape[:2]
    if h < 8 or w < 8:
        return [0., 1.]
    sm = cv2.resize(frame, (width, max(30, round(h*width/w))),
                    interpolation=cv2.INTER_AREA)
    cropped = sm[15:-15].astype(np.float32)
    if not cropped.size:
        return [0., 1.]
    brightness = cropped.mean(axis=2)
    vertical_std = brightness.std(axis=0)
    median_luma = np.median(brightness, axis=0)
    average_chroma = (cropped.max(axis=2)-cropped.min(axis=2)).mean(axis=0)
    flat_lit = (vertical_std < 16) & (median_luma > 125) & (average_chroma < 90)
    left, right = 0, width-1
    while left < width-1 and flat_lit[left]:
        left += 1
    while right > 0 and flat_lit[right]:
        right -= 1
    if left < 4:
        left = 0
    if right > width-5:
        right = width-1
    if left < 4 and right > width-5:
        return [0., 1.]
    if right <= left or right-left < width*.12:
        return [0., 1.]
    center = sm[:, max(left,width//3):min(right+1,width*2//3)]
    if not center.size or float(center.std()) < 25:
        return [0., 1.]
    return [round(left/width, 6), round((right+1)/width, 6)]


def apply_white_panels(frame, bounds, reference_frame=None):
    """Overlay the ACTUAL panel pixels from the reference, preserving shadows.

    If the frame isn't available (e.g. standalone manual test), draw a simple
    fallback. Never blend the reference person into the scene's central window.
    """
    if not bounds or len(bounds) != 2:
        return frame
    width = frame.shape[1]
    left = int(round(max(0., min(1., float(bounds[0])))*width))
    right = int(round(max(0., min(1., float(bounds[1])))*width))
    if reference_frame is not None and reference_frame.shape[:2] != frame.shape[:2]:
        reference_frame = cv2.resize(reference_frame, (width, frame.shape[0]))
    if left:
        frame[:, :left, :] = (reference_frame[:, :left, :]
                              if reference_frame is not None else 255)
    if right < width:
        frame[:, right:, :] = (reference_frame[:, right:, :]
                               if reference_frame is not None else 255)
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
