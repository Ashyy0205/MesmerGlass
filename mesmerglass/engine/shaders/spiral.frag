// Spiral fragment shader (procedural evolving hypnotic spiral)
#version 330 core
out vec4 FragColor;
in vec2 vUV;

uniform float uTime;
uniform int   uArms;
uniform float uBarWidth;
uniform float uOpacity;
uniform float uTwist;
uniform float uSpeedCPS;
uniform float uContrast;
uniform float uVignette;
uniform float uDirSignA;
uniform float uDirSignB;
uniform float uWavefrontRadius;
uniform float uWavefrontWidth;
uniform int   uBlendMode; // 0 multiply,1 screen,2 softlight
uniform vec4  uArmColor;
uniform vec4  uGapColor;
uniform vec4  uArmColorOuter;
uniform vec4  uGapColorOuter;
uniform float uGradientAmount;
uniform float uPaletteDrift;

// Utility
float smoothBlend(float a, float b, float t){
    t = clamp(t,0.0,1.0); return a + (b-a)*(t*t*(3.0-2.0*t));
}

vec3 softLight(vec3 a, vec3 b){
    return (1.0-2.0*b)*a*a + 2.0*b*a; // simple approx
}

void main(){
    // Diagnostic: output raw UV coordinates as color
        // Diagnostic: output vUV as color to confirm geometry/attribute mapping
        FragColor = vec4(vUV, 0.0, 1.0); // Keeping the original output for reference
}
