# visual_config.py

# --- Display ---
# Map Generation Base Size
# Fixed size to ensure consistent generation speed regardless of monitor resolution
MAP_GENERATION_WIDTH = 1600
MAP_GENERATION_HEIGHT = 900

# Render Resolutions
# Land: High resolution (Vertical pixels) - High detail
GAME_RENDER_H = 1280
# GAME_RENDER_W will be calculated dynamically in main.py based on aspect ratio

# Clouds: Low resolution (Vertical pixels) - Pixel art look
CLOUD_RENDER_H = 320
# CLOUD_RENDER_W will be calculated dynamically in main.py

# Vision
VISION_RADIUS = 50
TERRITORY_VISION_RADIUS = 25
CLOUD_RESISTANCE_VARIANCE = 0.20

# --- Cloud Logic ---
CLOUD_COUNT = 8000
CLOUD_MIN_RADIUS = 4
CLOUD_MAX_RADIUS = 24
CLOUD_BUFFER_SPACE = 120

# Movement
CLOUD_WANDER_SPEED = 1.0
CLOUD_WANDER_STRENGTH = 2.0
CLOUD_PULSE_SPEED = 0.5
CLOUD_PULSE_VARIANCE = 1.5

# Shape
SQUASH_MIN = 0.5
SQUASH_MAX = 1.0

# 3D Layers
CLOUD_MIN_HEIGHT = 10.0
CLOUD_MAX_HEIGHT = 50.0

# Shading / Layering
CLOUD_LAYER_OFFSET_X = 1.0
CLOUD_LAYER_OFFSET_Y = 2.0
CLOUD_LAYER_OFFSET_VARIANCE_Y = 1.5
CLOUD_LAYER_SIZE_DECREASE = 3.0
CLOUD_LAYER_SIZE_DECREASE_VARIANCE = 1.5

# --- Visual Effects ---
# Godrays
GODRAY_INTENSITY = 0.95
GODRAY_DECAY = 0.80
GODRAY_WEIGHT = 0.06
GODRAY_DENSITY = 0.8
GODRAY_SAMPLES = 40

# Bloom
BLOOM_INTENSITY = 0.15

# Vignette
VIGNETTE_STRENGTH = 0.6
VIGNETTE_RADIUS = 0.35
VIGNETTE_SOFTNESS = 0.4

# --- Palette ---
CLOUD_PALETTE = [
    (156, 112, 123),
    (198, 136, 129),
    (223, 155, 129),
    (253, 175, 129),
    (255, 205, 142)
]