import random
import struct
from visual_config import *

class CloudManager:
    def __init__(self, render_w, render_h):
        self.render_w = render_w
        self.render_h = render_h
        self.particles = []
        self.spawn_screen_space()

    def spawn_screen_space(self):
        # Use config buffer
        buffer = CLOUD_BUFFER_SPACE

        half_w = self.render_w / 2
        half_h = self.render_h / 2

        start_x = -half_w - buffer
        end_x = half_w + buffer
        start_y = -half_h - buffer
        end_y = half_h + buffer

        for _ in range(CLOUD_COUNT):
            x = random.uniform(start_x, end_x)
            y = random.uniform(start_y, end_y)
            z = random.uniform(CLOUD_MIN_HEIGHT, CLOUD_MAX_HEIGHT)

            radius = (random.uniform(0, 1) ** 1.5) * (CLOUD_MAX_RADIUS - CLOUD_MIN_RADIUS) + CLOUD_MIN_RADIUS
            squash = random.uniform(SQUASH_MIN, SQUASH_MAX)
            seed = random.uniform(0.0, 100.0)

            # Resistance: -0.15 to +0.15
            resistance = random.uniform(-CLOUD_RESISTANCE_VARIANCE, CLOUD_RESISTANCE_VARIANCE)

            speed_x = random.uniform(0.05, 0.15) * (1.0 + z * 0.05)
            speed_y = random.uniform(-0.02, 0.02)

            # [x, y, z, radius, squash, seed, resistance, speed_x, speed_y]
            self.particles.append([x, y, z, radius, squash, seed, resistance, speed_x, speed_y])

        self.particles.sort(key=lambda p: p[2])

    def update(self, scroll_x, scroll_y, dt):
        buffer = CLOUD_BUFFER_SPACE

        half_w = self.render_w / 2
        half_h = self.render_h / 2

        view_left = scroll_x - half_w - buffer
        view_right = scroll_x + half_w + buffer
        view_top = scroll_y - half_h - buffer
        view_bot = scroll_y + half_h + buffer

        width = view_right - view_left
        height = view_bot - view_top

        wind_multiplier = 2.0

        for p in self.particles:
            p[0] += p[7] * dt * wind_multiplier  # speed_x
            p[1] += p[8] * dt * wind_multiplier  # speed_y

            # Infinite Scroll Teleportation
            if p[0] < view_left:
                p[0] += width
            elif p[0] > view_right:
                p[0] -= width

            if p[1] < view_top:
                p[1] += height
            elif p[1] > view_bot:
                p[1] -= height

    def get_instance_buffer(self):
        data = bytearray()
        for p in self.particles:
            # Pack: x, y, z, radius, squash, seed, resistance (7 floats)
            data.extend(struct.pack('7f', p[0], p[1], p[2], p[3], p[4], p[5], p[6]))
        return data