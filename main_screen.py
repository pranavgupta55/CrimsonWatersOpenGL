import multiprocessing
from concurrent.futures import ProcessPoolExecutor
import pygame
import time
import sys
import os
import csv
import statistics
import socket
import struct
import queue
import threading
import string
import random
import math

import moderngl
import numpy as np
import cloud_manager
from visual_config import *

from text import drawText
from fontDict import fonts as fonts_definitions
from controlPanel import GenerationInfo, ResourceInfo, StructureInfo, Cols, uiInfo, VisualAssets, HexConstants
from player import Player
from calcs import normalize

MSG_QUEUE = queue.Queue()

ALPHABET = string.digits + string.ascii_uppercase + string.ascii_lowercase
BASE = len(ALPHABET)


def base62_encode(number):
    if number == 0: return ALPHABET[0]
    result = []
    while number > 0:
        number, rem = divmod(number, BASE)
        result.append(ALPHABET[rem])
    return ''.join(reversed(result))


def base62_decode(s):
    number = 0
    for char in s: number = number * BASE + ALPHABET.index(char)
    return number


def make_short_code(ip_suffix, port):
    ip_bytes = bytes(ip_suffix)
    port_bytes = struct.pack(">H", port)
    combined = ip_bytes + port_bytes
    num = int.from_bytes(combined, 'big')
    return base62_encode(num).zfill(6)


def decode_short_code(code):
    num = base62_decode(code)
    full_bytes = num.to_bytes(4, 'big')
    ip_suffix = list(full_bytes[:2])
    port = struct.unpack(">H", full_bytes[2:])[0]
    ip = f"192.168.{ip_suffix[0]}.{ip_suffix[1]}"
    return ip, port


def find_free_port(start_port, max_tries=100):
    for p in range(start_port, start_port + max_tries):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.bind(("0.0.0.0", p))
            s.close()
            return p
        except OSError:
            continue
    raise RuntimeError(f"No free UDP port in {start_port}–{start_port + max_tries}")


def get_local_ip_suggestion():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0)
    s.connect(('10.254.254.254', 1))
    ip = s.getsockname()[0]
    s.close()
    return ip


def server_thread(sock_instance, listen_ip, listen_port):
    if not (listen_ip or listen_port): return None
    while True:
        try:
            data, address = sock_instance.recvfrom(1024)
            MSG_QUEUE.put((address, data.decode()))
        except socket.timeout:
            continue
        except OSError as e:
            print(f"Server thread error: {e}. Exiting server thread.")
            break
        except Exception as e:
            print(f"Unexpected error in server thread: {e}")
            break


def client_recv_thread(sock):
    while True:
        try:
            data, address = sock.recvfrom(1024)
            MSG_QUEUE.put((address, data.decode()))
        except socket.timeout:
            continue
        except OSError as e:
            print(f"Client receive thread error: {e}. Exiting client receive thread.")
            break
        except Exception as e:
            print(f"Unexpected error in client receive thread: {e}")
            break


TIMES_CSV_FILE = "execution_times.csv"
INITIAL_PRESET_PLACEHOLDER_TIME = 1.0
PRESET_EXECUTION_TIMES = {}


def load_and_calculate_average_times():
    global PRESET_EXECUTION_TIMES
    new_preset_times = {}
    all_step_durations = {}
    if os.path.exists(TIMES_CSV_FILE):
        try:
            with open(TIMES_CSV_FILE, 'r', newline='') as csvfile:
                reader = csv.DictReader(csvfile)
                if reader.fieldnames and 'step_name' in reader.fieldnames and 'duration' in reader.fieldnames:
                    for row in reader:
                        try:
                            step_name = row['step_name']
                            duration = float(row['duration'])
                            if step_name not in all_step_durations: all_step_durations[step_name] = []
                            all_step_durations[step_name].append(duration)
                        except (ValueError, KeyError):
                            pass
            for step_name, durations in all_step_durations.items():
                if durations: new_preset_times[step_name] = statistics.mean(durations)
            if new_preset_times:
                PRESET_EXECUTION_TIMES = new_preset_times
                return
        except Exception as e_csv_load:
            print(f"Error loading or processing '{TIMES_CSV_FILE}': {e_csv_load}. Using default placeholder times.")
    PRESET_EXECUTION_TIMES = {}


def save_execution_times(new_times_dict):
    if not new_times_dict: return
    file_exists = os.path.exists(TIMES_CSV_FILE)
    try:
        with open(TIMES_CSV_FILE, 'a', newline='') as csvfile:
            fieldnames = ['timestamp', 'step_name', 'duration']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            if not file_exists or os.path.getsize(TIMES_CSV_FILE) == 0: writer.writeheader()
            current_timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
            for step_name, duration in new_times_dict.items():
                writer.writerow({'timestamp': current_timestamp, 'step_name': step_name, 'duration': duration})
    except Exception as e_csv_save:
        print(f"Error saving execution times to '{TIMES_CSV_FILE}': {e_csv_save}")


load_and_calculate_average_times()


def build_tile_handler_worker(args_tuple):
    map_width, map_height, viewport_width, viewport_height, gen_info, font_name_to_load, font_definitions_dict, cols_class, resource_info_class, structure_info_class, local_status_q, current_preset_times, worker_seed = args_tuple
    try:
        from generation import TileHandler
    except ImportError as e_import:
        if local_status_q: local_status_q.put_nowait(
            ("Error: Import Failed in Worker (TileHandler)", "ERROR", str(e_import)))
        raise

    _font = None
    TH_instance = TileHandler(
        map_width, map_height, gen_info.tileSize, cols_class,
        gen_info.waterThreshold, gen_info.mountainThreshold, gen_info.territorySize,
        font=_font, font_name=font_name_to_load,
        resource_info=resource_info_class, structure_info=structure_info_class,
        status_queue=local_status_q, preset_times=current_preset_times,
        seed=worker_seed, viewport_width=viewport_width, viewport_height=viewport_height
    )
    TH_instance.run_generation_sequence()
    return TH_instance.prepare_payload()


def load_shader(ctx, vert, frag):
    with open(vert, 'r') as f: v = f.read()
    with open(frag, 'r') as f: fr = f.read()
    return ctx.program(vertex_shader=v, fragment_shader=fr)


if __name__ == "__main__":
    try:
        multiprocessing.set_start_method("spawn", force=True)
    except RuntimeError:
        pass
    multiprocessing.freeze_support()
    pygame.init()

    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 3)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_CORE)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_FORWARD_COMPATIBLE_FLAG, True)

    info = pygame.display.Info()
    WINDOW_WIDTH = info.current_w
    WINDOW_HEIGHT = info.current_h
    aspect = WINDOW_WIDTH / WINDOW_HEIGHT

    INT_GAME_RENDER_W = int(GAME_RENDER_H * aspect)
    INT_GAME_RENDER_H = GAME_RENDER_H
    INT_CLOUD_RENDER_W = int(CLOUD_RENDER_H * aspect)
    INT_CLOUD_RENDER_H = CLOUD_RENDER_H

    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT),
                                     pygame.OPENGL | pygame.DOUBLEBUF | pygame.FULLSCREEN)
    ctx = moderngl.create_context()
    ctx.enable(moderngl.BLEND)
    ctx.blend_func = moderngl.DEFAULT_BLENDING

    surf_game = pygame.Surface((INT_GAME_RENDER_W, INT_GAME_RENDER_H))
    surf_ui = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)

    tex_game = ctx.texture((INT_GAME_RENDER_W, INT_GAME_RENDER_H), 3)
    tex_game.filter = (moderngl.NEAREST, moderngl.NEAREST)
    tex_ui = ctx.texture((WINDOW_WIDTH, WINDOW_HEIGHT), 4)
    tex_ui.filter = (moderngl.LINEAR, moderngl.LINEAR)

    tex_cloud_color = ctx.texture((INT_CLOUD_RENDER_W, INT_CLOUD_RENDER_H), 4)
    tex_cloud_color.filter = (moderngl.NEAREST, moderngl.NEAREST)
    tex_cloud_color.repeat_x = False
    tex_cloud_color.repeat_y = False
    fbo_clouds = ctx.framebuffer(color_attachments=[tex_cloud_color])

    tex_composite = ctx.texture((INT_GAME_RENDER_W, INT_GAME_RENDER_H), 3)
    tex_composite.filter = (moderngl.NEAREST, moderngl.NEAREST)
    fbo_composite = ctx.framebuffer(color_attachments=[tex_composite])

    prog_clouds = load_shader(ctx, 'shaders/cloud_layer.vert', 'shaders/cloud_layer.frag')
    prog_comp = load_shader(ctx, 'shaders/basic.vert', 'shaders/final_composite.frag')
    prog_post = load_shader(ctx, 'shaders/basic.vert', 'shaders/post_high.frag')
    prog_ui = load_shader(ctx, 'shaders/basic.vert', 'shaders/ui_overlay.frag')

    palette_flat = [c / 255.0 for col in CLOUD_PALETTE for c in col]
    if 'u_palette' in prog_clouds:
        prog_clouds['u_palette'].write(struct.pack(f'{len(palette_flat)}f', *palette_flat))

    clouds = cloud_manager.CloudManager(INT_CLOUD_RENDER_W, INT_CLOUD_RENDER_H)

    quad_data = np.array([-1, -1, 1, -1, -1, 1, 1, 1], dtype='f4')
    vbo_quad = ctx.buffer(quad_data)
    vbo_instances = ctx.buffer(reserve=CLOUD_COUNT * 7 * 4)
    vao_clouds = ctx.vertex_array(prog_clouds, [(vbo_quad, '2f', 'in_vert'),
                                                (vbo_instances, '4f 3f /i', 'in_pos_z_rad', 'in_squash_seed_res')])

    vbo_fs = ctx.buffer(struct.pack('16f', -1, 1, 0, 1, -1, -1, 0, 0, 1, 1, 1, 1, 1, -1, 1, 0))
    vao_comp = ctx.vertex_array(prog_comp, [(vbo_fs, '2f 2f', 'in_vert', 'in_texcoord')])
    vao_post = ctx.vertex_array(prog_post, [(vbo_fs, '2f 2f', 'in_vert', 'in_texcoord')])
    vao_ui = ctx.vertex_array(prog_ui, [(vbo_fs, '2f 2f', 'in_vert', 'in_texcoord')])

    prog_clouds['u_resolution'].value = (INT_CLOUD_RENDER_W, INT_CLOUD_RENDER_H)
    prog_clouds['u_layer_offset_x'].value = CLOUD_LAYER_OFFSET_X
    prog_clouds['u_layer_offset_y'].value = CLOUD_LAYER_OFFSET_Y
    prog_clouds['u_layer_var_y'].value = CLOUD_LAYER_OFFSET_VARIANCE_Y
    prog_clouds['u_layer_dec'].value = CLOUD_LAYER_SIZE_DECREASE
    prog_clouds['u_layer_dec_var'].value = CLOUD_LAYER_SIZE_DECREASE_VARIANCE
    prog_clouds['u_wander_speed'].value = CLOUD_WANDER_SPEED
    prog_clouds['u_wander_strength'].value = CLOUD_WANDER_STRENGTH
    prog_clouds['u_pulse_speed'].value = CLOUD_PULSE_SPEED
    prog_clouds['u_pulse_var'].value = CLOUD_PULSE_VARIANCE

    prog_comp['u_map'].value = 0
    prog_comp['u_clouds'].value = 1
    prog_comp['u_godray_intensity'].value = GODRAY_INTENSITY
    prog_comp['u_godray_decay'].value = GODRAY_DECAY
    prog_comp['u_godray_weight'].value = GODRAY_WEIGHT
    prog_comp['u_godray_density'].value = GODRAY_DENSITY
    prog_comp['u_godray_samples'].value = GODRAY_SAMPLES

    prog_post['u_scene'].value = 0
    prog_post['u_bloom_intensity'].value = BLOOM_INTENSITY
    prog_post['u_vig_strength'].value = VIGNETTE_STRENGTH
    prog_post['u_vig_radius'].value = VIGNETTE_RADIUS
    prog_post['u_vig_softness'].value = VIGNETTE_SOFTNESS

    prog_ui['u_ui'].value = 0

    clock = pygame.time.Clock()
    fps = 60
    screen_width, screen_height = WINDOW_WIDTH, WINDOW_HEIGHT
    screen_center = [screen_width / 2, screen_height / 2]

    loaded_fonts = {}
    for name, (path, size) in fonts_definitions.items():
        try:
            if not os.path.exists(path): continue
            loaded_fonts[name] = pygame.font.Font(path, size)
        except Exception as e_font_load:
            print(f"Main Error: Failed to load font {name} from {path} (size {size}): {e_font_load}")

    Alkhemikal20 = loaded_fonts.get('Alkhemikal20')
    Alkhemikal30 = loaded_fonts.get('Alkhemikal30')
    Alkhemikal50 = loaded_fonts.get('Alkhemikal50')
    Alkhemikal80 = loaded_fonts.get('Alkhemikal80')
    Alkhemikal150 = loaded_fonts.get('Alkhemikal150')
    Alkhemikal200 = loaded_fonts.get('Alkhemikal200')

    player = None
    generationScreenBackgroundImg = pygame.transform.scale(pygame.image.load("assets/UI/LoadingPageBackground.png"),
                                                           (screen_width, screen_height))

    manager = multiprocessing.Manager()
    status_queue_for_main_thread = manager.Queue()
    executor = ProcessPoolExecutor(max_workers=1)
    font_name_needed_by_worker = 'Alkhemikal30'

    username = ''.join(random.choice(string.ascii_uppercase) for _ in range(5))
    local_ip_full = get_local_ip_suggestion()
    local_ip_suffix = tuple(map(int, local_ip_full.split('.')))[2:]
    connectingPort = 4000 + random.randint(0, 999)

    room_code = ""
    mode = "INIT"
    players = {}
    joined = False
    server_socket = None
    server_thread_instance = None

    client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client_socket.settimeout(0.5)
    threading.Thread(target=client_recv_thread, args=(client_socket,), daemon=True).start()

    seed_to_send = None
    seed = None
    requestSentTime = None
    target_host_ip = None
    target_host_port = None

    client_ping_interval = 0.5
    client_timeout_threshold = 2.0
    last_ping_sent_time = 0.0
    client_last_ping_time = {}
    last_host_check_time = 0.0

    toggle = True
    userString = ""
    userStringErrorDisplay = None
    keyHoldFrames = {}
    delayThreshold = 10
    shifting = False
    lobby_timer_for_error_display = 0

    future = None
    numPeriods = 0
    PHASE_WORKER_INIT = "Initializing World Generation"
    PHASE_DATA_TRANSFER_PREP = "Preparing Data for Transfer"
    PHASE_RETRIEVING_MAP_DATA = "Retrieving World Data"
    PHASE_GFX_INIT = "Initializing Graphics"

    LOADING_STEPS_ORDER = ["tileGen", "linkAdj", "generationCycles", "setTileColors", "findLandRegionsParallel",
                           "indexOceansParallel", "assignCoastTiles", "createTerritories", "connectHarborsParallel",
                           "workerInit", "dataSerialization", "retrieveMapData", "gfxTotalInit"]
    LOADING_STEPS_FOR_PROGRESS_BAR = ["tileGen", "linkAdj", "generationCycles", "setTileColors",
                                      "findLandRegionsParallel", "indexOceansParallel", "assignCoastTiles",
                                      "createTerritories", "connectHarborsParallel", "dataSerialization"]
    DISPLAY_NAMES_MAP = {"tileGen": "Generating Tiles", "linkAdj": "Connecting Adjacent Tiles",
                         "generationCycles": "Simulating Biomes (50 cycles)", "setTileColors": "Coloring Map Tiles",
                         "findLandRegionsParallel": "Identifying Landmasses (Parallel)",
                         "indexOceansParallel": "Indexing Oceans (Parallel)",
                         "assignCoastTiles": "Assigning Coastline Tiles", "createTerritories": "Forming Territories",
                         "connectHarborsParallel": "Connecting Harbors (Parallel)",
                         "workerInit": "World Generation Complete (Worker)",
                         "dataSerialization": "Serializing World Data", "retrieveMapData": "Retrieving World Data",
                         "gfxTotalInit": "Initializing Game Graphics"}

    task_display_states = {}
    for step_name_key in LOADING_STEPS_ORDER:
        task_display_states[step_name_key] = {'status': 'Pending', 'start_time': 0.0, 'duration': 0.0,
                                              'expected_time': PRESET_EXECUTION_TIMES.get(step_name_key,
                                                                                          INITIAL_PRESET_PLACEHOLDER_TIME)}

    total_expected_loading_time = 0.0
    for step_name_key in LOADING_STEPS_FOR_PROGRESS_BAR:
        total_expected_loading_time += task_display_states[step_name_key]['expected_time']
    if total_expected_loading_time == 0.0: total_expected_loading_time = 20.0

    loading_screen_start_time = time.time()
    TH_fully_initialized = False
    TH = None
    all_current_run_times = {}
    worker_tasks_complete = False
    retrieving_result_active = False

    main_title_x = screen_width * 0.25
    main_overall_phase_x = screen_width * 0.25
    tasks_list_x = screen_width * 0.5
    line_height = 30
    progress_bar_width = screen_width * 0.17
    progress_bar_height = 15
    progress_bar_corner_radius = int(progress_bar_height / 3)
    progress_bar_y_offset = 5
    single_task_display_start_y = screen_center[1] - (len(LOADING_STEPS_ORDER) * line_height / 2)

    last_time = time.time()
    running = True
    pygame.mouse.set_visible(False)
    overlay = pygame.Surface((screen_width, screen_height), pygame.SRCALPHA)
    overlay.fill((0, 8, 10, 150))

    while running:
        surf_ui.fill((0, 0, 0, 0))
        surf_ui.blit(generationScreenBackgroundImg, (0, 0))
        surf_ui.blit(overlay, (0, 0))

        dt = time.time() - last_time
        dt *= fps
        last_time = time.time()
        mx, my = pygame.mouse.get_pos()
        lobby_timer_for_error_display -= 1 * dt

        try:
            while not MSG_QUEUE.empty():
                addr, msg = MSG_QUEUE.get_nowait()
                if mode == "HOST_LOBBY":
                    if msg.startswith("JOIN:"):
                        name = msg.split(":", 1)[1]
                        players[addr] = name
                        client_last_ping_time[addr] = time.time()
                        if server_socket: server_socket.sendto(b"ACK_JOIN", addr)
                        print(f"Main: Player '{name}' joined from {addr}")
                    elif msg.startswith("PING:"):
                        if addr in players: client_last_ping_time[addr] = time.time()
                elif mode == "CLIENT_LOBBY":
                    if msg == "ACK_JOIN":
                        joined = True
                        last_ping_sent_time = time.time()
                        print("Main: Successfully joined lobby")
                    elif msg.startswith("SEED:"):
                        seed = int(msg.split(":", 1)[1])
                        mode = "IN_GAME"
                        loading_screen_start_time = time.time()
                        print(f"Main: Client received seed {seed}. Starting generation.")
        except queue.Empty:
            pass
        except Exception as e_queue_process:
            print(f"Main Error processing network queue: {e_queue_process}")

        for event in pygame.event.get():
            if event.type == pygame.QUIT: running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE: running = False
                if event.key == pygame.K_TAB: toggle = not toggle
                if event.key == pygame.K_LSHIFT or event.key == pygame.K_RSHIFT: shifting = True
                if event.key == pygame.K_RETURN:
                    txt = userString.strip()
                    if mode == "INIT":
                        if len(userString) != 6 and userString.lower() not in ['start', 's']:
                            lobby_timer_for_error_display = 0.5 * fps
                            userStringErrorDisplay = "type smth" if userString == "" else "that's not a code"
                            continue
                        if txt.lower() in ["start", "s"]:
                            connectingPort = find_free_port(connectingPort)
                            server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                            server_socket.bind(("0.0.0.0", connectingPort))
                            server_thread_instance = threading.Thread(target=server_thread,
                                                                      args=(server_socket, "0.0.0.0", connectingPort),
                                                                      daemon=True)
                            server_thread_instance.start()
                            mode = "HOST_LOBBY"
                            room_code = make_short_code(local_ip_suffix, connectingPort)
                            userString = ""
                            userStringErrorDisplay = None
                            target_host_ip = local_ip_full
                            target_host_port = connectingPort
                        else:
                            try:
                                host_ip, host_port = decode_short_code(txt)
                                client_socket.sendto(f"JOIN:{username}".encode(), (host_ip, host_port))
                                mode = "CLIENT_LOBBY"
                                requestSentTime = time.time()
                                userString = ""
                                userStringErrorDisplay = None
                                target_host_ip = host_ip
                                target_host_port = host_port
                            except Exception:
                                lobby_timer_for_error_display = 0.5 * fps
                                userStringErrorDisplay = "invalid code"
                                continue
                    elif mode == "HOST_LOBBY":
                        if txt.lower() in ["begin", "b"]:
                            seed_to_send = random.randint(0, 2 ** 31 - 1)
                            for addr in players:
                                if server_socket: server_socket.sendto(f"SEED:{seed_to_send}".encode(), addr)
                            mode = "IN_GAME"
                            seed = seed_to_send
                            loading_screen_start_time = time.time()
                            userString = ""
                            userStringErrorDisplay = None
                            print(f"Main: Host starting game with seed {seed}")
                        elif txt.lower() in ['quit', 'q']:
                            print("Host: Returning to INIT screen. Closing server.")
                            if server_socket:
                                server_socket.close()
                                server_socket = None
                            mode = "INIT"
                            room_code = ""
                            players = {}
                            client_last_ping_time = {}
                            seed_to_send = None
                            seed = None
                            requestSentTime = None
                            target_host_ip = None
                            target_host_port = None
                            userString = ""
                            userStringErrorDisplay = None
                            lobby_timer_for_error_display = 0
                            continue
                        else:
                            lobby_timer_for_error_display = 0.5 * fps
                            userStringErrorDisplay = "you gotta type smth" if userString == "" else "that's not 'begin' or 'quit'"
                            continue
                    elif mode == "CLIENT_LOBBY":
                        if userString.lower() == 'quit':
                            print("Client: Returning to INIT screen.")
                            mode = "INIT"
                            joined = False
                            requestSentTime = None
                            target_host_ip = None
                            target_host_port = None
                            userString = ""
                            userStringErrorDisplay = None
                            lobby_timer_for_error_display = 0
                            last_ping_sent_time = 0.0
                            continue
                        else:
                            lobby_timer_for_error_display = 0.5 * fps
                            userStringErrorDisplay = "press enter to continue" if userString == "" else "no other input for client"
                            continue
                elif event.key not in keyHoldFrames:
                    keyHoldFrames[event.key] = 0
            if event.type == pygame.KEYUP:
                keyHoldFrames.pop(event.key, None)
                if event.key == pygame.K_LSHIFT or event.key == pygame.K_RSHIFT: shifting = False

        for key, hold_time in list(keyHoldFrames.items()):
            keyHoldFrames[key] += 1
            if hold_time == 0 or hold_time > delayThreshold:
                if key == pygame.K_BACKSPACE:
                    if userString: userString = userString[:-1]
                elif pygame.K_0 <= key <= pygame.K_9:
                    if len(userString) < 6: userString += chr(key)
                elif pygame.K_a <= key <= pygame.K_z:
                    if len(userString) < 6:
                        if shifting:
                            userString += chr(key - 32)
                        else:
                            userString += chr(key)
                if hold_time > delayThreshold: keyHoldFrames[key] = delayThreshold

        if mode != "IN_GAME":
            if mode == "CLIENT_LOBBY" and joined:
                if time.time() - last_ping_sent_time > client_ping_interval:
                    if target_host_ip and target_host_port:
                        try:
                            client_socket.sendto(f"PING:{username}".encode(), (target_host_ip, target_host_port))
                            last_ping_sent_time = time.time()
                        except OSError as err:
                            print(f"Client: Error sending ping: {err}. Host likely disconnected.")
                            lobby_timer_for_error_display = 1.0 * fps
                            userString = ""
                            userStringErrorDisplay = "Host disconnected or timed out"
                            requestSentTime = None
                            mode = "INIT"
                    else:
                        print("Client: Cannot send ping, target_host_ip/port not set after joining. Resetting.")
                        mode = "INIT"
                        userStringErrorDisplay = "Connection error"
            if mode == "CLIENT_LOBBY" and not joined:
                if requestSentTime and time.time() - requestSentTime > 2.0:
                    lobby_timer_for_error_display = 1.0 * fps
                    userString = ""
                    userStringErrorDisplay = "lobby doesn't exist or timed out"
                    requestSentTime = None
                    mode = "INIT"
            if mode == "HOST_LOBBY" and time.time() - last_host_check_time > 1.0:
                disconnected_players = []
                for addr, last_time_ping in client_last_ping_time.items():
                    if time.time() - last_time_ping > client_timeout_threshold:
                        disconnected_players.append(addr)
                for addr_to_remove in disconnected_players:
                    if addr_to_remove in players:
                        print(f"Host: Player '{players[addr_to_remove]}' ({addr_to_remove}) timed out.")
                        del players[addr_to_remove]
                    del client_last_ping_time[addr_to_remove]
                last_host_check_time = time.time()

            if mode == "INIT":
                drawText(surf_ui, Cols.crimson, Alkhemikal200, main_title_x, screen_center[1] - 80, "Crimson",
                         Cols.dark, shadowSize=5, justify="center", centeredVertically=True)
                drawText(surf_ui, Cols.crimson, Alkhemikal200, main_title_x, screen_center[1] + 80, "Wakes", Cols.dark,
                         shadowSize=5, justify="center", centeredVertically=True)
                if lobby_timer_for_error_display < 0:
                    blink_char = '~' if int(lobby_timer_for_error_display / fps * 2) % 2 else ' '
                    userStringErrorDisplay = (f"-> {blink_char} <-" if userString == "" else None)
                prompt = "type 'start' to host or enter a code to join"
                drawText(surf_ui, Cols.light, Alkhemikal50, screen_width * 0.75, screen_center[1] - 40, prompt,
                         Cols.dark, 3, justify="middle", centeredVertically=True, maxLen=screen_width / 3, wrap=True)
                drawText(surf_ui, Cols.crimson if lobby_timer_for_error_display > 0 else Cols.light,
                         Alkhemikal80 if userStringErrorDisplay else Alkhemikal200, screen_width * 0.75,
                         screen_center[1] + 100,
                         userString if userStringErrorDisplay is None else userStringErrorDisplay, Cols.dark, 3,
                         justify="middle", centeredVertically=True)
            elif mode == "HOST_LOBBY":
                drawText(surf_ui, Cols.crimson, Alkhemikal150, screen_center[0], screen_center[1] - 260, "HOST LOBBY",
                         Cols.dark, 3, justify="middle", centeredVertically=True)
                drawText(surf_ui, Cols.light, Alkhemikal80, screen_center[0], screen_center[1] - 160,
                         f"Room code: {room_code}", Cols.dark, 3, justify="middle", centeredVertically=True)
                drawText(surf_ui, Cols.light, Alkhemikal20, screen_center[0], screen_center[1] - 100,
                         f"Players joined:", Cols.dark, 3, justify="middle", centeredVertically=True)
                current_players_list = list(players.values())
                drawText(surf_ui, Cols.light, Alkhemikal20, screen_center[0], screen_center[1] - 90 + 1 * 25,
                         f"{username} (You)", Cols.dark, 3, justify="middle", centeredVertically=True)
                for i, name in enumerate(current_players_list, start=2):
                    drawText(surf_ui, Cols.light, Alkhemikal20, screen_center[0], screen_center[1] - 90 + i * 25, name,
                             Cols.dark, 3, justify="middle", centeredVertically=True)
                drawText(surf_ui, Cols.light, Alkhemikal30, screen_center[0], screen_center[1] + 280,
                         "type 'begin' to start or 'quit' to exit", Cols.dark, 3, justify="middle",
                         centeredVertically=True)
                if lobby_timer_for_error_display < 0:
                    blink_char = '~' if int(lobby_timer_for_error_display / fps * 2) % 2 else ' '
                    userStringErrorDisplay = (f"-> {blink_char} <-" if userString == "" else None)
                drawText(surf_ui, Cols.crimson if lobby_timer_for_error_display > 0 else Cols.light,
                         Alkhemikal80 if userStringErrorDisplay else Alkhemikal200, screen_center[0],
                         screen_center[1] + 180,
                         userString if userStringErrorDisplay is None else userStringErrorDisplay, Cols.dark, 3,
                         justify="middle", centeredVertically=True)
            elif mode == "CLIENT_LOBBY":
                drawText(surf_ui, Cols.light, Alkhemikal50, screen_center[0], screen_center[1] - 100, "CLIENT LOBBY",
                         Cols.dark, 3, justify="middle", centeredVertically=True)
                status = "JOINED! waiting for host..." if joined else "joining..."
                drawText(surf_ui, Cols.light, Alkhemikal30, screen_center[0], screen_center[1], status, Cols.dark, 3,
                         justify="middle", centeredVertically=True)
                drawText(surf_ui, Cols.light, Alkhemikal30, screen_center[0], screen_center[1] + 180,
                         "type 'quit' to exit", Cols.dark, 3, justify="middle", centeredVertically=True)
                drawText(surf_ui, Cols.crimson if lobby_timer_for_error_display > 0 else Cols.light,
                         Alkhemikal80 if userStringErrorDisplay else Alkhemikal200, screen_center[0],
                         screen_center[1] + 80,
                         userString if userStringErrorDisplay is None else userStringErrorDisplay, Cols.dark, 3,
                         justify="middle", centeredVertically=True)

            if toggle:
                string_fps = f"FPS: {round(clock.get_fps())}"
                drawText(surf_ui, Cols.crimson, Alkhemikal30, 5, screen_height - 30, string_fps, Cols.dark, 3,
                         antiAliasing=False)
                drawText(surf_ui, Cols.light, Alkhemikal30, screen_width / 2, 30, f"your name is {username}", Cols.dark,
                         3, justify="middle", centeredVertically=True)
                pygame.draw.circle(surf_ui, Cols.dark, (mx + 2, my + 2), 7, 2)
                pygame.draw.circle(surf_ui, Cols.light, (mx, my), 7, 2)

            ctx.screen.use()
            ctx.clear(0, 0, 0, 1)
            tex_ui.write(pygame.image.tobytes(surf_ui, 'RGBA'))
            tex_ui.use(location=0)
            vao_ui.render(moderngl.TRIANGLE_STRIP)
            pygame.display.flip()
            clock.tick(fps)
            continue

        if future is None:
            print(f"Main: Submitting TileHandler generation task to worker with seed: {seed}.")
            target_width = int(MAP_GENERATION_WIDTH * GenerationInfo.mapSizeScalar)
            target_height = int(MAP_GENERATION_HEIGHT * GenerationInfo.mapSizeScalar)

            worker_args = (target_width, target_height, screen_width, screen_height, GenerationInfo,
                           font_name_needed_by_worker, fonts_definitions, Cols, ResourceInfo, StructureInfo,
                           status_queue_for_main_thread, PRESET_EXECUTION_TIMES, seed)
            future = executor.submit(build_tile_handler_worker, worker_args)
            loading_screen_start_time = time.time()

        if not TH_fully_initialized:
            numPeriods = (numPeriods + 3 / fps) % 4
            if not worker_tasks_complete and future.done() and not retrieving_result_active:
                print(f"[DEBUG_TIMING] Future Done detected at {time.time()}")
                worker_tasks_complete = True
                retrieving_result_active = True
                task_data = task_display_states["retrieveMapData"]
                task_data['status'] = 'Starting'
                task_data['start_time'] = time.time()
                task_data['expected_time'] = PRESET_EXECUTION_TIMES.get("retrieveMapData",
                                                                        INITIAL_PRESET_PLACEHOLDER_TIME)
            elif retrieving_result_active:
                t0 = time.perf_counter()
                try:
                    print(f"[DEBUG] Calling future.result() at {time.time()}...")
                    payload = future.result()
                    t1 = time.perf_counter()
                    print(f"[DEBUG] payload retrieved in {t1 - t0:.4f}s")
                    from generation import TileHandler

                    TH = TileHandler(
                        payload['mapWidth'], payload['mapHeight'],
                        GenerationInfo.tileSize, Cols,
                        GenerationInfo.waterThreshold, GenerationInfo.mountainThreshold, GenerationInfo.territorySize,
                        font=None, font_name=None,
                        resource_info=ResourceInfo, structure_info=StructureInfo,
                        viewport_width=payload['viewportWidth'], viewport_height=payload['viewportHeight']
                    )
                    TH.reconstruct_from_payload(payload, loaded_fonts, status_queue_for_main_thread,
                                                PRESET_EXECUTION_TIMES)
                    t2 = time.perf_counter()
                    print(f"[DEBUG] reconstruction took {t2 - t1:.4f}s")
                    retrieval_duration = t1 - t0
                    all_current_run_times["retrieveMapData"] = retrieval_duration
                    task_data = task_display_states["retrieveMapData"]
                    task_data['status'] = 'Finished'
                    task_data['duration'] = retrieval_duration
                    retrieving_result_active = False
                    if TH and hasattr(TH, 'execution_times'): all_current_run_times.update(TH.execution_times)
                    TH_fully_initialized = True
                except Exception as e_future_result:
                    t_err = time.perf_counter()
                    print(f"[DEBUG] Error retrieving result: {e_future_result} (Time: {t_err - t0:.4f}s)")
                    import traceback

                    traceback.print_exc()
                    retrieval_duration = t_err - t0
                    all_current_run_times["retrieveMapData (Error)"] = retrieval_duration
                    task_data = task_display_states["retrieveMapData"]
                    task_data['status'] = 'Error'
                    task_data['duration'] = retrieval_duration
                    print(f"Main Error: Retrieving map data failed: {e_future_result}")
                    TH_fully_initialized = True
                    retrieving_result_active = False

            try:
                while not status_queue_for_main_thread.empty():
                    step_name_key_from_worker, status_type, time_value = status_queue_for_main_thread.get_nowait()
                    display_name_human_readable = DISPLAY_NAMES_MAP.get(step_name_key_from_worker,
                                                                        step_name_key_from_worker)
                    if step_name_key_from_worker not in task_display_states:
                        print(f"Main: Received unknown task status key: '{step_name_key_from_worker}'.")
                        continue
                    current_task_data = task_display_states[step_name_key_from_worker]
                    if status_type == "START":
                        current_task_data['status'] = 'Starting'
                        current_task_data['start_time'] = time.time()
                        current_task_data['expected_time'] = time_value
                    elif status_type == "SENT":
                        current_task_data['status'] = 'Sent'
                        current_task_data['start_time'] = time.time()
                        current_task_data['expected_time'] = time_value
                    elif status_type == "FINISHED":
                        current_task_data['status'] = 'Finished'
                        current_task_data['duration'] = time_value
                    elif status_type == "ERROR":
                        current_task_data['status'] = 'Error'
                        current_task_data['duration'] = 0.0
                        print(f"Main (Error from queue): Task '{display_name_human_readable}' failed.")
                        TH_fully_initialized = True
            except (multiprocessing.queues.Empty, EOFError):
                pass
            except Exception as e_queue:
                print(f"Main: Error processing status queue: {e_queue}")
                TH_fully_initialized = True

            drawText(surf_ui, Cols.crimson, Alkhemikal200, main_title_x, screen_center[1] - 150, "Crimson", Cols.dark,
                     shadowSize=5, justify="center", centeredVertically=True)
            drawText(surf_ui, Cols.crimson, Alkhemikal200, main_title_x, screen_center[1] - 10, "Wakes", Cols.dark,
                     shadowSize=5, justify="center", centeredVertically=True)

            current_overall_phase = PHASE_WORKER_INIT
            if task_display_states["gfxTotalInit"]['status'] in ['Starting', 'Sent', 'Finished', 'Error']:
                current_overall_phase = PHASE_GFX_INIT
            elif task_display_states["retrieveMapData"]['status'] in ['Starting', 'Sent', 'Finished', 'Error']:
                current_overall_phase = PHASE_RETRIEVING_MAP_DATA
            elif task_display_states["dataSerialization"]['status'] in ['Starting', 'Sent', 'Finished', 'Error']:
                current_overall_phase = PHASE_DATA_TRANSFER_PREP

            top_loading_text = current_overall_phase + ("." * int(numPeriods))
            if TH_fully_initialized and TH:
                top_loading_text = "Loading Complete!"
            elif TH_fully_initialized and not TH:
                top_loading_text = "Generation Error"

            drawText(surf_ui, Cols.light, Alkhemikal50, main_overall_phase_x, screen_center[1] + 90, top_loading_text,
                     Cols.dark, shadowSize=5, justify="center", centeredVertically=True)

            y_pos_offset = 0
            for task_name_key in LOADING_STEPS_ORDER:
                task_data = task_display_states[task_name_key]
                status = task_data['status']
                task_y_pos = single_task_display_start_y + y_pos_offset
                display_name_human_readable = DISPLAY_NAMES_MAP.get(task_name_key, task_name_key)
                if display_name_human_readable == "World Generation Complete (Worker)": continue

                infoText = ""
                progress_ratio = 0.0
                show_progress_bar = False

                if status == 'Pending':
                    infoText = "Pending"
                elif status == 'Starting':
                    elapsed_time = time.time() - task_data['start_time']
                    expected = task_data['expected_time']
                    expected_str = f"{expected:.2f}s" if expected != INITIAL_PRESET_PLACEHOLDER_TIME else "Calc..."
                    infoText = f"{elapsed_time:.2f}s / {expected_str}"
                    progress_ratio = normalize(elapsed_time, 0, expected, clamp=True) if expected > 0 else 0.0
                    show_progress_bar = True
                elif status == 'Sent':
                    elapsed_time = time.time() - task_data['start_time']
                    expected = task_data['expected_time']
                    expected_str = f"{expected:.2f}s" if expected != INITIAL_PRESET_PLACEHOLDER_TIME else "Calc..."
                    infoText = f"SENT ({elapsed_time:.2f}s / {expected_str})"
                    progress_ratio = normalize(elapsed_time, 0, expected, clamp=True) if expected > 0 else 0.0
                    show_progress_bar = True
                elif status == 'Finished':
                    infoText = f"Done ({task_data['duration']:.2f}s)"
                    progress_ratio = 1.0
                    show_progress_bar = True
                elif status == 'Error':
                    infoText = "Error!"
                    progress_ratio = 0.0
                    show_progress_bar = False

                if Alkhemikal20:
                    drawText(surf_ui, Cols.light, Alkhemikal20, tasks_list_x, task_y_pos, display_name_human_readable,
                             Cols.dark, shadowSize=2, justify="left")
                    drawText(surf_ui, Cols.light, Alkhemikal20, screen_width - 10, task_y_pos, infoText, Cols.dark,
                             shadowSize=2, justify="right")

                if show_progress_bar:
                    bar_start_x = screen_width * 0.7
                    bar_y = task_y_pos + progress_bar_y_offset
                    outline_rect = pygame.Rect(bar_start_x, bar_y, progress_bar_width, progress_bar_height)
                    pygame.draw.rect(surf_ui, Cols.dark, outline_rect, 2, border_radius=progress_bar_corner_radius)
                    fill_width = progress_bar_width * progress_ratio
                    if fill_width >= 1:
                        current_corner_radius = progress_bar_corner_radius
                        if fill_width < 2 * progress_bar_corner_radius: current_corner_radius = int(fill_width / 2)
                        if current_corner_radius < 0: current_corner_radius = 0
                        fill_rect = pygame.Rect(bar_start_x, bar_y, fill_width, progress_bar_height)
                        pygame.draw.rect(surf_ui, Cols.crimson, fill_rect, 0, border_radius=current_corner_radius)
                y_pos_offset += line_height

            total_current_progress_elapsed = 0.0
            for task_name_key in LOADING_STEPS_FOR_PROGRESS_BAR:
                task_data = task_display_states[task_name_key]
                if task_data['status'] == 'Finished':
                    total_current_progress_elapsed += task_data['expected_time']
                elif task_data['status'] == 'Starting' or task_data['status'] == 'Sent':
                    total_current_progress_elapsed += min(time.time() - task_data['start_time'],
                                                          task_data['expected_time'])

            total_progress_ratio = normalize(total_current_progress_elapsed, 0, total_expected_loading_time, clamp=True)
            total_bar_height = 20
            total_bar_y = screen_height - total_bar_height - 30
            total_bar_x_margin = 200
            total_bar_width = screen_width - 2 * total_bar_x_margin

            pygame.draw.rect(surf_ui, Cols.dark, (total_bar_x_margin, total_bar_y, total_bar_width, total_bar_height),
                             2, border_radius=total_bar_height // 3)
            fill_total_width = total_bar_width * total_progress_ratio
            if fill_total_width >= 1:
                current_corner_radius = total_bar_height // 3
                if fill_total_width < 2 * current_corner_radius: current_corner_radius = int(fill_total_width / 2)
                if current_corner_radius < 0: current_corner_radius = 0
                fill_rect = pygame.Rect(total_bar_x_margin, total_bar_y, fill_total_width, total_bar_height)
                pygame.draw.rect(surf_ui, Cols.crimson, fill_rect, 0, border_radius=current_corner_radius)

            progress_percentage = int(total_progress_ratio * 100)
            if Alkhemikal30: drawText(surf_ui, Cols.light, Alkhemikal30, screen_width / 2, total_bar_y - 25,
                                      f"Total Progress: {progress_percentage}%", Cols.dark, 3, justify="middle",
                                      centeredVertically=True)

            if toggle:
                string_fps = f"FPS: {round(clock.get_fps())}"
                drawText(surf_ui, Cols.crimson, Alkhemikal30, 5, screen_height - 30, string_fps, Cols.dark, 3,
                         antiAliasing=False)
                drawText(surf_ui, Cols.light, Alkhemikal30, screen_width / 2, 30, f"your name is {username}", Cols.dark,
                         3, justify="middle", centeredVertically=True)
                pygame.draw.circle(surf_ui, Cols.dark, (mx + 2, my + 2), 7, 2)
                pygame.draw.circle(surf_ui, Cols.light, (mx, my), 7, 2)

            ctx.screen.use()
            ctx.clear(0, 0, 0, 1)
            tex_ui.write(pygame.image.tobytes(surf_ui, 'RGBA'))
            tex_ui.use(location=0)
            vao_ui.render(moderngl.TRIANGLE_STRIP)
            pygame.display.flip()
            clock.tick(fps)
            continue

        if loading_screen_start_time != 0:
            total_loading_screen_time = time.time() - loading_screen_start_time
            print(f"Main: Loading screen displayed for: {total_loading_screen_time:.4f} seconds.")
            loading_screen_start_time = 0

        print("Main: Shutting down executor and manager.")
        executor.shutdown(wait=True)
        manager.shutdown()

        if all_current_run_times: save_execution_times(all_current_run_times)
        if TH is None or TH.playersSurfScreen is None:
            print("Error: TileHandler failed to initialize. Exiting.")
            pygame.quit()
            sys.exit()

        print("Main: TileHandler fully initialized. Starting game.")
        player = Player(target_host_ip, target_host_port, None, (screen_width, screen_height),
                        {'30': Alkhemikal30, '50': Alkhemikal50, '80': Alkhemikal80, '150': Alkhemikal150,
                         '200': Alkhemikal200}, Cols)
        break

    if not running:
        pygame.quit()
        sys.exit()

    scrollSpeed = 50
    scroll = [0.0, 0.0]
    targetScroll = [0.0, 0.0]
    momentum = [0.0, 0.0]
    moving = [0.0, 0.0]
    bottomUIBarSize = uiInfo.bottomUIBarSize * screen_height
    max_scroll_x = 0
    min_scroll_x = min(0, -(TH.mapWidth - screen_width))
    max_scroll_y = 0
    min_scroll_y = min(0, -(TH.mapHeight - screen_height))
    debug = False
    mouseSize = 1
    click = False
    showClouds = True
    pygame.mouse.set_visible(False)
    t = 0.0

    while running:
        dt_raw = clock.tick(fps) / 1000.0
        t += dt_raw
        dt = dt_raw * fps
        last_time = time.time()
        mx, my = pygame.mouse.get_pos()
        mx_render = mx * (INT_CLOUD_RENDER_W / WINDOW_WIDTH)
        my_render = (WINDOW_HEIGHT - my) * (INT_CLOUD_RENDER_H / WINDOW_HEIGHT)

        surf_game.fill(Cols.dark)
        surf_ui.fill((0, 0, 0, 0))

        for event in pygame.event.get():
            if event.type == pygame.QUIT: running = False
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1: click = True
            if event.type == pygame.MOUSEBUTTONUP and event.button == 1: click = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE: running = False
                if event.key == pygame.K_SPACE: toggle = not toggle
                if event.key == pygame.K_a: moving[0] += 1
                if event.key == pygame.K_d: moving[0] -= 1
                if event.key == pygame.K_w: moving[1] += 1
                if event.key == pygame.K_s: moving[1] -= 1
                if event.key == pygame.K_x: debug = not debug
                if event.key == pygame.K_m: mouseSize = (mouseSize + 1) % 4
                if event.key == pygame.K_c: showClouds = not showClouds
            if event.type == pygame.KEYUP:
                if event.key == pygame.K_a: moving[0] -= 1
                if event.key == pygame.K_d: moving[0] += 1
                if event.key == pygame.K_w: moving[1] -= 1
                if event.key == pygame.K_s: moving[1] += 1

        targetScroll[0] += scrollSpeed * moving[0]
        targetScroll[1] += scrollSpeed * moving[1]
        scrollBufferSize = 100
        targetScroll[0] = min(max(targetScroll[0], min_scroll_x - scrollBufferSize), max_scroll_x + scrollBufferSize)
        targetScroll[1] = min(max(targetScroll[1], min_scroll_y - scrollBufferSize), max_scroll_y + scrollBufferSize)
        diffs = [targetScroll[0] - scroll[0], targetScroll[1] - scroll[1]]
        for idx, diff in enumerate(diffs):
            momentum[idx] += diff / 25
            momentum[idx] *= 0.7
            scroll[idx] += momentum[idx]
            scroll[idx] = min(max(scroll[idx], [min_scroll_x - scrollBufferSize, min_scroll_y - scrollBufferSize][idx]),
                              [max_scroll_x + scrollBufferSize, max_scroll_y + scrollBufferSize][idx])

        adjustedMx, adjustedMy = [mx - scroll[0], my - scroll[1]]
        tile_under_mouse = None
        if TH.hitMaskSurf:
            try:
                if 0 <= int(adjustedMx) < TH.mapWidth and 0 <= int(adjustedMy) < TH.mapHeight:
                    col = TH.hitMaskSurf.get_at((int(adjustedMx), int(adjustedMy)))
                    if col.a > 0:
                        picked_id = col.r + (col.g << 8) + (col.b << 16)
                        tile_under_mouse = TH.tiles_by_id.get(picked_id)
            except IndexError:
                pass

        hovered_territory = None
        if tile_under_mouse and tile_under_mouse.territory_id != -1:
            potential_hovered_terr = TH.territories_by_id.get(tile_under_mouse.territory_id)
            hovered_territory = potential_hovered_terr

        player.handleClick(click, dt, hovered_territory)
        player.update(dt)

        high_res_view = pygame.Surface((screen_width, screen_height))
        high_res_view.fill(Cols.dark)
        if TH.baseMapSurf: high_res_view.blit(TH.baseMapSurf, (scroll[0], scroll[1]))
        if debug and TH.debugOverlayFullMap: high_res_view.blit(TH.debugOverlayFullMap, (scroll[0], scroll[1]))
        TH.drawTerritoryHighlights(high_res_view, hovered_territory, player.selectedTerritory, scroll)
        TH.playersSurfScreen.fill((0, 0, 0, 0))
        player.draw(TH.playersSurfScreen, surf_ui, False, scroll)
        high_res_view.blit(TH.playersSurfScreen, (0, 0))
        pygame.transform.scale(high_res_view, (INT_GAME_RENDER_W, INT_GAME_RENDER_H), surf_game)

        pygame.draw.line(surf_ui, Cols.debugRed, (0, screen_height - bottomUIBarSize),
                         (screen_width, screen_height - bottomUIBarSize), 2)
        if toggle:
            fps_text = f"{clock.get_fps():.1f}"
            if Alkhemikal30:
                sel_terr_text = "No Territory"
                if player.selectedTerritory and hasattr(player.selectedTerritory,
                                                        'id'): sel_terr_text = f"Territory ID: {player.selectedTerritory.id}"
                drawText(surf_ui, Cols.light, Alkhemikal30, screen_width / 2, 30, f"your name is {username}", Cols.dark,
                         3, justify="middle", centeredVertically=True)
                drawText(surf_ui, Cols.debugRed, Alkhemikal30, 5, screen_height - 90, sel_terr_text, Cols.dark, 3,
                         antiAliasing=False)
                drawText(surf_ui, Cols.debugRed, Alkhemikal30, 5, screen_height - 60, fps_text, Cols.dark, 3,
                         antiAliasing=False)
                drawText(surf_ui, Cols.debugRed, Alkhemikal30, 5, screen_height - 30,
                         "[spc] UI, [x] Debug, [m] Mouse Size, [c] Clouds", Cols.dark, 3, antiAliasing=False)
            pygame.draw.circle(surf_ui, Cols.dark, (mx + 2, my + 2), 7, 2)
            pygame.draw.circle(surf_ui, Cols.light, (mx, my), 7, 2)

        cam_x = -scroll[0]
        cam_y = -scroll[1]
        scroll_render_x = cam_x * (INT_CLOUD_RENDER_W / WINDOW_WIDTH)
        scroll_render_y = cam_y * (INT_CLOUD_RENDER_H / WINDOW_HEIGHT)
        clouds.update(scroll_render_x, scroll_render_y, dt_raw)

        tex_game.write(pygame.image.tobytes(surf_game, 'RGB'))
        tex_ui.write(pygame.image.tobytes(surf_ui, 'RGBA'))
        vbo_instances.write(clouds.get_instance_buffer())

        holes = []
        holes.append((mx_render, my_render))
        for s in player.ships:
            screen_x = s.pos[0] + scroll[0]
            screen_y = s.pos[1] + scroll[1]
            sx = screen_x * (INT_CLOUD_RENDER_W / WINDOW_WIDTH)
            sy = (WINDOW_HEIGHT - screen_y) * (INT_CLOUD_RENDER_H / WINDOW_HEIGHT)
            holes.append((sx, sy))

        visible_tiles_count = 0
        MAX_SHADER_HOLES = 256
        view_rect = pygame.Rect(-scroll[0], -scroll[1], screen_width, screen_height)
        for tid in player.visibleTerritoryIDs:
            terr = TH.territories_by_id.get(tid)
            if terr:
                for tile in terr.tiles:
                    if view_rect.collidepoint(tile.x, tile.y):
                        screen_x = tile.x + scroll[0]
                        screen_y = tile.y + scroll[1]
                        tx = screen_x * (INT_CLOUD_RENDER_W / WINDOW_WIDTH)
                        ty = (WINDOW_HEIGHT - screen_y) * (INT_CLOUD_RENDER_H / WINDOW_HEIGHT)
                        holes.append((tx, ty))
                        visible_tiles_count += 1
                        if len(holes) >= MAX_SHADER_HOLES: break
            if len(holes) >= MAX_SHADER_HOLES: break
        while len(holes) < MAX_SHADER_HOLES: holes.append((-9999.0, -9999.0))

        prog_clouds['u_holes'].value = holes
        prog_clouds['u_num_holes'].value = visible_tiles_count + 1 + len(player.ships)
        prog_clouds['u_vision_radius'].value = VISION_RADIUS

        fbo_clouds.use()
        ctx.clear(0, 0, 0, 0)
        prog_clouds['u_scroll'].value = (scroll_render_x, -scroll_render_y)
        prog_clouds['u_time'].value = t
        if showClouds:
            for i in range(5):
                prog_clouds['u_layer_idx'].value = i
                vao_clouds.render(moderngl.TRIANGLE_STRIP, instances=CLOUD_COUNT)

        fbo_composite.use()
        ctx.clear(0, 0, 0, 0)
        tex_game.use(location=0)
        tex_cloud_color.use(location=1)
        vao_comp.render(moderngl.TRIANGLE_STRIP)

        ctx.screen.use()
        ctx.clear(0, 0, 0, 1)
        tex_composite.use(location=0)
        prog_post['u_time'].value = t
        vao_post.render(moderngl.TRIANGLE_STRIP)

        tex_ui.use(location=0)
        vao_ui.render(moderngl.TRIANGLE_STRIP)
        pygame.display.flip()

    pygame.quit()
    sys.exit()