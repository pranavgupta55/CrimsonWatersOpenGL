import pygame
import os
import random


class HexConstants:
    # --- GLOBAL SCALAR ---
    # Change this to 2, 3, 4 etc. to scale the game up while keeping resolution
    SPRITE_SCALE = 2

    # --- BASE DIMENSIONS (Do not change these, they match the source art) ---
    _BASE_WIDTH = 20
    _BASE_HEIGHT_STEP = 14
    _BASE_TOTAL_HEIGHT = 26  # Face + Depth
    _BASE_DEPTH = 8
    _BASE_LAND_ELEVATION = 0

    # --- SCALED DIMENSIONS (Use these in logic) ---
    WIDTH = _BASE_WIDTH * SPRITE_SCALE
    HEIGHT_STEP = _BASE_HEIGHT_STEP * SPRITE_SCALE
    TOTAL_HEIGHT = _BASE_TOTAL_HEIGHT * SPRITE_SCALE
    DEPTH = _BASE_DEPTH * SPRITE_SCALE
    LAND_ELEVATION = _BASE_LAND_ELEVATION * SPRITE_SCALE


class GenerationInfo:
    waterThreshold = 0.505
    mountainThreshold = 0.5125

    # Deprecated size reference, kept for scaler calculations in main
    tileSize = 36

    territorySize = 100
    mapSizeScalar = 1.5

    territoryBorderAlpha = 180
    territoryFillAlpha = 60
    territoryBorderWidth = 3 * HexConstants.SPRITE_SCALE


class ResourceInfo:
    resourceTypes = ['wood', 'stone', 'iron', 'pine', 'amber']
    numResources = len(resourceTypes)

    spawnRates = {'wood': 0.021, 'stone': 0.014, 'iron': 0.025, 'pine': 0.005, 'amber': 0.006}

    @staticmethod
    def getSpawnableTiles(resourceType, tiles):
        # Restored the check for (len(t.adjacent) == 6) to prevent edge spawning
        spawnableTiles = {
            'wood': [t for t in tiles if t.isLand and not t.isMountain and not t.isCoast and (len(t.adjacent) == 6)],
            'stone': [t for t in tiles if t.isLand and not t.isCoast and (len(t.adjacent) == 6)],
            'iron': [t for t in tiles if t.isLand and t.isMountain and not t.isCoast and (len(t.adjacent) == 6)],
            'pine': [t for t in tiles if t.isLand and not t.isMountain and not t.isCoast and (len(t.adjacent) == 6)],
            'amber': [t for t in tiles if t.isLand and t.isMountain and not t.isCoast and (len(t.adjacent) == 6)]
        }
        return spawnableTiles.get(resourceType, [])


class StructureInfo:
    pass


class ShipInfo:
    shipTypes = ['fluyt', 'carrack', 'cutter', 'corsair', 'longShip', 'galleon']
    shipClasses = {'fluyt': 'TradeShip', 'carrack': 'TradeShip', 'cutter': 'Warship', 'corsair': 'Warship',
                   'longShip': 'LongShip', 'galleon': 'LongShip', }

    shipHPs = {'fluyt': 50, 'carrack': 100, 'cutter': 75, 'corsair': 90, 'longShip': 80, 'galleon': 120}
    shipMSs = {'fluyt': 0.3, 'carrack': 0.2, 'cutter': 0.4, 'corsair': 0.35, 'longShip': 0.25, 'galleon': 0.15}
    shipVisionRanges = {'fluyt': 24, 'carrack': 20, 'cutter': 16, 'corsair': 18, 'longShip': 22, 'galleon': 18}
    shipDMGs = {'fluyt': 0, 'carrack': 0, 'cutter': 15, 'corsair': 25, 'longShip': 10, 'galleon': 20}
    shipAttackRanges = {'fluyt': 0, 'carrack': 0, 'cutter': 3, 'corsair': 4, 'longShip': 2, 'galleon': 3}
    shipStorageCapacities = {'fluyt': 150, 'carrack': 200, 'cutter': 0, 'corsair': 0, 'longShip': 100, 'galleon': 250}

    # Scale ship sizes by the global scalar
    shipSizes = {
        'fluyt': 35 * HexConstants.SPRITE_SCALE,
        'carrack': 40 * HexConstants.SPRITE_SCALE,
        'cutter': 30 * HexConstants.SPRITE_SCALE,
        'corsair': 35 * HexConstants.SPRITE_SCALE,
        'longShip': 35 * HexConstants.SPRITE_SCALE,
        'galleon': 50 * HexConstants.SPRITE_SCALE
    }


class uiInfo:
    bottomUIBarSize = 0.07


class Cols:
    oceanBlue = [59, 95, 111]
    oceanGreen = [73, 120, 122]
    lightOceanGreen = [86, 142, 143]
    oceanFoam = [148, 182, 180]
    sandyBrown = [172, 146, 95]
    darkSandyBrown = [159, 143, 91]
    oliveGreen = [95, 115, 84]
    darkOliveGreen = [54, 64, 57]
    mountainBlue = (83, 78, 90)
    darkMountainBlue = [42, 40, 52]
    light = [220, 216, 201]
    dark = [19, 21, 22]
    crimson = [94, 32, 47]
    brightCrimson = [85, 42, 56]
    cloudLight = [176, 185, 205]
    cloudMedium = [124, 134, 156]
    cloudDark = [105, 116, 140]
    debugRed = [255, 96, 141]


class VisualAssets:
    SQUASH_FACTOR = 0.6  # Kept for compatibility

    sprites = {}
    hit_mask_img = None

    @staticmethod
    def load_assets(tileSize=None):
        # We ignore tileSize input now, relying on HexConstants
        target_w = HexConstants.WIDTH
        target_h = HexConstants.TOTAL_HEIGHT

        asset_map = {
            'water_deep': ('deepWater', 'deepWater1.png'),
            'water_shallow': ('shallowWater', 'shallowWater1.png'),
            'sand': ('sand', 'sand1.png'),
            'plains': ('plains', 'plains1.png'),
            'mountain': ('mountains', 'mountains1.png'),

            'forest': ('forest', 'forest1.png'),
            'stone': ('stone', 'stone1.png'),
            'pine': ('pine', 'pine1.png'),
            'iron': ('iron', 'iron1.png'),
            'amber': ('amber', 'defaultTileImg.png'),

            'default': ('defaultTileImg', 'defaultTileImg.png')
        }

        base_path = os.path.join("assets", "tiles")

        for key, (prefix, fallback) in asset_map.items():
            loaded_versions = []
            index = 1
            while True:
                filename = f"{prefix}{index}.png"
                path = os.path.join(base_path, filename)
                if os.path.exists(path):
                    try:
                        img = pygame.image.load(path).convert_alpha()
                        # --- FIX FOR PATCHY OFFSETS ---
                        # Force exact dimensions. Do not preserve aspect ratio if source is off by 1px.
                        if img.get_width() != target_w or img.get_height() != target_h:
                            img = pygame.transform.scale(img, (target_w, target_h))
                        loaded_versions.append(img)
                    except Exception as e:
                        print(f"Failed to load {filename}: {e}")
                    index += 1
                else:
                    break

            if not loaded_versions:
                path = os.path.join(base_path, fallback)
                if not os.path.exists(path):
                    path = os.path.join(base_path, 'defaultTileImg.png')
                if os.path.exists(path):
                    try:
                        img = pygame.image.load(path).convert_alpha()
                        if img.get_width() != target_w or img.get_height() != target_h:
                            img = pygame.transform.scale(img, (target_w, target_h))
                        loaded_versions.append(img)
                    except:
                        pass

            VisualAssets.sprites[key] = loaded_versions

        # Generate Hit Mask based on SCALED editor coordinates
        VisualAssets.hit_mask_img = pygame.Surface((target_w, target_h), pygame.SRCALPHA)
        s = HexConstants.SPRITE_SCALE

        # Exact Face Coordinates from Editor scaled up
        face_poly = [
            (8 * s, 0 * s), (11 * s, 0 * s),  # Top
            (19 * s, 4 * s), (19 * s, 13 * s),  # Right
            (11 * s, 17 * s), (8 * s, 17 * s),  # Bottom
            (0 * s, 13 * s), (0 * s, 4 * s)  # Left
        ]
        pygame.draw.polygon(VisualAssets.hit_mask_img, (255, 255, 255), face_poly)

    @staticmethod
    def get_ground_sprite(tile):
        if not tile.isLand:
            if tile.waterLand < 0.35:
                return 'water_deep'
            else:
                return 'water_shallow'

        if tile.isMountain:
            return 'mountain'

        if tile.waterLand < 0.55:
            return 'sand'

        if tile.tile_id % 7 == 0:
            return 'forest'

        return 'plains'

    @staticmethod
    def get_structure_sprite(tile):
        if hasattr(tile, 'resourceType') and tile.resourceType:
            if tile.resourceType == 'wood': return 'forest'
            if tile.resourceType == 'pine': return 'pine'
            if tile.resourceType == 'stone': return 'stone'
            if tile.resourceType == 'iron': return 'iron'
            if tile.resourceType == 'amber': return 'amber'
        return None

    @staticmethod
    def get_random_version(key):
        versions = VisualAssets.sprites.get(key)
        if versions:
            return random.choice(versions)
        return None