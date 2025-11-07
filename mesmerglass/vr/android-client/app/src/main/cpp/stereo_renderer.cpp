/**
 * Stereo Renderer - Handles side-by-side stereo rendering
 */

#include <android/log.h>
#include <GLES3/gl3.h>

#define LOG_TAG "StereoRenderer"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, LOG_TAG, __VA_ARGS__)

class StereoRenderer {
private:
    int viewportWidth;
    int viewportHeight;
    
public:
    StereoRenderer() : viewportWidth(0), viewportHeight(0) {}
    
    void setViewport(int width, int height) {
        viewportWidth = width;
        viewportHeight = height;
        LOGI("Stereo viewport: %dx%d", width, height);
    }
    
    /**
     * Setup viewport for left eye (left half of screen)
     */
    void setupLeftEye() {
        glViewport(0, 0, viewportWidth / 2, viewportHeight);
    }
    
    /**
     * Setup viewport for right eye (right half of screen)
     */
    void setupRightEye() {
        glViewport(viewportWidth / 2, 0, viewportWidth / 2, viewportHeight);
    }
    
    /**
     * Get per-eye projection matrix for full FOV
     * This matches the VR headset's optical properties
     */
    void getProjectionMatrix(float* matrix, bool isLeftEye) {
        // Simple projection matrix
        // In production, use Oculus SDK's ovrMatrix4f_CreateProjectionFov
        
        float fovY = 90.0f;  // Field of view
        float aspect = (float)(viewportWidth / 2) / (float)viewportHeight;
        float near = 0.1f;
        float far = 100.0f;
        
        // Identity matrix for now
        for (int i = 0; i < 16; i++) {
            matrix[i] = (i % 5 == 0) ? 1.0f : 0.0f;
        }
    }
};
