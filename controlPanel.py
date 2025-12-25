import pygame
import os
import random


class GenerationInfo:
    waterThreshold = 0.505
    mountainThreshold = 0.5125

    tileSize = 36

    territorySize = 100

    mapSizeScalar = 1.5


class ResourceInfo:
    resourceTypes = ['wood', 'stone', 'iron', 'pine', 'amber']
    numResources = len(resourceTypes)

    spawnRates = {'wood': 0.021,
                  'stone': 0.014,
                  'iron': 0.025,
                  'pine': 0.005,
                  'amber': 0.006}

    @staticmethod
    def getSpawnableTiles(resourceType, tiles):
        spawnableTiles = {'wood': [t for t in tiles if t.isLand and not t.isMountain and not t.isCoast and (len(t.adjacent) == 6)],
                          'stone': [t for t in tiles if t.isLand and not t.isCoast and (len(t.adjacent) == 6)],
                          'iron': [t for t in tiles if t.isLand and t.isMountain and not t.isCoast and (len(t.adjacent) == 6)],
                          'pine': [t for t in tiles if t.isLand and not t.isMountain and not t.isCoast and (len(t.adjacent) == 6)],
                          'amber': [t for t in tiles if t.isLand and t.isMountain and not t.isCoast and (len(t.adjacent) == 6)]}
        return spawnableTiles[resourceType]


class StructureInfo:
    pass


class ShipInfo:
    shipTypes = ['fluyt', 'carrack', 'cutter', 'corsair', 'longShip', 'galleon']
    shipClasses = {'fluyt': 'TradeShip', 'carrack': 'TradeShip', 'cutter': 'Warship', 'corsair': 'Warship', 'longShip': 'LongShip', 'galleon': 'LongShip', }

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
    SQUASH_FACTOR = 0.6  # 2.5D Isometric Squash
    SPRITE_SCALE = 1.0  # Adjust based on raw image size vs tile size

    sprites = {}
    hit_mask_img = None

    @staticmethod
    def load_assets(tileSize):
        # Expected width is radius * 2
        # We perform scaling so sprites match the grid size

        target_w = int(tileSize * 2 * VisualAssets.SPRITE_SCALE)

        # Asset Map: internal_name -> (prefix, fallback_file)
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
            'amber': ('amber', 'amber1.png'),
            'default': ('defaultTileImg', 'defaultTileImg.png')
        }

        base_path = os.path.join("assets", "tiles")

        for key, (prefix, fallback) in asset_map.items():
            loaded_versions = []

            # Try to load indexed versions (name1.png, name2.png, etc.)
            index = 1
            while True:
                filename = f"{prefix}{index}.png"
                path = os.path.join(base_path, filename)
                if os.path.exists(path):
                    try:
                        img = pygame.image.load(path).convert()
                        img.set_colorkey((0, 0, 0))  # Assuming black background

                        # Scale logic
                        # We maintain aspect ratio but ensure width matches target
                        scale_ratio = target_w / img.get_width()
                        new_h = int(img.get_height() * scale_ratio)

                        # Faster blitting
                        scaled_surf = pygame.transform.scale(img, (target_w, new_h))
                        loaded_versions.append(scaled_surf)
                    except Exception as e:
                        print(f"Failed to load {filename}: {e}")
                    index += 1
                else:
                    break

            # If no indexed versions found, try fallback or default
            if not loaded_versions:
                path = os.path.join(base_path, fallback)
                if not os.path.exists(path):
                    path = os.path.join(base_path, 'defaultTileImg.png')

                if os.path.exists(path):
                    img = pygame.image.load(path).convert()
                    img.set_colorkey((0, 0, 0))
                    scale_ratio = target_w / img.get_width()
                    new_h = int(img.get_height() * scale_ratio)
                    loaded_versions.append(pygame.transform.scale(img, (target_w, new_h)))

            VisualAssets.sprites[key] = loaded_versions

        # Generate Hit Mask (Generic Hexagon shape for mouse picking)
        # We create a white hexagon on a transparent surface
        mask_h = int(target_w * VisualAssets.SQUASH_FACTOR)
        VisualAssets.hit_mask_img = pygame.Surface((target_w, mask_h), pygame.SRCALPHA)

        import math
        center = (target_w // 2, mask_h // 2)
        # Create a slightly smaller hex for precise picking
        size_mask = (target_w // 2) * 0.95
        points = []
        for i in range(6):
            angle_deg = 60 * i
            angle_rad = math.pi / 180 * angle_deg
            # Pointy top hex math
            px = center[0] + size_mask * math.cos(
                angle_rad)  # cos for pointy top width? No, pointy top usually involves 30 deg offset or sin/cos swap
            # Using flat top math for width, then point for height?
            # Standard: Width = sqrt(3)*size, Height = 2*size. 
            # Vertices for pointy top: (size * cos(30+60i), size * sin(30+60i))
            # But we are drawing to fit a rect.

            # Let's just use the vertices relative to center
            # Squash Y
            vx = center[0] + size_mask * math.cos(angle_rad)
            vy = center[1] + size_mask * math.sin(
                angle_rad) * VisualAssets.SQUASH_FACTOR  # Apply squash here? No, mask_h is already squashed
            # If mask_h is squashed, and we draw normal hex inside, it will look tall.
            # We want to draw a full hex inside the squashed rect.

            vx = center[0] + size_mask * math.cos(angle_rad)
            vy = center[1] + (size_mask * math.sin(angle_rad))

            points.append((vx, vy))

        pygame.draw.polygon(VisualAssets.hit_mask_img, (255, 255, 255), points)

    @staticmethod
    def get_ground_sprite(tile):
        if not tile.isLand:
            return 'water_shallow' if tile.isCoast else 'water_deep'
        if tile.isMountain:
            return 'stone'  # Base for mountains
        # Biome logic
        if tile.waterLand < 0.55:
            return 'sand'
        if tile.tile_id % 7 == 0:  # Random logic for variety, ideally seeded
            return 'forest'
        return 'plains'

    @staticmethod
    def get_structure_sprite(tile):
        # Check resources first
        # We need a way to check if a tile has a resource. 
        # In current logic, resources are in Territory.containedResources.
        # But we don't have easy access from 'tile' object back to resource object without searching.
        # We will assume generation attaches a 'resourceType' string to tile for visual lookup if present.

        if hasattr(tile, 'resourceType') and tile.resourceType:
            if tile.resourceType == 'wood': return 'forest'  # woodIcon is for UI, usually trees on map
            if tile.resourceType == 'pine': return 'pine'
            if tile.resourceType == 'stone': return 'stone'  # Rock cluster?
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