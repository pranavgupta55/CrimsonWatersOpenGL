#version 330 core

in vec2 in_vert;

// SPLIT ATTRIBUTES
in vec4 in_pos_z_rad;   // x, y, z, base_radius
in vec3 in_squash_seed_res; // squash, seed, resistance

uniform vec2 u_resolution;
uniform vec2 u_scroll;
uniform int u_layer_idx;     // 0 to 4

// CHANGED: Increased hole limit for territory tiles
#define MAX_HOLES 256
uniform vec2 u_holes[MAX_HOLES];
uniform int u_num_holes;

uniform float u_vision_radius;
uniform float u_time;

// CONFIG UNIFORMS
uniform float u_layer_offset_x;
uniform float u_layer_offset_y;
uniform float u_layer_var_y;
uniform float u_layer_dec;
uniform float u_layer_dec_var;

// ANIMATION UNIFORMS
uniform float u_wander_speed;
uniform float u_wander_strength;
uniform float u_pulse_speed;
uniform float u_pulse_var;

out vec2 v_uv;
out float v_squash;

float hash(float n) { return fract(sin(n) * 43758.5453123); }

void main() {
    vec2 center_pos = in_pos_z_rad.xy;
    float z_height = in_pos_z_rad.z;
    float base_radius = in_pos_z_rad.w;
    float squash = in_squash_seed_res.x;
    float seed = in_squash_seed_res.y;
    float resistance = in_squash_seed_res.z;

    float f_idx = float(u_layer_idx);

    // --- MATH ---
    float rand_dec = (hash(seed + f_idx * 12.34) * 2.0 - 1.0) * u_layer_dec_var;
    float current_radius = base_radius - (u_layer_dec * f_idx) + rand_dec;

    // --- FIZZLE ---
    float pulse = sin((u_time * u_pulse_speed) + seed) * u_pulse_var;
    current_radius += pulse;

    float rand_x = (hash(seed + f_idx * 7.1) * 2.0 - 1.0) * u_layer_offset_x;
    float off_x = rand_x * pow(f_idx, 0.8);

    float rand_y = (hash(seed + f_idx * 3.3) * 2.0 - 1.0) * u_layer_var_y;
    float off_y = (u_layer_offset_y * pow(f_idx, 0.8)) + rand_y;

    // --- WANDER ---
    float wander_x = sin((u_time * u_wander_speed) + seed) * u_wander_strength;
    float wander_y = cos((u_time * u_wander_speed) + seed * 1.5) * u_wander_strength;

    center_pos.x -= off_x;
    center_pos.y += off_y;
    center_pos.x += wander_x;
    center_pos.y += wander_y;

    // --- VISION HOLES ---
    vec2 screen_pos_calc = center_pos - u_scroll + (u_resolution / 2.0);
    float effective_vision_radius = u_vision_radius * (1.0 + resistance);

    float final_scale = 1.0;

    for (int i = 0; i < MAX_HOLES; i++) {
        if (i >= u_num_holes) break;

        float dist = distance(screen_pos_calc, u_holes[i]);
        // Soft transition for fog clearing
        float hole_scale = smoothstep(effective_vision_radius - 15.0, effective_vision_radius + 15.0, dist);

        final_scale = min(final_scale, hole_scale);
    }

    current_radius *= final_scale;

    if (current_radius < 1.0) {
        gl_Position = vec4(2.0, 2.0, 2.0, 1.0); // Cull
        return;
    }

    // --- FINAL POSITIONING ---
    vec2 screen_pos = center_pos - u_scroll + (u_resolution / 2.0);
    vec2 vert_pos = in_vert * current_radius + screen_pos;
    vec2 clip_pos = (vert_pos / u_resolution) * 2.0 - 1.0;

    v_uv = in_vert * 0.5 + 0.5;
    v_squash = squash;

    gl_Position = vec4(clip_pos, 0.0, 1.0);
}