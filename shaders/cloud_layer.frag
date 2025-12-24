#version 330 core

out vec4 fragColor;
in vec2 v_uv;
in float v_squash;

uniform int u_layer_idx;
uniform vec3 u_palette[5];

void main() {
    vec2 coord = v_uv - 0.5;

    // Apply Squash to bottom half
    if (coord.y < 0.0) {
        coord.y /= v_squash;
    }

    float dist = length(coord);

    if (dist > 0.5) {
        discard;
    }

    vec3 base_color = u_palette[u_layer_idx];
    fragColor = vec4(base_color, 1.0);
}