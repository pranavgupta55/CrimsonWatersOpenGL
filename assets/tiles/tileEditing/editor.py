import pygame
import sys
import os
import math
from collections import Counter

# --- PATH SETUP ---
# Move up 3 levels to reach root (assets/tiles/tileEditing -> root)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

# Try imports, handle if config/utils aren't present (for standalone testing context)
try:
    from config import *
    from editor_utils import *
except ImportError:
    # Fallback constants if config is missing
    FPS = 60
    CANVAS_WIDTH = 32
    CANVAS_HEIGHT = 48
    CAMERA_SPEED = 300
    PALETTE = [
        (255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0),
        (255, 0, 255), (0, 255, 255), (255, 255, 255), (128, 128, 128)
    ]


    # Simple mask function mock if utils missing
    def createHexMaskSurface(w, h):
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        s.fill((255, 255, 255))
        return s


    def isPointInMask(x, y, mask):
        if x < 0 or y < 0 or x >= mask.get_width() or y >= mask.get_height(): return False
        return mask.get_at((x, y))[3] > 0


class Endesga:
    white = (255, 255, 255)


# --- THEME COLORS ---
class Theme:
    bg = (10, 12, 16)  # Very Dark Blue/Black
    panel = (18, 22, 28)  # Dark Blue-Grey
    border = (45, 55, 70)  # Lighter Blue-Grey

    text = (220, 220, 230)  # Off-White
    text_dim = (100, 110, 130)  # Dim Blue-Grey

    btn_idle = (30, 35, 45)  # Dark Button
    btn_hover = (50, 60, 80)  # Hover Button
    btn_active = (180, 40, 50)  # Red (Active/Toggle)
    btn_border = (60, 70, 90)  # Button Border

    accent = (60, 120, 200)  # Bright Blue

    outline = (255, 215, 0)  # Gold (High Contrast)
    neighbor_outline = (148, 0, 21)  # Dark Maroon for neighbor outlines (2px thick)
    toast_bg = (40, 180, 60)  # Green
    slider_bg = (40, 40, 50)
    slider_fill = (60, 120, 200)
    checkerboard_dark = (15, 18, 22)  # Slightly lighter than bg


# --- FONT LOADING ---
try:
    from fontDict import fonts
except ImportError:
    fonts = {}


def drawText(surf, col, font, x, y, text, justify="left", centeredVertically=False):
    t = font.render(text, True, col)
    w, h = t.get_size()
    drawX, drawY = x, y
    if justify == 'center':
        drawX -= w // 2
    elif justify == 'right':
        drawX -= w
    if centeredVertically: drawY -= h // 2
    surf.blit(t, (drawX, drawY))
    return w, h


# --- TOOLS ---
TOOL_BRUSH = 0
TOOL_FILL = 1
TOOL_LINE = 2


class Pixel:
    def __init__(self, x, y, color):
        self.gridX = x
        self.gridY = y
        self.c = color
        self.rect = pygame.Rect(0, 0, 1, 1)


class Button:
    def __init__(self, x, y, w, h, text, callback,
                 col=None, textCol=Theme.text,
                 borderCol=Theme.btn_border, toggle=False):
        self.rect = pygame.Rect(x, y, w, h)
        self.text = text
        self.callback = callback

        self.col = col if col else Theme.btn_idle
        self.textCol = textCol
        self.borderCol = borderCol

        self.hover = False
        self.visible = True
        self.isToggle = toggle
        self.active = False
        self.roundness = 6

    def draw(self, screen, font):
        if not self.visible: return

        # Determine Color
        drawCol = self.col
        if self.isToggle and self.active:
            drawCol = Theme.btn_active
        elif self.hover:
            drawCol = Theme.btn_hover

        # Draw Background
        pygame.draw.rect(screen, drawCol, self.rect, 0, self.roundness)
        # Draw Border
        pygame.draw.rect(screen, self.borderCol, self.rect, 2, self.roundness)

        # Draw Text
        drawText(screen, self.textCol, font, self.rect.centerx, self.rect.centery, self.text, justify="center",
                 centeredVertically=True)

    def handleEvent(self, event):
        if not self.visible: return False
        if event.type == pygame.MOUSEMOTION:
            self.hover = self.rect.collidepoint(event.pos)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.hover:
            self.callback()
            return True
        return False


class Slider:
    def __init__(self, x, y, w, h, min_val, max_val, initial, callback=None):
        self.rect = pygame.Rect(x, y, w, h)
        self.min_val = min_val
        self.max_val = max_val
        self.val = initial
        self.callback = callback
        self.hover = False
        self.dragging = False

    def get_pct(self):
        return (self.val - self.min_val) / (self.max_val - self.min_val)

    def draw(self, screen):
        # Background
        pygame.draw.rect(screen, Theme.slider_bg, self.rect, 0, 4)

        # Fill
        fill_w = self.rect.width * self.get_pct()
        fill_rect = pygame.Rect(self.rect.x, self.rect.y, fill_w, self.rect.height)
        pygame.draw.rect(screen, Theme.slider_fill, fill_rect, 0, 4)

        # Handle/Knob
        knob_x = self.rect.x + fill_w
        pygame.draw.circle(screen, Theme.text, (int(knob_x), self.rect.centery), self.rect.height // 2 + 2)

    def handleEvent(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.hover = self.rect.collidepoint(event.pos)
            if self.dragging:
                rel_x = max(0, min(event.pos[0] - self.rect.x, self.rect.width))
                pct = rel_x / self.rect.width
                self.val = self.min_val + pct * (self.max_val - self.min_val)
                if self.callback: self.callback(self.val)
                return True

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.hover:
                self.dragging = True
                rel_x = max(0, min(event.pos[0] - self.rect.x, self.rect.width))
                pct = rel_x / self.rect.width
                self.val = self.min_val + pct * (self.max_val - self.min_val)
                if self.callback: self.callback(self.val)
                return True

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.dragging = False

        return False


class FileEntry:
    def __init__(self, name, surface, isNew=False, isMod=False):
        self.name = name
        self.surface = surface.copy() if surface else None
        self.isNew = isNew
        self.isModified = isMod
        self.originalSurface = surface.copy() if surface and not isNew else None
        self.originalName = name


class Editor:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)

        global WINDOW_SIZE
        WINDOW_SIZE = self.screen.get_size()

        pygame.display.set_caption("Crimson Waters - Pixel Hex Editor")
        self.clock = pygame.time.Clock()

        # --- ASSETS ---
        self.tilesDir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

        # Fonts
        fontPathReg = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../fonts/Montserrat-Regular.ttf"))
        fontPathBold = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../fonts/Montserrat-Bold.ttf"))

        if os.path.exists(fontPathBold):
            self.fontBold = pygame.font.Font(fontPathBold, 18)
            self.fontSmall = pygame.font.Font(fontPathBold, 13)
            self.fontUI = pygame.font.Font(fontPathBold, 14)
        else:
            self.fontBold = pygame.font.SysFont("arial", 18, bold=True)
            self.fontSmall = pygame.font.SysFont("arial", 13, bold=True)
            self.fontUI = pygame.font.SysFont("arial", 14, bold=True)

        # --- STATE ---
        self.activeEntry = None
        self.files = []
        self.neighborMap = {}
        self.neighborCache = {}  # Caches the edge pixels: {filename: [(x,y), ...]}
        self.typingMode = False
        self.renameTarget = None
        self.userString = ""
        self.isPainting = False

        # Overlay State
        self.overlayMode = False
        self.overlaySurf = None  # Surface for the currently selected overlay image
        self.overlayOffset = [0, 0]  # Offset for the overlay
        self.overlayOpacity = 0.3
        self.overlayOriginal = None  # Original surface of the selected overlay image

        # Toast Notification
        self.toastMsg = ""
        self.toastTimer = 0

        # --- TOOLS ---
        self.tool = TOOL_BRUSH
        self.gapMode = False
        self.gridVisible = True
        self.showDepth = True

        # --- UNDO/REDO ---
        self.history = []
        self.redoStack = []
        self.undoDelay = 0.4
        self.undoRepeat = 0.08
        self.undo_timer = 0
        self.redo_timer = 0
        self.lineStart = None

        # --- CANVAS ---
        self.maskSurf = createHexMaskSurface(CANVAS_WIDTH, CANVAS_HEIGHT)
        self.outlinePixels = self.generatePixelOutline()

        self.pixels = []
        self.selectedColor = (*Endesga.white, 255)
        self.brushSize = 1

        # --- VIEW ---
        self.camZoom = 25.0
        self.camPos = [0, 0]

        self.refreshFileList()
        self.initUI()

        if self.files:
            self.switchFile(self.files[0])
        else:
            self.createNewFile()

    def generatePixelOutline(self):
        """
        Iterates through the mask and finds pixels that are on the edge.
        Returns a list of (x,y) coordinates.
        """
        pixels = []
        w, h = CANVAS_WIDTH, CANVAS_HEIGHT

        # We assume 0,0 is top left.
        for y in range(h):
            for x in range(w):
                if isPointInMask(x, y, self.maskSurf):
                    # Check 4 neighbors
                    is_border = False
                    for nx, ny in [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]:
                        # If neighbor is out of bounds OR not in mask, this is a border pixel
                        if nx < 0 or ny < 0 or nx >= w or ny >= h:
                            is_border = True
                        elif not isPointInMask(nx, ny, self.maskSurf):
                            is_border = True

                    if is_border:
                        pixels.append((x, y))
        return pixels

    def initUI(self):
        self.buttons = []
        self.sliders = []

        # --- LAYOUT CONSTANTS ---
        RIGHT_PANEL_W = 180
        BTN_W = 150
        BTN_H = 35
        BTN_GAP = 10
        SIDE_MARGIN = (RIGHT_PANEL_W - BTN_W) // 2

        anchorX = WINDOW_SIZE[0] - RIGHT_PANEL_W + SIDE_MARGIN
        currentY = 100  # Start below file list title area

        # --- SAVE BUTTON (Explicit) ---
        self.btnSave = Button(anchorX, currentY, BTN_W, BTN_H, "SAVE (Esc)", self.saveAll, col=Theme.btn_idle)
        self.buttons.append(self.btnSave)
        currentY += BTN_H + BTN_GAP * 2  # Extra spacer

        # --- TOOLS ---
        self.btnBrush = Button(anchorX, currentY, BTN_W, BTN_H, "BRUSH (B)", lambda: self.setTool(TOOL_BRUSH),
                               toggle=True)
        self.buttons.append(self.btnBrush)
        currentY += BTN_H + BTN_GAP

        self.btnFill = Button(anchorX, currentY, BTN_W, BTN_H, "FILL (F)", lambda: self.setTool(TOOL_FILL), toggle=True)
        self.buttons.append(self.btnFill)
        currentY += BTN_H + BTN_GAP

        self.btnLine = Button(anchorX, currentY, BTN_W, BTN_H, "LINE (L)", lambda: self.setTool(TOOL_LINE), toggle=True)
        self.buttons.append(self.btnLine)
        currentY += BTN_H + BTN_GAP * 2  # Extra spacer

        # --- VIEW SETTINGS ---
        self.btnGap = Button(anchorX, currentY, BTN_W, BTN_H, "GAP (G)", self.toggleGap, toggle=True)
        self.buttons.append(self.btnGap)
        currentY += BTN_H + BTN_GAP

        self.btnGrid = Button(anchorX, currentY, BTN_W, BTN_H, "GRID (H)", self.toggleGrid, toggle=True)
        self.btnGrid.active = True
        self.buttons.append(self.btnGrid)
        currentY += BTN_H + BTN_GAP

        self.btnDepth = Button(anchorX, currentY, BTN_W, BTN_H, "DEPTH (X)", self.toggleDepth, toggle=True)
        self.btnDepth.active = True
        self.buttons.append(self.btnDepth)
        currentY += BTN_H + BTN_GAP * 2

        # --- OVERLAY ---
        self.btnOverlay = Button(anchorX, currentY, BTN_W, BTN_H, "OVERLAY", self.toggleOverlayMode, toggle=True)
        self.buttons.append(self.btnOverlay)
        currentY += BTN_H + 5

        # Slider for Opacity
        self.sldOpacity = Slider(anchorX, currentY, BTN_W, 10, 0.0, 1.0, self.overlayOpacity, self.setOverlayOpacity)
        self.sliders.append(self.sldOpacity)
        currentY += 15 + BTN_GAP  # Add space for slider

        # --- NEW FILE BUTTON (Top Left) ---
        self.btnNew = Button(10, 50, 200, 30, "+ NEW TILE", self.createNewFile, col=Theme.accent)
        self.buttons.append(self.btnNew)

        self.setTool(TOOL_BRUSH)

    def setTool(self, t):
        self.tool = t
        self.btnBrush.active = (t == TOOL_BRUSH)
        self.btnFill.active = (t == TOOL_FILL)
        self.btnLine.active = (t == TOOL_LINE)
        self.lineStart = None

    def toggleGap(self):
        self.gapMode = not self.gapMode
        self.btnGap.active = self.gapMode

    def toggleGrid(self):
        self.gridVisible = not self.gridVisible
        self.btnGrid.active = self.gridVisible

    def toggleDepth(self):
        self.showDepth = not self.showDepth
        self.btnDepth.active = self.showDepth

    # --- OVERLAY LOGIC ---
    def toggleOverlayMode(self):
        self.overlayMode = not self.overlayMode
        self.btnOverlay.active = self.overlayMode
        if not self.overlayMode:
            self.overlaySurf = None  # Clear overlay surface when turned off
            self.overlayOriginal = None
            self.overlayOffset = [0, 0]  # Reset offset
            self.toastMsg = "Overlay OFF"
            self.toastTimer = 1.0
        else:
            self.toastMsg = "Select file to Overlay"
            self.toastTimer = 2.0

    def setOverlayOpacity(self, val):
        self.overlayOpacity = val

    def setOverlay(self, entry):
        if not entry.surface: return

        # 1. Scale DOWN immediately to canvas size.
        # This prevents performance lag with large images.
        surf = pygame.transform.scale(entry.surface, (CANVAS_WIDTH, CANVAS_HEIGHT))
        w, h = surf.get_size()

        # 2. Determine Colorkey (Winner of 4 corners) on the scaled surface
        corners = [
            surf.get_at((0, 0)),
            surf.get_at((w - 1, 0)),
            surf.get_at((0, h - 1)),
            surf.get_at((w - 1, h - 1))
        ]
        valid_corners = [c for c in corners if c.a > 0]
        if not valid_corners: valid_corners = [(0, 0, 0, 0)]

        c_tuples = [tuple(c) for c in valid_corners]
        most_common = Counter(c_tuples).most_common(1)[0][0]

        # 3. Apply Colorkey and set as overlay
        surf.set_colorkey(most_common)

        self.overlayOriginal = surf  # This is now small (e.g. 32x48)
        self.overlaySurf = surf
        self.overlayOffset = [0, 0]  # Reset offset when new overlay is selected
        self.toastMsg = f"Overlay: {entry.name}"
        self.toastTimer = 2.0

    # --- FILE MANAGEMENT ---
    def refreshFileList(self):
        existing = [f.name for f in self.files]
        if os.path.exists(self.tilesDir):
            for f in sorted(os.listdir(self.tilesDir)):
                if f.lower().endswith(".png") and f not in existing:
                    try:
                        path = os.path.join(self.tilesDir, f)
                        surf = pygame.image.load(path).convert_alpha()
                        self.files.append(FileEntry(f, surf))
                    except:
                        pass

    def createNewFile(self):
        cnt = 1
        while True:
            name = f"tile_{cnt}.png"
            if not any(f.name == name for f in self.files): break
            cnt += 1
        surf = pygame.Surface((CANVAS_WIDTH, CANVAS_HEIGHT), pygame.SRCALPHA)
        newEntry = FileEntry(name, surf, isNew=True)
        self.files.insert(0, newEntry)
        self.switchFile(newEntry)

    def switchFile(self, entry):
        if self.activeEntry: self.commitCanvasToEntry()
        self.activeEntry = entry
        self.initCanvas(entry.surface)
        self.neighborMap = {}
        self.neighborCache = {}  # Clear cache
        self.history = []
        self.redoStack = []
        # Reset overlay state when switching files
        self.overlayMode = False
        self.btnOverlay.active = False
        self.overlaySurf = None
        self.overlayOriginal = None
        self.overlayOffset = [0, 0]

    def revertFile(self, entry):
        if entry.name != entry.originalName:
            entry.name = entry.originalName
        if entry.isNew:
            if entry in self.files:
                self.files.remove(entry)
                if self.activeEntry == entry:
                    self.activeEntry = None
                    if self.files:
                        self.switchFile(self.files[0])
                    else:
                        self.createNewFile()
        else:
            entry.surface = entry.originalSurface.copy()
            entry.isModified = False
            if self.activeEntry == entry: self.initCanvas(entry.surface)

    def saveAll(self):
        if self.activeEntry: self.commitCanvasToEntry()
        count = 0
        for f in self.files:
            if f.isModified or f.isNew or f.name != f.originalName:
                oldPath = os.path.join(self.tilesDir, f.originalName)
                newPath = os.path.join(self.tilesDir, f.name)
                if f.name != f.originalName and not f.isNew and os.path.exists(oldPath):
                    os.remove(oldPath)
                try:
                    pygame.image.save(f.surface, newPath)
                    f.isModified = False
                    f.isNew = False
                    f.originalName = f.name
                    count += 1
                except Exception as e:
                    print(f"Error saving {f.name}: {e}")

        print(f"Saved {count} files.")
        self.toastMsg = f"Saved {count} files!"
        self.toastTimer = 2.0

    # --- CANVAS ---
    def initCanvas(self, surface):
        self.pixels = []
        w, h = surface.get_width(), surface.get_height()
        for y in range(CANVAS_HEIGHT):
            for x in range(CANVAS_WIDTH):
                col = (0, 0, 0, 0)
                if x < w and y < h:
                    raw_col = surface.get_at((x, y))
                    if isinstance(raw_col, pygame.Color):
                        col = (raw_col.r, raw_col.g, raw_col.b, raw_col.a)
                    elif len(raw_col) == 3:
                        col = (*raw_col, 255)
                    else:
                        col = tuple(raw_col)
                self.pixels.append(Pixel(x, y, col))

    def commitCanvasToEntry(self):
        if not self.activeEntry: return
        surf = pygame.Surface((CANVAS_WIDTH, CANVAS_HEIGHT), pygame.SRCALPHA)
        for p in self.pixels: surf.set_at((p.gridX, p.gridY), p.c)
        self.activeEntry.surface = surf

    # --- UNDO / REDO ---
    def pushHistory(self):
        state = [p.c for p in self.pixels]
        self.history.append(state)
        self.redoStack.clear()
        if len(self.history) > 200: self.history.pop(0)

    def performUndo(self):
        if not self.history: return
        self.redoStack.append([p.c for p in self.pixels])
        prev = self.history.pop()
        for i, col in enumerate(prev): self.pixels[i].c = col
        if self.activeEntry: self.activeEntry.isModified = True

    def performRedo(self):
        if not self.redoStack: return
        self.history.append([p.c for p in self.pixels])
        next_state = self.redoStack.pop()
        for i, col in enumerate(next_state): self.pixels[i].c = col
        if self.activeEntry: self.activeEntry.isModified = True

    # --- ALGORITHMS ---
    def getPixel(self, x, y):
        idx = y * CANVAS_WIDTH + x
        if 0 <= idx < len(self.pixels): return self.pixels[idx]
        return None

    def getHexOutlinePoints(self, surf):
        """
        Generates a list of line segments (start_point, end_point) for the outer edges
        of the visible pixels in the surface, forming a continuous outline.
        """
        lines = []
        w, h = surf.get_size()
        pixels_in_mask = set()  # Store (x,y) of pixels that are part of the shape

        # First, identify all pixels that are part of the shape
        for y in range(h):
            for x in range(w):
                if surf.get_at((x, y))[3] > 0:  # Check if pixel is not fully transparent
                    pixels_in_mask.add((x, y))

        # Then, find edge pixels and generate line segments
        for x, y in pixels_in_mask:
            # Check neighbors
            for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                nx, ny = x + dx, y + dy
                # If a neighbor is out of bounds or not part of the shape, this pixel has an edge here
                if (nx, ny) not in pixels_in_mask:
                    mid_x, mid_y, edge_dx, edge_dy = 0, 0, 0, 0
                    if dx == 1:  # right edge
                        mid_x = x + 1
                        mid_y = y + 0.5
                        edge_dx, edge_dy = 0, 1
                    elif dx == -1:  # left edge
                        mid_x = x
                        mid_y = y + 0.5
                        edge_dx, edge_dy = 0, 1
                    elif dy == 1:  # bottom edge
                        mid_x = x + 0.5
                        mid_y = y + 1
                        edge_dx, edge_dy = 1, 0
                    elif dy == -1:  # top edge
                        mid_x = x + 0.5
                        mid_y = y
                        edge_dx, edge_dy = 1, 0

                    half = 0.5
                    p1 = (mid_x - edge_dx * half, mid_y - edge_dy * half)
                    p2 = (mid_x + edge_dx * half, mid_y + edge_dy * half)
                    lines.append((p1, p2))

        return lines

    def performFill(self, startX, startY, targetCol):
        startP = self.getPixel(startX, startY)
        if not startP: return
        startCol = startP.c
        if startCol == targetCol: return

        queue = [(startX, startY)]
        visited = set()
        if not isPointInMask(startX, startY, self.maskSurf): return
        self.pushHistory()
        while queue:
            cx, cy = queue.pop(0)
            if (cx, cy) in visited: continue
            visited.add((cx, cy))
            p = self.getPixel(cx, cy)
            if p.c == startCol:
                p.c = targetCol
                for nx, ny in [(cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)]:
                    if 0 <= nx < CANVAS_WIDTH and 0 <= ny < CANVAS_HEIGHT:
                        if isPointInMask(nx, ny, self.maskSurf):
                            queue.append((nx, ny))
        if self.activeEntry: self.activeEntry.isModified = True

    def getLinePixels(self, x0, y0, x1, y1):
        points = []
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        while True:
            points.append((x0, y0))
            if x0 == x1 and y0 == y1: break
            e2 = 2 * err
            if e2 > -dy: err -= dy; x0 += sx
            if e2 < dx: err += dx; y0 += sy
        return points

    # --- MAIN LOOP ---
    def run(self):
        while True:
            dt = self.clock.tick(FPS) / 1000.0
            self.handleInput()
            self.update(dt)
            self.draw()

    def update(self, dt):
        # Toast Timer
        if self.toastTimer > 0:
            self.toastTimer -= dt

        if self.typingMode: return
        keys = pygame.key.get_pressed()
        moveSpeed = CAMERA_SPEED
        if keys[pygame.K_LSHIFT]: moveSpeed *= 3
        dx = (keys[pygame.K_d] - keys[pygame.K_a]) * moveSpeed
        dy = (keys[pygame.K_s] - keys[pygame.K_w]) * moveSpeed
        self.camPos[0] -= dx
        self.camPos[1] -= dy

        # Overlay Offset
        if self.overlayMode and self.overlaySurf:
            if keys[pygame.K_LEFT]: self.overlayOffset[0] -= 100 * dt
            if keys[pygame.K_RIGHT]: self.overlayOffset[0] += 100 * dt
            if keys[pygame.K_UP]: self.overlayOffset[1] -= 100 * dt
            if keys[pygame.K_DOWN]: self.overlayOffset[1] += 100 * dt

        # Undo/Redo Repeat
        if keys[pygame.K_z]:
            self.undo_timer += dt
            if self.undo_timer >= self.undoDelay:
                self.performUndo()
                self.undo_timer -= self.undoRepeat
        else:
            self.undo_timer = 0

        if keys[pygame.K_y]:
            self.redo_timer += dt
            if self.redo_timer >= self.undoDelay:
                self.performRedo()
                self.redo_timer -= self.undoRepeat
        else:
            self.redo_timer = 0

    def handleToolClick(self, mx, my):
        zoom = self.camZoom
        cx, cy = WINDOW_SIZE[0] // 2, WINDOW_SIZE[1] // 2
        offX = cx + self.camPos[0] - (CANVAS_WIDTH * zoom / 2)
        offY = cy + self.camPos[1] - (CANVAS_HEIGHT * zoom / 2)

        gx = int((mx - offX) / zoom)
        gy = int((my - offY) / zoom)

        p = self.getPixel(gx, gy)
        if p and isPointInMask(gx, gy, self.maskSurf):
            if self.tool == TOOL_FILL:
                self.performFill(gx, gy, self.selectedColor)
            elif self.tool == TOOL_LINE:
                if self.lineStart is None:
                    self.lineStart = (gx, gy)
                else:
                    self.pushHistory()
                    pts = self.getLinePixels(self.lineStart[0], self.lineStart[1], gx, gy)
                    for lx, ly in pts:
                        lp = self.getPixel(lx, ly)
                        if lp and isPointInMask(lx, ly, self.maskSurf): lp.c = self.selectedColor
                    if self.activeEntry: self.activeEntry.isModified = True
                    self.lineStart = None

    def handleInput(self):
        events = pygame.event.get()
        for event in events:
            if event.type == pygame.QUIT:
                self.saveAll()
                pygame.quit()
                sys.exit()

            if self.typingMode:
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_RETURN:
                        if self.renameTarget and self.userString:
                            newName = self.userString + ".png"
                            if newName == self.renameTarget.name or not any(f.name == newName for f in self.files):
                                self.renameTarget.name = newName
                                self.renameTarget.isModified = True
                        self.typingMode = False
                    elif event.key == pygame.K_ESCAPE:
                        self.typingMode = False
                    elif event.key == pygame.K_BACKSPACE:
                        self.userString = self.userString[:-1]
                    else:
                        if event.unicode.isprintable(): self.userString += event.unicode
                continue

            if event.type == pygame.MOUSEWHEEL:
                self.camZoom = max(2, min(60, self.camZoom + event.y))

            if event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos

                # Check UI collisions (Buttons)
                clickedUI = False
                for b in self.buttons:
                    if b.rect.collidepoint((mx, my)): clickedUI = True
                for s in self.sliders:
                    if s.rect.collidepoint((mx, my)): clickedUI = True

                # Check Palette Area
                sw = 30
                cols = 6
                startX = 10
                startY = WINDOW_SIZE[1] - 200
                if mx < (startX + cols * 35 + 20) and my > (startY - 10):
                    clickedUI = True

                # Check File List Panel
                if mx < 220 and my < (WINDOW_SIZE[1] - 200):
                    clickedUI = True

                if event.button == 1 and not clickedUI:
                    if self.tool == TOOL_BRUSH:
                        if not self.isPainting:
                            self.pushHistory()
                            self.isPainting = True
                    else:
                        self.handleToolClick(mx, my)

                if event.button == 3 and self.tool == TOOL_LINE: self.lineStart = None

            if event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1:
                    self.isPainting = False

            if event.type == pygame.KEYDOWN:

                # ESC -> Save + Exit
                if event.key == pygame.K_ESCAPE:
                    self.saveAll()
                    pygame.quit()
                    sys.exit()

                # CMD + S (Mac)  OR  CTRL + S (Windows/Linux)
                if event.key == pygame.K_s and (event.mod & pygame.KMOD_META or event.mod & pygame.KMOD_CTRL):
                    self.saveAll()

                if event.key == pygame.K_z:
                    self.performUndo()
                    self.undo_timer = 0
                if event.key == pygame.K_y:
                    self.performRedo()
                    self.redo_timer = 0
                if event.key == pygame.K_q: self.camZoom = max(2, self.camZoom - 2)
                if event.key == pygame.K_e: self.camZoom = min(60, self.camZoom + 2)
                if event.key == pygame.K_b: self.setTool(TOOL_BRUSH)
                if event.key == pygame.K_f: self.setTool(TOOL_FILL)
                if event.key == pygame.K_l: self.setTool(TOOL_LINE)
                if event.key == pygame.K_g: self.toggleGap()
                if event.key == pygame.K_h: self.toggleGrid()
                if event.key == pygame.K_x: self.toggleDepth()
                if pygame.K_1 <= event.key <= pygame.K_9: self.brushSize = event.key - pygame.K_0

            for b in self.buttons:
                if b.handleEvent(event): break
            for s in self.sliders:
                if s.handleEvent(event): break

    def draw(self):
        self.screen.fill(Theme.bg)
        self.drawBackgroundCheckerboard()  # Draw checkerboard first
        self.drawPainter()
        self.drawUI()
        self.drawToast()

        mx, my = pygame.mouse.get_pos()
        if mx > 220 and mx < (WINDOW_SIZE[0] - 180):  # Between panels
            pygame.mouse.set_visible(False)
            pygame.draw.circle(self.screen, Theme.accent, (mx, my), 3)
            pygame.draw.circle(self.screen, Theme.text, (mx, my), 2)
        else:
            pygame.mouse.set_visible(True)

        pygame.display.flip()

    def drawBackgroundCheckerboard(self):
        checker_size = 32  # Size of each checker square in pixels
        for y in range(0, WINDOW_SIZE[1], checker_size):
            for x in range(0, WINDOW_SIZE[0], checker_size):
                # Alternate colors based on grid position
                if (x // checker_size + y // checker_size) % 2 == 0:
                    color = Theme.bg
                else:
                    color = Theme.checkerboard_dark
                pygame.draw.rect(self.screen, color, (x, y, checker_size, checker_size))

    def drawToast(self):
        if self.toastTimer > 0:
            w, h = 200, 40
            x = WINDOW_SIZE[0] // 2 - w // 2
            y = 30
            r = pygame.Rect(x, y, w, h)
            pygame.draw.rect(self.screen, Theme.toast_bg, r, 0, 8)
            pygame.draw.rect(self.screen, Theme.text, r, 2, 8)
            drawText(self.screen, Theme.text, self.fontBold, r.centerx, r.centery, self.toastMsg, justify="center",
                     centeredVertically=True)

    def drawPainter(self):
        cx, cy = WINDOW_SIZE[0] // 2, WINDOW_SIZE[1] // 2
        zoom = self.camZoom

        # 1. PREPARE SURFACES & ENTITIES
        activeSurf = pygame.Surface((CANVAS_WIDTH, CANVAS_HEIGHT), pygame.SRCALPHA)
        for p in self.pixels: activeSurf.set_at((p.gridX, p.gridY), p.c)
        scaledActive = pygame.transform.scale(activeSurf, (int(CANVAS_WIDTH * zoom), int(CANVAS_HEIGHT * zoom)))

        sx, sy = (22, 0) if self.gapMode else (20, 0)
        dx, dy = (12, 16) if self.gapMode else (11, 15)

        neighbors_def = [(sx, sy), (-sx, -sy), (dx, dy), (-dx, dy), (dx, -dy), (-dx, -dy)]

        entities = []
        # Center
        entities.append({'gy': 0, 'gx': 0, 'surf': activeSurf, 'scaled': scaledActive, 'isCenter': True})

        # Neighbors
        for idx, (nx, ny) in enumerate(neighbors_def):
            if not self.showDepth and ny > 0: continue

            nSurf = activeSurf
            if idx in self.neighborMap:
                nSurf = self.neighborMap[idx]

            entities.append({'gy': ny, 'gx': nx, 'surf': nSurf, 'isCenter': False, 'id': idx})

        # SORT BY Y (Painter's Algorithm)
        entities.sort(key=lambda e: (e['gy'], e['gx']))

        # 2. DRAW LOOP
        for e in entities:
            px = e['gx'] * zoom
            py = e['gy'] * zoom
            destX = cx + self.camPos[0] + px - (scaledActive.get_width() / 2)
            destY = cy + self.camPos[1] + py - (scaledActive.get_height() / 2)

            if e['isCenter']:
                # --- DRAW OVERLAY IF ACTIVE ---
                if self.overlayMode and self.overlaySurf:
                    # Scale overlay, apply offset, and then draw with opacity
                    o_w = int(self.overlayOriginal.get_width() * zoom)
                    o_h = int(self.overlayOriginal.get_height() * zoom)
                    o_scaled = pygame.transform.scale(self.overlayOriginal, (o_w, o_h))

                    # Calculate final position including offset and camera
                    overlay_draw_x = destX + self.overlayOffset[0]
                    overlay_draw_y = destY + self.overlayOffset[1]

                    o_scaled.set_alpha(int(255 * self.overlayOpacity))
                    self.screen.blit(o_scaled, (overlay_draw_x, overlay_draw_y))

                # Draw Center Full Surface
                self.screen.blit(e['scaled'], (destX, destY))

                # Draw Main Pixel Outline (Yellow/Gold)
                if self.outlinePixels:
                    for (ox, oy) in self.outlinePixels:
                        scrX = destX + ox * zoom
                        scrY = destY + oy * zoom
                        pygame.draw.rect(self.screen, Theme.outline, (scrX, scrY, math.ceil(zoom), math.ceil(zoom)))

            else:
                # 1. Draw Neighbor Content (Restored)
                # We need to scale the raw surface to current zoom
                neighbor_scaled = pygame.transform.scale(e['surf'],
                                                         (int(CANVAS_WIDTH * zoom), int(CANVAS_HEIGHT * zoom)))
                # Fade it slightly so it doesn't look exactly like the active tile
                neighbor_scaled.set_alpha(250)
                self.screen.blit(neighbor_scaled, (destX, destY))

                # 2. Draw Neighbor Hex Outlines
                edge_lines = []
                use_cache = (e['surf'] != activeSurf)

                if use_cache and e['id'] in self.neighborCache:
                    edge_lines = self.neighborCache[e['id']]
                else:
                    # Generate outline points for this neighbor surface
                    edge_lines = self.getHexOutlinePoints(e['surf'])
                    if use_cache: self.neighborCache[e['id']] = edge_lines

                # Draw the generated lines for the neighbor
                for line in edge_lines:
                    (p1x, p1y), (p2x, p2y) = line
                    screen_p1 = (destX + p1x * zoom, destY + p1y * zoom)
                    screen_p2 = (destX + p2x * zoom, destY + p2y * zoom)
                    pygame.draw.line(self.screen, Theme.neighbor_outline, screen_p1, screen_p2, 2)

            # Draw Center UI (Grid, Highlights) - Only for the center tile
            if e['isCenter']:
                mx, my = pygame.mouse.get_pos()
                clickL = pygame.mouse.get_pressed()[0]
                clickR = pygame.mouse.get_pressed()[2]

                offX = cx + self.camPos[0] - (CANVAS_WIDTH * zoom / 2)
                offY = cy + self.camPos[1] - (CANVAS_HEIGHT * zoom / 2)

                hoveredPixel = None

                # determine hovered pixel by mapping mouse -> grid (independent of grid visibility)
                hoveredPixel = None
                if mx > 220 and mx < (WINDOW_SIZE[0] - 180):
                    gx = int((mx - offX) / zoom)
                    gy = int((my - offY) / zoom)
                    if 0 <= gx < CANVAS_WIDTH and 0 <= gy < CANVAS_HEIGHT and isPointInMask(gx, gy, self.maskSurf):
                        hoveredPixel = self.getPixel(gx, gy)

                # draw grid squares only when requested
                if self.gridVisible and zoom > 4:
                    for p in self.pixels:
                        if isPointInMask(p.gridX, p.gridY, self.maskSurf):
                            rx = offX + p.gridX * zoom
                            ry = offY + p.gridY * zoom
                            pygame.draw.rect(self.screen, (20, 20, 25), (rx, ry, math.ceil(zoom), math.ceil(zoom)), 1)

                # Brush/Tool Highlighting & Action
                if hoveredPixel:
                    targetPixels = []
                    if self.tool == TOOL_BRUSH:
                        if self.brushSize == 1:
                            targetPixels.append(hoveredPixel)
                        else:
                            rad = self.brushSize - 0.5
                            for p in self.pixels:
                                if not isPointInMask(p.gridX, p.gridY, self.maskSurf): continue
                                dist = math.sqrt(
                                    (p.gridX - hoveredPixel.gridX) ** 2 + (p.gridY - hoveredPixel.gridY) ** 2)
                                if dist <= rad: targetPixels.append(p)
                    elif self.tool == TOOL_LINE:
                        if self.lineStart:
                            pts = self.getLinePixels(self.lineStart[0], self.lineStart[1], hoveredPixel.gridX,
                                                     hoveredPixel.gridY)
                            for lx, ly in pts:
                                lp = self.getPixel(lx, ly)
                                if lp and isPointInMask(lx, ly, self.maskSurf): targetPixels.append(lp)
                        else:
                            targetPixels.append(hoveredPixel)
                    elif self.tool == TOOL_FILL:
                        targetPixels.append(hoveredPixel)

                    # Highlight and perform action
                    for tp in targetPixels:
                        rx = offX + tp.gridX * zoom
                        ry = offY + tp.gridY * zoom
                        pygame.draw.rect(self.screen, Theme.text, (rx, ry, math.ceil(zoom), math.ceil(zoom)), 1)

                        if clickL and self.tool == TOOL_BRUSH:
                            tp.c = self.selectedColor
                            if self.activeEntry: self.activeEntry.isModified = True
                        if clickR and self.tool == TOOL_BRUSH:
                            tp.c = (0, 0, 0, 0)
                            if self.activeEntry: self.activeEntry.isModified = True

        # Line Preview
        if self.tool == TOOL_LINE and self.lineStart:
            sp = self.getPixel(self.lineStart[0], self.lineStart[1])
            if sp:
                offX = cx + self.camPos[0] - (CANVAS_WIDTH * zoom / 2)
                offY = cy + self.camPos[1] - (CANVAS_HEIGHT * zoom / 2)
                rx = offX + sp.gridX * zoom
                ry = offY + sp.gridY * zoom
                pygame.draw.rect(self.screen, Theme.btn_active, (rx, ry, zoom, zoom), 2)

    def drawHotkeys(self):
        items = [
            "Q/E: Zoom | WASD: Pan",
            "Z: Undo | Y: Redo",
            "B: Brush | F: Fill | L: Line",
            "G: Gap | H: Grid | X: Depth",
            "1-9: Brush Size",
            "L-Click: Paint | R-Click: Erase",
            "Overlay: Select File",
            "+/- Alpha, Arrows: Offset"
        ]

        bgW = 260
        bgH = len(items) * 20 + 20
        x = WINDOW_SIZE[0] - 190 - bgW  # Position to left of sidebar
        y = WINDOW_SIZE[1] - bgH - 10

        pygame.draw.rect(self.screen, Theme.panel, (x, y, bgW, bgH), 0, 10)
        pygame.draw.rect(self.screen, Theme.border, (x, y, bgW, bgH), 2, 10)

        for i, text in enumerate(items):
            drawText(self.screen, Theme.text_dim, self.fontSmall, x + 10, y + 10 + (i * 20), text)

    def drawInfo(self):
        infoText = [
            f"Size: {self.brushSize}",
            f"Zoom: {int(self.camZoom)}",
        ]

        bgW = 100
        bgH = len(infoText) * 20 + 20
        x = WINDOW_SIZE[0] - 180 - bgW - 10
        y = 10

        pygame.draw.rect(self.screen, Theme.panel, (x, y, bgW, bgH), 0, 10)
        pygame.draw.rect(self.screen, Theme.border, (x, y, bgW, bgH), 2, 10)

        for i, text in enumerate(infoText):
            drawText(self.screen, Theme.text, self.fontUI, x + 10, y + 10 + (i * 20), text)

    def drawUI(self):
        mx, my = pygame.mouse.get_pos()
        click = pygame.mouse.get_pressed()[0]

        # --- LEFT PANEL (Files) ---
        w = 220
        pygame.draw.rect(self.screen, Theme.panel, (0, 0, w, WINDOW_SIZE[1]))
        pygame.draw.line(self.screen, Theme.border, (w, 0), (w, WINDOW_SIZE[1]), 2)

        # --- RIGHT PANEL (Tools) ---
        rw = 180
        rx = WINDOW_SIZE[0] - rw
        pygame.draw.rect(self.screen, Theme.panel, (rx, 0, rw, WINDOW_SIZE[1]))
        pygame.draw.line(self.screen, Theme.border, (rx, 0), (rx, WINDOW_SIZE[1]), 2)

        # Label for Tools
        drawText(self.screen, Theme.text_dim, self.fontBold, rx + rw // 2, 70, "TOOLS", justify="center")

        # --- PALETTE (Bottom Left) ---
        sw = 30
        cols = 6
        startX = 10
        startY = WINDOW_SIZE[1] - 200

        # --- PALETTE (Bottom Left) ---
        sw = 30
        cols = 6
        spacing = 35
        startX = 10
        startY = WINDOW_SIZE[1] - 200

        # Only show up to N colors (keep your original cap if desired)
        max_colors = 24
        num_colors = min(len(PALETTE), max_colors)

        # compute rows required
        rows = math.ceil(num_colors / cols)

        # Palette Background sized to actual rows
        pRect = pygame.Rect(startX - 5, startY - 5, cols * spacing + 5, rows * spacing + 5)
        pygame.draw.rect(self.screen, Theme.bg, pRect, 0, 5)

        for i in range(num_colors):
            c = PALETTE[i]
            rgba = c if len(c) == 4 else (*c, 255)
            r = pygame.Rect(startX + (i % cols) * spacing, startY + (i // cols) * spacing, sw, sw)

            if self.selectedColor == rgba:
                pygame.draw.rect(self.screen, Theme.text, r.inflate(4, 4), 2)

            pygame.draw.rect(self.screen, c, r)
            pygame.draw.rect(self.screen, Theme.bg, r, 1)

            if click and r.collidepoint((mx, my)):
                self.selectedColor = rgba

        # --- FILE LIST ---
        y = 100
        activeList = [f for f in self.files if f.isModified or f.isNew]
        libraryList = [f for f in self.files if not (f.isModified or f.isNew)]

        if activeList:
            drawText(self.screen, Theme.accent, self.fontBold, w // 2, y, "WORKSPACE", justify="center")
            y += 25
            for f in activeList[:]:
                if self.drawFileRow(f, y, w, mx, my, click): return
                y += 25
            y += 15

        drawText(self.screen, Theme.text_dim, self.fontBold, w // 2, y, "LIBRARY", justify="center")
        y += 25
        for f in libraryList[:]:
            if self.drawFileRow(f, y, w, mx, my, click): return
            y += 25

        # Draw Buttons and Sliders
        for b in self.buttons: b.draw(self.screen, self.fontBold)
        for s in self.sliders: s.draw(self.screen)

        # Typing Overlay
        if self.typingMode:
            pygame.draw.rect(self.screen, Theme.bg, (w // 2 - 100, 300, 200, 40))
            pygame.draw.rect(self.screen, Theme.accent, (w // 2 - 100, 300, 200, 40), 2)
            drawText(self.screen, Theme.text, self.fontBold, w // 2, 320, self.userString + "|", justify="center",
                     centeredVertically=True)

        self.drawHotkeys()
        self.drawInfo()

    def drawFileRow(self, f, y, w, mx, my, click):
        r = pygame.Rect(5, y, w - 10, 22)
        isHover = r.collidepoint((mx, my))

        if f == self.activeEntry:
            pygame.draw.rect(self.screen, Theme.bg, r, 0, 5)
        elif isHover:
            pygame.draw.rect(self.screen, Theme.btn_hover, r, 0, 5)

            if click and mx < w:
                if self.overlayMode:
                    self.setOverlay(f)
                else:
                    self.switchFile(f)

            # Enable renaming with right-click only if not in overlay mode
            if isHover and pygame.mouse.get_pressed()[2] and not self.typingMode and not self.overlayMode:
                self.typingMode = True
                self.renameTarget = f
                self.userString = f.name.replace(".png", "")

        col = Theme.text if f == self.activeEntry else Theme.text_dim
        if f.isNew:
            col = Theme.accent
        elif f.isModified:
            col = Theme.btn_active

        nameStr = f.name
        if len(nameStr) > 20: nameStr = nameStr[:17] + "..."
        drawText(self.screen, col, self.fontSmall, 10, y + 3, nameStr)

        if f.isModified or f.isNew or f.name != f.originalName:
            cx = r.right - 20
            cRect = pygame.Rect(cx, y + 2, 18, 18)
            hoverC = cRect.collidepoint((mx, my))
            pygame.draw.rect(self.screen, Theme.btn_active if hoverC else Theme.btn_idle, cRect, 0, 5)
            drawText(self.screen, Theme.text, self.fontSmall, cRect.centerx, cRect.centery, "x", justify="center",
                     centeredVertically=True)

            if click and hoverC:
                self.revertFile(f)
                return True
        return False


if __name__ == "__main__":
    e = Editor()
    e.run()