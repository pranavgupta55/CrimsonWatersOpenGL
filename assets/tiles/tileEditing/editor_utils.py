import pygame
import math
from config import *


def get_hex_points(center_x, center_y, radius, squash):
    """Generates vertices for a pointy-topped hexagon with vertical squash."""
    points = []
    for i in range(6):
        angle_rad = (math.pi / 3) * i
        ox = radius * math.cos(angle_rad)
        oy = radius * math.sin(angle_rad)
        oy *= squash
        points.append((center_x + ox, center_y + oy))
    return points


def create_hex_mask_surface(width, height):
    """
    Creates a surface where the hexagon is white (255) and background is black (0).
    """
    surf = pygame.Surface((width, height))
    surf.fill((0, 0, 0))

    # Integer division for exact pixel centering on grid
    cx = width // 2

    # Bottom alignment logic
    base_hex_height = (TILE_RADIUS * 2) * SQUASH_FACTOR
    cy = height - (base_hex_height / 2)

    points = get_hex_points(cx, cy, TILE_RADIUS, SQUASH_FACTOR)
    pygame.draw.polygon(surf, (255, 255, 255), points)
    return surf


def is_point_in_hex(x, y, mask_surface):
    """Checks if a pixel coordinate is within the white area of the mask."""
    if 0 <= x < mask_surface.get_width() and 0 <= y < mask_surface.get_height():
        col = mask_surface.get_at((int(x), int(y)))
        return col[0] > 128
    return False


def generate_checkerboard(w, h, num_cells=25):
    """Generates the checkerboard background."""
    surf = pygame.Surface((w, h))
    surf.fill(Endesga.greyVD)

    cell_w = w / num_cells
    cell_h = cell_w * (5 / 4)

    colors = [Endesga.greyVD, Endesga.my_blue]

    for y in range(int(h / cell_h) + 1):
        for x in range(int(w / cell_w) + 1):
            c = colors[(x + y) % 2]
            if c == Endesga.greyVD:
                rect = pygame.Rect(x * cell_w, y * cell_h, cell_w, cell_h)
                pygame.draw.rect(surf, (40, 43, 50), rect)

    surf.set_alpha(30)
    return surf