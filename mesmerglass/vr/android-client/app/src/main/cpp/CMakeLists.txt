cmake_minimum_required(VERSION 3.22.1)

project("vrrenderer")

# OpenGL ES 3.0
find_library(GLES3_LIBRARY GLESv3)
find_library(EGL_LIBRARY EGL)
find_library(LOG_LIBRARY log)
find_library(ANDROID_LIBRARY android)

# Add source files
add_library(vrrenderer SHARED
    vr_renderer.cpp
    frame_decoder.cpp
    stereo_renderer.cpp
)

target_link_libraries(vrrenderer
    ${GLES3_LIBRARY}
    ${EGL_LIBRARY}
    ${LOG_LIBRARY}
    ${ANDROID_LIBRARY}
    jnigraphics
)

# Compiler flags
target_compile_options(vrrenderer PRIVATE
    -Wall
    -Wextra
    -std=c++14
)
