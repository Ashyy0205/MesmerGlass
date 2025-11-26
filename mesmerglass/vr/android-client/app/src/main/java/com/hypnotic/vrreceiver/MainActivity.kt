package com.hypnotic.vrreceiver

import android.Manifest
import android.app.Activity
import android.content.pm.PackageManager
import android.graphics.BitmapFactory
import android.graphics.Color
import android.media.MediaCodec
import android.media.MediaFormat
import android.opengl.GLSurfaceView
import android.opengl.GLUtils
import android.os.Bundle
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
    
    // Clear color (changes based on status)
    private var clearR = 0.0f
    private var clearG = 0.0f
    private var clearB = 1.0f // Start with blue
    
    // OpenGL resources
    private var textureId = 0
    private var leftEyeTextureId = 0
    private var rightEyeTextureId = 0
    private var shaderProgram = 0
    private var vertexBuffer: FloatBuffer? = null
    private var hasFrame = false
    
    // Shader attribute/uniform locations
    private var positionHandle = 0
    private var texCoordHandle = 0
    private var textureHandle = 0
    
    // Frame data
    private var leftFrameData: ByteArray? = null
    private var rightFrameData: ByteArray? = null
    private val frameLock = Any()
    
    // Protocol detection
    private var streamProtocol: StreamProtocol = StreamProtocol.UNKNOWN
    
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
    
    enum class StreamProtocol {
        UNKNOWN,
        VRHP,  // JPEG encoding
        VRH2   // H.264 encoding
    }
    
    companion object {
        private const val PERMISSION_REQUEST_CODE = 1
        private const val DISCOVERY_PORT = 5556  // UDP: Client sends hello, server listens
        private const val DEFAULT_STREAMING_PORT = 5555  // TCP: Video streaming
        
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
        glSurfaceView.renderMode = GLSurfaceView.RENDERMODE_WHEN_DIRTY  // Render on demand
        setContentView(glSurfaceView)
        
        // Start automatic server discovery
        startAutoDiscovery()
    }
    
    // GLSurfaceView.Renderer methods
    override fun onSurfaceCreated(gl: GL10?, config: EGLConfig?) {
        // Called when surface is created - on GL thread
        GLES30.glClearColor(clearR, clearG, clearB, 1.0f)
        
        // Compile shaders
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
        GLES30.glViewport(0, 0, width, height)
    }
    
    override fun onDrawFrame(gl: GL10?) {
        // Called every frame - on GL thread
        val renderStart = System.currentTimeMillis()
        
        // ALWAYS use black background when streaming (for letterbox bars)
        // Only use status color when NOT streaming
        if (isStreaming && hasFrame) {
            GLES30.glClearColor(0.0f, 0.0f, 0.0f, 1.0f)  // Black bars during streaming
        } else {
            GLES30.glClearColor(clearR, clearG, clearB, 1.0f)  // Status color when not streaming
        }
        GLES30.glClear(GLES30.GL_COLOR_BUFFER_BIT or GLES30.GL_DEPTH_BUFFER_BIT)
        
        // If we have frame data, update and render textures
        synchronized(frameLock) {
            if (hasFrame && leftFrameData != null && rightFrameData != null) {
                // Measure decode time
                val decodeStart = System.currentTimeMillis()
                
                // Decode and upload left eye
                val leftBitmap = BitmapFactory.decodeByteArray(leftFrameData, 0, leftFrameData!!.size)
                if (leftBitmap != null) {
                    GLES30.glBindTexture(GLES30.GL_TEXTURE_2D, leftEyeTextureId)
                    GLUtils.texImage2D(GLES30.GL_TEXTURE_2D, 0, leftBitmap, 0)
                    leftBitmap.recycle()
                }
                
                // Decode and upload right eye
                val rightBitmap = BitmapFactory.decodeByteArray(rightFrameData, 0, rightFrameData!!.size)
                if (rightBitmap != null) {
                    GLES30.glBindTexture(GLES30.GL_TEXTURE_2D, rightEyeTextureId)
                    GLUtils.texImage2D(GLES30.GL_TEXTURE_2D, 0, rightBitmap, 0)
                    rightBitmap.recycle()
                }
                
                // Track decode time
                val decodeTime = System.currentTimeMillis() - decodeStart
                decodeTimes.add(decodeTime)
                
                // Render stereo (left half = left eye, right half = right eye)
                renderStereo()
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
            
            println("📊 VR Client Performance Stats (Frame $framesReceived):")
            println("   Client FPS: ${"%.1f".format(clientFPS)}")
            println("   Latency: ${"%.1f".format(totalLatency)}ms (decode: ${"%.1f".format(avgDecode)}ms, render: ${"%.1f".format(avgRender)}ms)")
            println("   Bandwidth: ${"%.2f".format(bandwidthMbps)} Mbps")
            println("   Bytes received: ${bytesReceived / 1024} KB")
            
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
        
        // 16:9 aspect ratio for the video (native video format)
        val videoAspect = 16.0f / 9.0f
        
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
        
        // CRITICAL FIX: Always stop existing discovery before creating new one
        discoveryService?.stop()
        discoveryService = null
        
        discoveryService = DiscoveryService(DISCOVERY_PORT, DEFAULT_STREAMING_PORT) { serverIp, serverPort ->
            runOnUiThread {
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
        updateStatus("STREAMING\nSTARTING", Color.rgb(255, 165, 0))
        
        // Create network receiver with disconnect handler
        networkReceiver = NetworkReceiver(ip, port, 
            // Frame received callback
            onFrameReceived = { leftData, rightData, protocol ->
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
                    
                    // Initialize H.264 decoders if needed
                    if (protocol == StreamProtocol.VRH2) {
                        initializeH264Decoders()
                    }
                }
                
                // Mark as streaming on first frame
                if (!isStreaming) {
                    isStreaming = true
                    runOnUiThread {
                        // Change to black when streaming (for letterbox bars)
                        clearR = 0.0f
                        clearG = 0.0f
                        clearB = 0.0f
                    }
                }
                
                // Store frame data for rendering and track bytes received
                synchronized(frameLock) {
                    leftFrameData = leftData
                    rightFrameData = rightData
                    hasFrame = true
                    
                    // Track bytes received for bandwidth calculation
                    bytesReceived += leftData.size.toLong() + rightData.size.toLong()
                }
                
                // Request render on UI thread
                runOnUiThread {
                    glSurfaceView.requestRender()
                }
            },
            // Disconnect callback - RESTART DISCOVERY
            onDisconnected = {
                println("🔄 Connection lost. Restarting discovery...")
                
                // Clean up streaming state
                isStreaming = false
                streamProtocol = StreamProtocol.UNKNOWN
                networkReceiver = null
                
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
                    glSurfaceView.requestRender()  // Force redraw with blue background
                }
                
                // CRITICAL FIX: Stop old discovery service before starting new one
                discoveryService?.stop()
                discoveryService = null
                
                // Small delay to ensure socket is fully released
                Thread.sleep(500)
                
                // Restart discovery to find server again
                startAutoDiscovery()
            }
        )
        
        networkReceiver?.start()
    }
    
    private fun initializeH264Decoders() {
        try {
            // Left eye decoder
            leftDecoder = MediaCodec.createDecoderByType(MediaFormat.MIMETYPE_VIDEO_AVC)
            val leftFormat = MediaFormat.createVideoFormat(MediaFormat.MIMETYPE_VIDEO_AVC, 1920, 1080)
            leftDecoder?.configure(leftFormat, null, null, 0)
            leftDecoder?.start()
            
            // Right eye decoder
            rightDecoder = MediaCodec.createDecoderByType(MediaFormat.MIMETYPE_VIDEO_AVC)
            val rightFormat = MediaFormat.createVideoFormat(MediaFormat.MIMETYPE_VIDEO_AVC, 1920, 1080)
            rightDecoder?.configure(rightFormat, null, null, 0)
            rightDecoder?.start()
            
            runOnUiThread {
                Toast.makeText(this, "H.264 hardware decoders initialized", Toast.LENGTH_SHORT).show()
            }
        } catch (e: Exception) {
            e.printStackTrace()
            runOnUiThread {
                Toast.makeText(this, "H.264 decoder init failed: ${e.message}", Toast.LENGTH_LONG).show()
            }
        }
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
        releaseDecoders()
    }
    
    override fun onResume() {
        super.onResume()
        glSurfaceView.onResume()
        
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
    private val onFrameReceived: (ByteArray, ByteArray, MainActivity.StreamProtocol) -> Unit,
    private val onDisconnected: () -> Unit  // ← NEW: Callback when connection is lost
) {
    
    private var socket: Socket? = null
    private var isRunning = false
    private var receiveJob: Job? = null
    private var detectedProtocol = MainActivity.StreamProtocol.UNKNOWN
    
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
            socket = null
        }
        
        println("✅ Network receiver stopped")
    }
    
    private suspend fun connectAndReceive() {
        try {
            socket = Socket(serverIp, serverPort)
            val inputStream = DataInputStream(socket!!.getInputStream())
            
            println("📡 Connected to server $serverIp:$serverPort")
            
            while (isRunning) {
                // Read packet size
                val packetSize = inputStream.readInt()
                
                // Read packet data
                val packetData = ByteArray(packetSize)
                inputStream.readFully(packetData)
                
                // Parse packet and detect protocol
                val (leftFrame, rightFrame, protocol) = parsePacket(packetData)
                
                // Update detected protocol
                if (detectedProtocol == MainActivity.StreamProtocol.UNKNOWN) {
                    detectedProtocol = protocol
                    println("✅ Detected protocol: ${protocol.name}")
                }
                
                // Callback with frames
                onFrameReceived(leftFrame, rightFrame, protocol)
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
            
            // Notify MainActivity that connection was lost
            // This triggers restart of discovery
            withContext(Dispatchers.Main) {
                onDisconnected()
            }
        }
    }
    
    private fun parsePacket(packet: ByteArray): Triple<ByteArray, ByteArray, MainActivity.StreamProtocol> {
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
        
        // Read left eye frame
        val leftFrame = ByteArray(leftSize)
        buffer.get(leftFrame)
        
        // Read right eye frame
        val rightFrame = ByteArray(rightSize)
        buffer.get(rightFrame)
        
        return Triple(leftFrame, rightFrame, protocol)
    }
}
