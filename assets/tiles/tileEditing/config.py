import pygame


# --- COLORS (Matching Framework/Endesga) ---
class Endesga:
    maroon_red = (87, 28, 39)
    lighter_maroon_red = (127, 36, 51)
    dark_green = (9, 26, 23)
    light_brown = (191, 111, 74)
    black = (19, 19, 19)
    grey_blue = (66, 76, 110)
    cream = (237, 171, 80)
    white = (255, 255, 255)
    greyL = (200, 200, 200)
    grey = (150, 150, 150)
    greyD = (100, 100, 100)
    greyVD = (50, 50, 50)
    very_light_blue = (199, 207, 221)
    my_blue = [7, 15, 21]
    debug_red = (255, 96, 141)
    crimson = (94, 32, 47)

    # Status Colors
    status_new = (100, 200, 120)  # Greenish
    status_mod = (230, 200, 80)  # Yellowish


# Combined palette for the color picker
PALETTE = [
    Endesga.black, Endesga.white, Endesga.maroon_red, Endesga.lighter_maroon_red,
    Endesga.dark_green, Endesga.light_brown, Endesga.grey_blue, Endesga.cream,
    Endesga.greyL, Endesga.grey, Endesga.greyD, Endesga.greyVD,
    Endesga.very_light_blue, Endesga.my_blue, Endesga.debug_red,
    Endesga.crimson, (0, 255, 0), (0, 0, 255), (255, 255, 0), (0, 255, 255)
]

# --- MATH CONSTANTS ---
TILE_RADIUS = 12
SQUASH_FACTOR = 0.6

# The raw image size (+1 for symmetry)
TARGET_WIDTH = int(TILE_RADIUS * 2) + 1
TARGET_HEIGHT = int(TARGET_WIDTH * SQUASH_FACTOR) + 8

# --- EDITOR SETTINGS ---
FPS = 60
WINDOW_SIZE = (1280, 720)
SIDEBAR_WIDTH = 250
CAMERA_SPEED = 5