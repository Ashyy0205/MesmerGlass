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
    // Center in -1..1 space
    vec2 p = vUV * 2.0 - 1.0;
    float r = length(p);
    // Slight aspect preserve assuming square viewport (UI will letterbox if needed)
    float angle = atan(p.y, p.x);
    float baseRot = uTime * uSpeedCPS * 6.2831853; // cycles per second -> radians
    // Two direction components create subtle counter-motion
    float rotA = baseRot * uDirSignA;
    float rotB = baseRot * 0.35 * uDirSignB;
    float twistTerm = r * uTwist * 3.0;
    float a = angle + rotA + rotB + twistTerm;
    float arms = float(max(uArms,2));
    float sector = (a / 6.2831853) * arms; // spiral arms in angular domain
    float stripe = fract(sector + r * 0.15);
    float bar = smoothstep(uBarWidth, uBarWidth - 0.08, stripe);
    // Wavefront radial highlight (direction flip evolution)
    float wave = 0.0;
    if(uWavefrontRadius > 0.0){
        float d = abs(r - uWavefrontRadius);
        wave = 1.0 - smoothstep(0.0, uWavefrontWidth, d);
    }
    float contrast = clamp(uContrast,0.1,4.0);
    float luminance = mix(bar, 1.0-bar, wave * 0.5);
    luminance = pow(luminance, 1.0/contrast);
    // Radial gradient color mixing
    float g = clamp(r,0.0,1.0);
    vec4 armInner = uArmColor;
    vec4 gapInner = uGapColor;
    vec4 armOuter = mix(uArmColor, uArmColorOuter, uGradientAmount);
    vec4 gapOuter = mix(uGapColor, uGapColorOuter, uGradientAmount);
    vec4 armCol = mix(armInner, armOuter, g);
    vec4 gapCol = mix(gapInner, gapOuter, g);
    vec4 baseCol = mix(gapCol, armCol, bar);
    // Palette drift: rotate hue-ish by mixing components
    if(uPaletteDrift > 0.0001){
        float t = (sin(uTime*0.1)+1.0)*0.5 * uPaletteDrift;
        baseCol.rgb = vec3(
            smoothBlend(baseCol.r, baseCol.g, t),
            smoothBlend(baseCol.g, baseCol.b, t),
            smoothBlend(baseCol.b, baseCol.r, t)
        );
    }
    // Vignette
    float vig = 1.0 - pow(r, 1.4) * uVignette;
    vec3 col = baseCol.rgb * luminance * vig;
    // Blend mode applied later in compositing; here we just output premultiplied-ish
    float alpha = clamp(uOpacity * vig, 0.0, 1.0);
    FragColor = vec4(col, alpha);
}
