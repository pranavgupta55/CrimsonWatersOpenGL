import pygame
import sys
import os
import math
import copy

# --- PATH SETUP ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

from config import *
from editor_utils import *

# Framework imports
from fontDict import fonts
from text import drawText, getFontSize
from calcs import distance


class Pixel:
    """Represents a single pixel on the hex canvas."""

    def __init__(self, x, y, color):
        self.grid_x = x
        self.grid_y = y
        self.c = color
        self.history = [self.c]  # Fixed crash here
        self.rect = pygame.Rect(0, 0, 1, 1)


class Button:
    def __init__(self, x, y, w, h, text, callback, col=Endesga.grey_blue, text_col=Endesga.white):
        self.rect = pygame.Rect(x, y, w, h)
        self.text = text
        self.callback = callback
        self.col = col
        self.text_col = text_col
        self.hover = False
        self.visible = True

    def draw(self, screen, font):
        if not self.visible: return
        color = Endesga.lighter_maroon_red if self.hover else self.col
        pygame.draw.rect(screen, color, self.rect, 0, 4)
        pygame.draw.rect(screen, Endesga.black, self.rect, 1, 4)
        drawText(screen, self.text_col, font, self.rect.centerx, self.rect.centery, self.text, justify="center",
                 centeredVertically=True)

    def handle_event(self, event):
        if not self.visible: return False
        if event.type == pygame.MOUSEMOTION:
            self.hover = self.rect.collidepoint(event.pos)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.hover:
            self.callback()
            return True
        return False


class FileEntry:
    def __init__(self, name, surface, is_new=False, is_mod=False):
        self.name = name
        self.surface = surface.copy() if surface else None
        self.is_new = is_new
        self.is_modified = is_mod
        self.original_surface = surface.copy() if surface and not is_new else None


class Editor:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode(WINDOW_SIZE)
        pygame.display.set_caption("Crimson Waters - Hex Editor")
        self.clock = pygame.time.Clock()

        # --- ASSETS ---
        self.tiles_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))

        # --- FONTS ---
        self.font_reg = self.load_font("montserrat-regular25", 25)
        self.font_bold = self.load_font("montserrat-bold25", 25)
        self.font_small = self.load_font("montserrat-bold15", 15)

        # --- KEYBOARD / TYPING STATE ---
        self.shiftPressed = False
        self.keyHoldFrames = {}
        self.delayThreshold = 10
        self.typing_mode = False
        self.rename_target = None
        self.user_string = ""

        # --- EDITOR STATE ---
        self.mode = "PAINTER"
        self.active_entry = None

        self.pixels = []
        self.mask_surf = create_hex_mask_surface(TARGET_WIDTH, TARGET_HEIGHT)

        # --- FILES ---
        self.files = []
        self.refresh_file_list()

        if self.files:
            self.switch_file(self.files[0])
        else:
            self.create_new_file()

        # --- VIEW ---
        self.cam_zoom = 20.0
        self.cam_pos = [0, 0]
        self.oscillating_thing = 0

        # --- CROPPER ---
        self.source_img = None
        self.crop_view_zoom = 20.0
        self.img_pos = [WINDOW_SIZE[0] // 2, WINDOW_SIZE[1] // 2]
        self.img_scale = 1.0

        # --- UI ---
        self.selected_color = Endesga.white
        self.message_timer = 0
        self.message = ""
        self.bg_surf = generate_checkerboard(WINDOW_SIZE[0], WINDOW_SIZE[1])

        self.buttons = []
        self.init_ui_elements()

    def load_font(self, key, size):
        if key in fonts:
            val = fonts[key]
            if isinstance(val, tuple):
                path = os.path.join(self.project_root, val[0])
                try:
                    return pygame.font.Font(path, size)
                except:
                    pass
            else:
                return val
        return pygame.font.SysFont("arial", size)

    def _to_rgba(self, color):
        if len(color) == 3: return (*color, 255)
        return color

    def init_ui_elements(self):
        self.buttons = []
        bx = WINDOW_SIZE[0] - 220
        by = WINDOW_SIZE[1] - 100
        self.buttons.append(Button(bx, by, 40, 30, "<<", lambda: self.zoom_step(0.9), Endesga.greyVD))
        self.buttons.append(Button(bx + 45, by, 40, 30, "<", lambda: self.zoom_step(0.98), Endesga.greyVD))
        self.buttons.append(Button(bx + 90, by, 40, 30, ">", lambda: self.zoom_step(1.02), Endesga.greyVD))
        self.buttons.append(Button(bx + 135, by, 40, 30, ">>", lambda: self.zoom_step(1.1), Endesga.greyVD))

        self.btn_mode = Button(WINDOW_SIZE[0] - 110, 10, 100, 30, "SWITCH", self.toggle_mode, Endesga.grey_blue)
        self.buttons.append(self.btn_mode)

        self.btn_capture = Button(WINDOW_SIZE[0] // 2 - 60, WINDOW_SIZE[1] - 80, 120, 40, "CAPTURE", self.capture_crop,
                                  Endesga.crimson)
        self.buttons.append(self.btn_capture)

        self.btn_new = Button(10, 50, 180, 25, "+ NEW CANVAS", self.create_new_file, Endesga.grey_blue)
        self.buttons.append(self.btn_new)

    def toggle_mode(self):
        if self.mode == "PAINTER":
            self.mode = "CROPPER"
            self.show_message("Switched to Cropper")
        else:
            self.mode = "PAINTER"
            self.show_message("Switched to Painter")

    def zoom_step(self, factor):
        if self.mode == "PAINTER":
            self.cam_zoom = max(1.0, min(100.0, self.cam_zoom * factor))
        else:
            self.scale_image_centered(factor)

    def scale_image_centered(self, factor):
        old_scale = self.img_scale
        self.img_scale = max(0.001, self.img_scale * factor)
        cx, cy = WINDOW_SIZE[0] / 2, WINDOW_SIZE[1] / 2
        self.img_pos[0] = cx - (cx - self.img_pos[0]) * (self.img_scale / old_scale)
        self.img_pos[1] = cy - (cy - self.img_pos[1]) * (self.img_scale / old_scale)

    def refresh_file_list(self):
        """Loads existing files from disk into FileEntry objects."""
        existing_names = [f.name for f in self.files]
        try:
            for f in os.listdir(self.tiles_dir):
                if f.lower().endswith('.png') and f not in existing_names:
                    try:
                        path = os.path.join(self.tiles_dir, f)
                        # Load image regardless of size
                        img = pygame.image.load(path).convert_alpha()
                        self.files.append(FileEntry(f, img))
                    except:
                        pass

            self.files.sort(key=lambda x: x.name)
        except:
            pass

    def switch_file(self, entry):
        if self.active_entry:
            self.commit_canvas_to_entry()

        self.active_entry = entry
        self.active_filename = entry.name

        # Check size mismatch
        if entry.surface.get_width() != TARGET_WIDTH or entry.surface.get_height() != TARGET_HEIGHT:
            self.show_message(f"Size Mismatch! Opening Cropper.")
            self.source_img = entry.surface
            self.mode = "CROPPER"
            # Reset image pos
            self.img_scale = 10.0
            self.img_pos = [WINDOW_SIZE[0] // 2 - (entry.surface.get_width() * self.img_scale) // 2,
                            WINDOW_SIZE[1] // 2 - (entry.surface.get_height() * self.img_scale) // 2]
        else:
            self.init_canvas(entry.surface)
            self.mode = "PAINTER"

    def create_new_file(self):
        cnt = 1
        while True:
            name = f"untitled_{cnt}.png"
            if not any(f.name == name for f in self.files):
                break
            cnt += 1

        surf = pygame.Surface((TARGET_WIDTH, TARGET_HEIGHT), pygame.SRCALPHA)
        new_entry = FileEntry(name, surf, is_new=True)
        self.files.insert(0, new_entry)
        self.switch_file(new_entry)
        self.show_message("Created New File")

    def capture_crop(self):
        """Creates a NEW file from crop."""
        if not self.source_img: return

        cx, cy = WINDOW_SIZE[0] // 2, WINDOW_SIZE[1] // 2
        reticle_zoom = self.crop_view_zoom
        reticle_x = cx - (TARGET_WIDTH * reticle_zoom) / 2
        reticle_y = cy - (TARGET_HEIGHT * reticle_zoom) / 2

        new_surf = pygame.Surface((TARGET_WIDTH, TARGET_HEIGHT), pygame.SRCALPHA)

        for y in range(TARGET_HEIGHT):
            for x in range(TARGET_WIDTH):
                if is_point_in_hex(x, y, self.mask_surf):
                    screen_px = reticle_x + (x * reticle_zoom) + (reticle_zoom / 2)
                    screen_py = reticle_y + (y * reticle_zoom) + (reticle_zoom / 2)
                    img_x = int((screen_px - self.img_pos[0]) / self.img_scale)
                    img_y = int((screen_py - self.img_pos[1]) / self.img_scale)

                    if 0 <= img_x < self.source_img.get_width() and 0 <= img_y < self.source_img.get_height():
                        new_surf.set_at((x, y), self.source_img.get_at((img_x, img_y)))

        cnt = 1
        base = self.active_filename.replace(".png", "")
        while True:
            name = f"{base}_crop{cnt}.png"
            if not any(f.name == name for f in self.files):
                break
            cnt += 1

        new_entry = FileEntry(name, new_surf, is_new=True)
        self.files.insert(0, new_entry)
        self.switch_file(new_entry)
        self.show_message("Captured to New File!")

    def revert_file(self, entry):
        if entry.is_new:
            if entry in self.files:
                self.files.remove(entry)
                if self.active_entry == entry:
                    self.active_entry = None
                    if self.files:
                        self.switch_file(self.files[0])
                    else:
                        self.create_new_file()
        else:
            entry.surface = entry.original_surface.copy()
            entry.is_modified = False
            if self.active_entry == entry:
                self.init_canvas(entry.surface)
        self.show_message(f"Reverted {entry.name}")

    def start_rename(self, entry):
        self.rename_target = entry
        self.user_string = entry.name.replace(".png", "")
        self.typing_mode = True
        self.show_message("Type to Rename...")

    def commit_rename(self):
        if self.rename_target and self.user_string:
            new_name = self.user_string + ".png"
            if not any(f.name == new_name for f in self.files if f != self.rename_target):
                self.rename_target.name = new_name
                self.rename_target.is_modified = True
            else:
                self.show_message("Name Exists!")
        self.typing_mode = False
        self.rename_target = None

    def save_all_and_quit(self):
        if self.active_entry:
            self.commit_canvas_to_entry()

        count = 0
        for f in self.files:
            if f.is_modified or f.is_new:
                path = os.path.join(self.tiles_dir, f.name)
                try:
                    pygame.image.save(f.surface, path)
                    count += 1
                except Exception as e:
                    print(f"Failed to save {f.name}: {e}")

        print(f"Saved {count} files.")
        pygame.quit()
        sys.exit()

    def init_canvas(self, surface=None):
        self.pixels = []
        for y in range(TARGET_HEIGHT):
            for x in range(TARGET_WIDTH):
                col = (0, 0, 0, 0)
                if surface and x < surface.get_width() and y < surface.get_height():
                    col = surface.get_at((x, y))
                if is_point_in_hex(x, y, self.mask_surf):
                    self.pixels.append(Pixel(x, y, self._to_rgba(col)))

    def commit_canvas_to_entry(self):
        if not self.active_entry: return
        surf = pygame.Surface((TARGET_WIDTH, TARGET_HEIGHT), pygame.SRCALPHA)
        for p in self.pixels:
            surf.set_at((p.grid_x, p.grid_y), p.c)
        self.active_entry.surface = surf

    def show_message(self, msg):
        self.message = msg
        self.message_timer = 120

    def update(self):
        dt = self.clock.tick(FPS) / 1000.0
        self.oscillating_thing += math.pi * dt
        if self.message_timer > 0: self.message_timer -= 1

        if self.typing_mode:
            keys = pygame.key.get_pressed()
            if keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]:
                self.shiftPressed = True
            else:
                self.shiftPressed = False
            return

        keys = pygame.key.get_pressed()
        move_speed = CAMERA_SPEED
        if keys[pygame.K_LSHIFT]: move_speed *= 3

        pan_x = (keys[pygame.K_d] - keys[pygame.K_a] + keys[pygame.K_RIGHT] - keys[pygame.K_LEFT]) * move_speed
        pan_y = (keys[pygame.K_s] - keys[pygame.K_w] + keys[pygame.K_DOWN] - keys[pygame.K_UP]) * move_speed

        if self.mode == "PAINTER":
            self.cam_pos[0] -= pan_x
            self.cam_pos[1] -= pan_y
            if keys[pygame.K_q]: self.zoom_step(0.98)
            if keys[pygame.K_e]: self.zoom_step(1.02)

        elif self.mode == "CROPPER":
            self.img_pos[0] -= pan_x
            self.img_pos[1] -= pan_y
            if keys[pygame.K_q]: self.scale_image_centered(0.98)
            if keys[pygame.K_e]: self.scale_image_centered(1.02)

        self.btn_capture.visible = (self.mode == "CROPPER")
        self.btn_mode.text = "PAINT" if self.mode == "CROPPER" else "CROP"

    def handle_input(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.save_all_and_quit()

            if self.typing_mode:
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.typing_mode = False
                    elif event.key == pygame.K_RETURN:
                        self.commit_rename()
                    elif event.key == pygame.K_BACKSPACE:
                        self.user_string = self.user_string[:-1]
                    elif event.key == pygame.K_SPACE:
                        self.user_string += " "
                    else:
                        if event.unicode.isprintable():
                            self.user_string += event.unicode
                continue

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.save_all_and_quit()

            for b in self.buttons:
                if b.handle_event(event): break

    def draw_ui(self):
        mx, my = pygame.mouse.get_pos()
        click = pygame.mouse.get_pressed()[0]

        for b in self.buttons:
            b.draw(self.screen, self.font_bold)

        if self.mode == "PAINTER":
            ui_size = 30
            cols = 2
            start_x = WINDOW_SIZE[0] - (ui_size * cols) - 10
            start_y = 50
            p_bg = pygame.Rect(start_x - 5, start_y - 5, (ui_size * cols) + 10, (len(PALETTE) // cols * ui_size) + 10)
            pygame.draw.rect(self.screen, Endesga.black, p_bg, 0, 5)
            pygame.draw.rect(self.screen, Endesga.grey, p_bg, 1, 5)

            for i, color in enumerate(PALETTE):
                r = pygame.Rect(start_x + (i % cols) * ui_size, start_y + (i // cols) * ui_size, ui_size, ui_size)
                if self.selected_color == color:
                    pygame.draw.rect(self.screen, Endesga.white, r.inflate(4, 4), 2)
                pygame.draw.rect(self.screen, color, r)
                pygame.draw.rect(self.screen, Endesga.black, r, 1)
                if click and r.collidepoint((mx, my)):
                    self.selected_color = self._to_rgba(color)

        panel_w = 200
        pygame.draw.rect(self.screen, (10, 12, 15), (0, 0, panel_w, WINDOW_SIZE[1]))
        pygame.draw.line(self.screen, Endesga.grey, (panel_w, 0), (panel_w, WINDOW_SIZE[1]))

        modified_files = [f for f in self.files if f.is_modified or f.is_new]
        unedited_files = [f for f in self.files if not (f.is_modified or f.is_new)]

        y_off = 90

        if modified_files:
            drawText(self.screen, Endesga.status_mod, self.font_bold, panel_w // 2, y_off, "WORKSPACE",
                     justify="center")
            y_off += 25
            for f in modified_files:
                self.draw_file_row(f, y_off, panel_w, mx, my, click)
                y_off += 25
            y_off += 15

        drawText(self.screen, Endesga.grey, self.font_bold, panel_w // 2, y_off, "LIBRARY", justify="center")
        y_off += 25
        for f in unedited_files:
            self.draw_file_row(f, y_off, panel_w, mx, my, click)
            y_off += 25

        if self.message_timer > 0:
            drawText(self.screen, Endesga.debug_red, self.font_bold, WINDOW_SIZE[0] // 2, 50, self.message,
                     justify="center")

        info_x = 220
        drawText(self.screen, Endesga.grey, self.font_small, info_x, WINDOW_SIZE[1] - 60, f"Mode: {self.mode}")
        drawText(self.screen, Endesga.grey, self.font_small, info_x, WINDOW_SIZE[1] - 40,
                 f"Zoom: {self.cam_zoom if self.mode == 'PAINTER' else self.img_scale:.4f}")
        drawText(self.screen, Endesga.grey, self.font_small, info_x, WINDOW_SIZE[1] - 20,
                 "ESC: Save & Quit | WASD: Pan | Q/E: Zoom | Right-Click File to Rename")

    def draw_file_row(self, f, y, w, mx, my, click):
        r = pygame.Rect(5, y, w - 10, 22)

        bg_col = (0, 0, 0, 0)
        text_col = Endesga.grey

        if f.is_new:
            text_col = Endesga.status_new
        elif f.is_modified:
            text_col = Endesga.status_mod

        if f == self.active_entry:
            bg_col = Endesga.grey_blue
            text_col = Endesga.white
        elif r.collidepoint((mx, my)):
            bg_col = (30, 35, 40)
            if click:
                self.switch_file(f)
            if pygame.mouse.get_pressed()[2] and not self.typing_mode:
                self.start_rename(f)

        if bg_col != (0, 0, 0, 0):
            pygame.draw.rect(self.screen, bg_col, r, 0, 4)

        if f.is_modified or f.is_new:
            cancel_rect = pygame.Rect(r.right - 20, r.y + 2, 18, 18)
            col_x = Endesga.crimson if cancel_rect.collidepoint((mx, my)) else Endesga.maroon_red
            pygame.draw.rect(self.screen, col_x, cancel_rect, 0, 3)
            drawText(self.screen, Endesga.white, self.font_small, cancel_rect.centerx, cancel_rect.centery, "x",
                     justify="center", centeredVertically=True)
            if click and cancel_rect.collidepoint((mx, my)):
                self.revert_file(f)
                return

        if self.typing_mode and self.rename_target == f:
            pygame.draw.rect(self.screen, Endesga.black, r, 0, 4)
            pygame.draw.rect(self.screen, Endesga.white, r, 1, 4)
            cursor = "|" if (pygame.time.get_ticks() // 500) % 2 == 0 else ""
            drawText(self.screen, Endesga.white, self.font_small, r.x + 5, r.y + 4, self.user_string + cursor)
        else:
            disp_name = f.name if len(f.name) < 20 else f.name[:17] + "..."
            drawText(self.screen, text_col, self.font_small, r.x + 5, r.y + 4, disp_name)

    def draw(self):
        self.screen.fill(Endesga.black)
        self.screen.blit(self.bg_surf, (0, 0))

        cx, cy = WINDOW_SIZE[0] // 2, WINDOW_SIZE[1] // 2

        if self.mode == "PAINTER":
            grid_w = TARGET_WIDTH * self.cam_zoom
            grid_h = TARGET_HEIGHT * self.cam_zoom
            off_x = cx + self.cam_pos[0] - (grid_w / 2)
            off_y = cy + self.cam_pos[1] - (grid_h / 2)

            mx, my = pygame.mouse.get_pos()
            m_L = pygame.mouse.get_pressed()[0]
            m_R = pygame.mouse.get_pressed()[2]

            for p in self.pixels:
                p.rect.x = off_x + p.grid_x * self.cam_zoom
                p.rect.y = off_y + p.grid_y * self.cam_zoom
                p.rect.width = math.ceil(self.cam_zoom)
                p.rect.height = math.ceil(self.cam_zoom)

                if len(p.c) == 4 and p.c[3] > 0:
                    pygame.draw.rect(self.screen, p.c, p.rect)
                elif self.cam_zoom > 5:
                    pygame.draw.rect(self.screen, (30, 30, 30), p.rect, 1)

                if not self.typing_mode and mx > 200 and p.rect.collidepoint((mx, my)):
                    pygame.draw.rect(self.screen, Endesga.white, p.rect, 1)
                    if m_L and p.c != self.selected_color:
                        p.history.append(p.c)
                        p.c = self.selected_color
                        if self.active_entry: self.active_entry.is_modified = True
                    if m_R and p.c != (0, 0, 0, 0):
                        p.history.append(p.c)
                        p.c = (0, 0, 0, 0)
                        if self.active_entry: self.active_entry.is_modified = True

        elif self.mode == "CROPPER":
            self.draw_cropper_view()

        self.draw_ui()

        mx, my = pygame.mouse.get_pos()
        if mx > 200:
            pygame.mouse.set_visible(False)
            pygame.draw.circle(self.screen, Endesga.black, (mx + 1, my + 1), 3, 1)
            pygame.draw.circle(self.screen, Endesga.white, (mx, my), 3, 1)
        else:
            pygame.mouse.set_visible(True)

        pygame.display.flip()

    def run(self):
        while True:
            self.handle_input()
            self.update()
            self.draw()


if __name__ == "__main__":
    Editor().run()