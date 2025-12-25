import pygame
from config import *

def createHexMaskSurface(width, height):
    """
    Creates the clickable area based on hardcoded coordinates.
    Red = Face, Green = Depth.
    """
    surf = pygame.Surface((width, height), pygame.SRCALPHA)
    surf.fill((0, 0, 0, 0))

    # --- COORDINATES ---
    face_poly = [
        (8, 0), (11, 0),    # Top Edge
        (19, 4), (19, 13),  # Right Edge
        (11, 17), (8, 17),  # Bottom Edge
        (0, 13), (0, 4)     # Left Edge
    ]

    depth_poly = [
        (0, 13), (8, 17), (11, 17), (19, 13), # Top seam (Face Bottom)
        (19, 21), (11, 25), (8, 25), (0, 21)  # Bottom of depth
    ]

    # Draw Depth (Green)
    pygame.draw.polygon(surf, (0, 255, 0, 255), depth_poly)
    # Draw Face (Red)
    pygame.draw.polygon(surf, (255, 0, 0, 255), face_poly)

    return surf

def isPointInMask(x, y, maskSurface):
    """Returns True if pixel is paintable (Face or Depth)."""
    if 0 <= x < maskSurface.get_width() and 0 <= y < maskSurface.get_height():
        col = maskSurface.get_at((int(x), int(y)))
        return col.a > 0
    return False

def generateCheckerboard(w, h, numCells=25):
    surf = pygame.Surface((w, h))
    surf.fill(Endesga.greyVD)
    cellW = w / numCells
    cellH = cellW
    colors = [Endesga.greyVD, Endesga.my_blue]
    for y in range(int(h / cellH) + 1):
        for x in range(int(w / cellW) + 1):
            c = colors[(x + y) % 2]
            if c == Endesga.greyVD:
                rect = pygame.Rect(x * cellW, y * cellH, cellW, cellH)
                pygame.draw.rect(surf, (40, 43, 50), rect)
    return surf