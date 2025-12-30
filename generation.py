import pygame
import math
import random
import numpy as np
from sklearn.cluster import KMeans
from collections import deque
from text import drawText
from calcs import distance, ang, normalize_angle, draw_arrow, linearGradient, normalize
from territory import Territory
from locationalObjects import Resource, Harbor
import time
import multiprocessing
from concurrent.futures import ThreadPoolExecutor
from controlPanel import GenerationInfo, VisualAssets, HexConstants
import os
import sys

# Global check for Shapely
try:
    from shapely.geometry import Polygon
    import shapely.wkb

    SHAPELY_AVAILABLE = True
except ImportError:
    SHAPELY_AVAILABLE = False


class Hex:
    __slots__ = (
        'grid_x', 'grid_y', 'x', 'y', 'tile_id', 'col', 'cloudCol',
        'center', 'hex', 'floatHexVertices',
        'adjacent_tile_ids', 'territory_id', 'adjacent', 'territory',
        'region', 'mountainRegion', 'regionCol',
        'waterLand', 'mountainous', 'cloudy',
        'isLand', 'isMountain', 'isCoast',
        'connectedOceanID', 'cloudOpacity', 'precomp_chunk_coords',
        'resourceType', 'draw_y_offset', 'size'
    )

    def __init__(self, grid_x, grid_y, tile_id, col=(0, 0, 0), cloudCol=(50, 50, 50)):
        self.tile_id = tile_id
        self.grid_x = grid_x
        self.grid_y = grid_y
        self.col = col
        self.cloudCol = cloudCol

        # --- DISCRETE PIXEL MATH (Matching Editor) ---
        self.x = self.grid_x * HexConstants.WIDTH
        if self.grid_y % 2 != 0:
            self.x += HexConstants.WIDTH // 2
        self.y = self.grid_y * HexConstants.HEIGHT_STEP

        # Logic center (visual center of face)
        self.center = [self.x + HexConstants.WIDTH // 2, self.y + 9]  # 9 is approx half of face height 18

        # --- COMPATIBILITY ATTRIBUTE ---
        # LocationalObjects and Ships rely on tile.size for radius-based math
        # Width = 20. If Width approx 2*size (pointy) or sqrt(3)*size (flat).
        # We assume 10.0 for logic radius.
        self.size = 10.0

        self.calculate_geometry()

        self.adjacent_tile_ids = []
        self.adjacent = []
        self.territory_id = -1
        self.territory = None
        self.resourceType = None

        self.region = None
        self.mountainRegion = None
        self.regionCol = None
        self.waterLand = random.random()
        self.mountainous = random.random()
        self.cloudy = random.random()

        self.isLand = False
        self.isMountain = False
        self.isCoast = False
        self.connectedOceanID = -1
        self.cloudOpacity = 1.0
        self.precomp_chunk_coords = None
        self.draw_y_offset = 0

    def calculate_geometry(self):
        # Precise polygon coordinates matching Editor for Territory Borders
        # Top-Left is (self.x, self.y)
        face_poly = [
            (8, 0), (11, 0),  # Top
            (19, 4), (19, 13),  # Right
            (11, 17), (8, 17),  # Bottom
            (0, 13), (0, 4)  # Left
        ]

        self.hex = [(self.x + p[0], self.y + p[1]) for p in face_poly]
        self.floatHexVertices = [(float(p[0]), float(p[1])) for p in self.hex]

    def draw(self, s):
        # Fallback debug draw
        pygame.draw.polygon(s, self.col, self.hex)


class TileHandler:
    def __init__(self, target_map_width, target_map_height, size_ignored, cols, waterThreshold=0.51,
                 mountainThreshold=0.51,
                 territorySize=100, font=None, font_name=None, resource_info=None, structure_info=None,
                 status_queue: multiprocessing.Queue = None, preset_times: dict = None, seed: int = None,
                 viewport_width=0, viewport_height=0):

        self.execution_times = {}
        self.status_queue = status_queue
        self.preset_times = preset_times if preset_times else {}

        self.seed = seed
        if self.seed is not None:
            random.seed(self.seed)
            np.random.seed(self.seed)
            print(f"WORKER STDOUT: Initialized TileHandler with provided seed: {self.seed}")
        else:
            self.seed = random.randint(0, 2 ** 32 - 1)
            random.seed(self.seed)
            np.random.seed(self.seed)
            print(f"WORKER STDOUT: Initialized TileHandler with new random seed: {self.seed}")

        self.cols = cols
        self.font = font
        self.font_name = font_name
        self.resource_info = resource_info
        self.structure_info = structure_info
        self.territorySize = territorySize
        self.waterThreshold = waterThreshold
        self.mountainThreshold = mountainThreshold
        self.borderSize = 0

        # Hardcoded size for logic consistency
        self.size = 10.0

        self.gridSizeX = int(target_map_width / HexConstants.WIDTH)
        self.gridSizeY = int(target_map_height / HexConstants.HEIGHT_STEP)

        self.mapWidth = self.gridSizeX * HexConstants.WIDTH + (HexConstants.WIDTH // 2)
        self.mapHeight = self.gridSizeY * HexConstants.HEIGHT_STEP + HexConstants.DEPTH + 20

        self.viewportWidth = viewport_width
        self.viewportHeight = viewport_height

        self.tiles = []
        self.tiles_by_id = {}
        self.tiles_by_grid_coords = {}
        self.territories_by_id = {}
        self.harbors_by_id = {}
        self.contiguousTerritoryIDs = []
        self.all_territories_for_unpickling = []
        self.oceanTiles = {}
        self._ocean_id_map = {}
        self._ocean_water = {}
        self.allWaterTiles = []
        self.allLandTiles = []
        self.allCoastalTiles = []
        self.allHarbors = None
        self.baseMapSurf = None
        self.debugOverlayFullMap = None
        self.territoryHighlightSurfScreen = None
        self.playersSurfScreen = None
        self.hitMaskSurf = None
        self._temp_contiguous_territories_objs = None

        self.STEP_NAMES = {"TILE_GEN": "tileGen", "LINK_ADJ": "linkAdj", "GEN_CYCLES": "generationCycles",
                           "SET_COLORS": "setTileColors", "FIND_REGIONS": "findLandRegionsParallel",
                           "INDEX_OCEANS": "indexOceansParallel", "ASSIGN_COAST": "assignCoastTiles",
                           "CREATE_TERR": "createTerritories", "CONNECT_HARBORS": "connectHarborsParallel",
                           "TOTAL_INIT": "workerInit", "PREP_PICKLING": "dataSerialization",
                           "GFX_TOTAL_INIT": "gfxTotalInit"}

    def run_generation_sequence(self):
        total_init_start_time_timer = time.time()
        landRegionsRaw_result = None

        def _run_step_sequential(step_key, func_to_run, *args):
            step_full_name = self.STEP_NAMES[step_key]
            expected_time = self.preset_times.get(step_full_name, 999.0)
            if self.status_queue:
                self.status_queue.put_nowait((step_full_name, "START", expected_time))

            s_time = time.time()
            result = func_to_run(*args)
            duration = time.time() - s_time

            self.execution_times[step_full_name] = duration
            if self.status_queue:
                self.status_queue.put_nowait((step_full_name, "FINISHED", duration))
            return result

        def _threaded_task_wrapper(step_key, func, *args):
            return _run_step_sequential(step_key, func, *args)

        internal_executor = ThreadPoolExecutor(max_workers=os.cpu_count() or 1)

        _run_step_sequential("TILE_GEN", self.generateTiles)
        _run_step_sequential("LINK_ADJ", self._link_adjacent_objects)
        _run_step_sequential("GEN_CYCLES", lambda: [self.generationCycle() for _ in range(50)])
        _run_step_sequential("SET_COLORS", self.setTileCols)

        find_regions_future = internal_executor.submit(_threaded_task_wrapper, "FIND_REGIONS",
                                                       self.findContiguousRegions,
                                                       [t for t in self.tiles if t.waterLand >= self.waterThreshold])
        index_oceans_future = internal_executor.submit(_threaded_task_wrapper, "INDEX_OCEANS", self.indexOceans)

        landRegionsRaw_result = find_regions_future.result()
        index_oceans_future.result()

        assign_coast_future = internal_executor.submit(_threaded_task_wrapper, "ASSIGN_COAST", self.assignCoastTiles)
        assign_coast_future.result()

        _run_step_sequential("CREATE_TERR", lambda: self.createTerritories(landRegionsRaw_result))

        connect_harbors_future = internal_executor.submit(_threaded_task_wrapper, "CONNECT_HARBORS",
                                                          self.connectTerritoryHarbors)
        connect_harbors_future.result()

        for t in self.tiles:
            if hasattr(t.territory, 'containedResources'):
                for res in t.territory.containedResources:
                    if res.tile == t:
                        t.resourceType = res.resourceType

        internal_executor.shutdown(wait=True)

        self.execution_times[self.STEP_NAMES["TOTAL_INIT"]] = time.time() - total_init_start_time_timer
        if self.status_queue:
            self.status_queue.put_nowait(
                (self.STEP_NAMES["TOTAL_INIT"], "FINISHED", self.execution_times[self.STEP_NAMES["TOTAL_INIT"]]))

    def prepare_payload(self):
        method_start_time = time.time()
        print("[WORKER] Preparing Payload (Structure of Arrays)...")

        if self.status_queue:
            expected_time = self.preset_times.get(self.STEP_NAMES["PREP_PICKLING"], 999.0)
            self.status_queue.put_nowait((self.STEP_NAMES["PREP_PICKLING"], "START", expected_time))

        if hasattr(self, '_temp_contiguous_territories_objs') and self._temp_contiguous_territories_objs:
            self.contiguousTerritoryIDs = []
            for terr_list in self._temp_contiguous_territories_objs:
                current_id_list = []
                for terr in terr_list:
                    if hasattr(terr, 'id'):
                        current_id_list.append(terr.id)
                self.contiguousTerritoryIDs.append(current_id_list)
            del self._temp_contiguous_territories_objs
        else:
            self.contiguousTerritoryIDs = []

        soa_tiles = {
            'grid_x': [t.grid_x for t in self.tiles],
            'grid_y': [t.grid_y for t in self.tiles],
            'tile_id': [t.tile_id for t in self.tiles],
            'col': [t.col for t in self.tiles],
            'cloudCol': [t.cloudCol for t in self.tiles],
            'waterLand': [t.waterLand for t in self.tiles],
            'mountainous': [t.mountainous for t in self.tiles],
            'cloudy': [t.cloudy for t in self.tiles],
            'isLand': [t.isLand for t in self.tiles],
            'isMountain': [t.isMountain for t in self.tiles],
            'isCoast': [t.isCoast for t in self.tiles],
            'connectedOceanID': [t.connectedOceanID for t in self.tiles],
            'territory_id': [t.territory_id for t in self.tiles],
            'resourceType': [t.resourceType for t in self.tiles]
        }

        all_terrs = list(self.territories_by_id.values())
        soa_territories = {
            'id': [t.id for t in all_terrs],
            'centerPos': [t.centerPos for t in all_terrs],
            'territoryCol': [t.territoryCol for t in all_terrs],
            'selectedTerritoryCol': [t.selectedTerritoryCol for t in all_terrs],
            'tile_ids': [[ti.tile_id for ti in t.tiles] for t in all_terrs],
            'harbor_ids': [[h.harbor_id for h in t.harbors] for t in all_terrs],
            'exteriors': [t.exteriors for t in all_terrs],
            'interiors': [t.interiors for t in all_terrs],
            'wkb': []
        }

        soa_territories['resources'] = []
        for terr in all_terrs:
            res_data = [(r.tile.tile_id, r.resourceType) for r in terr.containedResources]
            soa_territories['resources'].append(res_data)
            if SHAPELY_AVAILABLE and terr.polygon:
                soa_territories['wkb'].append(terr.polygon.wkb)
            else:
                soa_territories['wkb'].append(None)

        all_harbors_flat = []
        for terr in all_terrs:
            all_harbors_flat.extend(terr.harbors)

        soa_harbors = {
            'id': [h.harbor_id for h in all_harbors_flat],
            'tile_id': [(h.tile.tile_id if h.tile else -1) for h in all_harbors_flat],
            'isUsable': [h.isUsable for h in all_harbors_flat],
            'tradeRoutesData': [h.tradeRoutesData for h in all_harbors_flat],
            'tradeRoutesPoints': [h.tradeRoutesPoints for h in all_harbors_flat]
        }

        payload = {
            'tiles': soa_tiles,
            'territories': soa_territories,
            'harbors': soa_harbors,
            'mapWidth': self.mapWidth,
            'mapHeight': self.mapHeight,
            'viewportWidth': self.viewportWidth,
            'viewportHeight': self.viewportHeight,
            'execution_times': self.execution_times,
            'contiguousTerritoryIDs': self.contiguousTerritoryIDs
        }

        duration = time.time() - method_start_time
        self.execution_times[self.STEP_NAMES["PREP_PICKLING"]] = duration
        if self.status_queue:
            self.status_queue.put_nowait((self.STEP_NAMES["PREP_PICKLING"], "FINISHED", duration))

        return payload

    def reconstruct_from_payload(self, payload, fonts_dict, status_queue=None, preset_times=None):
        _local_q_gfx = status_queue
        _local_preset_times_gfx = preset_times if preset_times else {}

        if not hasattr(self, 'execution_times'):
            self.execution_times = {}
        if 'execution_times' in payload:
            self.execution_times.update(payload['execution_times'])

        GFX_TOTAL_INIT_STEP_NAME = self.STEP_NAMES["GFX_TOTAL_INIT"]
        expected_time = _local_preset_times_gfx.get(GFX_TOTAL_INIT_STEP_NAME, 999.0)

        if _local_q_gfx:
            _local_q_gfx.put_nowait((GFX_TOTAL_INIT_STEP_NAME, "START", expected_time))

        method_total_start_time = time.time()
        print("[MAIN THREAD] Reconstructing World from Payload...")

        if not VisualAssets.sprites:
            VisualAssets.load_assets()

        self.mapWidth = payload['mapWidth']
        self.mapHeight = payload['mapHeight']
        self.viewportWidth = payload['viewportWidth']
        self.viewportHeight = payload['viewportHeight']
        self.contiguousTerritoryIDs = payload['contiguousTerritoryIDs']

        self.baseMapSurf = pygame.Surface((self.mapWidth, self.mapHeight)).convert_alpha()
        self.debugOverlayFullMap = pygame.Surface((self.mapWidth, self.mapHeight), pygame.SRCALPHA)
        self.territoryHighlightSurfScreen = pygame.Surface((self.viewportWidth, self.viewportHeight), pygame.SRCALPHA)
        self.playersSurfScreen = pygame.Surface((self.viewportWidth, self.viewportHeight), pygame.SRCALPHA)
        self.baseMapSurf.fill((0, 0, 0, 0))
        self.debugOverlayFullMap.fill((0, 0, 0, 0))
        self.territoryHighlightSurfScreen.fill((0, 0, 0, 0))
        self.playersSurfScreen.fill((0, 0, 0, 0))

        if self.font_name and self.font_name in fonts_dict:
            self.font = fonts_dict[self.font_name]

        t_data = payload['tiles']
        count = len(t_data['tile_id'])
        self.tiles = [None] * count
        self.tiles_by_id = {}
        self.tiles_by_grid_coords = {}
        self.allWaterTiles = []
        self.allLandTiles = []
        self.allCoastalTiles = []
        self.oceanTiles = {}
        self._ocean_id_map = {}
        self._ocean_water = {}

        for i in range(count):
            h = Hex(
                t_data['grid_x'][i], t_data['grid_y'][i],
                t_data['tile_id'][i],
                t_data['col'][i], t_data['cloudCol'][i]
            )
            h.waterLand = t_data['waterLand'][i]
            h.mountainous = t_data['mountainous'][i]
            h.cloudy = t_data['cloudy'][i]
            h.isLand = t_data['isLand'][i]
            h.isMountain = t_data['isMountain'][i]
            h.isCoast = t_data['isCoast'][i]
            h.connectedOceanID = t_data['connectedOceanID'][i]
            h.territory_id = t_data['territory_id'][i]
            h.resourceType = t_data['resourceType'][i] if 'resourceType' in t_data else None

            if h.isLand:
                h.draw_y_offset = HexConstants.LAND_ELEVATION
                h.calculate_geometry()  # Recalc borders with offset if needed
            else:
                h.draw_y_offset = 0

            self.tiles[i] = h
            self.tiles_by_id[h.tile_id] = h
            self.tiles_by_grid_coords[(h.grid_x, h.grid_y)] = h

            if h.isLand:
                self.allLandTiles.append(h)
            else:
                self.allWaterTiles.append(h)
            if h.isCoast: self.allCoastalTiles.append(h)

            if h.connectedOceanID != -1:
                self._ocean_id_map[h] = h.connectedOceanID
                if h.connectedOceanID not in self.oceanTiles:
                    self.oceanTiles[h.connectedOceanID] = set()
                    self._ocean_water[h.connectedOceanID] = set()
                self.oceanTiles[h.connectedOceanID].add(h)
                if not h.isLand:
                    self._ocean_water[h.connectedOceanID].add(h)

        self._link_adjacent_objects()

        h_data = payload['harbors']
        h_count = len(h_data['id'])
        temp_harbors = {}
        self.allHarbors = []
        self.harbors_by_id = {}

        for i in range(h_count):
            h_id = h_data['id'][i]
            h_obj = Harbor.__new__(Harbor)
            h_obj.harbor_id = h_id
            h_obj.tradeRoutesPoints = h_data['tradeRoutesPoints'][i]
            h_obj.tradeRoutesData = h_data['tradeRoutesData'][i]
            h_obj.isUsable = h_data['isUsable'][i]
            h_obj.tradeRouteObjects = {}

            tid = h_data['tile_id'][i]
            if 0 <= tid < count:
                h_obj.tile = self.tiles[tid]
            else:
                h_obj.tile = None

            temp_harbors[h_id] = h_obj
            self.harbors_by_id[h_id] = h_obj
            self.allHarbors.append(h_obj)

        tr_data = payload['territories']
        tr_count = len(tr_data['id'])
        self.territories_by_id = {}
        self.all_territories_for_unpickling = []

        for i in range(tr_count):
            tid = tr_data['id'][i]
            t_obj = Territory.__new__(Territory)
            t_obj.id = tid
            t_obj.centerPos = tr_data['centerPos'][i]
            t_obj.territoryCol = tr_data['territoryCol'][i]
            t_obj.selectedTerritoryCol = tr_data['selectedTerritoryCol'][i]
            t_obj.exteriors = tr_data['exteriors'][i]
            t_obj.interiors = tr_data['interiors'][i]
            if SHAPELY_AVAILABLE and tr_data['wkb'][i]:
                try:
                    t_obj.polygon = shapely.wkb.loads(tr_data['wkb'][i])
                except Exception:
                    t_obj.polygon = None
            else:
                t_obj.polygon = None

            t_obj.tiles = []
            t_obj.landTiles = []
            t_obj.mountainTiles = []
            t_obj.coastTiles = []
            for tile_id in tr_data['tile_ids'][i]:
                if 0 <= tile_id < count:
                    tile = self.tiles[tile_id]
                    tile.territory = t_obj
                    t_obj.tiles.append(tile)
                    if tile.isLand: t_obj.landTiles.append(tile)
                    if tile.isMountain: t_obj.mountainTiles.append(tile)
                    if tile.isCoast: t_obj.coastTiles.append(tile)

            t_obj.harbors = []
            for hid in tr_data['harbor_ids'][i]:
                if hid in temp_harbors:
                    h = temp_harbors[hid]
                    h.parentTerritory = t_obj
                    t_obj.harbors.append(h)

            t_obj.containedResources = []
            for (rtid, rtype) in tr_data['resources'][i]:
                if 0 <= rtid < count:
                    res = Resource(self.tiles[rtid], rtype)
                    res.initializeImg()
                    t_obj.containedResources.append(res)

            t_obj.cols = self.cols
            t_obj.resource_info = self.resource_info
            t_obj.baseMapSurf = self.baseMapSurf
            t_obj.debugOverlayFullMap = self.debugOverlayFullMap
            t_obj.reachableHarbors = {}
            t_obj.shortestPathToReachableTerritories = {}

            self.territories_by_id[tid] = t_obj
            self.all_territories_for_unpickling.append(t_obj)

            for h in t_obj.harbors:
                h.initialize_graphics_and_external_libs(self.tiles_by_id, self.harbors_by_id)

            if hasattr(t_obj, 'update_reachable_harbors'):
                t_obj.update_reachable_harbors()

        self.drawBaseMapStaticContent()

        self.execution_times[GFX_TOTAL_INIT_STEP_NAME] = time.time() - method_total_start_time
        if _local_q_gfx:
            _local_q_gfx.put_nowait(
                (GFX_TOTAL_INIT_STEP_NAME, "FINISHED", self.execution_times[GFX_TOTAL_INIT_STEP_NAME]))

    def print_all_execution_times(self):
        pass

    def generationCycle(self):
        shifts = {'waterLand': [], 'mountainous': [], 'cloudy': []}
        for tile in self.tiles:
            if tile.adjacent:
                for prop_name in shifts:
                    avg_val = sum(getattr(adj, prop_name) for adj in tile.adjacent) / len(tile.adjacent)
                    shifts[prop_name].append(avg_val)
            else:
                for prop_name in shifts:
                    shifts[prop_name].append(getattr(tile, prop_name))

        for i, tile in enumerate(self.tiles):
            for prop_name in shifts:
                current_val = getattr(tile, prop_name)
                new_val = max(0.0, min(1.0, current_val + (shifts[prop_name][i] - current_val) / 2.0))
                setattr(tile, prop_name, new_val)

    def generateTiles(self):
        tile_id_counter = 0
        self.tiles = []
        self.tiles_by_id = {}
        self.tiles_by_grid_coords = {}

        for x in range(self.gridSizeX):
            for y in range(self.gridSizeY):
                hex_obj = Hex(x, y, tile_id_counter)
                self.tiles.append(hex_obj)
                self.tiles_by_id[tile_id_counter] = hex_obj
                self.tiles_by_grid_coords[(x, y)] = hex_obj
                tile_id_counter += 1

    def _link_adjacent_objects(self):
        for tile in self.tiles:
            tile.adjacent = []
            if tile.grid_y % 2 == 0:
                offsets = [(1, 0), (-1, 0), (0, -1), (1, -1), (0, 1), (1, 1)]
            else:
                offsets = [(1, 0), (-1, 0), (-1, -1), (0, -1), (-1, 1), (0, 1)]

            for dx, dy in offsets:
                nx, ny = tile.grid_x + dx, tile.grid_y + dy
                neighbor = self.tiles_by_grid_coords.get((nx, ny))
                if neighbor:
                    tile.adjacent.append(neighbor)

    def getTileAtPosition(self, x_map, y_map):
        grid_y_approx = int(y_map // HexConstants.HEIGHT_STEP)
        offset = HexConstants.WIDTH // 2 if grid_y_approx % 2 != 0 else 0
        grid_x_approx = int((x_map - offset) // HexConstants.WIDTH)

        candidates = []
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                t = self.tiles_by_grid_coords.get((grid_x_approx + dx, grid_y_approx + dy))
                if t: candidates.append(t)

        mask = VisualAssets.hit_mask_img
        if not mask: return candidates[0] if candidates else None

        for t in candidates:
            draw_x = t.x
            draw_y = t.y + t.draw_y_offset
            rel_x = int(x_map - draw_x)
            rel_y = int(y_map - draw_y)
            if 0 <= rel_x < mask.get_width() and 0 <= rel_y < mask.get_height():
                if mask.get_at((rel_x, rel_y))[3] > 0:
                    return t

        return candidates[0] if candidates else None

    def setTileCols(self):
        for tile in self.tiles:
            tile.isLand = (tile.waterLand >= self.waterThreshold)
            tile.isMountain = (tile.isLand and tile.mountainous >= self.mountainThreshold)

            if tile.isLand:
                tile.draw_y_offset = HexConstants.LAND_ELEVATION
            else:
                tile.draw_y_offset = 0

        # RESTORED NOISE LOGIC FOR GRADIENT SUPPORT
        value_sets = {'water': [], 'land': [], 'mountain': [], 'cloud': []}
        for t in self.tiles:
            if not t.isLand:
                value_sets['water'].append(t.waterLand)
            elif t.isLand and not t.isMountain:
                value_sets['land'].append(t.waterLand)
            elif t.isMountain:
                value_sets['mountain'].append(t.mountainous)
            if hasattr(t, 'cloudy'): value_sets['cloud'].append(t.cloudy)

        bounds = {}
        for k, v_list in value_sets.items():
            if v_list:
                bounds[k] = [min(v_list), max(v_list)]
            else:
                bounds[k] = [0.0, 1.0]

        if bounds.get('water') and len(bounds['water']) == 2:
            bounds['water'][1] = self.waterThreshold
        if bounds.get('land') and len(bounds['land']) == 2:
            bounds['land'][0] = self.waterThreshold
        if bounds.get('mountain') and len(bounds['mountain']) == 2:
            bounds['mountain'][0] = self.mountainThreshold

        noise_levels = {'water': 0.0035, 'land': 0.004, 'mountain': 0.007, 'cloud': 0.008}
        dist_funcs = {'water': lambda x_norm: (x_norm ** 2) / 2 + (1 - (1 - x_norm) ** 2) ** 10 / 2,
                      'land': lambda x_norm: (1 - 2 ** (-3 * x_norm)) * 8 / 7,
                      'cloud': lambda x_norm: (1 - 2 ** (-3 * x_norm)) * 8 / 7}

        self.allWaterTiles, self.allLandTiles, self.allCoastalTiles = [], [], []
        for tile in self.tiles:
            tile.isCoast = False

            cloud_noise = random.uniform(-noise_levels['cloud'], noise_levels['cloud'])
            norm_cloud = 0.5
            if bounds['cloud'][1] > bounds['cloud'][0]:
                norm_cloud = normalize(tile.cloudy + cloud_noise, bounds['cloud'][0], bounds['cloud'][1], clamp=True)
            tile.cloudCol = linearGradient([self.cols.cloudDark, self.cols.cloudMedium, self.cols.cloudLight],
                                           dist_funcs['cloud'](norm_cloud))

            if not tile.isLand:
                noise = random.uniform(-noise_levels['water'], noise_levels['water'])
                norm_val = 0.5
                if bounds['water'][1] > bounds['water'][0]:
                    norm_val = normalize(tile.waterLand + noise, bounds['water'][0], bounds['water'][1], clamp=True)
                tile.col = linearGradient(
                    [self.cols.oceanBlue, self.cols.oceanGreen, self.cols.lightOceanGreen, self.cols.oceanFoam],
                    dist_funcs['water'](norm_val))
                self.allWaterTiles.append(tile)
            elif tile.isMountain:
                noise = random.uniform(-noise_levels['mountain'], noise_levels['mountain'])
                norm_val = 0.5
                if bounds['mountain'][1] > bounds['mountain'][0]:
                    norm_val = normalize(tile.mountainous + noise, bounds['mountain'][0], bounds['mountain'][1],
                                         clamp=True)
                tile.col = linearGradient([self.cols.mountainBlue, self.cols.darkMountainBlue], norm_val)
                self.allLandTiles.append(tile)
            else:
                noise = random.uniform(-noise_levels['land'], noise_levels['land'])
                norm_val = 0.5
                if bounds['land'][1] > bounds['land'][0]:
                    norm_val = normalize(tile.waterLand + noise, bounds['land'][0], bounds['land'][1], clamp=True)
                tile.col = linearGradient([self.cols.oliveGreen, self.cols.darkOliveGreen],
                                          dist_funcs['land'](norm_val))
                self.allLandTiles.append(tile)

        allWaterSet = set(self.allWaterTiles)
        for tile in self.allLandTiles:
            is_coastal_tile = False
            for adj in tile.adjacent:
                if adj in allWaterSet:
                    is_coastal_tile = True
                    break
            if is_coastal_tile:
                self.allCoastalTiles.append(tile)
                tile.isCoast = True

    def indexOceans(self):
        self.oceanTiles = {}
        self._ocean_id_map = {}
        self._ocean_water = {}

        unvisited_water_tiles = set(self.allWaterTiles)
        visited = set()
        current_ocean_id = 0
        while unvisited_water_tiles:
            start_tile = unvisited_water_tiles.pop()
            current_ocean_set = {start_tile}
            queue = deque([start_tile])
            visited.add(start_tile)
            self._ocean_id_map[start_tile] = current_ocean_id
            start_tile.connectedOceanID = current_ocean_id

            while queue:
                tile = queue.popleft()
                for neighbor in tile.adjacent:
                    if neighbor in unvisited_water_tiles:
                        neighbor.connectedOceanID = current_ocean_id
                        self._ocean_id_map[neighbor] = current_ocean_id
                        unvisited_water_tiles.remove(neighbor)
                        current_ocean_set.add(neighbor)
                        queue.append(neighbor)

            if current_ocean_set:
                self.oceanTiles[current_ocean_id] = current_ocean_set
                self._ocean_water[current_ocean_id] = current_ocean_set
                current_ocean_id += 1

    def assignCoastTiles(self):
        allWaterTilesSet = set(self.allWaterTiles)
        for coastTile in self.allCoastalTiles:
            ocean_ids_for_coast_tile = set()
            for adj in coastTile.adjacent:
                if adj in allWaterTilesSet and hasattr(adj, 'connectedOceanID') and adj.connectedOceanID != -1:
                    ocean_ids_for_coast_tile.add(adj.connectedOceanID)
            if ocean_ids_for_coast_tile:
                coastTile.connectedOceanID = max(ocean_ids_for_coast_tile)
            else:
                coastTile.connectedOceanID = -1

    @staticmethod
    def findContiguousRegions(tiles_to_check):
        visited = set()
        regions = []
        tilesSet = set(tiles_to_check)
        for tile in tiles_to_check:
            if tile not in visited:
                current_region = []
                q = deque([tile])
                visited.add(tile)
                while q:
                    curr = q.popleft()
                    current_region.append(curr)
                    for adj in curr.adjacent:
                        if adj in tilesSet and adj not in visited:
                            visited.add(adj)
                            q.append(adj)
                if current_region:
                    regions.append(current_region)
        return regions

    def createTerritories(self, land_regions_list):
        self.contiguousTerritoryIDs = []
        self.territories_by_id = {}
        self.all_territories_for_unpickling = []
        self._temp_contiguous_territories_objs = []

        tid_counter = 0
        for region_tiles in land_regions_list:
            if not region_tiles: continue
            centers = np.array([(t.x, t.y) for t in region_tiles])
            num_actual_tiles_in_region = len(region_tiles)
            n_clusters = max(1, math.ceil(num_actual_tiles_in_region / self.territorySize))
            n_clusters = min(n_clusters, num_actual_tiles_in_region)
            if n_clusters == 0: continue

            kmeans = KMeans(n_clusters=n_clusters, random_state=random.randint(0, 10000), n_init='auto',
                            init='k-means++')
            assigned_labels = kmeans.fit_predict(centers)

            grouped_tiles_for_territories = [[] for _ in range(n_clusters)]
            for i, tile_obj in enumerate(region_tiles):
                grouped_tiles_for_territories[assigned_labels[i]].append(tile_obj)

            region_territory_objects_list = []
            for i in range(n_clusters):
                if grouped_tiles_for_territories[i]:
                    current_territory_tiles = grouped_tiles_for_territories[i]
                    cx = sum(t.x for t in current_territory_tiles) / len(current_territory_tiles)
                    cy = sum(t.y for t in current_territory_tiles) / len(current_territory_tiles)
                    terr = Territory(self.mapWidth, self.mapHeight, [cx, cy], current_territory_tiles,
                                     self.allWaterTiles, self.cols, self.resource_info, self.structure_info)
                    terr.id = tid_counter
                    self.all_territories_for_unpickling.append(terr)
                    self.territories_by_id[terr.id] = terr
                    region_territory_objects_list.append(terr)
                    for t_in_terr in current_territory_tiles:
                        t_in_terr.territory_id = terr.id
                    tid_counter += 1

            if region_territory_objects_list:
                self._temp_contiguous_territories_objs.append(region_territory_objects_list)

    def connectTerritoryHarbors(self):
        # RESTORED ORIGINAL LOGIC
        self.allHarbors = []
        for terr_obj in self.all_territories_for_unpickling:
            if hasattr(terr_obj, 'harbors') and isinstance(terr_obj.harbors, list):
                self.allHarbors.extend(terr_obj.harbors)

        if not self.allHarbors:
            return 0

        self.harbors_by_id = {}
        hid_counter = 0
        for h_obj in self.allHarbors:
            if not hasattr(h_obj, 'harbor_id') or h_obj.harbor_id == -1:
                h_obj.harbor_id = hid_counter
            self.harbors_by_id[h_obj.harbor_id] = h_obj
            hid_counter = max(hid_counter, h_obj.harbor_id + 1)

        harbors_by_ocean = {}
        ocean_harbors_by_id_map = {}

        for h_obj in self.allHarbors:
            if hasattr(h_obj, 'tile') and h_obj.tile and hasattr(h_obj.tile, 'adjacent'):
                for adj_tile in h_obj.tile.adjacent:
                    if adj_tile in self._ocean_id_map:
                        ocean_id = self._ocean_id_map[adj_tile]
                        if ocean_id not in harbors_by_ocean:
                            harbors_by_ocean[ocean_id] = []
                            ocean_harbors_by_id_map[ocean_id] = {}
                        harbors_by_ocean[ocean_id].append(h_obj)
                        ocean_harbors_by_id_map[ocean_id][h_obj.harbor_id] = h_obj
                        break

        routes_found_count = 0
        for ocean_id, harbors_in_ocean_list in harbors_by_ocean.items():
            if len(harbors_in_ocean_list) < 2:
                continue

            water_tile_set_for_ocean = self._ocean_water.get(ocean_id)
            if not water_tile_set_for_ocean:
                continue

            current_ocean_harbors_id_map = ocean_harbors_by_id_map.get(ocean_id, {})

            for i, src_harbor in enumerate(harbors_in_ocean_list):
                destination_harbors = [h for h in harbors_in_ocean_list[i + 1:] if h.harbor_id != -1]
                if not destination_harbors:
                    continue

                if not hasattr(src_harbor, 'generateAllRoutes'):
                    continue

                routes_found_count += src_harbor.generateAllRoutes(destination_harbors, water_tile_set_for_ocean,
                                                                   current_ocean_harbors_id_map)

        print(f"WORKER STDOUT: Found/Generated {routes_found_count} harbor routes.")
        return len(self.allHarbors)

    def drawBaseMapStaticContent(self):
        if not self.baseMapSurf: return
        self.baseMapSurf.fill(self.cols.oceanBlue)

        sorted_tiles = sorted(self.tiles, key=lambda t: (t.grid_y, t.grid_x))

        for tile in sorted_tiles:
            key = VisualAssets.get_ground_sprite(tile)
            sprite = VisualAssets.get_random_version(key)
            if sprite:
                draw_x = tile.x
                draw_y = tile.y + tile.draw_y_offset
                self.baseMapSurf.blit(sprite, (draw_x, draw_y))

            struct_key = VisualAssets.get_structure_sprite(tile)
            if struct_key:
                s_sprite = VisualAssets.get_random_version(struct_key)
                if s_sprite:
                    sx = tile.x + (HexConstants.WIDTH - s_sprite.get_width()) // 2
                    sy = tile.y + tile.draw_y_offset - s_sprite.get_height() + HexConstants.HEIGHT_STEP + 4
                    self.baseMapSurf.blit(s_sprite, (sx, sy))

        self.hitMaskSurf = pygame.Surface((self.mapWidth, self.mapHeight), pygame.SRCALPHA)
        mask_base = VisualAssets.hit_mask_img
        if mask_base:
            for tile in sorted_tiles:
                r = tile.tile_id & 0xFF
                g = (tile.tile_id >> 8) & 0xFF
                b = (tile.tile_id >> 16) & 0xFF
                c_mask = mask_base.copy()
                c_mask.fill((r, g, b), special_flags=pygame.BLEND_RGB_MULT)
                self.hitMaskSurf.blit(c_mask, (tile.x, tile.y + tile.draw_y_offset))

        self.debugOverlayFullMap.fill((0, 0, 0, 0))
        for id_list in self.contiguousTerritoryIDs:
            for tid in id_list:
                terr = self.territories_by_id.get(tid)
                if terr:
                    terr.drawInternalTerritoryBaseline(self.baseMapSurf, self.debugOverlayFullMap)

        for id_list in self.contiguousTerritoryIDs:
            for tid in id_list:
                terr = self.territories_by_id.get(tid)
                if terr:
                    for harbor in terr.harbors:
                        harbor.draw(self.baseMapSurf, 0, 0)

    def drawTerritoryHighlights(self, s, hovered_territory=None, selected_territory=None, scroll=(0, 0)):
        if not self.territoryHighlightSurfScreen: return
        self.territoryHighlightSurfScreen.fill((0, 0, 0, 0))
        scroll_x, scroll_y = scroll[0], scroll[1]

        if hovered_territory:
            if selected_territory is None:
                hovered_territory.drawCurrent(self.territoryHighlightSurfScreen, 'b', scroll_x, scroll_y)
            else:
                if hovered_territory == selected_territory:
                    hovered_territory.drawCurrent(self.territoryHighlightSurfScreen, 'r', scroll_x, scroll_y)
                else:
                    selected_territory.drawCurrent(self.territoryHighlightSurfScreen, 'r', scroll_x, scroll_y)
                    hovered_territory.drawCurrent(self.territoryHighlightSurfScreen, 'b', scroll_x, scroll_y)
                selected_territory.drawRoutes(self.territoryHighlightSurfScreen, self.cols.brightCrimson, scroll_x,
                                              scroll_y)
            if (selected_territory is None) or (selected_territory == hovered_territory):
                hovered_territory.drawRoutes(self.territoryHighlightSurfScreen, self.cols.brightCrimson, scroll_x,
                                             scroll_y)
        else:
            if selected_territory is not None:
                selected_territory.drawCurrent(self.territoryHighlightSurfScreen, 'r', scroll_x, scroll_y)
                selected_territory.drawRoutes(self.territoryHighlightSurfScreen, self.cols.brightCrimson, scroll_x,
                                              scroll_y)

        s.blit(self.territoryHighlightSurfScreen, (0, 0))