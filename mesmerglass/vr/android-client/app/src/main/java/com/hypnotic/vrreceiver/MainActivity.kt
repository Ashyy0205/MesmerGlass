package com.hypnotic.vrreceiver

import android.Manifest
import android.app.Activity
import android.app.UiModeManager
import android.content.Context
import android.content.pm.ActivityInfo
import android.content.pm.PackageManager
import android.content.res.Configuration
import android.graphics.BitmapFactory
import android.graphics.Color
import android.media.MediaCodec
import android.media.MediaFormat
import android.graphics.SurfaceTexture
import android.opengl.GLSurfaceView
import android.opengl.GLES11Ext
import android.opengl.GLUtils
import android.os.Bundle
import android.os.Handler
import android.os.HandlerThread
import android.os.Looper
import android.util.Log
import android.view.Surface
import android.view.WindowManager
import android.widget.Toast
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import kotlinx.coroutines.*
import java.io.DataInputStream
import java.net.Socket
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.FloatBuffer
import javax.microedition.khronos.egl.EGLConfig
import javax.microedition.khronos.opengles.GL10
import android.opengl.GLES30
import android.media.MediaCodecList
import android.media.MediaCodecInfo
import java.net.NetworkInterface
import java.net.Inet4Address

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
    private var oesShaderProgram = 0
    private var vertexBuffer: FloatBuffer? = null
    private var hasFrame = false
    
    // Shader attribute/uniform locations
    private var positionHandle = 0
    private var texCoordHandle = 0
    private var textureHandle = 0

    private var oesPositionHandle = 0
    private var oesTexCoordHandle = 0
    private var oesTextureHandle = 0
    private var oesTexMatrixHandle = 0
    
    // Frame data
    private var leftFrameData: ByteArray? = null
    private var rightFrameData: ByteArray? = null
    private val frameLock = Any()
    
    // Protocol detection
    private var streamProtocol: StreamProtocol = StreamProtocol.UNKNOWN

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

    private var leftSurfaceTexture: SurfaceTexture? = null
    private var rightSurfaceTexture: SurfaceTexture? = null

    @Volatile private var leftSurfaceFrameAvailable: Boolean = false
    @Volatile private var rightSurfaceFrameAvailable: Boolean = false

    // Instrumentation + safety fallback for SurfaceTexture updates.
    // Some devices/driver combos can fail to deliver OnFrameAvailable reliably; without a fallback,
    // the renderer can appear to freeze on the first frame.
    @Volatile private var leftOnFrameAvailableCount: Long = 0
    @Volatile private var rightOnFrameAvailableCount: Long = 0
    @Volatile private var leftUpdateTexImageCount: Long = 0
    @Volatile private var rightUpdateTexImageCount: Long = 0
    @Volatile private var leftCodecQueuedInputCount: Long = 0
    @Volatile private var rightCodecQueuedInputCount: Long = 0
    @Volatile private var leftCodecReleasedOutputCount: Long = 0
    @Volatile private var rightCodecReleasedOutputCount: Long = 0

    @Volatile private var leftLastOnFrameAvailableNs: Long = 0L
    @Volatile private var rightLastOnFrameAvailableNs: Long = 0L
    private var leftLastUpdateTexImageNs: Long = 0L
    private var rightLastUpdateTexImageNs: Long = 0L

    private var surfaceTextureCallbackThread: HandlerThread? = null
    private var surfaceTextureCallbackHandler: Handler? = null

    private val leftTexMatrix = FloatArray(16)
    private val rightTexMatrix = FloatArray(16)

    private var leftOesTexId: Int = 0
    private var rightOesTexId: Int = 0

    private var h264Configured = false
    private var h264Csd0: ByteArray? = null
    private var h264Csd1: ByteArray? = null
    private var h264PtsUs: Long = 0
    private var h264Width: Int? = null
    private var h264Height: Int? = null

    private var surfaceWidth: Int = 0
    private var surfaceHeight: Int = 0

    @Volatile private var leftNeedsIdr: Boolean = false
    @Volatile private var rightNeedsIdr: Boolean = false
    private var lastLeftNeedIdrRequestAtMs = 0L
    private var lastRightNeedIdrRequestAtMs = 0L

    // H.264 smoothness-first scheduling: keep a small playout buffer so decoding/render stays smooth
    // even when network delivery is jittery, at the cost of latency.
    private var vrh2FpsMilli: Int = 0
    @Volatile private var vrh2LastPlayoutBufferMs: Int = 0

    private val vrh2MinTargetBufferMs: Int = 150
    private val vrh2MaxTargetBufferMs: Int = 1000
    @Volatile private var vrh2AdaptiveTargetBufferMs: Int = 250
    private var vrh2LastTuneAtMs: Long = 0L
    private var vrh2UnderflowEventsSinceTune: Int = 0

    private var leftPlayoutBasePtsUs: Long? = null
    private var leftPlayoutBaseNs: Long = 0L
    private var rightPlayoutBasePtsUs: Long? = null
    private var rightPlayoutBaseNs: Long = 0L
    @Volatile private var leftPlayoutBufferMs: Int = 0
    @Volatile private var rightPlayoutBufferMs: Int = 0

    private fun tuneH264PlayoutTargetBuffer() {
        val nowMs = android.os.SystemClock.uptimeMillis()
        if (nowMs - vrh2LastTuneAtMs < 500) return
        vrh2LastTuneAtMs = nowMs

        val observedMs = vrh2LastPlayoutBufferMs
        val underflows = vrh2UnderflowEventsSinceTune
        vrh2UnderflowEventsSinceTune = 0

        var target = vrh2AdaptiveTargetBufferMs

        // Bias strongly toward avoiding underruns; reduce target slowly.
        if (underflows > 0 || observedMs < 80) {
            target = (target + 50).coerceAtMost(vrh2MaxTargetBufferMs)
        } else if (observedMs < target - 120) {
            target = (target + 10).coerceAtMost(vrh2MaxTargetBufferMs)
        } else if (observedMs > target + 200) {
            target = (target - 10).coerceAtLeast(vrh2MinTargetBufferMs)
        } else if (observedMs > target + 120) {
            target = (target - 5).coerceAtLeast(vrh2MinTargetBufferMs)
        }

        if (target != vrh2AdaptiveTargetBufferMs) {
            vrh2AdaptiveTargetBufferMs = target
            Log.d(
                TAG,
                "H.264: adaptive playout target=${target}ms (buffer=${observedMs}ms, underflows=${underflows}, protocol=$streamProtocol)"
            )
        }
    }

    private fun maybeRequestIdr(isRight: Boolean, reason: String) {
        val now = android.os.SystemClock.uptimeMillis()
        val last = if (isRight) lastRightNeedIdrRequestAtMs else lastLeftNeedIdrRequestAtMs
        // Rate-limit to avoid spamming the server.
        if (now - last < 2000) return
        if (isRight) lastRightNeedIdrRequestAtMs = now else lastLeftNeedIdrRequestAtMs = now
        networkReceiver?.requestIdr()
        Log.i(TAG, "H.264: ${if (isRight) "R" else "L"} requested IDR ($reason) (protocol=$streamProtocol)")
    }

    private fun byteArrayStartsWith(data: ByteArray, prefix: ByteArray): Boolean {
        if (data.size < prefix.size) return false
        for (i in prefix.indices) {
            if (data[i] != prefix[i]) return false
        }
        return true
    }

    private fun looksLikeAnnexBAccessUnitWithSlice(data: ByteArray): Boolean {
        // Basic sanity: VRH2 should be Annex-B and contain at least one slice NAL (type 1 or 5).
        if (data.size < 5) return false
        if (!(byteArrayStartsWith(data, byteArrayOf(0, 0, 1)) || byteArrayStartsWith(data, byteArrayOf(0, 0, 0, 1)))) {
            return false
        }

        var hasSlice = false
        val n = data.size
        var i = 0
        while (i + 4 < n) {
            var startLen = 0
            if (data[i] == 0.toByte() && data[i + 1] == 0.toByte()) {
                if (data[i + 2] == 1.toByte()) {
                    startLen = 3
                } else if (data[i + 2] == 0.toByte() && data[i + 3] == 1.toByte()) {
                    startLen = 4
                }
            }
            if (startLen > 0) {
                val hdr = i + startLen
                if (hdr < n) {
                    val nalType = (data[hdr].toInt() and 0x1F)
                    if (nalType == 1 || nalType == 5) {
                        hasSlice = true
                        break
                    }
                }
                i = hdr
            } else {
                i++
            }
        }
        return hasSlice
    }

    private val h264InitLock = Any()
    @Volatile private var h264InitInProgress: Boolean = false
    
    // Performance tracking
    private var framesReceived = 0
    private var bytesReceived: Long = 0
    private var lastStatsTime = System.currentTimeMillis()
    private var decodeStartTime: Long = 0
    private var decodeTimes = mutableListOf<Long>()
    private var renderTimes = mutableListOf<Long>()
    
    enum class StreamProtocol {
        UNKNOWN,
        VRHP,  // JPEG encoding
        VRH2,  // H.264 encoding (legacy header)
        VRH3   // H.264 encoding (extended header)
    }

    private fun isH264Protocol(protocol: StreamProtocol): Boolean {
        return protocol == StreamProtocol.VRH2 || protocol == StreamProtocol.VRH3
    }
    
    companion object {
        private const val TAG = "MesmerVisor"

        private const val PERMISSION_REQUEST_CODE = 1
        private const val DISCOVERY_PORT = 5556  // UDP: Client sends hello, server listens
        private const val DEFAULT_STREAMING_PORT = 5555  // TCP: Video streaming

        // If true, skip UDP discovery and connect directly.
        // NOTE: Keep this false by default; enabling it with the device's own IP will
        // cause the client to connect to itself.
        private const val FORCE_SERVER_IP_ENABLED = false
        private const val FORCE_SERVER_IP = "192.168.1.150"
        
        // Vertex shader - simple passthrough
        private const val VERTEX_SHADER = """
            attribute vec4 aPosition;
            attribute vec2 aTexCoord;
            varying vec2 vTexCoord;
            
            void main() {
                gl_Position = aPosition;
                vTexCoord = aTexCoord;
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

        // Fragment shader for SurfaceTexture external textures (MediaCodec surface decode)
        private const val OES_FRAGMENT_SHADER = """
            #extension GL_OES_EGL_image_external : require
            precision mediump float;
            varying vec2 vTexCoord;
            uniform samplerExternalOES uTexture;
            uniform mat4 uTexMatrix;

            void main() {
                vec4 tc = uTexMatrix * vec4(vTexCoord, 0.0, 1.0);
                gl_FragColor = texture2D(uTexture, tc.xy);
            }
        """
    }
    
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        
        // Keep screen on
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        
        // Request permissions
        if (!checkPermissions()) {
            requestPermissions()
        }
        
        // Setup GLSurfaceView - handles threading properly!
        glSurfaceView = GLSurfaceView(this)
        glSurfaceView.setEGLContextClientVersion(3) // OpenGL ES 3.0
        glSurfaceView.setRenderer(this)
        glSurfaceView.renderMode = GLSurfaceView.RENDERMODE_WHEN_DIRTY  // Switch to continuous while streaming
        setContentView(glSurfaceView)

        // SurfaceTexture frame-available callbacks require a Looper.
        // We use a dedicated thread so callbacks remain responsive even under UI load.
        surfaceTextureCallbackThread = HandlerThread("SurfaceTextureCallbacks").apply { start() }
        surfaceTextureCallbackHandler = Handler(surfaceTextureCallbackThread!!.looper)

        resolvedDisplayLayout = resolveDisplayLayout()
        applyOrientationForLayout(resolvedDisplayLayout)
        
        // Start automatic server discovery (or direct connect, if enabled)
        startStreamingOrDiscover()
    }

    private fun startStreamingOrDiscover() {
        val localIp = getLocalIpv4Address()
        if (FORCE_SERVER_IP_ENABLED) {
            if (localIp != null && FORCE_SERVER_IP == localIp) {
                Log.w(TAG, "Direct connect IP equals device IP ($localIp); falling back to discovery")
                startAutoDiscovery()
                return
            }
            Log.i(TAG, "Direct connect enabled -> ${FORCE_SERVER_IP}:${DEFAULT_STREAMING_PORT}")
            runOnUiThread {
                Toast.makeText(this, "Direct connect: ${FORCE_SERVER_IP}", Toast.LENGTH_SHORT).show()
            }
            connectToServer(FORCE_SERVER_IP, DEFAULT_STREAMING_PORT)
            return
        }
        startAutoDiscovery()
    }

    private fun getLocalIpv4Address(): String? {
        return try {
            val interfaces = NetworkInterface.getNetworkInterfaces()
            while (interfaces.hasMoreElements()) {
                val nif = interfaces.nextElement()
                if (!nif.isUp || nif.isLoopback) continue
                val addrs = nif.inetAddresses
                while (addrs.hasMoreElements()) {
                    val addr = addrs.nextElement()
                    if (addr is Inet4Address && !addr.isLoopbackAddress) {
                        val ip = addr.hostAddress
                        if (ip != null && ip != "127.0.0.1") return ip
                    }
                }
            }
            null
        } catch (_: Exception) {
            null
        }
    }
    
    // GLSurfaceView.Renderer methods
    override fun onSurfaceCreated(gl: GL10?, config: EGLConfig?) {
        // Called when surface is created - on GL thread
        GLES30.glClearColor(clearR, clearG, clearB, 1.0f)
        
        // Compile shaders
        val vertexShader = loadShader(GLES30.GL_VERTEX_SHADER, VERTEX_SHADER)
        val fragmentShader = loadShader(GLES30.GL_FRAGMENT_SHADER, FRAGMENT_SHADER)

        val oesFragmentShader = loadShader(GLES30.GL_FRAGMENT_SHADER, OES_FRAGMENT_SHADER)
        
        // Create program
        shaderProgram = GLES30.glCreateProgram()
        GLES30.glAttachShader(shaderProgram, vertexShader)
        GLES30.glAttachShader(shaderProgram, fragmentShader)
        GLES30.glLinkProgram(shaderProgram)

        // Create OES program (same vertex shader, different fragment shader)
        oesShaderProgram = GLES30.glCreateProgram()
        GLES30.glAttachShader(oesShaderProgram, vertexShader)
        GLES30.glAttachShader(oesShaderProgram, oesFragmentShader)
        GLES30.glLinkProgram(oesShaderProgram)
        
        // Get attribute/uniform locations
        positionHandle = GLES30.glGetAttribLocation(shaderProgram, "aPosition")
        texCoordHandle = GLES30.glGetAttribLocation(shaderProgram, "aTexCoord")
        textureHandle = GLES30.glGetUniformLocation(shaderProgram, "uTexture")

        oesPositionHandle = GLES30.glGetAttribLocation(oesShaderProgram, "aPosition")
        oesTexCoordHandle = GLES30.glGetAttribLocation(oesShaderProgram, "aTexCoord")
        oesTextureHandle = GLES30.glGetUniformLocation(oesShaderProgram, "uTexture")
        oesTexMatrixHandle = GLES30.glGetUniformLocation(oesShaderProgram, "uTexMatrix")
        
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

        // External OES textures for MediaCodec surface decode (VRH2)
        leftOesTexId = createExternalOesTexture()
        rightOesTexId = createExternalOesTexture()

        leftSurfaceTexture = SurfaceTexture(leftOesTexId)
        rightSurfaceTexture = SurfaceTexture(rightOesTexId)

        // Only update SurfaceTextures when a new decoded frame arrives.
        // Calling updateTexImage() every vsync can block the GL thread on some devices.
        val cbHandler = surfaceTextureCallbackHandler ?: Handler(Looper.getMainLooper())
        if (android.os.Build.VERSION.SDK_INT >= 21) {
            leftSurfaceTexture?.setOnFrameAvailableListener({
                leftSurfaceFrameAvailable = true
                leftOnFrameAvailableCount++
                leftLastOnFrameAvailableNs = System.nanoTime()
            }, cbHandler)
            rightSurfaceTexture?.setOnFrameAvailableListener({
                rightSurfaceFrameAvailable = true
                rightOnFrameAvailableCount++
                rightLastOnFrameAvailableNs = System.nanoTime()
            }, cbHandler)
        } else {
            // Fallback: ensure we register on a thread with a Looper.
            runOnUiThread {
                leftSurfaceTexture?.setOnFrameAvailableListener {
                    leftSurfaceFrameAvailable = true
                    leftOnFrameAvailableCount++
                    leftLastOnFrameAvailableNs = System.nanoTime()
                }
                rightSurfaceTexture?.setOnFrameAvailableListener {
                    rightSurfaceFrameAvailable = true
                    rightOnFrameAvailableCount++
                    rightLastOnFrameAvailableNs = System.nanoTime()
                }
            }
        }

        // Default transform is identity until we update from SurfaceTexture.
        for (i in 0 until 16) {
            leftTexMatrix[i] = if (i % 5 == 0) 1f else 0f
            rightTexMatrix[i] = if (i % 5 == 0) 1f else 0f
        }

        leftDecoderSurface = Surface(leftSurfaceTexture)
        rightDecoderSurface = Surface(rightSurfaceTexture)

        // Decoder config will happen once we see SPS/PPS in the stream
        h264Configured = false
        h264Csd0 = null
        h264Csd1 = null
        h264PtsUs = 0
        leftNeedsIdr = false
        rightNeedsIdr = false
        
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

        // Surface size changes can happen during display/orientation switches.
        resolvedDisplayLayout = resolveDisplayLayout()
    }
    
    override fun onDrawFrame(gl: GL10?) {
        // Called every frame - on GL thread
        val renderStart = System.currentTimeMillis()

        // Defensive GL state: prevent state leakage from causing framebuffer accumulation
        // artifacts ("trails") on some devices/drivers.
        GLES30.glDisable(GLES30.GL_BLEND)
        GLES30.glDisable(GLES30.GL_SCISSOR_TEST)
        GLES30.glDisable(GLES30.GL_DEPTH_TEST)
        GLES30.glDisable(GLES30.GL_STENCIL_TEST)
        GLES30.glDisable(GLES30.GL_CULL_FACE)
        GLES30.glColorMask(true, true, true, true)

        // Always reset full viewport first. (Stereo rendering temporarily changes it.)
        if (surfaceWidth > 0 && surfaceHeight > 0) {
            GLES30.glViewport(0, 0, surfaceWidth, surfaceHeight)
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

        if (isStreaming && isH264Protocol(streamProtocol) && h264Configured) {
            // Zero-copy path: MediaCodec outputs into SurfaceTextures, we just sample them.
            val decodeStart = System.currentTimeMillis()
            try {
                val nowNs = System.nanoTime()

                // Primary trigger: OnFrameAvailable callback.
                // Fallback trigger: if the codec is producing output but callbacks stop,
                // force a periodic update so we don't freeze on the first frame.
                val leftShouldUpdate = leftSurfaceFrameAvailable ||
                    (leftCodecReleasedOutputCount > leftUpdateTexImageCount && (nowNs - leftLastUpdateTexImageNs) > 50_000_000L)
                if (leftShouldUpdate) {
                    leftSurfaceTexture?.updateTexImage()
                    leftSurfaceTexture?.getTransformMatrix(leftTexMatrix)
                    leftSurfaceFrameAvailable = false
                    leftLastUpdateTexImageNs = nowNs
                    leftUpdateTexImageCount++
                }
                if (layout == DisplayLayout.VR_STEREO) {
                    val rightShouldUpdate = rightSurfaceFrameAvailable ||
                        (rightCodecReleasedOutputCount > rightUpdateTexImageCount && (nowNs - rightLastUpdateTexImageNs) > 50_000_000L)
                    if (rightShouldUpdate) {
                        rightSurfaceTexture?.updateTexImage()
                        rightSurfaceTexture?.getTransformMatrix(rightTexMatrix)
                        rightSurfaceFrameAvailable = false
                        rightLastUpdateTexImageNs = nowNs
                        rightUpdateTexImageCount++
                    }
                }
            } catch (_: Exception) {
                // Ignore transient SurfaceTexture errors during lifecycle changes.
            }
            val decodeTime = System.currentTimeMillis() - decodeStart
            decodeTimes.add(decodeTime)

            when (layout) {
                DisplayLayout.VR_STEREO -> renderStereoOes()
                DisplayLayout.FULLSCREEN -> renderFullscreenOes(leftOesTexId, leftTexMatrix)
                DisplayLayout.AUTO -> renderFullscreenOes(leftOesTexId, leftTexMatrix)
            }
        } else {
            // JPEG fallback path
            synchronized(frameLock) {
                if (hasFrame && leftFrameData != null && rightFrameData != null) {
                    val decodeStart = System.currentTimeMillis()

                    val leftBitmap = BitmapFactory.decodeByteArray(leftFrameData, 0, leftFrameData!!.size)
                    if (leftBitmap != null) {
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

                    val decodeTime = System.currentTimeMillis() - decodeStart
                    decodeTimes.add(decodeTime)

                    when (layout) {
                        DisplayLayout.VR_STEREO -> renderStereo()
                        DisplayLayout.FULLSCREEN -> renderFullscreen(leftEyeTextureId)
                        DisplayLayout.AUTO -> renderFullscreen(leftEyeTextureId)
                    }
                }
            }
        }
        
        // Track render time and update performance stats
        val renderTime = System.currentTimeMillis() - renderStart
        renderTimes.add(renderTime)
        framesReceived++

        // Lightweight debug stats for the H.264 path (helps diagnose freezes).
        if (framesReceived % 120 == 0 && isStreaming && isH264Protocol(streamProtocol)) {
            Log.d(
                TAG,
                "H.264 dbg: inQ(L/R)=${leftCodecQueuedInputCount}/${rightCodecQueuedInputCount} " +
                    "outRel(L/R)=${leftCodecReleasedOutputCount}/${rightCodecReleasedOutputCount} " +
                    "onFA(L/R)=${leftOnFrameAvailableCount}/${rightOnFrameAvailableCount} " +
                    "upd(L/R)=${leftUpdateTexImageCount}/${rightUpdateTexImageCount} " +
                    "bufMs=${vrh2LastPlayoutBufferMs} target=${vrh2AdaptiveTargetBufferMs} protocol=$streamProtocol"
            )
        }
        
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
            
            println("📊 VR Client Performance Stats (Frame $framesReceived):")
            println("   Client FPS: ${"%.1f".format(clientFPS)}")
            println("   Latency: ${"%.1f".format(totalLatency)}ms (decode: ${"%.1f".format(avgDecode)}ms, render: ${"%.1f".format(avgRender)}ms)")
            println("   Bandwidth: ${"%.2f".format(bandwidthMbps)} Mbps")
            println("   Bytes received: ${bytesReceived / 1024} KB")

            // Send client-side smoothness stats back to server (best-effort, non-blocking).
            // This enables server adaptation based on actual client buffer/pace.
            if (isH264Protocol(streamProtocol)) {
                val bufferMs = vrh2LastPlayoutBufferMs
                val fpsMilli = (clientFPS * 1000.0).toInt()
                val decodeAvgMs = avgDecode.toInt()
                CoroutineScope(Dispatchers.IO).launch {
                    networkReceiver?.sendStats(bufferMs, fpsMilli, decodeAvgMs)
                }
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
        
        // Get viewport dimensions
        val viewport = IntArray(4)
        GLES30.glGetIntegerv(GLES30.GL_VIEWPORT, viewport, 0)
        val width = viewport[2]
        val height = viewport[3]
        
        val videoAspect = getStreamAspect()
        
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

    private fun renderStereoOes() {
        GLES30.glUseProgram(oesShaderProgram)

        GLES30.glEnableVertexAttribArray(oesPositionHandle)
        GLES30.glEnableVertexAttribArray(oesTexCoordHandle)

        GLES30.glActiveTexture(GLES30.GL_TEXTURE0)
        GLES30.glUniform1i(oesTextureHandle, 0)

        val viewport = IntArray(4)
        GLES30.glGetIntegerv(GLES30.GL_VIEWPORT, viewport, 0)
        val width = viewport[2]
        val height = viewport[3]

        val videoAspect = getStreamAspect()
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

        // IMPORTANT: For SurfaceTexture/OES, do NOT pre-flip V. The SurfaceTexture transform
        // matrix already accounts for coordinate origin/rotation/cropping.
        val fullVertices = floatArrayOf(
            -scaleX, -scaleY,         0.0f, 0f,
             scaleX, -scaleY,         1.0f, 0f,
            -scaleX,  scaleY,         0.0f, 1f,
             scaleX,  scaleY,         1.0f, 1f
        )
        val fullBuffer = ByteBuffer.allocateDirect(fullVertices.size * 4)
            .order(ByteOrder.nativeOrder())
            .asFloatBuffer()
            .put(fullVertices)

        // Left eye
        GLES30.glViewport(0, 0, width / 2, height)
        GLES30.glBindTexture(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, leftOesTexId)
        GLES30.glUniformMatrix4fv(oesTexMatrixHandle, 1, false, leftTexMatrix, 0)
        fullBuffer.position(0)
        GLES30.glVertexAttribPointer(oesPositionHandle, 2, GLES30.GL_FLOAT, false, 16, fullBuffer)
        fullBuffer.position(2)
        GLES30.glVertexAttribPointer(oesTexCoordHandle, 2, GLES30.GL_FLOAT, false, 16, fullBuffer)
        GLES30.glDrawArrays(GLES30.GL_TRIANGLE_STRIP, 0, 4)

        // Right eye
        GLES30.glViewport(width / 2, 0, width / 2, height)
        GLES30.glBindTexture(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, rightOesTexId)
        GLES30.glUniformMatrix4fv(oesTexMatrixHandle, 1, false, rightTexMatrix, 0)
        fullBuffer.position(0)
        GLES30.glVertexAttribPointer(oesPositionHandle, 2, GLES30.GL_FLOAT, false, 16, fullBuffer)
        fullBuffer.position(2)
        GLES30.glVertexAttribPointer(oesTexCoordHandle, 2, GLES30.GL_FLOAT, false, 16, fullBuffer)
        GLES30.glDrawArrays(GLES30.GL_TRIANGLE_STRIP, 0, 4)

        GLES30.glViewport(0, 0, width, height)

        GLES30.glDisableVertexAttribArray(oesPositionHandle)
        GLES30.glDisableVertexAttribArray(oesTexCoordHandle)
    }

    private fun renderFullscreenOes(textureId: Int, texMatrix: FloatArray) {
        GLES30.glUseProgram(oesShaderProgram)

        GLES30.glEnableVertexAttribArray(oesPositionHandle)
        GLES30.glEnableVertexAttribArray(oesTexCoordHandle)

        GLES30.glActiveTexture(GLES30.GL_TEXTURE0)
        GLES30.glUniform1i(oesTextureHandle, 0)

        val viewport = IntArray(4)
        GLES30.glGetIntegerv(GLES30.GL_VIEWPORT, viewport, 0)
        val width = viewport[2]
        val height = viewport[3]

        val videoAspect = getStreamAspect()
        val screenAspect = width / height.toFloat()

        val scaleX: Float
        val scaleY: Float

        // Fill (center-crop)
        if (screenAspect > videoAspect) {
            scaleX = 1.0f
            scaleY = screenAspect / videoAspect
        } else {
            scaleY = 1.0f
            scaleX = videoAspect / screenAspect
        }

        // IMPORTANT: For SurfaceTexture/OES, do NOT pre-flip V. The SurfaceTexture transform
        // matrix already accounts for coordinate origin/rotation/cropping.
        val fullVertices = floatArrayOf(
            -scaleX, -scaleY,         0.0f, 0f,
             scaleX, -scaleY,         1.0f, 0f,
            -scaleX,  scaleY,         0.0f, 1f,
             scaleX,  scaleY,         1.0f, 1f
        )
        val fullBuffer = ByteBuffer.allocateDirect(fullVertices.size * 4)
            .order(ByteOrder.nativeOrder())
            .asFloatBuffer()
            .put(fullVertices)

        GLES30.glBindTexture(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, textureId)
        GLES30.glUniformMatrix4fv(oesTexMatrixHandle, 1, false, texMatrix, 0)

        fullBuffer.position(0)
        GLES30.glVertexAttribPointer(oesPositionHandle, 2, GLES30.GL_FLOAT, false, 16, fullBuffer)
        fullBuffer.position(2)
        GLES30.glVertexAttribPointer(oesTexCoordHandle, 2, GLES30.GL_FLOAT, false, 16, fullBuffer)
        GLES30.glDrawArrays(GLES30.GL_TRIANGLE_STRIP, 0, 4)

        GLES30.glDisableVertexAttribArray(oesPositionHandle)
        GLES30.glDisableVertexAttribArray(oesTexCoordHandle)
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

        // Get viewport dimensions
        val viewport = IntArray(4)
        GLES30.glGetIntegerv(GLES30.GL_VIEWPORT, viewport, 0)
        val width = viewport[2]
        val height = viewport[3]

        val videoAspect = getStreamAspect()
        val screenAspect = width / height.toFloat()

        val scaleX: Float
        val scaleY: Float

        // Fullscreen for flat devices: fill the screen (center-crop). This avoids letterboxing.
        if (screenAspect > videoAspect) {
            // Screen is wider than video - fill width, crop top/bottom
            scaleX = 1.0f
            scaleY = screenAspect / videoAspect
        } else {
            // Screen is taller than video - fill height, crop left/right
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

    private fun getStreamAspect(): Float {
        val w = h264Width ?: 2048
        val h = h264Height ?: 1024
        return w.toFloat() / h.toFloat()
    }

    private fun applyOrientationForLayout(layout: DisplayLayout) {
        // Phones/TVs should always be landscape.
        // VR headsets often manage orientation differently; keep it flexible.
        requestedOrientation = when (layout) {
            DisplayLayout.FULLSCREEN -> ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE
            DisplayLayout.VR_STEREO -> ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED
            DisplayLayout.AUTO -> ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE
        }
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
        return packageManager.hasSystemFeature(PackageManager.FEATURE_LEANBACK)
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
        val combined = "$mfg $model $device $product"

        return listOf(
            "oculus",
            "meta",
            "quest",
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
        if (FORCE_SERVER_IP_ENABLED) {
            // Avoid discovery if direct-connect is configured.
            Log.i(TAG, "Discovery skipped (direct connect enabled)")
            return
        }

        if (isConnecting || isStreaming) {
            Log.i(TAG, "Discovery skipped (connecting/streaming)")
            return
        }

        updateStatus("SEARCHING\nFOR\nSERVER", Color.BLUE)

        Log.i(TAG, "Starting UDP discovery on port=$DISCOVERY_PORT")
        
        // CRITICAL FIX: Always stop existing discovery before creating new one
        discoveryService?.stop()
        discoveryService = null
        
        discoveryService = DiscoveryService(this, DISCOVERY_PORT, DEFAULT_STREAMING_PORT) { serverIp, serverPort ->
            runOnUiThread {
                updateStatus("SERVER\nFOUND\nCONNECTING", Color.GREEN)

                Log.i(TAG, "Discovered server $serverIp:$serverPort")

                // Debounce: stop discovery immediately and connect once.
                if (isConnecting || isStreaming) {
                    Log.i(TAG, "Ignoring discovery result (already connecting/streaming)")
                    return@runOnUiThread
                }
                isConnecting = true
                discoveryService?.stop()
                discoveryService = null
                
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
            Log.i(TAG, "connectToServer ignored: already streaming")
            return
        }

        // Ensure discovery is stopped so we don't connect repeatedly.
        discoveryService?.stop()
        discoveryService = null

        // Stop any existing receiver before starting a new one.
        try {
            networkReceiver?.stop()
        } catch (_: Exception) {
        }
        networkReceiver = null

        isConnecting = true
        updateStatus("STREAMING\nSTARTING", Color.rgb(255, 165, 0))

        Log.i(TAG, "Connecting to server $ip:$port")
        
        // Create network receiver with disconnect handler
        networkReceiver = NetworkReceiver(ip, port, 
            // Frame received callback
            onFrameReceived = { leftData, rightData, protocol, frameId, fpsMilli ->
                // Detect and initialize decoders on first frame
                if (streamProtocol == StreamProtocol.UNKNOWN && protocol != StreamProtocol.UNKNOWN) {
                    streamProtocol = protocol
                    runOnUiThread {
                        val protocolName = when(protocol) {
                            StreamProtocol.VRH2 -> "H.264 (GPU)"
                            StreamProtocol.VRH3 -> "H.264 (GPU) [VRH3]"
                            StreamProtocol.VRHP -> "JPEG (CPU)"
                            else -> "UNKNOWN"
                        }
                        Toast.makeText(this, "Protocol: $protocolName", Toast.LENGTH_SHORT).show()
                    }

                    Log.i(TAG, "Protocol detected: $protocol")
                    
                    // Initialize H.264 decoders if needed
                    if (isH264Protocol(protocol)) {
                        // Configure decoders once we see SPS/PPS; for now just mark protocol.
                    }
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

                        // Render continuously while streaming for vsync-paced smoothness
                        glSurfaceView.renderMode = GLSurfaceView.RENDERMODE_CONTINUOUSLY
                    }
                }

                // Track bytes received for bandwidth calculation
                bytesReceived += leftData.size.toLong() + rightData.size.toLong()

                if (isH264Protocol(protocol)) {
                    // Hardware decode path
                    handleH264Frames(leftData, rightData, frameId, fpsMilli)
                    hasFrame = true
                } else {
                    // Store frame data for software/JPEG rendering
                    synchronized(frameLock) {
                        leftFrameData = leftData
                        rightFrameData = rightData
                        hasFrame = true
                    }
                    // If not in continuous mode (should be), request redraw
                    runOnUiThread { glSurfaceView.requestRender() }
                }
            },
            // Disconnect callback - RESTART DISCOVERY
            onDisconnected = {
                Log.w(TAG, "Connection lost. Restarting discovery...")
                
                // Clean up streaming state
                isStreaming = false
                isConnecting = false
                streamProtocol = StreamProtocol.UNKNOWN
                networkReceiver = null

                h264Configured = false
                h264Csd0 = null
                h264Csd1 = null
                h264Width = null
                h264Height = null
                
                // Clear frame data and reset display to blue searching screen
                synchronized(frameLock) {
                    hasFrame = false
                    leftFrameData = null
                    rightFrameData = null
                }
                
                // Reset clear color to blue (searching status)
                runOnUiThread {
                    clearR = 0.0f
                    clearG = 0.0f
                    clearB = 1.0f
                    glSurfaceView.renderMode = GLSurfaceView.RENDERMODE_WHEN_DIRTY
                    glSurfaceView.requestRender()  // Force redraw with blue background
                }
                
                // CRITICAL FIX: Stop old discovery service before starting new one
                discoveryService?.stop()
                discoveryService = null
                
                // Small delay to ensure socket is fully released
                Thread.sleep(500)
                
                // Restart discovery to find server again
                if (FORCE_SERVER_IP_ENABLED) {
                    Log.i(TAG, "Direct connect enabled -> reconnecting to ${FORCE_SERVER_IP}:${DEFAULT_STREAMING_PORT}")
                    connectToServer(FORCE_SERVER_IP, DEFAULT_STREAMING_PORT)
                } else {
                    startAutoDiscovery()
                }
            }
        )
        
        networkReceiver?.start()
    }

    private fun handleH264Frames(leftData: ByteArray, rightData: ByteArray, frameId: Int, fpsMilli: Int) {
        if (fpsMilli > 0) {
            vrh2FpsMilli = fpsMilli
        }

        // Avoid racing decoder initialization across multiple frames/threads.
        synchronized(h264InitLock) {
            if (!h264Configured && h264InitInProgress) {
                return
            }
            if (!h264Configured) {
                h264InitInProgress = true
            }
        }

        // Extract SPS/PPS once, then configure decoders.
        if (!h264Configured) {
            try {
                if (leftDecoderSurface == null || (resolvedDisplayLayout == DisplayLayout.VR_STEREO && rightDecoderSurface == null)) {
                    Log.w(TAG, "H.264: decoder surfaces not ready yet; deferring init (protocol=$streamProtocol)")
                    return
                }

                if (h264Csd0 == null || h264Csd1 == null) {
                    val (sps, pps) = extractSpsPps(leftData) ?: Pair(null, null)
                    if (sps != null && pps != null) {
                        h264Csd0 = sps
                        h264Csd1 = pps

                        val spsNoStart = stripAnnexBStartCode(sps)
                        val dims = parseSpsDimensions(spsNoStart)
                        if (dims != null) {
                            h264Width = dims.first
                            h264Height = dims.second
                        }

                        Log.i(
                            TAG,
                            "H.264: SPS/PPS found. spsBytes=${sps.size} ppsBytes=${pps.size} (protocol=$streamProtocol) " +
                                "spsNoStart=${spsNoStart.size} dims=${h264Width}x${h264Height} " +
                                "spsHead=${toHexPrefix(spsNoStart, 16)} ppsHead=${toHexPrefix(stripAnnexBStartCode(pps), 16)}"
                        )
                    }
                }

                if (h264Csd0 == null || h264Csd1 == null) {
                    // Not enough codec config yet; wait for next frames.
                    return
                }

                configureH264Decoders(h264Csd0!!, h264Csd1!!)
                h264Configured = true

                // Ask the server for a clean keyframe soon after (re)configure.
                // This shortens any mosaic time if we ever start mid-GOP or hit transient corruption.
                maybeRequestIdr(isRight = false, reason = "post-config")

                runOnUiThread {
                    val protoLabel = when (streamProtocol) {
                        StreamProtocol.VRH3 -> "VRH3"
                        StreamProtocol.VRH2 -> "VRH2"
                        else -> "H.264"
                    }
                    Toast.makeText(this, "$protoLabel: hardware decode enabled", Toast.LENGTH_SHORT).show()
                }
                Log.i(TAG, "H.264: MediaCodec configured OK (protocol=$streamProtocol)")
            } catch (e: Exception) {
                Log.e(TAG, "H.264 decode init failed (protocol=$streamProtocol)", e)
                Log.e(TAG, "H.264 init context: dims=${h264Width}x${h264Height} leftBytes=${leftData.size} rightBytes=${rightData.size} layout=$resolvedDisplayLayout")
                logAvcDecoderCandidates()
                runOnUiThread {
                    Toast.makeText(this, "H.264 decode init failed: ${e.message}", Toast.LENGTH_LONG).show()
                }
                return
            } finally {
                synchronized(h264InitLock) {
                    h264InitInProgress = false
                }
            }
        }

        // Feed access units into decoders.
        // NOTE: We treat each packet as a complete access unit (typical with our server).
        feedDecoder(leftDecoder, leftData, isRight = false, frameId = frameId, fpsMilli = vrh2FpsMilli)
        if (resolvedDisplayLayout == DisplayLayout.VR_STEREO) {
            feedDecoder(rightDecoder, rightData, isRight = true, frameId = frameId, fpsMilli = vrh2FpsMilli)
        }
    }

    private fun configureH264Decoders(csd0: ByteArray, csd1: ByteArray) {
        synchronized(h264InitLock) {
            // Ensure configure/start can't overlap with itself.
        }

        // Prefer SPS-derived dimensions when available; fall back to historical default.
        val width = h264Width ?: 2048
        val height = h264Height ?: 1024

        // Ensure SurfaceTexture buffer sizes match decoder output.
        try {
            leftSurfaceTexture?.setDefaultBufferSize(width, height)
            rightSurfaceTexture?.setDefaultBufferSize(width, height)
        } catch (_: Exception) {
        }

        val csd0NoStart = stripAnnexBStartCode(csd0)
        val csd1NoStart = stripAnnexBStartCode(csd1)

        Log.i(
            TAG,
            "Configuring AVC decoder width=$width height=$height " +
                "csd0=${csd0.size}->${csd0NoStart.size} csd1=${csd1.size}->${csd1NoStart.size}"
        )

        releaseDecoders()

        // Reset playout scheduling anchors on reconfigure.
        leftPlayoutBasePtsUs = null
        rightPlayoutBasePtsUs = null
        vrh2LastPlayoutBufferMs = 0
        vrh2AdaptiveTargetBufferMs = 250
        vrh2LastTuneAtMs = 0L
        vrh2UnderflowEventsSinceTune = 0
        leftPlayoutBufferMs = 0
        rightPlayoutBufferMs = 0

        leftDecoder = MediaCodec.createDecoderByType(MediaFormat.MIMETYPE_VIDEO_AVC)
        val leftFormat = MediaFormat.createVideoFormat(MediaFormat.MIMETYPE_VIDEO_AVC, width, height)
        // Many devices expect csd buffers WITHOUT Annex-B start codes.
        leftFormat.setByteBuffer("csd-0", ByteBuffer.wrap(csd0NoStart))
        leftFormat.setByteBuffer("csd-1", ByteBuffer.wrap(csd1NoStart))
        leftDecoder?.configure(leftFormat, leftDecoderSurface, null, 0)
        leftDecoder?.start()
        leftNeedsIdr = false
        leftSurfaceFrameAvailable = false
        leftLastUpdateTexImageNs = 0L

        // Only configure right-eye decoder when we are actually in VR stereo mode.
        if (resolvedDisplayLayout == DisplayLayout.VR_STEREO) {
            rightDecoder = MediaCodec.createDecoderByType(MediaFormat.MIMETYPE_VIDEO_AVC)
            val rightFormat = MediaFormat.createVideoFormat(MediaFormat.MIMETYPE_VIDEO_AVC, width, height)
            rightFormat.setByteBuffer("csd-0", ByteBuffer.wrap(csd0NoStart))
            rightFormat.setByteBuffer("csd-1", ByteBuffer.wrap(csd1NoStart))
            rightDecoder?.configure(rightFormat, rightDecoderSurface, null, 0)
            rightDecoder?.start()
            rightNeedsIdr = false
            rightSurfaceFrameAvailable = false
            rightLastUpdateTexImageNs = 0L
        } else {
            rightDecoder = null
            rightNeedsIdr = false
            rightSurfaceFrameAvailable = false
        }
    }

    private fun stripAnnexBStartCode(nal: ByteArray): ByteArray {
        if (nal.size >= 4 && nal[0] == 0.toByte() && nal[1] == 0.toByte()) {
            if (nal[2] == 1.toByte()) {
                return nal.copyOfRange(3, nal.size)
            }
            if (nal[2] == 0.toByte() && nal[3] == 1.toByte()) {
                return nal.copyOfRange(4, nal.size)
            }
        }
        return nal
    }

    private fun toHexPrefix(data: ByteArray, maxBytes: Int): String {
        val n = minOf(maxBytes, data.size)
        val sb = StringBuilder(n * 3)
        for (i in 0 until n) {
            sb.append(String.format("%02X", data[i]))
            if (i + 1 < n) sb.append(' ')
        }
        return sb.toString()
    }

    private fun logAvcDecoderCandidates() {
        try {
            val list = MediaCodecList(MediaCodecList.ALL_CODECS)
            val infos = list.codecInfos
            val avc = infos.filter { !it.isEncoder && it.supportedTypes.any { t -> t.equals(MediaFormat.MIMETYPE_VIDEO_AVC, ignoreCase = true) } }
            Log.e(TAG, "AVC decoders found: ${avc.size}")
            for (info in avc.take(15)) {
                val caps = try {
                    info.getCapabilitiesForType(MediaFormat.MIMETYPE_VIDEO_AVC)
                } catch (_: Exception) {
                    null
                }
                val prof = caps?.profileLevels?.joinToString(prefix = "[", postfix = "]") { pl -> "${pl.profile}/${pl.level}" } ?: "[]"
                Log.e(TAG, "- ${info.name} hw=${info.isHardwareAccelerated} sw=${info.isSoftwareOnly} vendor=${info.isVendor} profiles=$prof")
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to enumerate MediaCodec decoders", e)
        }
    }

    private fun parseSpsDimensions(spsNalNoStart: ByteArray): Pair<Int, Int>? {
        // Very small SPS parser: expects NAL type 7 with the NAL header byte included.
        // Returns (width,height) in pixels, or null if parsing fails.
        if (spsNalNoStart.isEmpty()) return null

        // spsNalNoStart[0] is NAL header (forbidden_zero_bit + nal_ref_idc + nal_unit_type)
        val nalType = (spsNalNoStart[0].toInt() and 0x1F)
        if (nalType != 7) return null

        val rbsp = removeEmulationPreventionBytes(spsNalNoStart.copyOfRange(1, spsNalNoStart.size))
        val br = BitReader(rbsp)
        return try {
            val profileIdc = br.readBits(8)
            br.readBits(8) // constraint_set flags + reserved
            br.readBits(8) // level_idc
            readUe(br) // seq_parameter_set_id

            val chromaFormatIdc = if (profileIdc in setOf(100, 110, 122, 244, 44, 83, 86, 118, 128, 138, 139, 134, 135)) {
                val cfi = readUe(br)
                if (cfi == 3) {
                    br.readBits(1) // separate_colour_plane_flag
                }
                readUe(br) // bit_depth_luma_minus8
                readUe(br) // bit_depth_chroma_minus8
                br.readBits(1) // qpprime_y_zero_transform_bypass_flag
                val scaling = br.readBits(1)
                if (scaling == 1) {
                    // Skip scaling lists (not needed for dimensions)
                    val count = if (cfi != 3) 8 else 12
                    for (i in 0 until count) {
                        val present = br.readBits(1)
                        if (present == 1) {
                            skipScalingList(br, if (i < 6) 16 else 64)
                        }
                    }
                }
                cfi
            } else {
                1
            }

            readUe(br) // log2_max_frame_num_minus4
            val picOrderCntType = readUe(br)
            if (picOrderCntType == 0) {
                readUe(br) // log2_max_pic_order_cnt_lsb_minus4
            } else if (picOrderCntType == 1) {
                br.readBits(1) // delta_pic_order_always_zero_flag
                readSe(br) // offset_for_non_ref_pic
                readSe(br) // offset_for_top_to_bottom_field
                val numRef = readUe(br)
                for (i in 0 until numRef) {
                    readSe(br)
                }
            }

            readUe(br) // max_num_ref_frames
            br.readBits(1) // gaps_in_frame_num_value_allowed_flag
            val picWidthInMbsMinus1 = readUe(br)
            val picHeightInMapUnitsMinus1 = readUe(br)
            val frameMbsOnlyFlag = br.readBits(1)
            if (frameMbsOnlyFlag == 0) {
                br.readBits(1) // mb_adaptive_frame_field_flag
            }
            br.readBits(1) // direct_8x8_inference_flag
            val frameCroppingFlag = br.readBits(1)

            var cropLeft = 0
            var cropRight = 0
            var cropTop = 0
            var cropBottom = 0
            if (frameCroppingFlag == 1) {
                cropLeft = readUe(br)
                cropRight = readUe(br)
                cropTop = readUe(br)
                cropBottom = readUe(br)
            }

            val width = (picWidthInMbsMinus1 + 1) * 16
            val height = (picHeightInMapUnitsMinus1 + 1) * 16 * (if (frameMbsOnlyFlag == 1) 1 else 2)

            // Crop units depend on chroma_format_idc.
            val cropUnitX = when (chromaFormatIdc) {
                0 -> 1
                1, 2 -> 2
                3 -> 1
                else -> 1
            }
            val cropUnitY = when (chromaFormatIdc) {
                0 -> 2 - frameMbsOnlyFlag
                1 -> 2 * (2 - frameMbsOnlyFlag)
                2 -> 1 * (2 - frameMbsOnlyFlag)
                3 -> 1 * (2 - frameMbsOnlyFlag)
                else -> 2 - frameMbsOnlyFlag
            }

            val croppedW = width - (cropLeft + cropRight) * cropUnitX
            val croppedH = height - (cropTop + cropBottom) * cropUnitY
            Pair(croppedW, croppedH)
        } catch (_: Exception) {
            null
        }
    }

    private fun removeEmulationPreventionBytes(data: ByteArray): ByteArray {
        val out = ByteArray(data.size)
        var j = 0
        var zeros = 0
        for (i in data.indices) {
            val b = data[i]
            if (zeros == 2 && b == 0x03.toByte()) {
                zeros = 0
                continue
            }
            out[j++] = b
            if (b == 0.toByte()) zeros++ else zeros = 0
        }
        return out.copyOfRange(0, j)
    }

    private class BitReader(private val data: ByteArray) {
        private var bitPos = 0

        fun readBits(n: Int): Int {
            var v = 0
            for (_i in 0 until n) {
                val byteIndex = bitPos / 8
                val shift = 7 - (bitPos % 8)
                val bit = (data[byteIndex].toInt() ushr shift) and 1
                v = (v shl 1) or bit
                bitPos++
            }
            return v
        }

        fun readBit(): Int = readBits(1)
    }

    private fun readUe(br: BitReader): Int {
        var zeros = 0
        while (br.readBit() == 0) {
            zeros++
        }
        var v = 1
        for (_i in 0 until zeros) {
            v = (v shl 1) or br.readBit()
        }
        return v - 1
    }

    private fun readSe(br: BitReader): Int {
        val ueVal = readUe(br)
        val sign = if ((ueVal and 1) == 0) -1 else 1
        return sign * ((ueVal + 1) / 2)
    }

    private fun skipScalingList(br: BitReader, size: Int) {
        var lastScale = 8
        var nextScale = 8
        for (_i in 0 until size) {
            if (nextScale != 0) {
                val deltaScale = readSe(br)
                nextScale = (lastScale + deltaScale + 256) % 256
            }
            lastScale = if (nextScale == 0) lastScale else nextScale
        }
    }

    private fun feedDecoder(decoder: MediaCodec?, accessUnit: ByteArray, isRight: Boolean, frameId: Int, fpsMilli: Int) {
        if (decoder == null) return
        val t0 = System.nanoTime()
        try {
            val isIdr = containsIdr(accessUnit)
            val needsIdr = if (isRight) rightNeedsIdr else leftNeedsIdr

            // If we ever get non-AnnexB / no-slice data, treat it as corruption and resync.
            // (Do NOT size-gate normal P-frames; they can be legitimately small.)
            if (!isIdr && !looksLikeAnnexBAccessUnitWithSlice(accessUnit)) {
                if (isRight) rightNeedsIdr = true else leftNeedsIdr = true
                Log.w(TAG, "H.264: ${if (isRight) "R" else "L"} invalid AU; bytes=${accessUnit.size} -> waiting for IDR (protocol=$streamProtocol)")
                maybeRequestIdr(isRight, reason = "invalid-au")
                return
            }
            if (needsIdr && !isIdr) {
                // We dropped a frame earlier; wait for the next keyframe to avoid mosaic corruption.
                maybeRequestIdr(isRight, reason = "waiting-for-idr")
                return
            }

            // Smoothness-first behavior:
            // If the decoder is temporarily backpressured, block/wait for a while rather than
            // dropping frames (dropping P-frames breaks references and causes mosaics).
            // Latency can grow; that's OK per current priority.
            val dequeueStepUs = 50_000L  // 50ms
            val maxWaitUs = 500_000L     // 500ms total before treating codec as stuck

            fun drainOutputNonBlocking() {
                val bufferInfo = MediaCodec.BufferInfo()
                var outIndex = decoder.dequeueOutputBuffer(bufferInfo, 0)
                while (outIndex >= 0) {
                    if (android.os.Build.VERSION.SDK_INT >= 21) {
                        val nowNs = System.nanoTime()
                        if (isRight) {
                            if (rightPlayoutBasePtsUs == null) {
                                rightPlayoutBasePtsUs = bufferInfo.presentationTimeUs
                                rightPlayoutBaseNs = nowNs + (vrh2AdaptiveTargetBufferMs.toLong() * 1_000_000L)
                            }
                            val basePts = rightPlayoutBasePtsUs ?: bufferInfo.presentationTimeUs
                            val desiredNs0 = rightPlayoutBaseNs + ((bufferInfo.presentationTimeUs - basePts) * 1000L)
                            val wasLate = desiredNs0 < nowNs
                            val clampedNs = if (wasLate) nowNs else desiredNs0
                            decoder.releaseOutputBuffer(outIndex, clampedNs)
                            rightCodecReleasedOutputCount++
                            val bufferMs = ((clampedNs - nowNs) / 1_000_000L).toInt()
                            rightPlayoutBufferMs = bufferMs.coerceAtLeast(0)
                            vrh2LastPlayoutBufferMs = if (resolvedDisplayLayout == DisplayLayout.VR_STEREO) {
                                minOf(leftPlayoutBufferMs, rightPlayoutBufferMs)
                            } else {
                                leftPlayoutBufferMs
                            }

                            if (wasLate) vrh2UnderflowEventsSinceTune++
                            tuneH264PlayoutTargetBuffer()

                            // Gently steer the base timestamp so the scheduled buffer tracks the target.
                            // This helps smooth playback when jitter changes over time.
                            val targetNs = vrh2AdaptiveTargetBufferMs.toLong() * 1_000_000L
                            val bufferNs = clampedNs - nowNs
                            val errorNs = targetNs - bufferNs
                            val adjustNs = (errorNs / 10).coerceIn(-4_000_000L, 4_000_000L)
                            rightPlayoutBaseNs += adjustNs

                            // If we underflowed, we're already late; rebase aggressively so we can rebuild
                            // the desired playout buffer instead of staying stuck at ~0ms forever.
                            if (wasLate) {
                                val deltaNs = (bufferInfo.presentationTimeUs - basePts) * 1000L
                                rightPlayoutBaseNs = nowNs + targetNs - deltaNs
                            }
                        } else {
                            if (leftPlayoutBasePtsUs == null) {
                                leftPlayoutBasePtsUs = bufferInfo.presentationTimeUs
                                leftPlayoutBaseNs = nowNs + (vrh2AdaptiveTargetBufferMs.toLong() * 1_000_000L)
                            }
                            val basePts = leftPlayoutBasePtsUs ?: bufferInfo.presentationTimeUs
                            val desiredNs0 = leftPlayoutBaseNs + ((bufferInfo.presentationTimeUs - basePts) * 1000L)
                            val wasLate = desiredNs0 < nowNs
                            val clampedNs = if (wasLate) nowNs else desiredNs0
                            decoder.releaseOutputBuffer(outIndex, clampedNs)
                            leftCodecReleasedOutputCount++
                            val bufferMs = ((clampedNs - nowNs) / 1_000_000L).toInt()
                            leftPlayoutBufferMs = bufferMs.coerceAtLeast(0)
                            vrh2LastPlayoutBufferMs = if (resolvedDisplayLayout == DisplayLayout.VR_STEREO) {
                                minOf(leftPlayoutBufferMs, rightPlayoutBufferMs)
                            } else {
                                leftPlayoutBufferMs
                            }

                            if (wasLate) vrh2UnderflowEventsSinceTune++
                            tuneH264PlayoutTargetBuffer()

                            val targetNs = vrh2AdaptiveTargetBufferMs.toLong() * 1_000_000L
                            val bufferNs = clampedNs - nowNs
                            val errorNs = targetNs - bufferNs
                            val adjustNs = (errorNs / 10).coerceIn(-4_000_000L, 4_000_000L)
                            leftPlayoutBaseNs += adjustNs

                            if (wasLate) {
                                val deltaNs = (bufferInfo.presentationTimeUs - basePts) * 1000L
                                leftPlayoutBaseNs = nowNs + targetNs - deltaNs
                            }
                        }
                    } else {
                        decoder.releaseOutputBuffer(outIndex, true)
                        vrh2LastPlayoutBufferMs = 0
                        if (isRight) rightCodecReleasedOutputCount++ else leftCodecReleasedOutputCount++
                    }
                    outIndex = decoder.dequeueOutputBuffer(bufferInfo, 0)
                }
            }

            // Drain first: on some devices output needs draining to free pipeline resources.
            drainOutputNonBlocking()

            val waitStartNs = System.nanoTime()
            var inputIndex = -1
            while (inputIndex < 0) {
                val waitedUs = (System.nanoTime() - waitStartNs) / 1000
                if (waitedUs >= maxWaitUs) break
                val remainingUs = maxWaitUs - waitedUs
                val timeoutUs = minOf(dequeueStepUs, remainingUs)
                inputIndex = decoder.dequeueInputBuffer(timeoutUs)
                if (inputIndex < 0) {
                    // Keep draining output while waiting; helps avoid deadlocky states.
                    drainOutputNonBlocking()
                }
            }

            if (inputIndex >= 0) {
                val buf = decoder.getInputBuffer(inputIndex)
                buf?.clear()
                buf?.put(accessUnit)
                // Prefer a stable, deterministic PTS based on frameId/fps. This enables
                // smooth playout scheduling via releaseOutputBuffer(renderTimeNs).
                val effFpsMilli = if (fpsMilli > 0) fpsMilli else 30_000
                val frameDurationUs = (1_000_000L * 1000L) / effFpsMilli.toLong()
                val pts = frameId.toLong() * frameDurationUs
                // For decoders, input flags are generally ignored except EOS; avoid KEY_FRAME here.
                decoder.queueInputBuffer(inputIndex, 0, accessUnit.size, pts, 0)

                if (isRight) rightCodecQueuedInputCount++ else leftCodecQueuedInputCount++

                if (isIdr) {
                    val wasWaiting = if (isRight) rightNeedsIdr else leftNeedsIdr
                    if (isRight) rightNeedsIdr = false else leftNeedsIdr = false
                    if (wasWaiting) {
                        Log.d(TAG, "H.264: ${if (isRight) "R" else "L"} IDR received; decoder resynced (protocol=$streamProtocol)")
                    }
                }
            } else {
                // Codec appears stuck (no input buffer for a long time). At this point, continuing
                // to read/skip frames tends to cause long-lived mosaic. Force a resync.
                if (isRight) rightNeedsIdr = true else leftNeedsIdr = true
                Log.w(TAG, "H.264: ${if (isRight) "R" else "L"} decoder backpressured >${maxWaitUs / 1000}ms; flushing and waiting for IDR (protocol=$streamProtocol)")
                maybeRequestIdr(isRight, reason = "decoder-stuck")
                try {
                    decoder.flush()
                } catch (_: Exception) {
                }
            }

            // Drain output (non-blocking). Rendering happens via SurfaceTexture sampling.
            drainOutputNonBlocking()
        } catch (_: Exception) {
            // Best-effort; decoder can throw during disconnects / reconfigure.
        } finally {
            // Best-effort per-frame codec/decode time sample for H.264.
            // Record only on the left eye to avoid double-counting stereo frames.
            if (!isRight) {
                val dtMs = (System.nanoTime() - t0) / 1_000_000.0
                decodeTimes.add(dtMs)
                if (decodeTimes.size > 240) {
                    decodeTimes.subList(0, decodeTimes.size - 240).clear()
                }
            }
        }
    }

    private fun containsIdr(data: ByteArray): Boolean {
        // Annex-B scan for NAL type 5 (IDR)
        if (data.size < 5) return false
        val n = data.size
        var i = 0
        while (i + 4 < n) {
            var startLen = 0
            if (data[i] == 0.toByte() && data[i + 1] == 0.toByte()) {
                if (data[i + 2] == 1.toByte()) {
                    startLen = 3
                } else if (data[i + 2] == 0.toByte() && data[i + 3] == 1.toByte()) {
                    startLen = 4
                }
            }
            if (startLen > 0) {
                val hdr = i + startLen
                if (hdr < n) {
                    val nalType = (data[hdr].toInt() and 0x1F)
                    if (nalType == 5) return true
                }
                i = hdr
            } else {
                i++
            }
        }
        return false
    }

    private fun extractSpsPps(data: ByteArray): Pair<ByteArray?, ByteArray?>? {
        // Annex-B NAL parsing: look for nal type 7 (SPS) and 8 (PPS)
        if (data.isEmpty()) return null

        fun startsAt(i: Int, len: Int): Boolean {
            if (i + len > data.size) return false
            for (j in 0 until len) {
                if (data[i + j] != 0.toByte()) return false
            }
            return true
        }

        val n = data.size
        val starts = ArrayList<Pair<Int, Int>>()
        var i = 0
        while (i + 3 < n) {
            if (data[i] == 0.toByte() && data[i + 1] == 0.toByte()) {
                if (data[i + 2] == 1.toByte()) {
                    starts.add(Pair(i, 3))
                    i += 3
                    continue
                }
                if (i + 4 < n && data[i + 2] == 0.toByte() && data[i + 3] == 1.toByte()) {
                    starts.add(Pair(i, 4))
                    i += 4
                    continue
                }
            }
            i += 1
        }

        var sps: ByteArray? = null
        var pps: ByteArray? = null

        for (idx in starts.indices) {
            val (pos, startLen) = starts[idx]
            val hdr = pos + startLen
            if (hdr >= n) continue
            val next = if (idx + 1 < starts.size) starts[idx + 1].first else n
            if (next <= hdr) continue
            val nalType = (data[hdr].toInt() and 0x1F)
            if (nalType == 7) {
                sps = data.copyOfRange(pos, next)
            } else if (nalType == 8) {
                pps = data.copyOfRange(pos, next)
            }
            if (sps != null && pps != null) break
        }

        return Pair(sps, pps)
    }
    
    override fun onPause() {
        super.onPause()
        glSurfaceView.onPause()
        discoveryService?.stop()
        networkReceiver?.stop()
        releaseDecoders()
    }
    
    override fun onResume() {
        super.onResume()
        glSurfaceView.onResume()

        resolvedDisplayLayout = resolveDisplayLayout()
        applyOrientationForLayout(resolvedDisplayLayout)
        
        // Resume connection logic.
        if (!isStreaming && !isConnecting) {
            startStreamingOrDiscover()
        }
    }
    
    override fun onDestroy() {
        super.onDestroy()
        discoveryService?.stop()
        networkReceiver?.stop()
        releaseDecoders()

        try {
            surfaceTextureCallbackThread?.quitSafely()
        } catch (_: Exception) {
        }
        surfaceTextureCallbackThread = null
        surfaceTextureCallbackHandler = null
    }
    
    private fun releaseDecoders() {
        try {
            synchronized(h264InitLock) {
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

                // IMPORTANT: Do NOT null decoder surfaces here. They are created on the GL thread
                // and are required for surface decoding.

                h264Configured = false
                leftNeedsIdr = false
                rightNeedsIdr = false
            }
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }
}

/**
 * Discovery Service - Automatically finds the VR server on the network
 */
class DiscoveryService(
    private val context: Context,
    private val discoveryPort: Int,
    private val streamingPort: Int = 5555,  // TCP streaming port (must match server)
    private val onServerFound: (String, Int) -> Unit
) {
    
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
                    val type = detectDeviceTypeForHello()
                    // Backwards-compatible with older servers: they will treat the whole suffix as the name.
                    val message = "VR_HEADSET_HELLO:$deviceName:$type"
                    val broadcastAddr = java.net.InetAddress.getByName("255.255.255.255")
                    val packet = java.net.DatagramPacket(
                        message.toByteArray(),
                        message.length,
                        broadcastAddr,
                        discoveryPort
                    )
                    socket?.send(packet)
                    
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

    private fun detectDeviceTypeForHello(): String {
        return try {
            val pm = context.packageManager

            val uiModeManager = context.getSystemService(Context.UI_MODE_SERVICE) as? UiModeManager
            val modeType = uiModeManager?.currentModeType
            if (modeType == Configuration.UI_MODE_TYPE_TELEVISION || pm.hasSystemFeature(PackageManager.FEATURE_LEANBACK)) {
                return "tv"
            }

            val uiModeType = context.resources.configuration.uiMode and Configuration.UI_MODE_TYPE_MASK
            if (uiModeType == Configuration.UI_MODE_TYPE_VR_HEADSET) {
                return "vr"
            }

            if (pm.hasSystemFeature(PackageManager.FEATURE_VR_MODE_HIGH_PERFORMANCE)) {
                return "vr"
            }

            val mfg = (android.os.Build.MANUFACTURER ?: "").lowercase()
            val model = (android.os.Build.MODEL ?: "").lowercase()
            val device = (android.os.Build.DEVICE ?: "").lowercase()
            val product = (android.os.Build.PRODUCT ?: "").lowercase()
            val combined = "$mfg $model $device $product"

            if (listOf(
                    "oculus",
                    "meta",
                    "quest",
                    "pico",
                    "vive",
                    "htc",
                    "focus",
                    "hololens",
                    "daydream"
                ).any { combined.contains(it) }
            ) {
                return "vr"
            }

            "phone"
        } catch (_: Exception) {
            "phone"
        }
    }
    
    // Remove the sendTcpResponse function - not needed anymore
}

/**
 * Network Receiver - Handles streaming connection
 * 
 * Supports protocol detection:
 * - VRH3: H.264 hardware decoding (preferred)
 * - VRH2: H.264 hardware decoding (legacy)
 * - VRHP: JPEG software decoding
 */
class NetworkReceiver(
    private val serverIp: String,
    private val serverPort: Int,
    private val onFrameReceived: (ByteArray, ByteArray, MainActivity.StreamProtocol, Int, Int) -> Unit,
    private val onDisconnected: () -> Unit  // ← NEW: Callback when connection is lost
) {
    
    private var socket: Socket? = null
    private var outputStream: java.io.OutputStream? = null
    private var isRunning = false
    private var receiveJob: Job? = null
    private var detectedProtocol = MainActivity.StreamProtocol.UNKNOWN

    private val sendLock = Any()
    
    fun start() {
        isRunning = true
        receiveJob = CoroutineScope(Dispatchers.IO).launch {
            connectAndReceive()
        }
    }

    fun requestIdr() {
        // Best-effort: 1-byte control message to ask the server to produce an IDR soon.
        // Safe even if server doesn't support it.
        try {
            val os = outputStream ?: return
            synchronized(sendLock) {
                os.write(byteArrayOf(0x01))
                os.flush()
            }
        } catch (_: Exception) {
        }
    }

    fun sendStats(bufferMs: Int, fpsMilli: Int, decodeAvgMs: Int? = null) {
        // Best-effort: framed control message.
        // Format:
        //   0x02 + bufferMs(int32 BE) + fpsMilli(int32 BE)
        //   0x02 + bufferMs(int32 BE) + fpsMilli(int32 BE) + decodeAvgMs(int32 BE)
        try {
            val os = outputStream ?: return
            val bb = if (decodeAvgMs != null) {
                ByteBuffer.allocate(1 + 4 + 4 + 4).order(ByteOrder.BIG_ENDIAN)
            } else {
                ByteBuffer.allocate(1 + 4 + 4).order(ByteOrder.BIG_ENDIAN)
            }
            bb.put(0x02)
            bb.putInt(bufferMs)
            bb.putInt(fpsMilli)
            if (decodeAvgMs != null) {
                bb.putInt(decodeAvgMs)
            }
            synchronized(sendLock) {
                os.write(bb.array())
                os.flush()
            }
        } catch (_: Exception) {
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
            socket = null
        }
        
        println("✅ Network receiver stopped")
    }
    
    private suspend fun connectAndReceive() {
        try {
            socket = Socket(serverIp, serverPort)
            val inputStream = DataInputStream(socket!!.getInputStream())
            outputStream = socket!!.getOutputStream()
            
            println("📡 Connected to server $serverIp:$serverPort")
            
            while (isRunning) {
                // Read packet size
                val packetSize = inputStream.readInt()
                
                // Read packet data
                val packetData = ByteArray(packetSize)
                inputStream.readFully(packetData)
                
                // Parse packet and detect protocol
                val parsed = parsePacket(packetData)
                val leftFrame = parsed.leftFrame
                val rightFrame = parsed.rightFrame
                val protocol = parsed.protocol
                val frameId = parsed.frameId
                val fpsMilli = parsed.fpsMilli
                
                // Update detected protocol
                if (detectedProtocol == MainActivity.StreamProtocol.UNKNOWN) {
                    detectedProtocol = protocol
                    println("✅ Detected protocol: ${protocol.name}")
                }
                
                // Callback with frames
                onFrameReceived(leftFrame, rightFrame, protocol, frameId, fpsMilli)
            }
        } catch (e: Exception) {
            e.printStackTrace()
            println("❌ Connection error: ${e.message}")
        } finally {
            // CRITICAL: Always close socket and notify disconnect
            try {
                socket?.close()
            } catch (e: Exception) {
                e.printStackTrace()
            }
            socket = null
            outputStream = null
            
            // Notify MainActivity that connection was lost
            // This triggers restart of discovery
            withContext(Dispatchers.Main) {
                onDisconnected()
            }
        }
    }
    
    private data class ParsedPacket(
        val leftFrame: ByteArray,
        val rightFrame: ByteArray,
        val protocol: MainActivity.StreamProtocol,
        val frameId: Int,
        val fpsMilli: Int
    )

    private fun parsePacket(packet: ByteArray): ParsedPacket {
        val buffer = ByteBuffer.wrap(packet).order(ByteOrder.BIG_ENDIAN)
        
        // Read header (16 bytes)
        val magic = ByteArray(4)
        buffer.get(magic)
        val magicString = String(magic, Charsets.US_ASCII)
        
        // Detect protocol from magic bytes
        val protocol = when (magicString) {
            "VRH2" -> MainActivity.StreamProtocol.VRH2  // H.264
            "VRH3" -> MainActivity.StreamProtocol.VRH3  // H.264 (extended header)
            "VRHP" -> MainActivity.StreamProtocol.VRHP  // JPEG
            else -> {
                println("⚠️ Unknown protocol magic: $magicString")
                MainActivity.StreamProtocol.UNKNOWN
            }
        }
        
        val frameId = buffer.int
        val leftSize = buffer.int
        val rightSize = buffer.int

        val fpsMilli = if (magicString == "VRH3") {
            buffer.int
        } else {
            0
        }
        
        // Read left eye frame
        val leftFrame = ByteArray(leftSize)
        buffer.get(leftFrame)
        
        // Read right eye frame
        val rightFrame = if (rightSize > 0) {
            val rf = ByteArray(rightSize)
            buffer.get(rf)
            rf
        } else {
            // Mono packet: right eye omitted
            leftFrame
        }

        return ParsedPacket(leftFrame, rightFrame, protocol, frameId, fpsMilli)
    }
}
