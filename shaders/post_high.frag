#version 330 core

out vec4 fragColor;
in vec2 uv;

uniform sampler2D u_scene;
uniform float u_time;

// Configs
uniform float u_bloom_intensity;
uniform float u_vig_strength;
uniform float u_vig_radius;
uniform float u_vig_softness;

void main() {
    vec3 color = texture(u_scene, uv).rgb;

    // --- BLOOM (Glowing Highlights) ---
    float pulse = 1.0 + sin(u_time * 0.5) * 0.05;

    // Adjusted for aspect ratio roughly
    vec2 texel = 1.0 / vec2(1600.0, 900.0);
    vec3 bloom = vec3(0.0);

    // Simple Box Blur
    for(float x=-2.0; x<=2.0; x+=1.0){
        for(float y=-2.0; y<=2.0; y+=1.0){
            vec3 s = texture(u_scene, uv + vec2(x,y)*texel*2.0).rgb;
            bloom += s * s;
        }
    }
    bloom /= 25.0;

    color += bloom * u_bloom_intensity * pulse;

    // --- VIGNETTE ---
    vec2 center = vec2(0.5, 0.5);
    float dist = distance(uv, center);

    float vig = smoothstep(u_vig_radius, u_vig_radius + u_vig_softness, dist);
    color = mix(color, vec3(0.0, 0.0, 0.05), vig * u_vig_strength);

    fragColor = vec4(color, 1.0);
}