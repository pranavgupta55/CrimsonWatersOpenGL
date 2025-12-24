#version 330 core

out vec4 fragColor;
in vec2 uv;

uniform sampler2D u_map;
uniform sampler2D u_clouds; // RGBA
uniform float u_time;

// GODRAYS UNIFORMS
uniform float u_godray_intensity;
uniform float u_godray_decay;
uniform float u_godray_weight;
uniform float u_godray_density;
uniform int u_godray_samples;

const int MAX_SAMPLES = 100;

float GetIGN(vec2 p) {
    vec3 magic = vec3(0.06711056, 0.00583715, 52.9829189);
    return fract(magic.z * fract(dot(p, magic.xy)));
}

vec3 applyColorGrade(vec3 color) {
    vec3 shadows = vec3(0.15, 0.1, 0.25);
    vec3 highlights = vec3(1.0, 0.95, 0.85);
    float lum = dot(color, vec3(0.299, 0.587, 0.114));
    return mix(shadows, highlights, lum) * color * 1.3;
}

void main() {
    // Flip Y-Axis for map texture to align OpenGL (Bottom-Left) with Pygame (Top-Left)
    vec3 mapColor = texture(u_map, vec2(uv.x, 1.0 - uv.y)).rgb;
    vec4 cloudSample = texture(u_clouds, uv);

    vec3 cloudColor = cloudSample.rgb;
    float cloudAlpha = cloudSample.a;

    // Apply Color Grading to Clouds ONLY
    cloudColor = applyColorGrade(cloudColor);

    // --- SHADOWS ---
    vec2 shadow_offset = vec2(0.04, 0.04);
    vec2 shadow_uv = uv + shadow_offset;

    float shadow_alpha_at_offset = 0.0;

    // Bounds check
    if (shadow_uv.x >= 0.0 && shadow_uv.x <= 1.0 && shadow_uv.y >= 0.0 && shadow_uv.y <= 1.0) {
        shadow_alpha_at_offset = texture(u_clouds, shadow_uv).a;
    }

    if (shadow_alpha_at_offset > 0.2 && cloudAlpha < 0.8) {
        // FIX: Fade shadow near edges to prevent sharp cutoff bands
        float edge_dist_x = min(shadow_uv.x, 1.0 - shadow_uv.x);
        float edge_dist_y = min(shadow_uv.y, 1.0 - shadow_uv.y);
        float edge_dist = min(edge_dist_x, edge_dist_y);

        // Fade out over 0.05 UV units
        float edge_fade = smoothstep(0.0, 0.05, edge_dist);

        vec3 shadow_col = vec3(0.15, 0.1, 0.2);
        mapColor = mix(mapColor, shadow_col, 0.5 * edge_fade);
    }

    // --- GOD RAYS ---
    vec2 lightDir = normalize(vec2(0.6, 1.0));
    float density = u_godray_density;
    vec2 deltaTextCoord = lightDir * density / float(u_godray_samples);
    vec2 texCoord = uv;

    float dither = GetIGN(gl_FragCoord.xy);
    texCoord += deltaTextCoord * dither;

    float illuminationDecay = 1.0;
    vec3 accumRayColor = vec3(0.0);
    vec3 lightColor = vec3(1.0, 0.95, 0.8);

    for(int i = 0; i < MAX_SAMPLES; i++) {
        if (i >= u_godray_samples) break;
        texCoord += deltaTextCoord;
        if (texCoord.x < 0.0 || texCoord.x > 1.0 || texCoord.y < 0.0 || texCoord.y > 1.0) break;

        float sampleAlpha = texture(u_clouds, texCoord).a;
        float openSky = max(0.0, 1.0 - sampleAlpha);

        vec3 stepColor = lightColor * openSky * illuminationDecay * u_godray_weight;
        accumRayColor += stepColor;
        illuminationDecay *= u_godray_decay;
    }

    accumRayColor *= u_godray_intensity;

    // Apply Color Grading to Godrays as well
    accumRayColor = applyColorGrade(accumRayColor);

    // --- COMBINE ---
    // Add Godrays to Map (Screen Blend)
    vec3 composite = 1.0 - (1.0 - mapColor) * (1.0 - accumRayColor);

    // Mix Clouds on top
    vec3 final_color = mix(composite, cloudColor, cloudAlpha);

    fragColor = vec4(final_color, 1.0);
}