
#version 330 core
in vec2 vUV;
out vec4 FragColor;
uniform vec2 uResolution;
uniform float uTime;
void main() {
    // Normalize UV coordinates
    // Diagnostic: output gradient using gl_FragCoord.xy / uResolution
    vec2 uv = vUV;
    vec2 p = (uv * 2.0 - 1.0);
    float r = length(p);
    float a = atan(p.y, p.x);
    float stripes = 0.5 + 0.5 * sin(a * 8.0 + r * 12.0 + uTime * 2.0);
    vec3 color = vec3(stripes);
    FragColor = vec4(color, 1.0);
}
