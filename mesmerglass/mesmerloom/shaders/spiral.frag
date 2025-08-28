// MesmerLoom fragment shader (Step 2): spiral + basic blend modes.
#version 330 core
in vec2 vUV;
out vec4 FragColor;
uniform vec2 uResolution; // (w,h)
uniform float uTime;      // seconds since start
uniform float uPhase;     // accumulated phase
uniform sampler2D uVideo; // bound video frame or fallback 1x1
// Extended uniforms (exported by SpiralDirector)
uniform float uBaseSpeed;
uniform float uEffectiveSpeed;
uniform float uBarWidth;
uniform float uTwist;
uniform float uSpiralOpacity;
uniform float uContrast;
uniform float uVignette;
uniform float uChromaticShift;
uniform float uFlipWaveRadius;
uniform int   uFlipState;
uniform float uIntensity;
uniform int   uSafetyClamped;
uniform int   uBlendMode; // 0=Normal 1=Add 2=Screen

float linstep(float a, float b, float v){ return clamp((v-a)/(b-a),0.0,1.0); }
float vignetteMask(vec2 uv, float strength){
    vec2 c = uv*2.0-1.0; float rr = dot(c,c); return clamp(1.0 - rr*strength, 0.0, 1.0);
}
vec3 chromaSample(sampler2D tex, vec2 uv, float shift){
    if(shift <= 0.0001) return texture(tex, uv).rgb;
    vec2 off = vec2(shift / max(uResolution.x,1.0), 0.0);
    float r = texture(tex, uv + off).r;
    float g = texture(tex, uv).g;
    float b = texture(tex, uv - off).b;
    return vec3(r,g,b);
}
void main() {
    vec2 uv = vUV / max(uResolution, vec2(1.0));
    uv = clamp(uv, 0.0, 1.0);
    // Centered coords for spiral calc
    vec2 p = (uv*2.0-1.0);
    float r = length(p);
    float a = atan(p.y, p.x);
    // Spiral field: stripes via sin of (angle + twist*r + phase)
    float stripes = 0.5 + 0.5 * sin(a * (4.0 + uTwist*20.0) + r * (8.0 + uTwist*10.0) + uPhase*6.28318);
    // Bar shaping by width -> convert to binary-ish bands
    float bars = smoothstep(0.5 - uBarWidth*0.5, 0.5 + uBarWidth*0.5, stripes);
    // Flip wave radial mask (inside-out reveal)
    float flipMask = 1.0;
    if(uFlipState == 1){
        flipMask = linstep(uFlipWaveRadius - 0.10, uFlipWaveRadius, r);
    }
    // Spiral grayscale
    float spiralGray = mix(0.0, 1.0, bars) * flipMask;
    // Contrast (+ simple safety indicator tint if clamped)
    float c = clamp((spiralGray - 0.5) * uContrast + 0.5, 0.0, 1.0);
    vec3 spiralRGB = vec3(c);
    if(uSafetyClamped == 1){ // tint slight amber when clamps engaged
        spiralRGB *= vec3(1.05, 0.95, 0.85);
    }
    // Opacity
    float spiralAlpha = clamp(uSpiralOpacity, 0.0, 1.0) * vignetteMask(uv, uVignette*0.85);
    // Video sample w/ optional chromatic shift
    vec3 videoRGB = chromaSample(uVideo, uv, uChromaticShift * 2.0);
    vec4 videoColor = vec4(videoRGB, 1.0);
    vec4 spiralColor = vec4(spiralRGB, spiralAlpha);
    // Blend modes
    vec3 outRGB;
    if(uBlendMode == 1){ // Add
        outRGB = clamp(videoColor.rgb + spiralColor.rgb * spiralColor.a, 0.0, 1.0);
    } else if(uBlendMode == 2){ // Screen
        vec3 s = spiralColor.rgb * spiralColor.a;
        outRGB = 1.0 - (1.0 - videoColor.rgb)*(1.0 - s);
    } else { // Normal
        outRGB = mix(videoColor.rgb, spiralColor.rgb, spiralColor.a);
    }
    FragColor = vec4(outRGB, 1.0);
}
