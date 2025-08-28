// Fullscreen triangle vertex shader (Step 1 pass-through)
// Expands a single triangle covering the viewport; attributes supplied by VBO.
#version 330 core
layout (location = 0) in vec2 aPos; // NDC position
layout (location = 1) in vec2 aUV;  // UV (may extend >1 for clipped triangle)
out vec2 vUV;
void main() {
    vUV = aUV;
    gl_Position = vec4(aPos, 0.0, 1.0);
}
