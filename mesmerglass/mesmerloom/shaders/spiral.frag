
// MesmerLoom Spiral Fragment Shader - High Precision Implementation
#version 330 core

// Use high precision for critical calculations
precision highp float;

in vec2 vUV;
out vec4 FragColor;

// Core uniforms from SpiralDirector
uniform vec2 uResolution;
uniform float uTime;
uniform float uPhase;
uniform float uBaseSpeed;
uniform float uEffectiveSpeed;
uniform float uBarWidth;
uniform float uTwist;
uniform float uSpiralOpacity;
uniform float uContrast;
uniform float uVignette;
uniform float uChromaticShift;
uniform float uFlipWaveRadius;
uniform int uFlipState;
uniform float uIntensity;
uniform int uSafetyClamped;

// Additional spiral parameters (with defaults)
uniform int uArms = 8;
uniform int uBlendMode = 0; // 0=multiply, 1=screen, 2=softlight
uniform vec3 uArmColor = vec3(1.0, 1.0, 1.0);
uniform vec3 uGapColor = vec3(0.0, 0.0, 0.0);
uniform int uSuperSamples = 4; // Anti-aliasing samples: 1=none, 4=2x2, 9=3x3, 16=4x4
uniform int uPrecisionLevel = 2; // 0=low, 1=medium, 2=high
uniform int uTestOpaqueMode = 0; // Test mode: 1=fully opaque for artifact testing
uniform int uTestLegacyBlend = 0; // Test mode: 1=legacy blend, 0=premultiplied alpha
uniform int uSRGBOutput = 0; // Test mode: 1=manual sRGB conversion, 0=let framebuffer handle it
uniform int uInternalOpacity = 0; // Test mode: 1=internal blending with opaque window, 0=window transparency
uniform vec3 uBackgroundColor = vec3(0.0, 0.0, 0.0); // Background color for internal blending

// High-precision mathematical constants
const float PI = 3.1415926535897932384626433832795;
const float TWO_PI = 6.2831853071795864769252867665590;

// sRGB conversion functions
vec3 linearToSRGB(vec3 linear) {
    return mix(linear * 12.92, 
               pow(linear, vec3(1.0/2.4)) * 1.055 - 0.055, 
               step(0.0031308, linear));
}

vec3 sRGBToLinear(vec3 srgb) {
    return mix(srgb / 12.92, 
               pow((srgb + 0.055) / 1.055, vec3(2.4)), 
               step(0.04045, srgb));
}

// Utility functions
float smoothBlend(float a, float b, float t) {
    t = clamp(t, 0.0, 1.0);
    return a + (b - a) * (t * t * (3.0 - 2.0 * t));
}

vec3 softLight(vec3 a, vec3 b) {
    return (1.0 - 2.0 * b) * a * a + 2.0 * b * a;
}

// High-precision angle normalization to reduce floating-point drift
float normalizeAngle(float angle) {
    // Use high-precision modulo to keep angles in [-PI, PI] range
    return angle - TWO_PI * floor((angle + PI) / TWO_PI);
}

// Pixel-perfect spiral calculation with enhanced precision
float calculateSpiralPattern(vec2 p, float twist, float phase, int arms) {
    // Calculate polar coordinates with clamped precision
    float r = length(p);
    float angle = atan(p.y, p.x);
    
    // Apply precision level settings
    if (uPrecisionLevel >= 2) {
        // High precision: normalize angle to prevent precision drift
        angle = normalizeAngle(angle);
    }
    
    // Apply twist with enhanced precision
    angle += twist * r;
    
    if (uPrecisionLevel >= 2) {
        angle = normalizeAngle(angle);
    }
    
    // Convert to spiral coordinate with precision-adjusted constants
    float spiralCoord;
    if (uPrecisionLevel >= 1) {
        // Medium/High precision: use high-precision division
        spiralCoord = angle * float(arms) / TWO_PI + phase;
    } else {
        // Low precision: use simple calculation for compatibility
        spiralCoord = angle * float(arms) / 6.283185 + phase;
    }
    
    // Return fractional part with appropriate precision
    return spiralCoord - floor(spiralCoord);
}

void main() {
    // FIXED: Calculate UV from gl_FragCoord instead of broken vUV attribute
    vec2 vUV = gl_FragCoord.xy / uResolution;
    
    // Convert UV to centered coordinates [-1, 1] with high precision
    vec2 p = (vUV * 2.0 - 1.0);
    
    // Apply aspect ratio correction with precise division
    p.x *= uResolution.x / uResolution.y;
    
    // Calculate polar coordinates for main calculation
    float r = length(p);
    float angle = atan(p.y, p.x);
    
    // Enhanced precision anti-aliasing with configurable supersampling
    vec2 pixelSize = 1.0 / uResolution;
    float baseAntiAlias = length(fwidth(p));
    
    // Apply precision-based clamping
    if (uPrecisionLevel >= 2) {
        // High precision: clamp pixel size to prevent precision underflow
        pixelSize = max(pixelSize, vec2(1e-6));
    } else if (uPrecisionLevel >= 1) {
        // Medium precision: moderate clamping
        pixelSize = max(pixelSize, vec2(1e-5));
    }
    // Low precision: no clamping for maximum compatibility
    
    // Multi-sample anti-aliasing: sample multiple points within the pixel
    float bar = 0.0;
    int samples = max(1, uSuperSamples);
    float sampleWeight = 1.0 / float(samples);
    
    // Calculate grid size for supersampling pattern
    int gridSize = int(sqrt(float(samples)));
    if (gridSize * gridSize != samples) {
        gridSize = 2;  // Fallback to 2x2 if not perfect square
        samples = 4;
        sampleWeight = 0.25;
    }
    
    for (int i = 0; i < samples; i++) {
        // Calculate sub-pixel offset with precision clamping
        vec2 offset = vec2(float(i % gridSize), float(i / gridSize)) * pixelSize / float(gridSize) - pixelSize * 0.5;
        
        // Apply precision-based offset clamping
        if (uPrecisionLevel >= 1) {
            // Medium/High precision: clamp offset to prevent precision issues
            offset = clamp(offset, -pixelSize * 0.5, pixelSize * 0.5);
        }
        vec2 sampleP = p + offset;
        
        // Use high-precision spiral calculation
        // Note: Add subtle uTime reference to prevent OpenGL optimization
        float effectivePhase = uPhase + (uTime * 0.0001); // Minimal time influence to keep uniform
        float sampleBarPattern = calculateSpiralPattern(sampleP, uTwist, effectivePhase, uArms);
        
        // Distance-based edge width for consistent quality
        float sampleR = length(sampleP);
        float distanceScale = 1.0 + sampleR * 0.5;
        float edgeWidth;
        
        // Precision-based edge width calculation
        if (uPrecisionLevel >= 2) {
            // High precision: very fine edge control
            edgeWidth = max(baseAntiAlias * distanceScale, uBarWidth * 0.002);
        } else if (uPrecisionLevel >= 1) {
            // Medium precision: balanced edge control
            edgeWidth = max(baseAntiAlias * distanceScale, uBarWidth * 0.005);
        } else {
            // Low precision: larger edges for stability
            edgeWidth = max(baseAntiAlias * distanceScale, uBarWidth * 0.01);
        }
        
        // Calculate bar contribution with enhanced smoothstep precision
        float halfWidth = uBarWidth * 0.5;
        float sampleBar = smoothstep(0.5 - halfWidth - edgeWidth, 
                                    0.5 - halfWidth + edgeWidth, sampleBarPattern) -
                         smoothstep(0.5 + halfWidth - edgeWidth, 
                                   0.5 + halfWidth + edgeWidth, sampleBarPattern);
        
        bar += sampleBar * sampleWeight;
    }
    
    // Precision-based gradient filtering
    float gradientMagnitude = length(vec2(dFdx(bar), dFdy(bar)));
    float gradientThreshold = (uPrecisionLevel >= 2) ? 0.03 : (uPrecisionLevel >= 1) ? 0.05 : 0.1;
    
    if (gradientMagnitude > gradientThreshold) {
        // Apply precision-enhanced smoothing
        bar = smoothstep(0.0, 1.0, bar);
    }
    
    // Apply flip wave effect during flip state (with precision-enhanced calculation)
    if (uFlipState == 1) {
        // Calculate polar coordinates for flip effect
        float r = length(p);
        
        // Use the same supersampling approach for flip wave with precision
        float flipEffect = 0.0;
        int flipSamples = max(1, uSuperSamples);
        int flipGridSize = int(sqrt(float(flipSamples)));
        if (flipGridSize * flipGridSize != flipSamples) {
            flipGridSize = 2;
            flipSamples = 4;
        }
        
        for (int i = 0; i < flipSamples; i++) {
            vec2 offset = vec2(float(i % flipGridSize), float(i / flipGridSize)) * pixelSize / float(flipGridSize) - pixelSize * 0.5;
            
            if (uPrecisionLevel >= 1) {
                offset = clamp(offset, -pixelSize * 0.5, pixelSize * 0.5);  // Precision clamp
            }
            vec2 sampleP = p + offset;
            float sampleR = length(sampleP);
            
            float flipWidth = max(baseAntiAlias * 2.0, (uPrecisionLevel >= 2) ? 0.01 : 0.02);
            float sampleFlipEffect = smoothstep(uFlipWaveRadius - flipWidth, 
                                               uFlipWaveRadius + flipWidth, sampleR);
            flipEffect += sampleFlipEffect / float(flipSamples);
        }
        bar = mix(bar, 1.0 - bar, flipEffect);
    }
    
    // Interpolate between arm and gap colors
    vec3 baseColor = mix(uGapColor, uArmColor, bar);
    
    // CRITICAL FIX: Apply intensity scaling to ensure uIntensity uniform is used
    // This prevents OpenGL from optimizing out the uIntensity uniform
    // Scale the spiral contrast/visibility based on intensity
    float intensityFactor = clamp(uIntensity, 0.0, 1.0);
    baseColor = mix(vec3(0.5), baseColor, intensityFactor); // Blend toward neutral when intensity is low
    
    // Apply contrast
    baseColor = (baseColor - 0.5) * uContrast + 0.5;
    baseColor = clamp(baseColor, 0.0, 1.0);
    
    // Apply vignette effect (smoother)
    float vignette = 1.0 - uVignette * smoothstep(0.0, 1.0, r * r);
    baseColor *= vignette;
    
    // Apply chromatic shift for hypnotic effect (precision-enhanced)
    if (uChromaticShift > 0.0) {
        // High-precision chromatic shift calculation (reuse existing r and angle)
        if (uPrecisionLevel >= 2) {
            angle = normalizeAngle(angle);  // Normalize for precision
        }
        
        float chromaPhase = angle + uPhase * 0.02;  // Further reduced for stability
        float chromaAmount = uChromaticShift * (uPrecisionLevel >= 1 ? 0.025 : 0.05);
        
        // Use precision-adjusted trigonometric functions
        baseColor.r += sin(chromaPhase) * chromaAmount;
        baseColor.g += sin(chromaPhase + TWO_PI / 3.0) * chromaAmount;  // 120 degrees
        baseColor.b += sin(chromaPhase + TWO_PI * 2.0 / 3.0) * chromaAmount;  // 240 degrees
        baseColor = clamp(baseColor, 0.0, 1.0);
    }
    
    // Apply final opacity
    float finalOpacity = uSpiralOpacity;
    
    // Safety clamp indicator (subtle red tint if clamped)
    if (uSafetyClamped == 1) {
        baseColor.r += 0.05;
    }
    
    // Output final color with DWM dithering solutions
    if (uTestOpaqueMode == 1) {
        // TEST MODE: Output fully opaque to test compositor/layered-window artifacts
        vec3 outputColor = (uSRGBOutput == 1) ? linearToSRGB(baseColor) : baseColor;
        FragColor = vec4(outputColor, 1.0);
    } else if (uInternalOpacity == 1) {
        // SOLUTION: Internal opacity blending with opaque window (bypasses DWM dithering)
        // Do your "opacity" inside your GL: mix(bgColor, spiralColor, globalOpacity)
        // CRITICAL: Always output alpha=1.0 to prevent any Qt/Windows alpha compositing
        vec3 outputColor = (uSRGBOutput == 1) ? linearToSRGB(baseColor) : baseColor;
        vec3 blendedColor = mix(uBackgroundColor, outputColor, finalOpacity);
        FragColor = vec4(blendedColor, 1.0); // Force alpha=1 - no exceptions
    } else if (uTestLegacyBlend == 1) {
        // TEST MODE: Legacy alpha blending (may show DWM dithering artifacts)
        vec3 outputColor = (uSRGBOutput == 1) ? linearToSRGB(baseColor) : baseColor;
        FragColor = vec4(outputColor, finalOpacity);
    } else {
        // Use premultiplied alpha (still subject to DWM dithering with layered windows)
        vec3 outputColor = (uSRGBOutput == 1) ? linearToSRGB(baseColor) : baseColor;
        vec3 premultipliedColor = outputColor * finalOpacity;
        FragColor = vec4(premultipliedColor, finalOpacity);
    }
}
