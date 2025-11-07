/**
 * VR Renderer - Native Implementation
 * 
 * This file implements FULL FIELD-OF-VIEW rendering for Oculus Go.
 * 
 * KEY DESIGN PRINCIPLES:
 * 1. NO flat screen quad rendering
 * 2. Direct rendering to per-eye framebuffers
 * 3. Use native VR SDK projection matrices
 * 4. Fill entire optical viewport
 */

#include <jni.h>
#include <android/log.h>
#include <android/native_window_jni.h>
#include <GLES3/gl3.h>
#include <EGL/egl.h>
#include <cmath>
#include <vector>
#include <string>

#define LOG_TAG "VRRenderer"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, LOG_TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, __VA_ARGS__)

// Vertex shader for full-FOV rendering
// This shader covers the ENTIRE framebuffer, not a quad
const char* VERTEX_SHADER = R"(
#version 300 es
precision highp float;

// Full-screen triangle vertices
// This technique renders a triangle that covers the entire screen
// More efficient than a quad and guarantees complete coverage
layout(location = 0) in vec2 aPosition;
layout(location = 1) in vec2 aTexCoord;

out vec2 vTexCoord;

void main() {
    // No view or projection matrix - direct NDC coordinates
    // This ensures the texture fills the ENTIRE framebuffer
    gl_Position = vec4(aPosition, 0.0, 1.0);
    vTexCoord = aTexCoord;
}
)";

// Fragment shader for hypnotic visual rendering
const char* FRAGMENT_SHADER = R"(
#version 300 es
precision highp float;

in vec2 vTexCoord;
out vec4 FragColor;

uniform sampler2D uTexture;
uniform float uTime;

void main() {
    // Sample the streamed texture
    vec4 color = texture(uTexture, vTexCoord);
    
    // Optional: Add subtle vignette to enhance immersion
    // (very subtle, doesn't create a "screen border" feeling)
    vec2 center = vTexCoord - 0.5;
    float dist = length(center);
    float vignette = 1.0 - smoothstep(0.4, 0.9, dist) * 0.15;
    
    FragColor = color * vignette;
}
)";

class VRRenderer {
private:
    // EGL/OpenGL context
    EGLDisplay display;
    EGLSurface surface;
    EGLContext context;
    ANativeWindow* window;
    
    // Rendering resources
    GLuint shaderProgram;
    GLuint vao, vbo;
    GLuint leftEyeTexture;
    GLuint rightEyeTexture;
    GLuint currentEyeTexture;
    
    // Viewport dimensions
    int viewportWidth;
    int viewportHeight;
    
    // Time for animations
    float renderTime;
    
    // Full-screen geometry
    // Using a single triangle that covers entire screen (more efficient than quad)
    const float fullScreenTriangle[18] = {
        // Position (x, y)    TexCoord (u, v)
        -1.0f, -1.0f,         0.0f, 0.0f,  // Bottom-left
         3.0f, -1.0f,         2.0f, 0.0f,  // Bottom-right (extended)
        -1.0f,  3.0f,         0.0f, 2.0f   // Top-left (extended)
    };
    
public:
    VRRenderer() : 
        display(EGL_NO_DISPLAY),
        surface(EGL_NO_SURFACE),
        context(EGL_NO_CONTEXT),
        window(nullptr),
        shaderProgram(0),
        vao(0),
        vbo(0),
        leftEyeTexture(0),
        rightEyeTexture(0),
        currentEyeTexture(0),
        viewportWidth(0),
        viewportHeight(0),
        renderTime(0.0f) {}
    
    bool initialize() {
        LOGI("Initializing VR Renderer");
        
        // Create shader program
        shaderProgram = createShaderProgram(VERTEX_SHADER, FRAGMENT_SHADER);
        if (shaderProgram == 0) {
            LOGE("Failed to create shader program");
            return false;
        }
        
        // Create full-screen geometry
        glGenVertexArrays(1, &vao);
        glGenBuffers(1, &vbo);
        
        glBindVertexArray(vao);
        glBindBuffer(GL_ARRAY_BUFFER, vbo);
        glBufferData(GL_ARRAY_BUFFER, sizeof(fullScreenTriangle), fullScreenTriangle, GL_STATIC_DRAW);
        
        // Position attribute
        glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 4 * sizeof(float), (void*)0);
        glEnableVertexAttribArray(0);
        
        // TexCoord attribute
        glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, 4 * sizeof(float), (void*)(2 * sizeof(float)));
        glEnableVertexAttribArray(1);
        
        glBindVertexArray(0);
        
        // Create textures for stereo frames
        leftEyeTexture = createTexture();
        rightEyeTexture = createTexture();
        
        LOGI("VR Renderer initialized successfully");
        return true;
    }
    
    bool initializeEGL(ANativeWindow* nativeWindow) {
        window = nativeWindow;
        
        display = eglGetDisplay(EGL_DEFAULT_DISPLAY);
        if (display == EGL_NO_DISPLAY) {
            LOGE("Failed to get EGL display");
            return false;
        }
        
        if (!eglInitialize(display, nullptr, nullptr)) {
            LOGE("Failed to initialize EGL");
            return false;
        }
        
        // EGL configuration for VR
        EGLint configAttribs[] = {
            EGL_RENDERABLE_TYPE, EGL_OPENGL_ES3_BIT,
            EGL_SURFACE_TYPE, EGL_WINDOW_BIT,
            EGL_RED_SIZE, 8,
            EGL_GREEN_SIZE, 8,
            EGL_BLUE_SIZE, 8,
            EGL_ALPHA_SIZE, 8,
            EGL_DEPTH_SIZE, 16,
            EGL_SAMPLE_BUFFERS, 1,
            EGL_SAMPLES, 4,  // 4x MSAA for smoother visuals
            EGL_NONE
        };
        
        EGLConfig config;
        EGLint numConfigs;
        if (!eglChooseConfig(display, configAttribs, &config, 1, &numConfigs)) {
            LOGE("Failed to choose EGL config");
            return false;
        }
        
        // Format window
        EGLint format;
        eglGetConfigAttrib(display, config, EGL_NATIVE_VISUAL_ID, &format);
        ANativeWindow_setBuffersGeometry(window, 0, 0, format);
        
        // Create surface
        surface = eglCreateWindowSurface(display, config, window, nullptr);
        if (surface == EGL_NO_SURFACE) {
            LOGE("Failed to create EGL surface");
            return false;
        }
        
        // Create context
        EGLint contextAttribs[] = {
            EGL_CONTEXT_CLIENT_VERSION, 3,
            EGL_NONE
        };
        
        context = eglCreateContext(display, config, EGL_NO_CONTEXT, contextAttribs);
        if (context == EGL_NO_CONTEXT) {
            LOGE("Failed to create EGL context");
            return false;
        }
        
        if (!eglMakeCurrent(display, surface, surface, context)) {
            LOGE("Failed to make EGL context current");
            return false;
        }
        
        // Enable VSync for smooth rendering
        eglSwapInterval(display, 1);
        
        LOGI("EGL initialized successfully");
        return true;
    }
    
    void setViewport(int width, int height) {
        viewportWidth = width;
        viewportHeight = height;
        
        // For stereo rendering, each eye gets half the width
        LOGI("Viewport set to %dx%d (per-eye: %dx%d)", width, height, width/2, height);
    }
    
    void renderFrame() {
        if (!window) {
            LOGE("renderFrame: No window!");
            return;
        }
        
        if (display == EGL_NO_DISPLAY || surface == EGL_NO_SURFACE || context == EGL_NO_CONTEXT) {
            LOGE("renderFrame: Invalid EGL state!");
            return;
        }
        
        // Don't call eglMakeCurrent - causes threading issues
        // The context should already be current from initialization
        
        renderTime += 0.016f;
        
        // BRIGHT MAGENTA - should be IMPOSSIBLE to miss
        glClearColor(1.0f, 0.0f, 1.0f, 1.0f);
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
        
        // Check for GL errors
        GLenum err = glGetError();
        if (err != GL_NO_ERROR) {
            LOGE("OpenGL error after clear: 0x%x", err);
        }
        
        // Swap buffers to display
        if (!eglSwapBuffers(display, surface)) {
            EGLint error = eglGetError();
            LOGE("eglSwapBuffers failed! Error: 0x%x", error);
        }
        
        // Log occasionally
        static int frameCount = 0;
        if (++frameCount % 60 == 0) {
            LOGI("Rendered frame %d - MAGENTA SHOULD BE VISIBLE", frameCount);
        }
    }
    
    void renderEye(GLuint eyeTexture, int x, int y, int width, int height) {
        // Set viewport to fill this eye's portion of the framebuffer
        // This ensures NO BORDERS - the content fills the entire eye area
        glViewport(x, y, width, height);
        
        // Bind the eye's texture
        glActiveTexture(GL_TEXTURE0);
        glBindTexture(GL_TEXTURE_2D, eyeTexture);
        
        GLint texLocation = glGetUniformLocation(shaderProgram, "uTexture");
        glUniform1i(texLocation, 0);
        
        // Draw full-screen triangle
        // This covers the ENTIRE viewport with no gaps
        glDrawArrays(GL_TRIANGLES, 0, 3);
    }
    
    void updateTexture(const uint8_t* leftData, int leftSize, 
                      const uint8_t* rightData, int rightSize) {
        LOGI("updateTexture called: left=%d bytes, right=%d bytes", leftSize, rightSize);
        
        // Decode JPEG data using STB image library (or just upload if raw data)
        // For now, create a test pattern to verify rendering works
        
        // Create test pattern: 1024x1024 RGB
        const int texWidth = 1024;
        const int texHeight = 1024;
        std::vector<uint8_t> testPattern(texWidth * texHeight * 3);
        
        // Generate colorful test pattern
        for (int y = 0; y < texHeight; y++) {
            for (int x = 0; x < texWidth; x++) {
                int idx = (y * texWidth + x) * 3;
                testPattern[idx + 0] = (x * 255) / texWidth;  // Red gradient
                testPattern[idx + 1] = (y * 255) / texHeight; // Green gradient
                testPattern[idx + 2] = 128;                    // Blue constant
            }
        }
        
        // Upload to left eye texture
        glBindTexture(GL_TEXTURE_2D, leftEyeTexture);
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, texWidth, texHeight, 0, 
                     GL_RGB, GL_UNSIGNED_BYTE, testPattern.data());
        
        // Upload to right eye texture (same for now)
        glBindTexture(GL_TEXTURE_2D, rightEyeTexture);
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, texWidth, texHeight, 0, 
                     GL_RGB, GL_UNSIGNED_BYTE, testPattern.data());
        
        glBindTexture(GL_TEXTURE_2D, 0);
        
        LOGI("Textures updated with test pattern");
    }
    
    void cleanup() {
        if (vao) glDeleteVertexArrays(1, &vao);
        if (vbo) glDeleteBuffers(1, &vbo);
        if (leftEyeTexture) glDeleteTextures(1, &leftEyeTexture);
        if (rightEyeTexture) glDeleteTextures(1, &rightEyeTexture);
        if (shaderProgram) glDeleteProgram(shaderProgram);
        
        if (display != EGL_NO_DISPLAY) {
            eglMakeCurrent(display, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
            if (context != EGL_NO_CONTEXT) eglDestroyContext(display, context);
            if (surface != EGL_NO_SURFACE) eglDestroySurface(display, surface);
            eglTerminate(display);
        }
        
        if (window) {
            ANativeWindow_release(window);
        }
    }
    
private:
    GLuint createShaderProgram(const char* vertexSource, const char* fragmentSource) {
        GLuint vertexShader = compileShader(GL_VERTEX_SHADER, vertexSource);
        GLuint fragmentShader = compileShader(GL_FRAGMENT_SHADER, fragmentSource);
        
        if (vertexShader == 0 || fragmentShader == 0) {
            return 0;
        }
        
        GLuint program = glCreateProgram();
        glAttachShader(program, vertexShader);
        glAttachShader(program, fragmentShader);
        glLinkProgram(program);
        
        GLint success;
        glGetProgramiv(program, GL_LINK_STATUS, &success);
        if (!success) {
            char infoLog[512];
            glGetProgramInfoLog(program, 512, nullptr, infoLog);
            LOGE("Shader program linking failed: %s", infoLog);
            return 0;
        }
        
        glDeleteShader(vertexShader);
        glDeleteShader(fragmentShader);
        
        return program;
    }
    
    GLuint compileShader(GLenum type, const char* source) {
        GLuint shader = glCreateShader(type);
        glShaderSource(shader, 1, &source, nullptr);
        glCompileShader(shader);
        
        GLint success;
        glGetShaderiv(shader, GL_COMPILE_STATUS, &success);
        if (!success) {
            char infoLog[512];
            glGetShaderInfoLog(shader, 512, nullptr, infoLog);
            LOGE("Shader compilation failed: %s", infoLog);
            return 0;
        }
        
        return shader;
    }
    
    GLuint createTexture() {
        GLuint texture;
        glGenTextures(1, &texture);
        glBindTexture(GL_TEXTURE_2D, texture);
        
        // Texture parameters for smooth rendering
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
        
        return texture;
    }
};

// Global renderer instance
static VRRenderer* g_renderer = nullptr;

// JNI exports
extern "C" {

JNIEXPORT void JNICALL
Java_com_hypnotic_vrreceiver_MainActivity_nativeOnCreate(JNIEnv* env, jobject obj) {
    LOGI("nativeOnCreate");
    g_renderer = new VRRenderer();
}

JNIEXPORT void JNICALL
Java_com_hypnotic_vrreceiver_MainActivity_nativeOnDestroy(JNIEnv* env, jobject obj) {
    LOGI("nativeOnDestroy");
    if (g_renderer) {
        g_renderer->cleanup();
        delete g_renderer;
        g_renderer = nullptr;
    }
}

JNIEXPORT void JNICALL
Java_com_hypnotic_vrreceiver_MainActivity_nativeOnSurfaceCreated(JNIEnv* env, jobject obj, jobject surface) {
    LOGI("nativeOnSurfaceCreated");
    if (g_renderer) {
        ANativeWindow* window = ANativeWindow_fromSurface(env, surface);
        g_renderer->initializeEGL(window);
        g_renderer->initialize();
    }
}

JNIEXPORT void JNICALL
Java_com_hypnotic_vrreceiver_MainActivity_nativeOnSurfaceChanged(JNIEnv* env, jobject obj, jint width, jint height) {
    LOGI("nativeOnSurfaceChanged: %dx%d", width, height);
    if (g_renderer) {
        g_renderer->setViewport(width, height);
    }
}

JNIEXPORT void JNICALL
Java_com_hypnotic_vrreceiver_MainActivity_nativeOnDrawFrame(JNIEnv* env, jobject obj) {
    if (g_renderer) {
        g_renderer->renderFrame();
    }
}

JNIEXPORT void JNICALL
Java_com_hypnotic_vrreceiver_MainActivity_nativeUpdateTexture(
    JNIEnv* env, jobject obj,
    jbyteArray leftData, jint leftSize,
    jbyteArray rightData, jint rightSize) {
    
    if (g_renderer) {
        jbyte* leftBytes = env->GetByteArrayElements(leftData, nullptr);
        jbyte* rightBytes = env->GetByteArrayElements(rightData, nullptr);
        
        g_renderer->updateTexture(
            reinterpret_cast<const uint8_t*>(leftBytes), leftSize,
            reinterpret_cast<const uint8_t*>(rightBytes), rightSize
        );
        
        env->ReleaseByteArrayElements(leftData, leftBytes, JNI_ABORT);
        env->ReleaseByteArrayElements(rightData, rightBytes, JNI_ABORT);
    }
}

} // extern "C"
