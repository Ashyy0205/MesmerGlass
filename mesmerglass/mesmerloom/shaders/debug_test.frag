// Debug Test Fragment Shader - Force test coordinates
#version 330 core

precision highp float;

in vec2 vUV;
out vec4 FragColor;

void main() {
    // Calculate UV from fragment position for testing
    vec2 screenPos = gl_FragCoord.xy / vec2(1920.0, 1080.0);
    
    // Show calculated UV as colors (red = X, green = Y)
    FragColor = vec4(screenPos.x, screenPos.y, 0.0, 1.0);
}
