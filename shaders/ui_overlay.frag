#version 330 core
out vec4 fragColor;
in vec2 uv;

uniform sampler2D u_ui;

void main() {
    // Flip Y because Pygame 0,0 is Top-Left, OpenGL is Bottom-Left
    vec4 col = texture(u_ui, vec2(uv.x, 1.0 - uv.y));
    if (col.a < 0.01) discard;
    fragColor = col;
}