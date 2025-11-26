// MesmerLoom Spiral Fragment Shader - Trance 7-Type Implementation with Cone Intersection
#version 330 core

precision highp float;

in vec2 vUV;
out vec4 FragColor;

// Trance-compatible uniforms (NEW - from shaders.h lines 82-92)
uniform float near_plane;        // Distance to near plane (controls FoV, typically 1.0)
uniform float far_plane;          // Distance to far plane (controls zoom effect, typically 5.0)
uniform float eye_offset;         // Eye offset for VR (0.0 for non-VR)
uniform float aspect_ratio;       // width / height for aspect correction
uniform float width;              // Spiral width in degrees (360, 180, 120, 90, 72, 60)
uniform float spiral_type;        // Spiral type selector (1-7, defaults to 7 if 0)
uniform float time;               // Rotation phase [0, 1]
uniform float rotation_speed;     // Rotation speed multiplier (4.0 = normal, 40.0 = max)
uniform vec4 acolour;             // Spiral arm color A (RGBA)
uniform vec4 bcolour;             // Spiral arm color B (RGBA)

// MesmerGlass existing uniforms (preserved for compatibility)
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
uniform float uFlipWaveWidth;
uniform int uFlipState;
uniform float uIntensity;
uniform int uSafetyClamped;
uniform int uArms;
uniform int uBlendMode;
uniform vec3 uArmColor;
uniform vec3 uGapColor;
uniform int uSuperSamples;
uniform int uPrecisionLevel;
uniform int uTestOpaqueMode;
uniform int uTestLegacyBlend;
uniform int uSRGBOutput;
uniform int uInternalOpacity;
uniform vec3 uBackgroundColor;
uniform float uWindowOpacity;

// Mathematical constants
const float PI = 3.1415926535897932384626433832795;
const float TWO_PI = 6.2831853071795864769252867665590;

// ============================================================================
// TRANCE SPIRAL TYPE FUNCTIONS (from shaders.h lines 98-134)
// ============================================================================

float spiral1(float r) {
    return log(r);
}

float spiral2(float r) {
    return r * r;
}

float spiral3(float r) {
    return r;
}

float spiral4(float r) {
    return sqrt(r);
}

float spiral5(float r) {
    return -abs(r - 1.0);
}

float spiral6(float r) {
    float r1 = r * 1.2;
    float r2 = (1.5 - 0.5 * r) * 1.2;
    return r < 1.0 ? pow(r1, 6.0) : -pow(r2, 6.0);
}

float spiral7(float r) {
    float m = mod(r, 0.2);
    m = m < 0.1 ? m : 0.2 - m;
    return r + m * 3.0;
}

// ============================================================================
// CONE INTERSECTION (3D Depth Effect) - from shaders.h lines 139-192
// ============================================================================

vec2 cone_intersection(vec2 aspect_position) {
    // Cone origin
    vec3 cone_origin = vec3(0.0, 0.0, far_plane);
    // Cone axis unit vector
    vec3 cone_axis = vec3(0.0, 0.0, -1.0);
    // Cone angle, chosen such that the cone intersects the corners of the near plane
    float max_width = aspect_ratio + abs(eye_offset);
    float cone_angle = atan(sqrt(max_width * max_width + 1.0) / (far_plane - near_plane));
    
    // Eye position
    vec3 ray_origin = vec3(eye_offset, 0.0, 0.0);
    // Unit vector from eye to near plane
    vec3 ray_vector = normalize(vec3(aspect_position, near_plane));
    
    // Quadratic equation for line-cone intersection
    vec3 m = cone_axis * cone_axis - cos(cone_angle) * cos(cone_angle);
    vec3 delta = ray_origin - cone_origin;
    
    float a = dot(m, ray_vector * ray_vector);
    float b = 2.0 * dot(m, ray_vector * delta);
    float c = dot(m, delta * delta);
    
    // Solution for equation
    float d = sqrt(b * b - 4.0 * a * c);
    float t0 = (-b - d) / (2.0 * a);
    float t1 = (-b + d) / (2.0 * a);
    float d0 = dot(cone_axis, ray_origin + t0 * ray_vector - cone_origin);
    float d1 = dot(cone_axis, ray_origin + t1 * ray_vector - cone_origin);
    
    float t = 0.0;
    if (a == 0.0) {
        // Ray parallel to cone; only one solution
        t = -c / b;
    } else if (d == 0.0) {
        // Only one intersection point
        t = -b / (2.0 * a);
    } else if (t0 < 0.0 || d0 < 0.0) {
        // Intersection behind near plane or far plane (respectively)
        t = t1;
    } else {
        t = t0;
    }
    
    // This is the intersection point with the cone
    vec3 cone_intersection_point = ray_origin + t * ray_vector;
    // Now we project back through the origin to correct the distortion (and cancel out if the
    // eye is at the origin)
    return near_plane * cone_intersection_point.xy / cone_intersection_point.z;
}

// ============================================================================
// MAIN TRANCE SPIRAL RENDERING (from shaders.h lines 195-226)
// ============================================================================

void main(void) {
    // Calculate UV from gl_FragCoord (compositor handles window size via uResolution)
    vec2 screen_uv = gl_FragCoord.xy / uResolution;
    
    // Convert to centered coordinates [-1, 1] with aspect ratio
    vec2 aspect_position = (screen_uv * 2.0 - 1.0) * vec2(aspect_ratio, 1.0);
    
    // Apply cone intersection for 3D depth effect
    vec2 position = cone_intersection(aspect_position);
    
    float angle = 0.0;
    float radius = length(position);
    
    if (position.x != 0.0 && position.y != 0.0) {
        angle = degrees(atan(position.y, position.x));
    }
    
    // Select spiral function based on type
    float factor =
        spiral_type == 1.0 ? spiral1(radius) :
        spiral_type == 2.0 ? spiral2(radius) :
        spiral_type == 3.0 ? spiral3(radius) :
        spiral_type == 4.0 ? spiral4(radius) :
        spiral_type == 5.0 ? spiral5(radius) :
        spiral_type == 6.0 ? spiral6(radius) :
                             spiral7(radius);
    
    // Calculate spiral arm position
    // IMPORTANT: 'time' is the signed phase accumulated from RPM in the director.
    // We do NOT multiply by rotation_speed here to avoid rpm^2 scaling and to keep
    // direction strictly controlled by the sign of the phase increment.
    // angle - width * time = rotation animation with correct direction
    // - 2 * width * factor = spiral twist based on radius
    float amod = mod(angle - width * time - 2.0 * width * factor, width);
    
    // Determine if we're on a light or dark arm
    float v = amod < width / 2.0 ? 0.0 : 1.0;
    
    // Anti-aliasing smoothing at edges
    float t = 0.2 + 2.0 * (1.0 - pow(min(1.0, radius), 0.4));
    if (amod > width / 2.0 - t && amod < width / 2.0 + t) {
        v = (amod - width / 2.0 + t) / (2.0 * t);
    }
    if (amod < t) {
        v = 1.0 - (amod + t) / (2.0 * t);
    }
    if (amod > width - t) {
        v = 1.0 - (amod - width + t) / (2.0 * t);
    }
    
    // Blend colors and fade out at center
    vec4 finalColor = mix(
        (acolour + bcolour) / 2.0,
        mix(acolour, bcolour, v),
        clamp(radius * 1024.0 / (360.0 / width), 0.0, 1.0)
    );
    
    // Apply MesmerGlass enhancements (optional compatibility layer)
    
    // Apply flip wave effect if active (MesmerGlass feature)
    if (uFlipState == 1) {
        vec2 p = screen_uv * 2.0 - 1.0;
        p.x *= aspect_ratio;
        float r = length(p);

        float band = max(0.001, uFlipWaveWidth);
        float band_dist = abs(r - uFlipWaveRadius);
        float flipEffect = smoothstep(1.5 * band, 0.5 * band, band_dist);
        float arm_v = finalColor.a > 0.5 ? 1.0 : 0.0;
        arm_v = mix(arm_v, 1.0 - arm_v, flipEffect);

        finalColor = mix(
            (acolour + bcolour) / 2.0,
            mix(acolour, bcolour, arm_v),
            clamp(radius * 1024.0 / (360.0 / width), 0.0, 1.0)
        );
    }
    
    // Apply intensity scaling (MesmerGlass feature)
    float intensityFactor = clamp(uIntensity, 0.0, 1.0);
    finalColor.rgb = mix(vec3(0.5), finalColor.rgb, intensityFactor);
    
    // Apply contrast (MesmerGlass feature)
    finalColor.rgb = (finalColor.rgb - 0.5) * uContrast + 0.5;
    finalColor.rgb = clamp(finalColor.rgb, 0.0, 1.0);
    
    // Apply both spiral opacity (from custom mode) and window opacity (from UI slider)
    finalColor.a *= uSpiralOpacity * uWindowOpacity;
    
    // Safety clamp indicator
    if (uSafetyClamped == 1) {
        finalColor.r += 0.05;
    }
    
    // Output with proper alpha handling
    if (uTestOpaqueMode == 1) {
        FragColor = vec4(finalColor.rgb, 1.0);
    } else if (uInternalOpacity == 1) {
        vec3 blendedColor = mix(uBackgroundColor, finalColor.rgb, finalColor.a);
        FragColor = vec4(blendedColor, 1.0);
    } else {
        if (finalColor.a < 0.001) {
            FragColor = vec4(0.0, 0.0, 0.0, 0.0);
        } else {
            if (uTestLegacyBlend == 1) {
                FragColor = finalColor;
            } else {
                // Premultiplied alpha
                FragColor = vec4(finalColor.rgb * finalColor.a, finalColor.a);
            }
        }
    }
}
