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
    greyVVDB = (5, 10, 15)
    very_light_blue = (199, 207, 221)
    my_blue = (32, 36, 46) # Updated to Framework
    debug_red = (255, 96, 141)
    sebastian_lague_purple = (70, 74, 124)
    sebastian_lague_light_purple = (137, 133, 181)
    network_green = (64, 128, 67)
    network_red = (127, 45, 41)

    # Editor Specific Status
    statusNew = (100, 200, 120)
    statusMod = (230, 200, 80)

# Expanded 6x4 Palette (24 Colors)
PALETTE = [
    Endesga.black, Endesga.greyVD, Endesga.greyD, Endesga.grey, Endesga.greyL, Endesga.white,
    Endesga.maroon_red, Endesga.lighter_maroon_red, Endesga.debug_red, Endesga.light_brown, Endesga.cream, Endesga.very_light_blue,
    Endesga.dark_green, Endesga.network_green, (50, 168, 82), (100, 255, 100), Endesga.grey_blue, Endesga.sebastian_lague_purple,
    Endesga.sebastian_lague_light_purple, (0, 0, 255), (0, 255, 255), (255, 255, 0), (255, 128, 0), (128, 0, 255)
]

# --- HARDCODED GEOMETRY ---
# Width: 0 to 19 = 20 pixels
# Height: Face (0 to 17) + Depth (8) = 26 pixels (0 to 25)
CANVAS_WIDTH = 20
CANVAS_HEIGHT = 26

# Editor Settings
FPS = 60
WINDOW_SIZE = (1400, 800)
CAMERA_SPEED = 5

# Apollo palette (converted from Paint.NET ARGB hex list -> RGB tuples)
# Original hexes had the format AARRGGBB (leading FF alpha). Alpha is ignored.
APOLLO_HEX = [
    "FF172038","FF253a5e","FF3c5e8b","FF4f8fba","FF73bed3","FFa4dddb",
    "FF19332d","FF25562e","FF468232","FF75a743","FFa8ca58","FFd0da91",
    "FF4d2b32","FF7a4841","FFad7757","FFc09473","FFd7b594","FFe7d5b3",
    "FF341c27","FF602c2c","FF884b2b","FFbe772b","FFde9e41","FFe8c170",
    "FF241527","FF411d31","FF752438","FFa53030","FFcf573c","FFda863e",
    "FF1e1d39","FF402751","FF7a367b","FFa23e8c","FFc65197","FFdf84a5",
    "FF090a14","FF10141f","FF151d28","FF202e37","FF394a50","FF577277",
    "FF819796","FFa8b5b2","FFc7cfcc","FFebede9"
]

APOLLO_PALETTE = [
    (23,  32,  56),  # FF172038
    (37,  58,  94),  # FF253a5e
    (60,  94, 139),  # FF3c5e8b
    (79, 143, 186),  # FF4f8fba
    (115,190,211),   # FF73bed3
    (164,221,219),   # FFa4dddb
    (25,  51,  45),  # FF19332d
    (37,  86,  46),  # FF25562e
    (70, 130, 50),   # FF468232
    (117,167,67),    # FF75a743
    (168,202,88),    # FFa8ca58
    (208,218,145),   # FFd0da91
    (77,  43,  50),  # FF4d2b32
    (122,72,  65),   # FF7a4841
    (173,119,87),    # FFad7757
    (192,148,115),   # FFc09473
    (215,181,148),   # FFd7b594
    (231,213,179),   # FFe7d5b3
    (52,  28,  39),  # FF341c27
    (96,  44,  44),  # FF602c2c
    (136,75,  43),   # FF884b2b
    (190,119,43),    # FFbe772b
    (222,158,65),    # FFde9e41
    (232,193,112),   # FFe8c170
    (36,  21,  39),  # FF241527
    (65,  29,  49),  # FF411d31
    (117,36,  56),   # FF752438
    (165,48,  48),   # FFa53030
    (207,87,  60),   # FFcf573c
    (218,134,62),    # FFda863e
    (30,  29,  57),  # FF1e1d39
    (64,  39,  81),  # FF402751
    (122,54, 123),   # FF7a367b
    (162,62, 140),   # FFa23e8c
    (198,81, 151),   # FFc65197
    (223,132,165),   # FFdf84a5
    (9,   10,  20),  # FF090a14
    (16,  20,  31),  # FF10141f
    (21,  29,  40),  # FF151d28
    (32,  46,  55),  # FF202e37
    (57,  74,  80),  # FF394a50
    (87,  114, 119), # FF577277
    (129,151,150),   # FF819796
    (168,181,178),   # FFa8b5b2
    (199,207,204),   # FFc7cfcc
    (235,237,233)    # FFebede9
]
