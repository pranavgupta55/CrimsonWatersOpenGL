import pygame
import os
import random


class HexConstants:
    # HARDCODED FROM EDITOR CONFIG
    # The image width is exactly 20 pixels
    WIDTH = 20
    # The vertical step between rows is exactly 14 pixels
    HEIGHT_STEP = 14
    # The visual depth of the tile (the 3D part hanging down)
    DEPTH = 8
    # Elevation offset for land tiles (negative Y moves up)
    LAND_ELEVATION = -4


class GenerationInfo:
    waterThreshold = 0.505
    mountainThreshold = 0.5125

    # Deprecated size reference, kept for scaler calculations in main
    tileSize = 36

    territorySize = 100
    mapSizeScalar = 1.5


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
    shipSizes = {'fluyt': 35, 'carrack': 40, 'cutter': 30, 'corsair': 35, 'longShip': 35, 'galleon': 50}


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
    SQUASH_FACTOR = 0.6  # Kept for compatibility, though dimensions are now hardcoded
    SPRITE_SCALE = 1.0

    sprites = {}
    hit_mask_img = None

    @staticmethod
    def load_assets(tileSize=None):
        # We ignore tileSize input now, relying on HexConstants
        target_w = HexConstants.WIDTH

        asset_map = {
            'water_deep': ('deepWater', 'deepWater1.png'),
            'water_shallow': ('shallowWater', 'shallowWater1.png'),
            'sand': ('sand', 'sand1.png'),
            'plains': ('plains', 'plains1.png'),
            'forest': ('forest', 'forest1.png'),
            'stone': ('stone', 'stone1.png'),
            'mountain': ('mountains', 'mountains1.png'),
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
                        # If assets are raw pixel art (20px wide), use as is.
                        # If they are high res, scale them down.
                        if img.get_width() != target_w:
                            scale_ratio = target_w / img.get_width()
                            new_h = int(img.get_height() * scale_ratio)
                            img = pygame.transform.scale(img, (target_w, new_h))
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
                        if img.get_width() != target_w:
                            scale_ratio = target_w / img.get_width()
                            new_h = int(img.get_height() * scale_ratio)
                            img = pygame.transform.scale(img, (target_w, new_h))
                        loaded_versions.append(img)
                    except:
                        pass

            VisualAssets.sprites[key] = loaded_versions

        # Generate Hit Mask based on exact editor coordinates for the Face
        # The face is roughly 18px tall within the 20x26 rect
        VisualAssets.hit_mask_img = pygame.Surface((HexConstants.WIDTH, 26), pygame.SRCALPHA)

        # Exact Face Coordinates from Editor
        face_poly = [
            (8, 0), (11, 0),  # Top Edge
            (19, 4), (19, 13),  # Right Edge
            (11, 17), (8, 17),  # Bottom Edge
            (0, 13), (0, 4)  # Left Edge
        ]
        pygame.draw.polygon(VisualAssets.hit_mask_img, (255, 255, 255), face_poly)

    @staticmethod
    def get_ground_sprite(tile):
        # Determine sprite based on noise values (diffusion map)
        if not tile.isLand:
            # Water: Deep vs Shallow based on diffusion value
            # waterThreshold is ~0.505.
            # Lower values are "deeper" (further from land seeds)
            if tile.waterLand < 0.35:
                return 'water_deep'
            else:
                return 'water_shallow'

        if tile.isMountain:
            return 'stone'

            # Land Biomes based on noise
        # Lower waterLand on land means "dryer" or "higher" depending on interpretation,
        # but here we use it for biome variation.
        # waterLand >= 0.505 is land.
        if tile.waterLand < 0.55:
            return 'sand'  # Beaches

        # Simple noise seeded randomization for forests if no resource present
        # This keeps some texture variety
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
        if tile.isMountain:
            return 'mountain'
        return None

    @staticmethod
    def get_random_version(key):
        versions = VisualAssets.sprites.get(key)
        if versions:
            return random.choice(versions)
        return None