package com.hypnotic.vrreceiver

import android.Manifest
import android.app.Activity
import android.app.UiModeManager
import android.content.pm.PackageManager
import android.content.res.Configuration
import android.graphics.BitmapFactory
import android.graphics.Color
import android.graphics.SurfaceTexture
import android.media.MediaCodec
import android.media.MediaFormat
import android.opengl.GLES11Ext
import android.opengl.GLSurfaceView
import android.opengl.GLUtils
import android.opengl.Matrix
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.view.Surface
import android.view.View
import android.view.WindowManager
import android.util.Log
import android.widget.Toast
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import kotlinx.coroutines.*
import java.io.DataInputStream
import java.io.OutputStream
import java.net.Socket
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.FloatBuffer
import javax.microedition.khronos.egl.EGLConfig
import javax.microedition.khronos.opengles.GL10
import android.opengl.GLES30

/**
 * Main Activity for VR Hypnotic Visual Receiver
 * 
 * Supports dual-protocol streaming:
 * - VRHP (JPEG): CPU software decoding via BitmapFactory
 * - VRH2 (H.264): GPU hardware decoding via MediaCodec
 */
class MainActivity : Activity(), GLSurfaceView.Renderer {
    
    private lateinit var glSurfaceView: GLSurfaceView
    private var networkReceiver: NetworkReceiver? = null
    private var discoveryService: DiscoveryService? = null
    private var statusColor = Color.BLUE
    private var isStreaming = false
    @Volatile private var isConnecting = false
    
    // Clear color (changes based on status)
    private var clearR = 0.0f
    private var clearG = 0.0f
    private var clearB = 1.0f // Start with blue
    
    // OpenGL resources
    private var textureId = 0
    private var leftEyeTextureId = 0
    private var rightEyeTextureId = 0
    private var shaderProgram = 0
    private var shaderProgramExternal = 0
    private var vertexBuffer: FloatBuffer? = null
    private var hasFrame = false

    // Surface size (updated in onSurfaceChanged)
    @Volatile private var surfaceWidth: Int = 0
    @Volatile private var surfaceHeight: Int = 0

    @Volatile private var lastSurfaceToastAtMs: Long = 0
    
    // Shader attribute/uniform locations
    private var positionHandle = 0
    private var texCoordHandle = 0
    private var textureHandle = 0
    private var texMatrixHandle = 0

    private var positionHandleExternal = 0
    private var texCoordHandleExternal = 0
    private var textureHandleExternal = 0
    private var texMatrixHandleExternal = 0

    // SurfaceTexture provides a transform matrix that must be applied to UVs for correct sampling.
    private val identityTexMatrix: FloatArray = FloatArray(16)
    private val flipYTexMatrix: FloatArray = FloatArray(16)
    private val leftTexMatrix: FloatArray = FloatArray(16)
    private val rightTexMatrix: FloatArray = FloatArray(16)
    private val leftTexMatrixFinal: FloatArray = FloatArray(16)
    private val rightTexMatrixFinal: FloatArray = FloatArray(16)

    // H.264 output (SurfaceTexture -> OES texture)
    private var leftEyeOesTextureId = 0
    private var rightEyeOesTextureId = 0
    private var leftSurfaceTexture: SurfaceTexture? = null
    private var rightSurfaceTexture: SurfaceTexture? = null
    @Volatile private var leftH264FrameAvailable = false
    @Volatile private var rightH264FrameAvailable = false
    @Volatile private var lastPacketWasMono = false

    private val decoderLock = Any()
    private var h264Configured = false
    private var h264LastSps: ByteArray? = null
    private var h264LastPps: ByteArray? = null

    // VRH2 smoothing: small jitter buffer + steady decode loop.
    private val h264QueueLock = Any()
    private val h264FrameQueue: ArrayDeque<H264StereoFrame> = ArrayDeque()
    @Volatile private var h264DecodeJob: Job? = null
    // NOTE: We avoid deferred flushes in the decode loop because flushing after queueing an IDR
    // can discard it and leave the decoder stuck (black screen). Flush is done synchronously
    // when we are about to queue a known IDR.
    @Volatile private var h264ShouldFlushDecoders: Boolean = false
    @Volatile private var h264NeedKeyframeResync: Boolean = false

    // Receiver-driven keyframe request (server control channel, optional).
    @Volatile private var lastNeedIdrSentAtMs: Long = 0
    private val needIdrMinIntervalMs: Long = 750

    // Tuning knobs: prioritize smoothness (adds a small, stable delay).
    private val h264TargetFps: Int = 60
    private val h264MinStartFrames: Int = 6
    // Latency is not critical; use a deeper queue to absorb bursty TCP delivery.
    private val h264QueueMaxFrames: Int = 120
    private val h264QueueHighWater: Int = 96

    private data class H264StereoFrame(
        val frameId: Int,
        val left: ByteArray,
        val right: ByteArray,
        val mono: Boolean,
        val keyframe: Boolean
    )
    
    // Frame data
    private var leftFrameData: ByteArray? = null
    private var rightFrameData: ByteArray? = null
    private val frameLock = Any()

    // Smoothness: render at a steady cadence, upload only on new frames.
    @Volatile private var receivedFrameVersion: Int = 0
    private var uploadedFrameVersion: Int = -1
    
    // Protocol detection
    private var streamProtocol: StreamProtocol = StreamProtocol.UNKNOWN

    // Dynamic video aspect ratio (updated as frames arrive)
    @Volatile private var videoAspectRatio: Float = 16.0f / 9.0f

    private enum class DisplayLayout {
        AUTO,
        VR_STEREO,
        FULLSCREEN
    }

    private var displayLayout: DisplayLayout = DisplayLayout.AUTO
    @Volatile private var resolvedDisplayLayout: DisplayLayout = DisplayLayout.FULLSCREEN
    
    // H.264 MediaCodec decoders (hardware accelerated)
    private var leftDecoder: MediaCodec? = null
    private var rightDecoder: MediaCodec? = null
    private var leftDecoderSurface: Surface? = null
    private var rightDecoderSurface: Surface? = null
    
    // Performance tracking
    private var framesReceived = 0
    private var bytesReceived: Long = 0
    private var lastStatsTime = System.currentTimeMillis()
    private var decodeStartTime: Long = 0
    private var decodeTimes = mutableListOf<Long>()
    private var renderTimes = mutableListOf<Long>()

    // Stream stats (Logcat-friendly; useful for wireless debugging)
    private val statsLock = Any()
    private var h264EnqueuedTotal: Long = 0
    private var h264DequeuedTotal: Long = 0
    private var h264DroppedTotal: Long = 0
    private var h264FlushTotal: Long = 0
    private var h264CodecInputStarveTotal: Long = 0
    private var h264FrameIdGapsTotal: Long = 0
    private var h264BadAccessUnitsTotal: Long = 0
    private var h264ResyncTotal: Long = 0
    private var lastRxFrameId: Int? = null
    private var lastRxTimeNs: Long = 0
    private var rxInterarrivalSumMs: Double = 0.0
    private var rxInterarrivalMaxMs: Double = 0.0
    private var rxInterarrivalCount: Int = 0

    private var lastLogH264Enqueued: Long = 0
    private var lastLogH264Dequeued: Long = 0
    private var lastLogH264Dropped: Long = 0
    private var lastLogH264Flush: Long = 0
    private var lastLogH264CodecStarve: Long = 0
    private var lastLogH264Gaps: Long = 0
    private var lastLogH264BadAccessUnits: Long = 0
    private var lastLogH264Resync: Long = 0
    
    enum class StreamProtocol {
        UNKNOWN,
        VRHP,  // JPEG encoding
        VRH2   // H.264 encoding
    }
    
    companion object {
        private const val TAG = "VRReceiver"
        private const val ENABLE_STREAM_STATS_LOG = true
        private const val PERMISSION_REQUEST_CODE = 1
        private const val DISCOVERY_PORT = 5556  // UDP: Client sends hello, server listens
        private const val DEFAULT_STREAMING_PORT = 5555  // TCP: Video streaming
        
        // Vertex shader - simple passthrough
        private const val VERTEX_SHADER = """
            attribute vec4 aPosition;
            attribute vec2 aTexCoord;
            varying vec2 vTexCoord;
            uniform mat4 uTexMatrix;
            
            void main() {
                gl_Position = aPosition;
                vec4 tc = uTexMatrix * vec4(aTexCoord, 0.0, 1.0);
                vTexCoord = tc.xy;
            }
        """
        
        // Fragment shader - sample texture
        private const val FRAGMENT_SHADER = """
            precision mediump float;
            varying vec2 vTexCoord;
            uniform sampler2D uTexture;
            
            void main() {
                gl_FragColor = texture2D(uTexture, vTexCoord);
            }
        """

        // Fragment shader for external (SurfaceTexture) video frames
        private const val FRAGMENT_SHADER_EXTERNAL = """
            #extension GL_OES_EGL_image_external : require
            precision mediump float;
            varying vec2 vTexCoord;
            uniform samplerExternalOES uTexture;

            void main() {
                gl_FragColor = texture2D(uTexture, vTexCoord);
            }
        """

        private const val H264_WIDTH = 2048
        private const val H264_HEIGHT = 1024
    }
    
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        
        // Keep screen on
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        // True fullscreen (important on Android/Google TV where system UI insets can reduce content area)
        hideSystemUi()
        
        // Request permissions
        if (!checkPermissions()) {
            requestPermissions()
        }
        
        // Setup GLSurfaceView - handles threading properly!
        glSurfaceView = GLSurfaceView(this)
        glSurfaceView.layoutParams = android.view.ViewGroup.LayoutParams(
            android.view.ViewGroup.LayoutParams.MATCH_PARENT,
            android.view.ViewGroup.LayoutParams.MATCH_PARENT
        )
        glSurfaceView.setEGLContextClientVersion(3) // OpenGL ES 3.0
        glSurfaceView.setRenderer(this)
        // Render continuously for smooth display. We only decode/upload when a new frame arrives.
        glSurfaceView.renderMode = GLSurfaceView.RENDERMODE_CONTINUOUSLY
        setContentView(glSurfaceView)

        resolvedDisplayLayout = resolveDisplayLayout()
        
        // Start automatic server discovery
        startAutoDiscovery()
    }

    private fun hideSystemUi() {
        try {
            window.addFlags(WindowManager.LayoutParams.FLAG_FULLSCREEN)

            if (Build.VERSION.SDK_INT >= 30) {
                window.setDecorFitsSystemWindows(false)
                window.insetsController?.hide(android.view.WindowInsets.Type.statusBars() or android.view.WindowInsets.Type.navigationBars())
                window.insetsController?.systemBarsBehavior = android.view.WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            } else {
                @Suppress("DEPRECATION")
                window.decorView.systemUiVisibility = (
                    View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                        or View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                        or View.SYSTEM_UI_FLAG_FULLSCREEN
                        or View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                        or View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                        or View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                    )
            }
        } catch (_: Exception) {
            // Best-effort; some devices/launchers may ignore.
        }
    }
    
    // GLSurfaceView.Renderer methods
    override fun onSurfaceCreated(gl: GL10?, config: EGLConfig?) {
        // Called when surface is created - on GL thread
        GLES30.glClearColor(clearR, clearG, clearB, 1.0f)

        // Initialize UV matrices
        Matrix.setIdentityM(identityTexMatrix, 0)
        // The app's vertex data uses a vertically flipped (bitmap-friendly) UV convention.
        // SurfaceTexture's transform matrix expects the standard convention, so we pre-flip.
        Matrix.setIdentityM(flipYTexMatrix, 0)
        Matrix.translateM(flipYTexMatrix, 0, 0f, 1f, 0f)
        Matrix.scaleM(flipYTexMatrix, 0, 1f, -1f, 1f)

        Matrix.setIdentityM(leftTexMatrix, 0)
        Matrix.setIdentityM(rightTexMatrix, 0)
        Matrix.setIdentityM(leftTexMatrixFinal, 0)
        Matrix.setIdentityM(rightTexMatrixFinal, 0)
        
        // Compile shaders (2D)
        val vertexShader = loadShader(GLES30.GL_VERTEX_SHADER, VERTEX_SHADER)
        val fragmentShader = loadShader(GLES30.GL_FRAGMENT_SHADER, FRAGMENT_SHADER)
        
        // Create program
        shaderProgram = GLES30.glCreateProgram()
        GLES30.glAttachShader(shaderProgram, vertexShader)
        GLES30.glAttachShader(shaderProgram, fragmentShader)
        GLES30.glLinkProgram(shaderProgram)
        
        // Get attribute/uniform locations
        positionHandle = GLES30.glGetAttribLocation(shaderProgram, "aPosition")
        texCoordHandle = GLES30.glGetAttribLocation(shaderProgram, "aTexCoord")
        textureHandle = GLES30.glGetUniformLocation(shaderProgram, "uTexture")
        texMatrixHandle = GLES30.glGetUniformLocation(shaderProgram, "uTexMatrix")

        // Compile shaders (external)
        val fragmentShaderExternal = loadShader(GLES30.GL_FRAGMENT_SHADER, FRAGMENT_SHADER_EXTERNAL)
        shaderProgramExternal = GLES30.glCreateProgram()
        GLES30.glAttachShader(shaderProgramExternal, vertexShader)
        GLES30.glAttachShader(shaderProgramExternal, fragmentShaderExternal)
        GLES30.glLinkProgram(shaderProgramExternal)

        positionHandleExternal = GLES30.glGetAttribLocation(shaderProgramExternal, "aPosition")
        texCoordHandleExternal = GLES30.glGetAttribLocation(shaderProgramExternal, "aTexCoord")
        textureHandleExternal = GLES30.glGetUniformLocation(shaderProgramExternal, "uTexture")
        texMatrixHandleExternal = GLES30.glGetUniformLocation(shaderProgramExternal, "uTexMatrix")
        
        // Create textures
        val textures = IntArray(2)
        GLES30.glGenTextures(2, textures, 0)
        leftEyeTextureId = textures[0]
        rightEyeTextureId = textures[1]
        
        // Setup textures
        for (texId in textures) {
            GLES30.glBindTexture(GLES30.GL_TEXTURE_2D, texId)
            GLES30.glTexParameteri(GLES30.GL_TEXTURE_2D, GLES30.GL_TEXTURE_MIN_FILTER, GLES30.GL_LINEAR)
            GLES30.glTexParameteri(GLES30.GL_TEXTURE_2D, GLES30.GL_TEXTURE_MAG_FILTER, GLES30.GL_LINEAR)
            GLES30.glTexParameteri(GLES30.GL_TEXTURE_2D, GLES30.GL_TEXTURE_WRAP_S, GLES30.GL_CLAMP_TO_EDGE)
            GLES30.glTexParameteri(GLES30.GL_TEXTURE_2D, GLES30.GL_TEXTURE_WRAP_T, GLES30.GL_CLAMP_TO_EDGE)
        }

        // Create external OES textures + SurfaceTextures for H.264 decoding
        leftEyeOesTextureId = createExternalOesTexture()
        rightEyeOesTextureId = createExternalOesTexture()

        val frameCallbackHandler = Handler(Looper.getMainLooper())

        leftSurfaceTexture = SurfaceTexture(leftEyeOesTextureId).apply {
            setOnFrameAvailableListener({
                leftH264FrameAvailable = true
            }, frameCallbackHandler)
        }
        rightSurfaceTexture = SurfaceTexture(rightEyeOesTextureId).apply {
            setOnFrameAvailableListener({
                rightH264FrameAvailable = true
            }, frameCallbackHandler)
        }

        leftDecoderSurface = Surface(leftSurfaceTexture)
        rightDecoderSurface = Surface(rightSurfaceTexture)
        
        // Create vertex buffer for full-screen quad
        val vertices = floatArrayOf(
            // Positions    Texture coords
            -1f, -1f,      0f, 1f,  // Bottom-left
             1f, -1f,      1f, 1f,  // Bottom-right
            -1f,  1f,      0f, 0f,  // Top-left
             1f,  1f,      1f, 0f   // Top-right
        )
        
        vertexBuffer = ByteBuffer.allocateDirect(vertices.size * 4)
            .order(ByteOrder.nativeOrder())
            .asFloatBuffer()
            .put(vertices)
        vertexBuffer?.position(0)
    }
    
    private fun loadShader(type: Int, shaderCode: String): Int {
        val shader = GLES30.glCreateShader(type)
        GLES30.glShaderSource(shader, shaderCode)
        GLES30.glCompileShader(shader)
        return shader
    }
    
    override fun onSurfaceChanged(gl: GL10?, width: Int, height: Int) {
        // Called when surface size changes - on GL thread
        surfaceWidth = width
        surfaceHeight = height
        GLES30.glViewport(0, 0, width, height)

        // Diagnostics for Android TV "2/3 screen" issues: show the surface size vs window bounds.
        // If the surface itself is smaller than the window/display, the TV/launcher is running us in
        // compatibility/overscan mode and GL scaling can't fix it.
        val now = System.currentTimeMillis()
        if (now - lastSurfaceToastAtMs > 4000) {
            lastSurfaceToastAtMs = now
            runOnUiThread {
                try {
                    val windowW: Int
                    val windowH: Int
                    if (Build.VERSION.SDK_INT >= 30) {
                        val bounds = windowManager.currentWindowMetrics.bounds
                        windowW = bounds.width()
                        windowH = bounds.height()
                    } else {
                        @Suppress("DEPRECATION")
                        val display = windowManager.defaultDisplay
                        val size = android.graphics.Point()
                        @Suppress("DEPRECATION")
                        display.getSize(size)
                        windowW = size.x
                        windowH = size.y
                    }

                    Toast.makeText(
                        this,
                        "Surface ${width}x${height} | Window ${windowW}x${windowH}",
                        Toast.LENGTH_LONG
                    ).show()
                } catch (_: Exception) {
                }
            }
        }

        // Surface size changes can happen during display/orientation switches.
        resolvedDisplayLayout = resolveDisplayLayout()
    }
    
    override fun onDrawFrame(gl: GL10?) {
        // Called every frame - on GL thread
        val renderStart = System.currentTimeMillis()

        // Always render into the full surface. Some devices/paths can leave a smaller viewport active.
        val sw = surfaceWidth
        val sh = surfaceHeight
        if (sw > 0 && sh > 0) {
            GLES30.glViewport(0, 0, sw, sh)
        }
        
        // ALWAYS use black background when streaming (for letterbox bars)
        // Only use status color when NOT streaming
        if (isStreaming && hasFrame) {
            GLES30.glClearColor(0.0f, 0.0f, 0.0f, 1.0f)  // Black bars during streaming
        } else {
            GLES30.glClearColor(clearR, clearG, clearB, 1.0f)  // Status color when not streaming
        }
        GLES30.glClear(GLES30.GL_COLOR_BUFFER_BIT or GLES30.GL_DEPTH_BUFFER_BIT)
        
        val layout = resolvedDisplayLayout

        if (streamProtocol == StreamProtocol.VRH2 && h264Configured) {
            // Update external textures.
            // Some devices/drivers are flaky about OnFrameAvailable delivery; updating every frame is robust
            // and prevents getting stuck on a stale first frame.
            try {
                leftSurfaceTexture?.updateTexImage()
                leftSurfaceTexture?.getTransformMatrix(leftTexMatrix)
                Matrix.multiplyMM(leftTexMatrixFinal, 0, leftTexMatrix, 0, flipYTexMatrix, 0)
            } catch (_: Exception) {
                // ignore transient surface texture issues
            } finally {
                leftH264FrameAvailable = false
            }

            if (!lastPacketWasMono) {
                try {
                    rightSurfaceTexture?.updateTexImage()
                    rightSurfaceTexture?.getTransformMatrix(rightTexMatrix)
                    Matrix.multiplyMM(rightTexMatrixFinal, 0, rightTexMatrix, 0, flipYTexMatrix, 0)
                } catch (_: Exception) {
                    // ignore transient surface texture issues
                } finally {
                    rightH264FrameAvailable = false
                }
            } else {
                // Mono stream: reuse left matrix for the right eye.
                System.arraycopy(leftTexMatrix, 0, rightTexMatrix, 0, 16)
                System.arraycopy(leftTexMatrixFinal, 0, rightTexMatrixFinal, 0, 16)
                rightH264FrameAvailable = false
            }

            // Draw latest decoded frames
            when (layout) {
                DisplayLayout.VR_STEREO -> renderStereoExternal(lastPacketWasMono)
                DisplayLayout.FULLSCREEN -> renderFullscreenExternal(leftEyeOesTextureId)
                DisplayLayout.AUTO -> renderFullscreenExternal(leftEyeOesTextureId)
            }
        } else {
            // VRHP (JPEG) path
            val shouldUpload = (hasFrame && receivedFrameVersion != uploadedFrameVersion)
            if (shouldUpload) {
                synchronized(frameLock) {
                    if (hasFrame && leftFrameData != null && rightFrameData != null && receivedFrameVersion != uploadedFrameVersion) {
                        val decodeStart = System.currentTimeMillis()

                        val leftBitmap = BitmapFactory.decodeByteArray(leftFrameData, 0, leftFrameData!!.size)
                        if (leftBitmap != null) {
                            videoAspectRatio = leftBitmap.width.toFloat() / leftBitmap.height.toFloat()
                            GLES30.glBindTexture(GLES30.GL_TEXTURE_2D, leftEyeTextureId)
                            GLUtils.texImage2D(GLES30.GL_TEXTURE_2D, 0, leftBitmap, 0)
                            leftBitmap.recycle()
                        }

                        if (layout == DisplayLayout.VR_STEREO) {
                            val rightBitmap = BitmapFactory.decodeByteArray(rightFrameData, 0, rightFrameData!!.size)
                            if (rightBitmap != null) {
                                GLES30.glBindTexture(GLES30.GL_TEXTURE_2D, rightEyeTextureId)
                                GLUtils.texImage2D(GLES30.GL_TEXTURE_2D, 0, rightBitmap, 0)
                                rightBitmap.recycle()
                            }
                        }

                        uploadedFrameVersion = receivedFrameVersion

                        val decodeTime = System.currentTimeMillis() - decodeStart
                        decodeTimes.add(decodeTime)
                    }
                }
            }

            if (hasFrame) {
                when (layout) {
                    DisplayLayout.VR_STEREO -> renderStereo()
                    DisplayLayout.FULLSCREEN -> renderFullscreen(leftEyeTextureId)
                    DisplayLayout.AUTO -> renderFullscreen(leftEyeTextureId)
                }
            }
        }
        
        // Track render time and update performance stats
        val renderTime = System.currentTimeMillis() - renderStart
        renderTimes.add(renderTime)
        framesReceived++
        
        // Log performance stats every 60 frames
        if (framesReceived % 60 == 0) {
            val currentTime = System.currentTimeMillis()
            val statsWindow = (currentTime - lastStatsTime) / 1000.0  // seconds
            
            // Calculate FPS
            val clientFPS = if (statsWindow > 0) 60 / statsWindow else 0.0
            
            // Calculate average decode and render times
            val recentDecodes = decodeTimes.takeLast(60)
            val recentRenders = renderTimes.takeLast(60)
            val avgDecode = if (recentDecodes.isNotEmpty()) recentDecodes.average() else 0.0
            val avgRender = if (recentRenders.isNotEmpty()) recentRenders.average() else 0.0
            val totalLatency = avgDecode + avgRender
            
            // Calculate bandwidth
            val bandwidthMbps = if (statsWindow > 0) (bytesReceived * 8) / (statsWindow * 1_000_000) else 0.0

            if (ENABLE_STREAM_STATS_LOG) {
                val qDepth = synchronized(h264QueueLock) { h264FrameQueue.size }

                var enqTotal: Long
                var deqTotal: Long
                var drpTotal: Long
                var flsTotal: Long
                var stvTotal: Long
                var gapTotal: Long
                var rxAvgMs: Double
                var rxMaxMs: Double
                var rxN: Int

                synchronized(statsLock) {
                    enqTotal = h264EnqueuedTotal
                    deqTotal = h264DequeuedTotal
                    drpTotal = h264DroppedTotal
                    flsTotal = h264FlushTotal
                    stvTotal = h264CodecInputStarveTotal
                    gapTotal = h264FrameIdGapsTotal

                    rxAvgMs = if (rxInterarrivalCount > 0) (rxInterarrivalSumMs / rxInterarrivalCount.toDouble()) else 0.0
                    rxMaxMs = rxInterarrivalMaxMs
                    rxN = rxInterarrivalCount

                    // Reset rx window stats
                    rxInterarrivalSumMs = 0.0
                    rxInterarrivalMaxMs = 0.0
                    rxInterarrivalCount = 0
                }

                val dEnq = enqTotal - lastLogH264Enqueued
                val dDeq = deqTotal - lastLogH264Dequeued
                val dDrp = drpTotal - lastLogH264Dropped
                val dFls = flsTotal - lastLogH264Flush
                val dStv = stvTotal - lastLogH264CodecStarve
                val dGap = gapTotal - lastLogH264Gaps

                val badTotal: Long
                val resyncTotal: Long
                synchronized(statsLock) {
                    badTotal = h264BadAccessUnitsTotal
                    resyncTotal = h264ResyncTotal
                }
                val dBad = badTotal - lastLogH264BadAccessUnits
                val dRsn = resyncTotal - lastLogH264Resync

                lastLogH264Enqueued = enqTotal
                lastLogH264Dequeued = deqTotal
                lastLogH264Dropped = drpTotal
                lastLogH264Flush = flsTotal
                lastLogH264CodecStarve = stvTotal
                lastLogH264Gaps = gapTotal
                lastLogH264BadAccessUnits = badTotal
                lastLogH264Resync = resyncTotal

                Log.i(TAG, "Client stats f=$framesReceived fps=${String.format("%.1f", clientFPS)} bw=${String.format("%.2f", bandwidthMbps)}Mbps decode=${String.format("%.1f", avgDecode)}ms render=${String.format("%.1f", avgRender)}ms q=$qDepth")
                Log.i(TAG, "H264 window: enq=$dEnq deq=$dDeq drop=$dDrp flush=$dFls codecStarve=$dStv gaps=$dGap badAU=$dBad resync=$dRsn rxJitterAvg=${String.format("%.1f", rxAvgMs)}ms rxJitterMax=${String.format("%.1f", rxMaxMs)}ms n=$rxN")
            }
            
            // Reset stats window
            lastStatsTime = currentTime
            bytesReceived = 0
            
            // Keep only last 120 measurements to avoid memory growth
            if (decodeTimes.size > 120) {
                decodeTimes.subList(0, decodeTimes.size - 120).clear()
            }
            if (renderTimes.size > 120) {
                renderTimes.subList(0, renderTimes.size - 120).clear()
            }
        }
    }
    
    private fun renderStereo() {
        // Use shader program
        GLES30.glUseProgram(shaderProgram)
        
        // Enable vertex attributes
        GLES30.glEnableVertexAttribArray(positionHandle)
        GLES30.glEnableVertexAttribArray(texCoordHandle)
        
        // Bind texture uniform
        GLES30.glActiveTexture(GLES30.GL_TEXTURE0)
        GLES30.glUniform1i(textureHandle, 0)

        // 2D textures use identity UV transform.
        if (texMatrixHandle >= 0) {
            GLES30.glUniformMatrix4fv(texMatrixHandle, 1, false, identityTexMatrix, 0)
        }
        
        // Get viewport dimensions
        val viewport = IntArray(4)
        GLES30.glGetIntegerv(GLES30.GL_VIEWPORT, viewport, 0)
        val width = viewport[2]
        val height = viewport[3]
        
        val videoAspect = videoAspectRatio
        
        // Each eye gets half the screen width, so calculate per-eye aspect
        val eyeWidth = width / 2.0f
        val eyeAspect = eyeWidth / height.toFloat()
        
        // Calculate scale to maintain video's 16:9 aspect in the eye viewport
        val scaleX: Float
        val scaleY: Float
        
        if (eyeAspect > videoAspect) {
            // Eye viewport is wider than video - fit to height, letterbox sides
            scaleY = 1.0f
            scaleX = videoAspect / eyeAspect
        } else {
            // Eye viewport is taller than video - fit to width, pillarbox top/bottom
            scaleX = 1.0f
            scaleY = eyeAspect / videoAspect
        }
        
        // Full quad vertices with corrected aspect ratio
        val fullVertices = floatArrayOf(
            // Positions              Texture coords (full texture)
            -scaleX, -scaleY,         0.0f, 1f,  // Bottom-left
             scaleX, -scaleY,         1.0f, 1f,  // Bottom-right
            -scaleX,  scaleY,         0.0f, 0f,  // Top-left
             scaleX,  scaleY,         1.0f, 0f   // Top-right
        )
        val fullBuffer = ByteBuffer.allocateDirect(fullVertices.size * 4)
            .order(ByteOrder.nativeOrder())
            .asFloatBuffer()
            .put(fullVertices)
        
        // Left eye - show full image to left half of screen
        GLES30.glViewport(0, 0, width / 2, height)
        GLES30.glBindTexture(GLES30.GL_TEXTURE_2D, leftEyeTextureId)
        
        fullBuffer.position(0)
        GLES30.glVertexAttribPointer(positionHandle, 2, GLES30.GL_FLOAT, false, 16, fullBuffer)
        fullBuffer.position(2)
        GLES30.glVertexAttribPointer(texCoordHandle, 2, GLES30.GL_FLOAT, false, 16, fullBuffer)
        GLES30.glDrawArrays(GLES30.GL_TRIANGLE_STRIP, 0, 4)
        
        // Right eye - show full image to right half of screen
        GLES30.glViewport(width / 2, 0, width / 2, height)
        GLES30.glBindTexture(GLES30.GL_TEXTURE_2D, rightEyeTextureId)
        
        fullBuffer.position(0)
        GLES30.glVertexAttribPointer(positionHandle, 2, GLES30.GL_FLOAT, false, 16, fullBuffer)
        fullBuffer.position(2)
        GLES30.glVertexAttribPointer(texCoordHandle, 2, GLES30.GL_FLOAT, false, 16, fullBuffer)
        GLES30.glDrawArrays(GLES30.GL_TRIANGLE_STRIP, 0, 4)
        
        // Restore full viewport
        GLES30.glViewport(0, 0, width, height)
        
        // Disable vertex attributes
        GLES30.glDisableVertexAttribArray(positionHandle)
        GLES30.glDisableVertexAttribArray(texCoordHandle)
    }

    private fun renderStereoExternal(mono: Boolean) {
        GLES30.glUseProgram(shaderProgramExternal)
        GLES30.glEnableVertexAttribArray(positionHandleExternal)
        GLES30.glEnableVertexAttribArray(texCoordHandleExternal)

        GLES30.glActiveTexture(GLES30.GL_TEXTURE0)
        GLES30.glUniform1i(textureHandleExternal, 0)

        val viewport = IntArray(4)
        GLES30.glGetIntegerv(GLES30.GL_VIEWPORT, viewport, 0)
        val width = viewport[2]
        val height = viewport[3]

        val videoAspect = videoAspectRatio
        val eyeWidth = width / 2.0f
        val eyeAspect = eyeWidth / height.toFloat()

        val scaleX: Float
        val scaleY: Float
        if (eyeAspect > videoAspect) {
            scaleY = 1.0f
            scaleX = videoAspect / eyeAspect
        } else {
            scaleX = 1.0f
            scaleY = eyeAspect / videoAspect
        }

        val fullVertices = floatArrayOf(
            -scaleX, -scaleY,         0.0f, 1f,
             scaleX, -scaleY,         1.0f, 1f,
            -scaleX,  scaleY,         0.0f, 0f,
             scaleX,  scaleY,         1.0f, 0f
        )
        val fullBuffer = ByteBuffer.allocateDirect(fullVertices.size * 4)
            .order(ByteOrder.nativeOrder())
            .asFloatBuffer()
            .put(fullVertices)

        // Left eye
        GLES30.glViewport(0, 0, width / 2, height)
        GLES30.glBindTexture(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, leftEyeOesTextureId)

        if (texMatrixHandleExternal >= 0) {
            GLES30.glUniformMatrix4fv(texMatrixHandleExternal, 1, false, leftTexMatrixFinal, 0)
        }

        fullBuffer.position(0)
        GLES30.glVertexAttribPointer(positionHandleExternal, 2, GLES30.GL_FLOAT, false, 16, fullBuffer)
        fullBuffer.position(2)
        GLES30.glVertexAttribPointer(texCoordHandleExternal, 2, GLES30.GL_FLOAT, false, 16, fullBuffer)
        GLES30.glDrawArrays(GLES30.GL_TRIANGLE_STRIP, 0, 4)

        // Right eye (reuse left in mono)
        GLES30.glViewport(width / 2, 0, width / 2, height)
        val rightTex = if (mono) leftEyeOesTextureId else rightEyeOesTextureId
        GLES30.glBindTexture(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, rightTex)

        if (texMatrixHandleExternal >= 0) {
            val m = if (mono) leftTexMatrixFinal else rightTexMatrixFinal
            GLES30.glUniformMatrix4fv(texMatrixHandleExternal, 1, false, m, 0)
        }

        fullBuffer.position(0)
        GLES30.glVertexAttribPointer(positionHandleExternal, 2, GLES30.GL_FLOAT, false, 16, fullBuffer)
        fullBuffer.position(2)
        GLES30.glVertexAttribPointer(texCoordHandleExternal, 2, GLES30.GL_FLOAT, false, 16, fullBuffer)
        GLES30.glDrawArrays(GLES30.GL_TRIANGLE_STRIP, 0, 4)

        GLES30.glViewport(0, 0, width, height)
        GLES30.glDisableVertexAttribArray(positionHandleExternal)
        GLES30.glDisableVertexAttribArray(texCoordHandleExternal)
    }

    private fun renderFullscreenExternal(textureId: Int) {
        GLES30.glUseProgram(shaderProgramExternal)
        GLES30.glEnableVertexAttribArray(positionHandleExternal)
        GLES30.glEnableVertexAttribArray(texCoordHandleExternal)

        GLES30.glActiveTexture(GLES30.GL_TEXTURE0)
        GLES30.glUniform1i(textureHandleExternal, 0)

        if (texMatrixHandleExternal >= 0) {
            // Fullscreen path is left-eye only.
            GLES30.glUniformMatrix4fv(texMatrixHandleExternal, 1, false, leftTexMatrixFinal, 0)
        }

        val viewport = IntArray(4)
        GLES30.glGetIntegerv(GLES30.GL_VIEWPORT, viewport, 0)
        val width = viewport[2]
        val height = viewport[3]

        val videoAspect = videoAspectRatio
        val screenAspect = width / height.toFloat()

        // Fill the screen (center-crop) rather than letterbox.
        val scaleX: Float
        val scaleY: Float
        if (screenAspect > videoAspect) {
            // Screen is wider than video -> expand vertically and crop top/bottom.
            scaleX = 1.0f
            scaleY = screenAspect / videoAspect
        } else {
            // Screen is taller than video -> expand horizontally and crop sides.
            scaleY = 1.0f
            scaleX = videoAspect / screenAspect
        }

        val fullVertices = floatArrayOf(
            -scaleX, -scaleY,         0.0f, 1f,
             scaleX, -scaleY,         1.0f, 1f,
            -scaleX,  scaleY,         0.0f, 0f,
             scaleX,  scaleY,         1.0f, 0f
        )
        val fullBuffer = ByteBuffer.allocateDirect(fullVertices.size * 4)
            .order(ByteOrder.nativeOrder())
            .asFloatBuffer()
            .put(fullVertices)

        GLES30.glBindTexture(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, textureId)

        fullBuffer.position(0)
        GLES30.glVertexAttribPointer(positionHandleExternal, 2, GLES30.GL_FLOAT, false, 16, fullBuffer)
        fullBuffer.position(2)
        GLES30.glVertexAttribPointer(texCoordHandleExternal, 2, GLES30.GL_FLOAT, false, 16, fullBuffer)
        GLES30.glDrawArrays(GLES30.GL_TRIANGLE_STRIP, 0, 4)

        GLES30.glDisableVertexAttribArray(positionHandleExternal)
        GLES30.glDisableVertexAttribArray(texCoordHandleExternal)
    }

    private fun createExternalOesTexture(): Int {
        val textures = IntArray(1)
        GLES30.glGenTextures(1, textures, 0)
        val texId = textures[0]

        GLES30.glBindTexture(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, texId)
        GLES30.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, GLES30.GL_TEXTURE_MIN_FILTER, GLES30.GL_LINEAR)
        GLES30.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, GLES30.GL_TEXTURE_MAG_FILTER, GLES30.GL_LINEAR)
        GLES30.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, GLES30.GL_TEXTURE_WRAP_S, GLES30.GL_CLAMP_TO_EDGE)
        GLES30.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, GLES30.GL_TEXTURE_WRAP_T, GLES30.GL_CLAMP_TO_EDGE)
        return texId
    }

    private fun renderFullscreen(textureId: Int) {
        // Use shader program
        GLES30.glUseProgram(shaderProgram)

        // Enable vertex attributes
        GLES30.glEnableVertexAttribArray(positionHandle)
        GLES30.glEnableVertexAttribArray(texCoordHandle)

        // Bind texture uniform
        GLES30.glActiveTexture(GLES30.GL_TEXTURE0)
        GLES30.glUniform1i(textureHandle, 0)

        // 2D textures use identity UV transform.
        if (texMatrixHandle >= 0) {
            GLES30.glUniformMatrix4fv(texMatrixHandle, 1, false, identityTexMatrix, 0)
        }

        // Get viewport dimensions
        val viewport = IntArray(4)
        GLES30.glGetIntegerv(GLES30.GL_VIEWPORT, viewport, 0)
        val width = viewport[2]
        val height = viewport[3]

        val videoAspect = videoAspectRatio
        val screenAspect = width / height.toFloat()

        // Fill the screen (center-crop) rather than letterbox.
        val scaleX: Float
        val scaleY: Float

        if (screenAspect > videoAspect) {
            // Screen is wider than video -> expand vertically and crop top/bottom.
            scaleX = 1.0f
            scaleY = screenAspect / videoAspect
        } else {
            // Screen is taller than video -> expand horizontally and crop sides.
            scaleY = 1.0f
            scaleX = videoAspect / screenAspect
        }

        val fullVertices = floatArrayOf(
            -scaleX, -scaleY,         0.0f, 1f,
             scaleX, -scaleY,         1.0f, 1f,
            -scaleX,  scaleY,         0.0f, 0f,
             scaleX,  scaleY,         1.0f, 0f
        )
        val fullBuffer = ByteBuffer.allocateDirect(fullVertices.size * 4)
            .order(ByteOrder.nativeOrder())
            .asFloatBuffer()
            .put(fullVertices)

        GLES30.glBindTexture(GLES30.GL_TEXTURE_2D, textureId)

        fullBuffer.position(0)
        GLES30.glVertexAttribPointer(positionHandle, 2, GLES30.GL_FLOAT, false, 16, fullBuffer)
        fullBuffer.position(2)
        GLES30.glVertexAttribPointer(texCoordHandle, 2, GLES30.GL_FLOAT, false, 16, fullBuffer)
        GLES30.glDrawArrays(GLES30.GL_TRIANGLE_STRIP, 0, 4)

        // Disable vertex attributes
        GLES30.glDisableVertexAttribArray(positionHandle)
        GLES30.glDisableVertexAttribArray(texCoordHandle)
    }

    private fun resolveDisplayLayout(): DisplayLayout {
        if (displayLayout != DisplayLayout.AUTO) {
            return displayLayout
        }
        if (isTelevisionDevice()) {
            return DisplayLayout.FULLSCREEN
        }
        if (isVrHeadsetDevice()) {
            return DisplayLayout.VR_STEREO
        }
        return DisplayLayout.FULLSCREEN
    }

    private fun isTelevisionDevice(): Boolean {
        val uiModeManager = getSystemService(UI_MODE_SERVICE) as? UiModeManager
        val modeType = uiModeManager?.currentModeType
        if (modeType == Configuration.UI_MODE_TYPE_TELEVISION) {
            return true
        }
        return packageManager.hasSystemFeature(PackageManager.FEATURE_TELEVISION) ||
            packageManager.hasSystemFeature(PackageManager.FEATURE_LEANBACK)
    }

    private fun isVrHeadsetDevice(): Boolean {
        val uiModeType = resources.configuration.uiMode and Configuration.UI_MODE_TYPE_MASK
        if (uiModeType == Configuration.UI_MODE_TYPE_VR_HEADSET) {
            return true
        }

        // Standard Android VR feature flag (present on some VR-class devices)
        if (packageManager.hasSystemFeature(PackageManager.FEATURE_VR_MODE_HIGH_PERFORMANCE)) {
            return true
        }

        // Fallback heuristics for common headsets.
        val mfg = (android.os.Build.MANUFACTURER ?: "").lowercase()
        val model = (android.os.Build.MODEL ?: "").lowercase()
        val device = (android.os.Build.DEVICE ?: "").lowercase()
        val product = (android.os.Build.PRODUCT ?: "").lowercase()
        val brand = (android.os.Build.BRAND ?: "").lowercase()
        val hardware = (android.os.Build.HARDWARE ?: "").lowercase()
        val combined = "$mfg $model $device $product $brand $hardware"

        return listOf(
            "oculus",
            "meta",
            "quest",
            "pacific",
            "pico",
            "vive",
            "htc",
            "focus",
            "hololens",
            "daydream"
        ).any { combined.contains(it) }
    }
    
    private fun updateStatus(message: String, color: Int) {
        runOnUiThread {
            statusColor = color
            // Convert Android color to GL color
            clearR = Color.red(color) / 255.0f
            clearG = Color.green(color) / 255.0f
            clearB = Color.blue(color) / 255.0f
        }
    }
    
    private fun startAutoDiscovery() {
        updateStatus("SEARCHING\nFOR\nSERVER", Color.BLUE)

        if (isStreaming || isConnecting) {
            return
        }
        
        // CRITICAL FIX: Always stop existing discovery before creating new one
        discoveryService?.stop()
        discoveryService = null
        
        discoveryService = DiscoveryService(DISCOVERY_PORT, DEFAULT_STREAMING_PORT) { serverIp, serverPort ->
            runOnUiThread {
                if (isStreaming || isConnecting) {
                    return@runOnUiThread
                }

                // Stop discovery immediately to avoid repeated callbacks creating multiple TCP connections.
                isConnecting = true
                discoveryService?.stop()
                discoveryService = null

                updateStatus("SERVER\nFOUND\nCONNECTING", Color.GREEN)
                
                // Wait 1 second before connecting
                CoroutineScope(Dispatchers.Main).launch {
                    delay(1000)
                    connectToServer(serverIp, serverPort)
                }
            }
        }
        
        discoveryService?.start()
    }
    
    private fun checkPermissions(): Boolean {
        return ContextCompat.checkSelfPermission(
            this,
            Manifest.permission.INTERNET
        ) == PackageManager.PERMISSION_GRANTED
    }
    
    private fun requestPermissions() {
        ActivityCompat.requestPermissions(
            this,
            arrayOf(Manifest.permission.INTERNET),
            PERMISSION_REQUEST_CODE
        )
    }
    
    private fun connectToServer(ip: String, port: Int) {
        if (isStreaming) {
            return
        }

        // Ensure UI/logic reflects an active connection attempt even if connectToServer is
        // invoked outside the discovery callback.
        isConnecting = true

        // If discovery is still alive for any reason, stop it before creating a connection.
        discoveryService?.stop()
        discoveryService = null

        // Ensure we never have multiple receivers running concurrently.
        networkReceiver?.stop()
        networkReceiver = null

        // Reset per-connection rx stats so gaps/jitter reflect the active stream.
        synchronized(statsLock) {
            h264EnqueuedTotal = 0
            h264DequeuedTotal = 0
            h264DroppedTotal = 0
            h264FlushTotal = 0
            h264FrameIdGapsTotal = 0
            lastRxFrameId = null
            lastRxTimeNs = 0
            rxInterarrivalSumMs = 0.0
            rxInterarrivalMaxMs = 0.0
            rxInterarrivalCount = 0

            lastLogH264Enqueued = 0
            lastLogH264Dequeued = 0
            lastLogH264Dropped = 0
            lastLogH264Flush = 0
            lastLogH264Gaps = 0
        }

        updateStatus("STREAMING\nSTARTING", Color.rgb(255, 165, 0))
        
        // Create network receiver with disconnect handler
        networkReceiver = NetworkReceiver(
            serverIp = ip,
            serverPort = port,
            // Frame received callback
            onFrameReceived = { leftData, rightData, protocol, frameId, isMono ->
                // Detect and initialize decoders on first frame
                if (streamProtocol == StreamProtocol.UNKNOWN && protocol != StreamProtocol.UNKNOWN) {
                    streamProtocol = protocol
                    runOnUiThread {
                        val protocolName = when(protocol) {
                            StreamProtocol.VRH2 -> "H.264 (GPU)"
                            StreamProtocol.VRHP -> "JPEG (CPU)"
                            else -> "UNKNOWN"
                        }
                        Toast.makeText(this, "Protocol: $protocolName", Toast.LENGTH_SHORT).show()
                    }
                    
                    // Initialize H.264 decoders lazily when we have SPS/PPS
                }
                
                // Mark as streaming on first frame
                if (!isStreaming) {
                    isStreaming = true
                    isConnecting = false
                    runOnUiThread {
                        // Change to black when streaming (for letterbox bars)
                        clearR = 0.0f
                        clearG = 0.0f
                        clearB = 0.0f
                    }
                }
                
                if (protocol == StreamProtocol.VRH2) {
                    lastPacketWasMono = isMono
                    videoAspectRatio = H264_WIDTH.toFloat() / H264_HEIGHT.toFloat()
                    recordH264Rx(frameId)
                    enqueueH264Frame(leftData, rightData, frameId, isMono)
                    // Track bytes received for bandwidth calculation
                    bytesReceived += leftData.size.toLong() + (if (isMono) 0L else rightData.size.toLong())
                    hasFrame = true
                } else {
                    // Store JPEG frame data for rendering
                    synchronized(frameLock) {
                        leftFrameData = leftData
                        rightFrameData = rightData
                        hasFrame = true

                        // Mark new frame available (used by render loop to decide when to decode/upload)
                        receivedFrameVersion += 1

                        // Track bytes received for bandwidth calculation
                        bytesReceived += leftData.size.toLong() + (if (isMono) 0L else rightData.size.toLong())
                    }
                }
            },
            // Disconnect callback - RESTART DISCOVERY
            onDisconnected = { reason ->
                Log.w(TAG, "Connection lost (${reason.ifBlank { "unknown" }}). Restarting discovery...")
                
                // Clean up streaming state
                isStreaming = false
                isConnecting = false
                streamProtocol = StreamProtocol.UNKNOWN
                networkReceiver = null

                synchronized(statsLock) {
                    lastRxFrameId = null
                    lastRxTimeNs = 0
                    rxInterarrivalSumMs = 0.0
                    rxInterarrivalMaxMs = 0.0
                    rxInterarrivalCount = 0
                }

                stopH264DecodeLoop(clearQueue = true)

                // Reset codecs on any disconnect so a reconnect always re-initializes from SPS/PPS.
                // Keep the decode Surfaces (created on the GL thread) so we can restart without recreating GL.
                resetH264CodecsKeepSurfaces()
                
                // Clear frame data and reset display to blue searching screen
                synchronized(frameLock) {
                    hasFrame = false
                    leftFrameData = null
                    rightFrameData = null
                    receivedFrameVersion += 1
                }
                
                // Reset clear color to blue (searching status)
                runOnUiThread {
                    clearR = 0.0f
                    clearG = 0.0f
                    clearB = 1.0f
                    glSurfaceView.requestRender()  // Force redraw with blue background
                }
                
                // CRITICAL FIX: Stop old discovery service before starting new one
                discoveryService?.stop()
                discoveryService = null

                // Small delay to ensure sockets are fully released; never block the UI thread.
                CoroutineScope(Dispatchers.Main).launch {
                    delay(500)
                    startAutoDiscovery()
                }
            },
            backpressureMs = { protocol ->
                // Backpressure: if the H.264 queue is getting deep, slow down socket reads a bit.
                // This lets TCP apply natural flow control and prevents burst-induced overflows.
                if (protocol != StreamProtocol.VRH2) return@NetworkReceiver 0L
                val q = synchronized(h264QueueLock) { h264FrameQueue.size }
                when {
                    q >= h264QueueMaxFrames -> 16L
                    q >= h264QueueHighWater -> 8L
                    else -> 0L
                }
            }
        )
        
        networkReceiver?.start()
    }
    
    private fun initializeH264Decoders() {
        // Deprecated placeholder - initialization happens in handleH264Frame once SPS/PPS are available.
    }

    private fun resetH264CodecsKeepSurfaces() {
        synchronized(decoderLock) {
            try {
                leftDecoder?.stop()
            } catch (_: Exception) {
            }
            try {
                leftDecoder?.release()
            } catch (_: Exception) {
            }
            leftDecoder = null

            try {
                rightDecoder?.stop()
            } catch (_: Exception) {
            }
            try {
                rightDecoder?.release()
            } catch (_: Exception) {
            }
            rightDecoder = null

            h264Configured = false
            leftH264FrameAvailable = false
            rightH264FrameAvailable = false

            h264LastSps = null
            h264LastPps = null
        }

        // Any reconnect should begin at a clean decoder state.
        enterH264Resync("codec_reset")
    }

    private fun enterH264Resync(reason: String) {
        h264NeedKeyframeResync = true
        maybeSendNeedIdr(reason)
    }

    private fun maybeSendNeedIdr(reason: String) {
        val nowMs = SystemClock.elapsedRealtime()
        if (nowMs - lastNeedIdrSentAtMs < needIdrMinIntervalMs) return
        lastNeedIdrSentAtMs = nowMs

        // Send on a background thread; writing can block if the socket is congested.
        CoroutineScope(Dispatchers.IO).launch {
            try {
                networkReceiver?.sendNeedIdr()
                Log.i(TAG, "VRH2: NEED_IDR sent (reason=$reason)")
            } catch (_: Exception) {
            }
        }
    }

    private fun byteArrayEquals(a: ByteArray?, b: ByteArray?): Boolean {
        if (a === b) return true
        if (a == null || b == null) return false
        return a.contentEquals(b)
    }

    private fun h264AccessUnitHasStartCode(data: ByteArray): Boolean {
        // Quick scan for Annex-B start codes (00 00 01 or 00 00 00 01).
        // Scan only the first ~128 bytes: start codes should appear early in an access unit.
        val limit = minOf(data.size - 3, 128)
        var i = 0
        while (i < limit) {
            if (data[i] == 0.toByte() && data[i + 1] == 0.toByte()) {
                if (data[i + 2] == 1.toByte()) return true
                if (i + 3 < data.size && data[i + 2] == 0.toByte() && data[i + 3] == 1.toByte()) return true
            }
            i += 1
        }
        return false
    }

    private fun enqueueH264Frame(leftData: ByteArray, rightData: ByteArray, frameId: Int, isMono: Boolean) {
        // If we detect corruption or codec errors, drop frames until the next keyframe (IDR/SPS)
        // and resync on the next IDR.
        if (!h264AccessUnitHasStartCode(leftData)) {
            synchronized(statsLock) {
                h264BadAccessUnitsTotal += 1
                h264DroppedTotal += 1
            }
            enterH264Resync("bad_au")
            return
        }

        val isKeyframe = h264AccessUnitLooksLikeKeyframe(leftData)

        // Resync is handled in handleH264Frame where we can flush immediately before queueing IDR.

        synchronized(h264QueueLock) {
            h264FrameQueue.addLast(
                H264StereoFrame(
                    frameId = frameId,
                    left = leftData,
                    right = rightData,
                    mono = isMono,
                    keyframe = isKeyframe
                )
            )

            synchronized(statsLock) {
                h264EnqueuedTotal += 1
            }

            // Hard cap queue size as a last resort. Prefer receiver backpressure so we rarely hit this.
            if (h264FrameQueue.size > h264QueueMaxFrames) {
                var dropped = 0
                while (h264FrameQueue.size > h264QueueMaxFrames) {
                    h264FrameQueue.removeFirst()
                    dropped += 1
                }

                if (dropped > 0) {
                    synchronized(statsLock) {
                        h264DroppedTotal += dropped.toLong()
                    }

                    // Dropping access units is effectively packet loss.
                    // Force a flush + IDR resync to avoid long-lived mosaic artifacts.
                    enterH264Resync("queue_drop")
                }
            }
        }

        startH264DecodeLoopIfNeeded()
    }

    private fun startH264DecodeLoopIfNeeded() {
        if (h264DecodeJob != null) return
        h264DecodeJob = CoroutineScope(Dispatchers.Default).launch {
            val frameIntervalMs = (1000.0 / h264TargetFps.toDouble()).toLong().coerceAtLeast(1)

            var started = false

            while (isActive) {
                if (!isStreaming || streamProtocol != StreamProtocol.VRH2) {
                    break
                }

                val loopStartMs = SystemClock.uptimeMillis()

                // Do not defer flushes here; see comment on h264ShouldFlushDecoders.
                h264ShouldFlushDecoders = false

                // Small startup prebuffer reduces jitter; after that, keep a steady tick.
                if (!started) {
                    val buffered = synchronized(h264QueueLock) { h264FrameQueue.size }
                    if (buffered >= h264MinStartFrames) {
                        started = true
                    } else {
                        delay(2)
                        continue
                    }
                }

                val next: H264StereoFrame? = synchronized(h264QueueLock) {
                    if (h264FrameQueue.isNotEmpty()) h264FrameQueue.removeFirst() else null
                }

                if (next != null) {
                    handleH264Frame(next.left, next.right, next.frameId, next.mono)
                    synchronized(statsLock) {
                        h264DequeuedTotal += 1
                    }
                }

                // Aim for a steady decode cadence without slowing down by (decode time + delay).
                // This prevents the queue from growing even when decoding takes a few ms.
                val elapsedMs = SystemClock.uptimeMillis() - loopStartMs
                val remainingMs = frameIntervalMs - elapsedMs
                if (remainingMs > 0) {
                    delay(remainingMs)
                } else {
                    yield()
                }
            }
        }
    }

    private fun stopH264DecodeLoop(clearQueue: Boolean) {
        h264DecodeJob?.cancel()
        h264DecodeJob = null
        if (clearQueue) {
            synchronized(h264QueueLock) {
                h264FrameQueue.clear()
                h264ShouldFlushDecoders = false
            }
        }
    }

    private fun recordH264Rx(frameId: Int) {
        val nowNs = System.nanoTime()
        synchronized(statsLock) {
            if (lastRxTimeNs != 0L) {
                val dtMs = (nowNs - lastRxTimeNs).toDouble() / 1_000_000.0
                rxInterarrivalSumMs += dtMs
                if (dtMs > rxInterarrivalMaxMs) rxInterarrivalMaxMs = dtMs
                rxInterarrivalCount += 1
            }
            lastRxTimeNs = nowNs

            val prevId = lastRxFrameId
            if (prevId != null) {
                val expected = prevId + 1
                if (frameId != expected) {
                    h264FrameIdGapsTotal += kotlin.math.abs(frameId - expected).toLong()
                }
            }
            lastRxFrameId = frameId
        }
    }

    private fun h264AccessUnitLooksLikeKeyframe(data: ByteArray): Boolean {
        // Annex-B scan. Treat IDR (type 5) as keyframe. Also accept SPS (7) because it helps resync
        // after dropping (NVENC repeats headers on keyframes in our config).
        fun isStartCode3(i: Int): Boolean {
            return i + 2 < data.size && data[i] == 0.toByte() && data[i + 1] == 0.toByte() && data[i + 2] == 1.toByte()
        }
        fun isStartCode4(i: Int): Boolean {
            return i + 3 < data.size && data[i] == 0.toByte() && data[i + 1] == 0.toByte() && data[i + 2] == 0.toByte() && data[i + 3] == 1.toByte()
        }

        var i = 0
        while (i < data.size - 4) {
            val start = when {
                isStartCode4(i) -> i
                isStartCode3(i) -> i
                else -> {
                    i += 1
                    continue
                }
            }

            val startCodeLen = if (isStartCode4(i)) 4 else 3
            val nalHeaderIndex = start + startCodeLen
            if (nalHeaderIndex >= data.size) break
            val nalType = (data[nalHeaderIndex].toInt() and 0x1F)
            if (nalType == 5 || nalType == 7) return true
            i = nalHeaderIndex + 1
        }

        return false
    }

    private fun h264AccessUnitContainsIdr(data: ByteArray): Boolean {
        // Annex-B scan. True IDR slices are NAL type 5.
        fun isStartCode3(i: Int): Boolean {
            return i + 2 < data.size && data[i] == 0.toByte() && data[i + 1] == 0.toByte() && data[i + 2] == 1.toByte()
        }
        fun isStartCode4(i: Int): Boolean {
            return i + 3 < data.size && data[i] == 0.toByte() && data[i + 1] == 0.toByte() && data[i + 2] == 0.toByte() && data[i + 3] == 1.toByte()
        }

        var i = 0
        while (i < data.size - 4) {
            val start = when {
                isStartCode4(i) -> i
                isStartCode3(i) -> i
                else -> {
                    i += 1
                    continue
                }
            }

            val startCodeLen = if (isStartCode4(i)) 4 else 3
            val nalHeaderIndex = start + startCodeLen
            if (nalHeaderIndex >= data.size) break
            val nalType = (data[nalHeaderIndex].toInt() and 0x1F)
            if (nalType == 5) return true
            i = nalHeaderIndex + 1
        }

        return false
    }

    private fun handleH264Frame(leftData: ByteArray, rightData: ByteArray, frameId: Int, isMono: Boolean) {
        synchronized(decoderLock) {
            val (sps, pps) = extractSpsPps(leftData)

            // If SPS/PPS changes mid-stream (e.g., server reset/recreate encoder), reconfigure.
            // Otherwise, the decoder can output severe mosaic artifacts even though the stream is valid.
            if (h264Configured && sps != null && pps != null) {
                val changed = (!byteArrayEquals(h264LastSps, sps)) || (!byteArrayEquals(h264LastPps, pps))
                if (changed) {
                    Log.w(TAG, "VRH2: SPS/PPS changed; reconfiguring decoders")
                    resetH264CodecsKeepSurfaces()
                }
            }

            if (!h264Configured) {
                if (sps == null || pps == null) {
                    // Wait for SPS/PPS in stream
                    return
                }

                try {
                    val format = MediaFormat.createVideoFormat(MediaFormat.MIMETYPE_VIDEO_AVC, H264_WIDTH, H264_HEIGHT)
                    format.setByteBuffer("csd-0", ByteBuffer.wrap(sps))
                    format.setByteBuffer("csd-1", ByteBuffer.wrap(pps))

                    leftDecoder = MediaCodec.createDecoderByType(MediaFormat.MIMETYPE_VIDEO_AVC)
                    leftDecoder?.configure(format, leftDecoderSurface, null, 0)
                    leftDecoder?.start()

                    if (!isMono) {
                        rightDecoder = MediaCodec.createDecoderByType(MediaFormat.MIMETYPE_VIDEO_AVC)
                        rightDecoder?.configure(format, rightDecoderSurface, null, 0)
                        rightDecoder?.start()
                    }

                    h264LastSps = sps
                    h264LastPps = pps
                    h264Configured = true

                    // IMPORTANT: Only begin decoding once we see an IDR.
                    // Some devices will produce heavy mosaic if decoding starts mid-GOP.
                    enterH264Resync("decoder_init")

                    runOnUiThread {
                        Toast.makeText(this, "VRH2: MediaCodec surface decode active", Toast.LENGTH_SHORT).show()
                    }
                } catch (e: Exception) {
                    e.printStackTrace()
                    runOnUiThread {
                        Toast.makeText(this, "VRH2 decoder init failed: ${e.message}", Toast.LENGTH_LONG).show()
                    }
                    return
                }
            }

            // If we need to resync, drop until we get a real IDR.
            val hasIdr = h264AccessUnitContainsIdr(leftData)
            if (h264NeedKeyframeResync) {
                if (!hasIdr) {
                    synchronized(statsLock) {
                        h264DroppedTotal += 1
                    }
                    return
                }

                // Flush NOW, before queueing this IDR, so we don't accidentally flush away
                // the very keyframe we need to recover.
                try {
                    leftDecoder?.flush()
                } catch (_: Exception) {
                }
                if (!isMono) {
                    try {
                        rightDecoder?.flush()
                    } catch (_: Exception) {
                    }
                }

                synchronized(statsLock) {
                    h264FlushTotal += 1
                    h264ResyncTotal += 1
                }
                h264NeedKeyframeResync = false
            }

            val ptsUs = System.nanoTime() / 1000L
            queueAccessUnit(leftDecoder, leftData, ptsUs)
            drainDecoder(leftDecoder)

            if (!isMono) {
                queueAccessUnit(rightDecoder, rightData, ptsUs)
                drainDecoder(rightDecoder)
            }
        }
    }

    private fun queueAccessUnit(decoder: MediaCodec?, data: ByteArray, ptsUs: Long) {
        if (decoder == null) return
        try {
            // Non-blocking dequeue can randomly fail under load, causing us to skip access units.
            // Skipping P-frames can create blocky "bleed" artifacts until the next keyframe.
            val inIndex = decoder.dequeueInputBuffer(5_000) // 5ms
            if (inIndex < 0) {
                synchronized(statsLock) {
                    h264CodecInputStarveTotal += 1
                    h264DroppedTotal += 1
                }

                // Treat this as packet loss: force a keyframe resync.
                enterH264Resync("codec_starve")
                return
            }

            val inputBuffer = decoder.getInputBuffer(inIndex)
            inputBuffer?.clear()
            inputBuffer?.put(data)
            decoder.queueInputBuffer(inIndex, 0, data.size, ptsUs, 0)
        } catch (e: Exception) {
            // Swallow transient codec errors; stream can recover on next frames.
            e.printStackTrace()

            // If the codec hits a bad state or we overflow an input buffer, resync from the next keyframe.
            synchronized(statsLock) {
                h264BadAccessUnitsTotal += 1
                h264DroppedTotal += 1
            }
            enterH264Resync("codec_error")
            h264ShouldFlushDecoders = false
        }
    }

    private fun drainDecoder(decoder: MediaCodec?) {
        if (decoder == null) return
        try {
            val bufferInfo = MediaCodec.BufferInfo()
            while (true) {
                val outIndex = decoder.dequeueOutputBuffer(bufferInfo, 0)
                if (outIndex >= 0) {
                    decoder.releaseOutputBuffer(outIndex, true)
                } else if (outIndex == MediaCodec.INFO_TRY_AGAIN_LATER) {
                    break
                } else if (outIndex == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED) {
                    // ignore
                } else {
                    break
                }
            }
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }

    private fun extractSpsPps(data: ByteArray): Pair<ByteArray?, ByteArray?> {
        // Parse Annex-B NAL units and return SPS (type 7) and PPS (type 8), including start codes.
        var sps: ByteArray? = null
        var pps: ByteArray? = null

        fun isStartCode3(i: Int): Boolean {
            return i + 2 < data.size && data[i] == 0.toByte() && data[i + 1] == 0.toByte() && data[i + 2] == 1.toByte()
        }
        fun isStartCode4(i: Int): Boolean {
            return i + 3 < data.size && data[i] == 0.toByte() && data[i + 1] == 0.toByte() && data[i + 2] == 0.toByte() && data[i + 3] == 1.toByte()
        }

        var i = 0
        while (i < data.size - 4) {
            val start = when {
                isStartCode4(i) -> i
                isStartCode3(i) -> i
                else -> {
                    i += 1
                    continue
                }
            }

            val startCodeLen = if (isStartCode4(i)) 4 else 3
            val nalHeaderIndex = start + startCodeLen
            if (nalHeaderIndex >= data.size) break
            val nalType = (data[nalHeaderIndex].toInt() and 0x1F)

            // Find next start code
            var j = nalHeaderIndex
            while (j < data.size - 4 && !(isStartCode3(j) || isStartCode4(j))) {
                j += 1
            }
            val end = j

            val nalWithStartCode = data.copyOfRange(start, end)
            if (nalType == 7 && sps == null) sps = nalWithStartCode
            if (nalType == 8 && pps == null) pps = nalWithStartCode
            if (sps != null && pps != null) break

            i = end
        }

        return Pair(sps, pps)
    }
    
    private fun decodeH264Frame(decoder: MediaCodec?, frameData: ByteArray): ByteArray? {
        if (decoder == null) return null
        
        try {
            // Get input buffer
            val inputBufferId = decoder.dequeueInputBuffer(10000)
            if (inputBufferId >= 0) {
                val inputBuffer = decoder.getInputBuffer(inputBufferId)
                inputBuffer?.clear()
                inputBuffer?.put(frameData)
                decoder.queueInputBuffer(inputBufferId, 0, frameData.size, 0, 0)
            }
            
            // Get output buffer
            val bufferInfo = MediaCodec.BufferInfo()
            val outputBufferId = decoder.dequeueOutputBuffer(bufferInfo, 10000)
            if (outputBufferId >= 0) {
                val outputBuffer = decoder.getOutputBuffer(outputBufferId)
                // For now, we'll still use JPEG-style texture upload
                // TODO: Use MediaCodec output surface for zero-copy
                decoder.releaseOutputBuffer(outputBufferId, false)
            }
            
            return null // Placeholder - need to extract decoded YUV data
        } catch (e: Exception) {
            e.printStackTrace()
            return null
        }
    }
    
    override fun onPause() {
        super.onPause()
        glSurfaceView.onPause()
        discoveryService?.stop()
        networkReceiver?.stop()
        stopH264DecodeLoop(clearQueue = true)
        releaseDecoders()
    }
    
    override fun onResume() {
        super.onResume()
        glSurfaceView.onResume()

        // Re-assert fullscreen in case the launcher/system UI came back.
        hideSystemUi()

        resolvedDisplayLayout = resolveDisplayLayout()
        
        // CRITICAL FIX: Restart discovery when app resumes
        // (it was stopped in onPause)
        if (!isStreaming) {
            startAutoDiscovery()
        }
    }
    
    override fun onDestroy() {
        super.onDestroy()
        discoveryService?.stop()
        networkReceiver?.stop()
        stopH264DecodeLoop(clearQueue = true)
        releaseDecoders()
    }
    
    private fun releaseDecoders() {
        try {
            leftDecoder?.stop()
            leftDecoder?.release()
            leftDecoder = null
            
            rightDecoder?.stop()
            rightDecoder?.release()
            rightDecoder = null
            
            leftDecoderSurface = null
            rightDecoderSurface = null

            h264Configured = false
            leftH264FrameAvailable = false
            rightH264FrameAvailable = false
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }
}

/**
 * Discovery Service - Automatically finds the VR server on the network
 */
class DiscoveryService(
    private val discoveryPort: Int,
    private val streamingPort: Int = 5555,  // TCP streaming port (must match server)
    private val onServerFound: (String, Int) -> Unit
) {

    companion object {
        // Optional: set to a specific desktop/server IP to bypass UDP broadcast discovery.
        // This is required when the client and server are on different subnets (e.g., 10.0.0.x vs 192.168.1.x)
        // because broadcast (255.255.255.255) will not cross routers/NAT.
        // Example: "192.168.1.123"
        private const val SERVER_IP_OVERRIDE: String = ""
    }
    
    private var socket: java.net.DatagramSocket? = null
    private var isRunning = false
    private var discoveryJob: Job? = null
    
    fun start() {
        isRunning = true
        discoveryJob = CoroutineScope(Dispatchers.IO).launch {
            discoverServer()
        }
    }
    
    fun stop() {
        println("🛑 Stopping discovery service...")
        isRunning = false
        discoveryJob?.cancel()
        
        // Close socket and ensure it's properly released
        try {
            socket?.close()
        } catch (e: Exception) {
            println("⚠️ Error closing discovery socket: ${e.message}")
        } finally {
            socket = null
        }
        
        println("✅ Discovery service stopped")
    }
    
    private suspend fun discoverServer() {
        try {
            socket = java.net.DatagramSocket()
            socket?.broadcast = true
            socket?.soTimeout = 1000
            
            val deviceName = android.os.Build.MODEL
            
            println("📡 Announcing to MesmerGlass servers on port $discoveryPort...")
            
            while (isRunning) {
                try {
                    // Send hello message to broadcast address (WORKING PROTOCOL)
                    val message = "VR_HEADSET_HELLO:$deviceName"
                    val overrideIp = SERVER_IP_OVERRIDE.trim().ifEmpty { null }
                    val targets = if (overrideIp != null) {
                        listOf(java.net.InetAddress.getByName(overrideIp))
                    } else {
                        listOf(java.net.InetAddress.getByName("255.255.255.255"))
                    }

                    for (addr in targets) {
                        val packet = java.net.DatagramPacket(
                            message.toByteArray(),
                            message.length,
                            addr,
                            discoveryPort
                        )
                        socket?.send(packet)
                    }
                    
                    println("📤 Sent hello: $message")
                    
                    // Listen for server acknowledgment
                    val buffer = ByteArray(1024)
                    val receivePacket = java.net.DatagramPacket(buffer, buffer.size)
                    
                    try {
                        socket?.receive(receivePacket)
                        val response = String(receivePacket.data, 0, receivePacket.length)
                        
                        if (response.startsWith("VR_SERVER_INFO:")) {
                            // Parse server response: "VR_SERVER_INFO:5555"
                            val parts = response.split(":")
                            val serverPort = if (parts.size > 1) parts[1].toIntOrNull() ?: streamingPort else streamingPort
                            val serverIp = receivePacket.address.hostAddress ?: continue
                            println("✅ Found MesmerGlass server at $serverIp:$serverPort")
                            
                            // Notify connection handler with port from server
                            withContext(Dispatchers.Main) {
                                onServerFound(serverIp, serverPort)
                            }
                        }
                    } catch (e: java.net.SocketTimeoutException) {
                        // Timeout is normal if no server responds
                    }
                    
                    // Send hello every 2 seconds
                    delay(2000)
                    
                } catch (e: Exception) {
                    println("❌ Discovery error: ${e.message}")
                    delay(2000)
                }
            }
            
        } catch (e: Exception) {
            e.printStackTrace()
        } finally {
            socket?.close()
        }
    }
    
    // Remove the sendTcpResponse function - not needed anymore
}

/**
 * Network Receiver - Handles streaming connection
 * 
 * Supports dual-protocol detection:
 * - VRH2: H.264 hardware decoding
 * - VRHP: JPEG software decoding
 */
class NetworkReceiver(
    private val serverIp: String,
    private val serverPort: Int,
    private val onFrameReceived: (ByteArray, ByteArray, MainActivity.StreamProtocol, Int, Boolean) -> Unit,
    private val onDisconnected: (String) -> Unit,  // Callback when connection is lost (includes reason)
    private val backpressureMs: (MainActivity.StreamProtocol) -> Long = { 0L }
) {
    
    private var socket: Socket? = null
    private val outputLock = Any()
    private var outputStream: OutputStream? = null
    private var isRunning = false
    private var receiveJob: Job? = null
    private var detectedProtocol = MainActivity.StreamProtocol.UNKNOWN

    // Optional control channel: 0x01 => NEED_IDR
    fun sendNeedIdr() {
        val os: OutputStream? = synchronized(outputLock) { outputStream }
        if (os == null) return
        try {
            os.write(byteArrayOf(0x01))
            os.flush()
        } catch (_: Exception) {
        }
    }
    
    fun start() {
        isRunning = true
        receiveJob = CoroutineScope(Dispatchers.IO).launch {
            connectAndReceive()
        }
    }
    
    fun stop() {
        println("🛑 Stopping network receiver...")
        isRunning = false
        receiveJob?.cancel()
        
        // Close socket and ensure it's properly released
        try {
            socket?.close()
        } catch (e: Exception) {
            println("⚠️ Error closing network socket: ${e.message}")
        } finally {
            synchronized(outputLock) {
                outputStream = null
            }
            socket = null
        }
        
        println("✅ Network receiver stopped")
    }
    
    private suspend fun connectAndReceive() {
        var disconnectReason: String = ""
        try {
            val connectTimeoutMs = 3000
            val readTimeoutMs = 1000
            val firstPacketTimeoutMs = 5000
            val idlePacketTimeoutMs = 7000

            val s = Socket()
            s.tcpNoDelay = true
            s.keepAlive = true
            s.soTimeout = readTimeoutMs
            s.connect(java.net.InetSocketAddress(serverIp, serverPort), connectTimeoutMs)
            socket = s

            val inputStream = DataInputStream(s.getInputStream())
            synchronized(outputLock) {
                outputStream = s.getOutputStream()
            }
            
            println("📡 Connected to server $serverIp:$serverPort")

            var hasReceivedAnyPacket = false
            val connectedAtMs = android.os.SystemClock.elapsedRealtime()
            var lastPacketAtMs = connectedAtMs
            
            while (isRunning) {
                // Read packet size
                val packetSize = try {
                    inputStream.readInt()
                } catch (e: java.net.SocketTimeoutException) {
                    val nowMs = android.os.SystemClock.elapsedRealtime()
                    val waitedMs = nowMs - connectedAtMs
                    val idleMs = nowMs - lastPacketAtMs
                    if (!hasReceivedAnyPacket && waitedMs >= firstPacketTimeoutMs) {
                        disconnectReason = "Timeout waiting for first packet (${waitedMs}ms)"
                        break
                    }
                    if (hasReceivedAnyPacket && idleMs >= idlePacketTimeoutMs) {
                        disconnectReason = "Timeout waiting for packets (${idleMs}ms)"
                        break
                    }
                    continue
                } catch (e: java.io.EOFException) {
                    disconnectReason = "EOF"
                    break
                }

                if (packetSize <= 0 || packetSize > 32_000_000) {
                    disconnectReason = "Invalid packetSize=$packetSize"
                    break
                }
                
                // Read packet data
                val packetData = ByteArray(packetSize)
                try {
                    inputStream.readFully(packetData)
                    hasReceivedAnyPacket = true
                    lastPacketAtMs = android.os.SystemClock.elapsedRealtime()
                } catch (e: java.io.EOFException) {
                    disconnectReason = "EOF (partial packet)"
                    break
                } catch (e: java.net.SocketTimeoutException) {
                    val nowMs = android.os.SystemClock.elapsedRealtime()
                    val idleMs = nowMs - lastPacketAtMs
                    if (idleMs >= idlePacketTimeoutMs) {
                        disconnectReason = "Timeout waiting for packet payload (${idleMs}ms)"
                        break
                    }
                    continue
                }
                
                // Parse packet and detect protocol
                val parsed = parsePacket(packetData)
                
                // Update detected protocol
                if (detectedProtocol == MainActivity.StreamProtocol.UNKNOWN) {
                    detectedProtocol = parsed.protocol
                    println("✅ Detected protocol: ${parsed.protocol.name}")
                }
                
                // Callback with frames
                onFrameReceived(parsed.leftFrame, parsed.rightFrame, parsed.protocol, parsed.frameId, parsed.isMono)

                // Apply receiver-side backpressure (primarily for VRH2) if requested.
                val bp = backpressureMs(parsed.protocol)
                if (bp > 0) {
                    delay(bp)
                }
            }
        } catch (e: Exception) {
            e.printStackTrace()
            disconnectReason = e.javaClass.simpleName + (e.message?.let { ": $it" } ?: "")
            println("❌ Connection error: $disconnectReason")
        } finally {
            // CRITICAL: Always close socket and notify disconnect
            try {
                socket?.close()
            } catch (e: Exception) {
                e.printStackTrace()
            }
            socket = null
            
            // Notify MainActivity that connection was lost.
            // Do NOT notify if we intentionally stopped the receiver (e.g., switching servers).
            if (isRunning) {
                isRunning = false
                withContext(Dispatchers.Main) {
                    onDisconnected(disconnectReason)
                }
            }
        }
    }
    
    private data class ParsedPacket(
        val leftFrame: ByteArray,
        val rightFrame: ByteArray,
        val protocol: MainActivity.StreamProtocol,
        val frameId: Int,
        val isMono: Boolean
    )

    private fun parsePacket(packet: ByteArray): ParsedPacket {
        val buffer = ByteBuffer.wrap(packet)
        
        // Read header (16 bytes)
        val magic = ByteArray(4)
        buffer.get(magic)
        val magicString = String(magic, Charsets.US_ASCII)
        
        // Detect protocol from magic bytes
        val protocol = when (magicString) {
            "VRH2" -> MainActivity.StreamProtocol.VRH2  // H.264
            "VRHP" -> MainActivity.StreamProtocol.VRHP  // JPEG
            else -> {
                println("⚠️ Unknown protocol magic: $magicString")
                MainActivity.StreamProtocol.UNKNOWN
            }
        }
        
        val frameId = buffer.int
        val leftSize = buffer.int
        val rightSize = buffer.int
        val isMono = (rightSize == 0)
        
        // Read left eye frame
        val leftFrame = ByteArray(leftSize)
        buffer.get(leftFrame)

        // Read right eye frame (optional). If missing, reuse left.
        val rightFrame = if (rightSize > 0) {
            ByteArray(rightSize).also { buffer.get(it) }
        } else {
            leftFrame
        }

        return ParsedPacket(leftFrame, rightFrame, protocol, frameId, isMono)
    }
}
