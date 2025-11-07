# OpenXR binding fallbacks (Windows, OpenGL)

This note documents the compatibility fallbacks used by the VR bridge when Python OpenXR bindings differ in API shape.

- Function resolution: First, we try instance/module methods. If unavailable, we resolve function pointers via `xrGetInstanceProcAddr` and cast them to the expected PFN types.
- Handle coercion: Some bindings wrap `XrSession`/`XrSwapchain` in Python classes. We coerce these to raw handles using `_as_xr_handle` which tries common attributes (`handle`, `value`, `ptr`, `c_void_p`) and `int(obj)`.
- Swapchain formats: If method and module variants are missing, we call `xrEnumerateSwapchainFormats` via function pointer. The array is a ctypes `c_int64 * n` as per the spec.
- Swapchain images (OpenGL): For `xrEnumerateSwapchainImages`, we allocate an array of `SwapchainImageOpenGLKHR`, set their `sType`/`pNext`, and pass a pointer cast to `SwapchainImageBaseHeader*`. We then extract `image` (GLuint) values for blitting.

Diagnostics:
- If image enumeration returns 0, we log the presence of `SwapchainImageOpenGLKHR` and `SwapchainImageBaseHeader` to guide further tuning for the installed binding.
- Use `MESMERGLASS_VR_DEBUG_SOLID=1` to force a solid green clear into swapchain images to validate visibility regardless of source FBO path.

These fallbacks are designed to be safe: if a step isn't supported by the current binding, the code simply returns an empty list and continues in mock/no-op mode rather than crashing.
