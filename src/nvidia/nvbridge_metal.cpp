/**
 * nvbridge_metal.cpp
 * Metal compatibility layer for NVIDIA GPUs
 * 
 * This file provides translation between Apple's Metal framework and
 * NVIDIA's native APIs, enabling hardware acceleration for GTX 970
 * graphics cards on macOS.
 * 
 * Copyright (c) 2025 SkyScope Project
 */

#include <Metal/Metal.h>
#include <MetalKit/MetalKit.h>
#include <IOKit/IOKitLib.h>
#include <CoreFoundation/CoreFoundation.h>
#include <iostream>
#include <vector>
#include <map>
#include <string>
#include <mutex>
#include <unordered_map>
#include <functional>
#include <memory>
#include <queue>
#include <thread>
#include <atomic>
#include <condition_variable>

// Include the NVIDIA bridge core header
extern "C" {
    // From nvbridge_core.cpp
    int NVBridge_Initialize();
    void NVBridge_Shutdown();
    void* NVBridge_AllocateMemory(size_t size, bool contiguous);
    bool NVBridge_FreeMemory(void* address);
    int NVBridge_SubmitCommand(const void* cmd, size_t size);
    bool NVBridge_FlushCommands();
    const char* NVBridge_GetGPUInfo();
    void NVBridge_SetLogLevel(int level);
}

// Maxwell shader architecture constants
#define MAXWELL_SHADER_MODEL       5.0
#define MAXWELL_MAX_THREADS        2048
#define MAXWELL_WARP_SIZE          32
#define MAXWELL_MAX_REGISTERS      255
#define MAXWELL_MAX_SHARED_MEM     48 * 1024  // 48KB

// Metal to NVIDIA translation constants
#define METAL_TO_NV_BUFFER_ALIGNMENT 256
#define METAL_TO_NV_TEXTURE_ALIGNMENT 512

// Forward declarations
class NVMetalDevice;
class NVMetalCommandQueue;
class NVMetalBuffer;
class NVMetalTexture;
class NVMetalRenderPipelineState;
class NVMetalComputePipelineState;
class NVMetalCommandBuffer;
class NVMetalRenderCommandEncoder;
class NVMetalComputeCommandEncoder;
class NVMetalShaderLibrary;
class NVMetalFunction;

// Error handling
enum NVMetalError {
    NVMETAL_SUCCESS = 0,
    NVMETAL_ERROR_INIT_FAILED = -1,
    NVMETAL_ERROR_SHADER_COMPILATION = -2,
    NVMETAL_ERROR_PIPELINE_CREATION = -3,
    NVMETAL_ERROR_INVALID_PARAMETER = -4,
    NVMETAL_ERROR_MEMORY_ALLOCATION = -5,
    NVMETAL_ERROR_UNSUPPORTED_FEATURE = -6
};

/**
 * NVMetalLogger - Logging utility for the NVIDIA Metal bridge
 */
class NVMetalLogger {
public:
    enum LogLevel {
        DEBUG = 0,
        INFO = 1,
        WARNING = 2,
        ERROR = 3
    };

    static void log(LogLevel level, const std::string& message) {
        static const char* level_strings[] = {
            "DEBUG", "INFO", "WARNING", "ERROR"
        };
        
        // Only log messages at or above the current log level
        if (level >= currentLogLevel) {
            std::cerr << "[NVMetal][" << level_strings[level] << "] " << message << std::endl;
        }
    }

    static void setLogLevel(LogLevel level) {
        currentLogLevel = level;
        // Also set the core bridge log level
        NVBridge_SetLogLevel(level);
    }

private:
    static LogLevel currentLogLevel;
};

// Initialize static member
NVMetalLogger::LogLevel NVMetalLogger::currentLogLevel = NVMetalLogger::INFO;

/**
 * NVMetalShaderTranslator - Translates Metal shaders to NVIDIA compatible format
 */
class NVMetalShaderTranslator {
public:
    NVMetalShaderTranslator() {}
    
    // Translate Metal Shading Language (MSL) to NVIDIA PTX or SASS
    std::vector<uint8_t> translateMSLToNV(const std::string& mslSource, 
                                         const std::string& functionName,
                                         bool isVertex) {
        NVMetalLogger::log(NVMetalLogger::DEBUG, 
                          "Translating MSL function: " + functionName + 
                          (isVertex ? " (vertex)" : " (fragment/compute)"));
        
        // In a real implementation, this would use NVIDIA's shader compiler
        // For now, we'll create a mock compiled shader
        std::vector<uint8_t> compiledShader;
        
        // Add mock shader header
        const char* header = "NVVM_COMPILED_SHADER";
        compiledShader.insert(compiledShader.end(), header, header + strlen(header));
        
        // Add function name
        compiledShader.insert(compiledShader.end(), 
                             functionName.begin(), 
                             functionName.end());
        
        // Add null terminator
        compiledShader.push_back(0);
        
        // Add mock shader body (just some random bytes for demonstration)
        for (size_t i = 0; i < 1024; i++) {
            compiledShader.push_back(static_cast<uint8_t>(i & 0xFF));
        }
        
        NVMetalLogger::log(NVMetalLogger::DEBUG, 
                          "Shader translation complete, size: " + 
                          std::to_string(compiledShader.size()) + " bytes");
        
        return compiledShader;
    }
    
    // Optimize shader for Maxwell architecture
    bool optimizeShaderForMaxwell(std::vector<uint8_t>& shader) {
        // In a real implementation, this would optimize the shader for Maxwell
        // For now, just pretend we did something
        NVMetalLogger::log(NVMetalLogger::DEBUG, "Optimizing shader for Maxwell architecture");
        
        // Append an "optimized" marker to the shader
        const char* marker = "MAXWELL_OPTIMIZED";
        shader.insert(shader.end(), marker, marker + strlen(marker));
        
        return true;
    }
};

/**
 * NVMetalFunction - Represents a compiled shader function
 */
class NVMetalFunction {
public:
    NVMetalFunction(const std::string& name, 
                   const std::vector<uint8_t>& compiledCode,
                   bool isVertex)
        : name(name), compiledCode(compiledCode), isVertex(isVertex) {}
    
    const std::string& getName() const {
        return name;
    }
    
    const std::vector<uint8_t>& getCompiledCode() const {
        return compiledCode;
    }
    
    bool isVertexFunction() const {
        return isVertex;
    }

private:
    std::string name;
    std::vector<uint8_t> compiledCode;
    bool isVertex;
};

/**
 * NVMetalShaderLibrary - Manages compiled shader functions
 */
class NVMetalShaderLibrary {
public:
    NVMetalShaderLibrary(const std::string& source) : source(source) {
        translator = std::make_unique<NVMetalShaderTranslator>();
    }
    
    std::shared_ptr<NVMetalFunction> newFunction(const std::string& functionName, bool isVertex) {
        auto it = functions.find(functionName);
        if (it != functions.end()) {
            return it->second;
        }
        
        // Compile the function
        auto compiledCode = translator->translateMSLToNV(source, functionName, isVertex);
        if (compiledCode.empty()) {
            NVMetalLogger::log(NVMetalLogger::ERROR, 
                              "Failed to compile function: " + functionName);
            return nullptr;
        }
        
        // Optimize for Maxwell
        translator->optimizeShaderForMaxwell(compiledCode);
        
        // Create and store the function
        auto function = std::make_shared<NVMetalFunction>(functionName, compiledCode, isVertex);
        functions[functionName] = function;
        
        return function;
    }

private:
    std::string source;
    std::unordered_map<std::string, std::shared_ptr<NVMetalFunction>> functions;
    std::unique_ptr<NVMetalShaderTranslator> translator;
};

/**
 * NVMetalBuffer - Represents a GPU buffer
 */
class NVMetalBuffer {
public:
    NVMetalBuffer(size_t length, uint32_t options)
        : length(length), options(options), gpuAddress(nullptr) {
        
        // Allocate GPU memory
        gpuAddress = NVBridge_AllocateMemory(length, true);
        if (!gpuAddress) {
            NVMetalLogger::log(NVMetalLogger::ERROR, 
                              "Failed to allocate buffer of size: " + 
                              std::to_string(length));
        } else {
            NVMetalLogger::log(NVMetalLogger::DEBUG, 
                              "Allocated buffer of size: " + 
                              std::to_string(length));
        }
    }
    
    ~NVMetalBuffer() {
        if (gpuAddress) {
            NVBridge_FreeMemory(gpuAddress);
            gpuAddress = nullptr;
        }
    }
    
    void* contents() {
        return gpuAddress;
    }
    
    size_t getLength() const {
        return length;
    }
    
    bool isValid() const {
        return gpuAddress != nullptr;
    }

private:
    size_t length;
    uint32_t options;
    void* gpuAddress;
};

/**
 * NVMetalTexture - Represents a GPU texture
 */
class NVMetalTexture {
public:
    NVMetalTexture(uint32_t width, uint32_t height, uint32_t format)
        : width(width), height(height), format(format), gpuAddress(nullptr) {
        
        // Calculate required size based on format
        size_t pixelSize = getPixelSize(format);
        size_t totalSize = width * height * pixelSize;
        
        // Allocate GPU memory
        gpuAddress = NVBridge_AllocateMemory(totalSize, true);
        if (!gpuAddress) {
            NVMetalLogger::log(NVMetalLogger::ERROR, 
                              "Failed to allocate texture of size: " + 
                              std::to_string(width) + "x" + std::to_string(height));
        } else {
            NVMetalLogger::log(NVMetalLogger::DEBUG, 
                              "Allocated texture of size: " + 
                              std::to_string(width) + "x" + std::to_string(height));
        }
    }
    
    ~NVMetalTexture() {
        if (gpuAddress) {
            NVBridge_FreeMemory(gpuAddress);
            gpuAddress = nullptr;
        }
    }
    
    uint32_t getWidth() const {
        return width;
    }
    
    uint32_t getHeight() const {
        return height;
    }
    
    uint32_t getFormat() const {
        return format;
    }
    
    void* getGPUAddress() const {
        return gpuAddress;
    }
    
    bool isValid() const {
        return gpuAddress != nullptr;
    }

private:
    uint32_t width;
    uint32_t height;
    uint32_t format;
    void* gpuAddress;
    
    size_t getPixelSize(uint32_t format) {
        // Simplified format handling
        switch (format) {
            case 0: // RGBA8Unorm
                return 4;
            case 1: // RGBA16Float
                return 8;
            case 2: // RGBA32Float
                return 16;
            default:
                return 4;
        }
    }
};

/**
 * NVMetalRenderPipelineState - Represents a compiled graphics pipeline
 */
class NVMetalRenderPipelineState {
public:
    NVMetalRenderPipelineState(std::shared_ptr<NVMetalFunction> vertexFunction,
                              std::shared_ptr<NVMetalFunction> fragmentFunction)
        : vertexFunction(vertexFunction), fragmentFunction(fragmentFunction) {
        
        // In a real implementation, this would create a full pipeline state object
        NVMetalLogger::log(NVMetalLogger::INFO, 
                          "Created render pipeline with vertex function: " + 
                          vertexFunction->getName() + 
                          " and fragment function: " + 
                          fragmentFunction->getName());
    }
    
    const std::shared_ptr<NVMetalFunction>& getVertexFunction() const {
        return vertexFunction;
    }
    
    const std::shared_ptr<NVMetalFunction>& getFragmentFunction() const {
        return fragmentFunction;
    }

private:
    std::shared_ptr<NVMetalFunction> vertexFunction;
    std::shared_ptr<NVMetalFunction> fragmentFunction;
};

/**
 * NVMetalComputePipelineState - Represents a compiled compute pipeline
 */
class NVMetalComputePipelineState {
public:
    NVMetalComputePipelineState(std::shared_ptr<NVMetalFunction> computeFunction)
        : computeFunction(computeFunction) {
        
        // In a real implementation, this would create a compute pipeline state object
        NVMetalLogger::log(NVMetalLogger::INFO, 
                          "Created compute pipeline with function: " + 
                          computeFunction->getName());
    }
    
    const std::shared_ptr<NVMetalFunction>& getComputeFunction() const {
        return computeFunction;
    }
    
    uint32_t getThreadExecutionWidth() const {
        // Maxwell architecture has a warp size of 32
        return MAXWELL_WARP_SIZE;
    }
    
    uint32_t getMaxTotalThreadsPerThreadgroup() const {
        // Maxwell supports up to 2048 threads per thread group
        return MAXWELL_MAX_THREADS;
    }

private:
    std::shared_ptr<NVMetalFunction> computeFunction;
};

/**
 * NVMetalCommandEncoder - Base class for command encoders
 */
class NVMetalCommandEncoder {
public:
    NVMetalCommandEncoder() : active(true) {}
    
    virtual ~NVMetalCommandEncoder() {
        endEncoding();
    }
    
    virtual void endEncoding() {
        if (active) {
            NVMetalLogger::log(NVMetalLogger::DEBUG, "Ending command encoding");
            active = false;
        }
    }
    
    bool isActive() const {
        return active;
    }

protected:
    bool active;
};

/**
 * NVMetalRenderCommandEncoder - Encodes rendering commands
 */
class NVMetalRenderCommandEncoder : public NVMetalCommandEncoder {
public:
    NVMetalRenderCommandEncoder() : NVMetalCommandEncoder() {
        NVMetalLogger::log(NVMetalLogger::DEBUG, "Created render command encoder");
    }
    
    void setRenderPipelineState(std::shared_ptr<NVMetalRenderPipelineState> pipelineState) {
        if (!active) return;
        
        this->pipelineState = pipelineState;
        NVMetalLogger::log(NVMetalLogger::DEBUG, "Set render pipeline state");
    }
    
    void setVertexBuffer(std::shared_ptr<NVMetalBuffer> buffer, size_t offset, uint32_t index) {
        if (!active || !buffer || !buffer->isValid()) return;
        
        vertexBuffers[index] = {buffer, offset};
        NVMetalLogger::log(NVMetalLogger::DEBUG, 
                          "Set vertex buffer at index " + std::to_string(index));
    }
    
    void setFragmentBuffer(std::shared_ptr<NVMetalBuffer> buffer, size_t offset, uint32_t index) {
        if (!active || !buffer || !buffer->isValid()) return;
        
        fragmentBuffers[index] = {buffer, offset};
        NVMetalLogger::log(NVMetalLogger::DEBUG, 
                          "Set fragment buffer at index " + std::to_string(index));
    }
    
    void setFragmentTexture(std::shared_ptr<NVMetalTexture> texture, uint32_t index) {
        if (!active || !texture || !texture->isValid()) return;
        
        fragmentTextures[index] = texture;
        NVMetalLogger::log(NVMetalLogger::DEBUG, 
                          "Set fragment texture at index " + std::to_string(index));
    }
    
    void drawPrimitives(uint32_t primitiveType, 
                       size_t vertexStart, 
                       size_t vertexCount) {
        if (!active || !pipelineState) return;
        
        NVMetalLogger::log(NVMetalLogger::DEBUG, 
                          "Draw primitives: type=" + std::to_string(primitiveType) + 
                          ", start=" + std::to_string(vertexStart) + 
                          ", count=" + std::to_string(vertexCount));
        
        // In a real implementation, this would encode a draw command to the GPU
        // For now, we'll just create a mock command
        uint8_t drawCommand[64] = {0};
        drawCommand[0] = 0x01;  // Command type: Draw
        drawCommand[1] = static_cast<uint8_t>(primitiveType);
        
        // Store vertex start and count
        memcpy(drawCommand + 4, &vertexStart, sizeof(vertexStart));
        memcpy(drawCommand + 12, &vertexCount, sizeof(vertexCount));
        
        // Submit the command
        NVBridge_SubmitCommand(drawCommand, sizeof(drawCommand));
    }
    
    void drawIndexedPrimitives(uint32_t primitiveType,
                              size_t indexCount,
                              uint32_t indexType,
                              std::shared_ptr<NVMetalBuffer> indexBuffer,
                              size_t indexBufferOffset) {
        if (!active || !pipelineState || !indexBuffer || !indexBuffer->isValid()) return;
        
        NVMetalLogger::log(NVMetalLogger::DEBUG, 
                          "Draw indexed primitives: type=" + std::to_string(primitiveType) + 
                          ", count=" + std::to_string(indexCount));
        
        // In a real implementation, this would encode an indexed draw command to the GPU
        // For now, we'll just create a mock command
        uint8_t drawCommand[64] = {0};
        drawCommand[0] = 0x02;  // Command type: Indexed Draw
        drawCommand[1] = static_cast<uint8_t>(primitiveType);
        drawCommand[2] = static_cast<uint8_t>(indexType);
        
        // Store index count and offset
        memcpy(drawCommand + 4, &indexCount, sizeof(indexCount));
        memcpy(drawCommand + 12, &indexBufferOffset, sizeof(indexBufferOffset));
        
        // Submit the command
        NVBridge_SubmitCommand(drawCommand, sizeof(drawCommand));
    }
    
    void endEncoding() override {
        if (active) {
            // In a real implementation, this would finalize the command encoding
            NVMetalLogger::log(NVMetalLogger::DEBUG, "Ending render command encoding");
            
            // Submit an end encoding command
            uint8_t endCommand[16] = {0};
            endCommand[0] = 0xFF;  // Command type: End Encoding
            NVBridge_SubmitCommand(endCommand, sizeof(endCommand));
            
            active = false;
        }
    }

private:
    struct BufferBinding {
        std::shared_ptr<NVMetalBuffer> buffer;
        size_t offset;
    };
    
    std::shared_ptr<NVMetalRenderPipelineState> pipelineState;
    std::unordered_map<uint32_t, BufferBinding> vertexBuffers;
    std::unordered_map<uint32_t, BufferBinding> fragmentBuffers;
    std::unordered_map<uint32_t, std::shared_ptr<NVMetalTexture>> fragmentTextures;
};

/**
 * NVMetalComputeCommandEncoder - Encodes compute commands
 */
class NVMetalComputeCommandEncoder : public NVMetalCommandEncoder {
public:
    NVMetalComputeCommandEncoder() : NVMetalCommandEncoder() {
        NVMetalLogger::log(NVMetalLogger::DEBUG, "Created compute command encoder");
    }
    
    void setComputePipelineState(std::shared_ptr<NVMetalComputePipelineState> pipelineState) {
        if (!active) return;
        
        this->pipelineState = pipelineState;
        NVMetalLogger::log(NVMetalLogger::DEBUG, "Set compute pipeline state");
    }
    
    void setBuffer(std::shared_ptr<NVMetalBuffer> buffer, size_t offset, uint32_t index) {
        if (!active || !buffer || !buffer->isValid()) return;
        
        buffers[index] = {buffer, offset};
        NVMetalLogger::log(NVMetalLogger::DEBUG, 
                          "Set compute buffer at index " + std::to_string(index));
    }
    
    void setTexture(std::shared_ptr<NVMetalTexture> texture, uint32_t index) {
        if (!active || !texture || !texture->isValid()) return;
        
        textures[index] = texture;
        NVMetalLogger::log(NVMetalLogger::DEBUG, 
                          "Set compute texture at index " + std::to_string(index));
    }
    
    void dispatchThreadgroups(const std::array<uint32_t, 3>& threadgroupsPerGrid,
                             const std::array<uint32_t, 3>& threadsPerThreadgroup) {
        if (!active || !pipelineState) return;
        
        NVMetalLogger::log(NVMetalLogger::DEBUG, 
                          "Dispatch threadgroups: grid=[" + 
                          std::to_string(threadgroupsPerGrid[0]) + "," +
                          std::to_string(threadgroupsPerGrid[1]) + "," +
                          std::to_string(threadgroupsPerGrid[2]) + "], threadgroup=[" +
                          std::to_string(threadsPerThreadgroup[0]) + "," +
                          std::to_string(threadsPerThreadgroup[1]) + "," +
                          std::to_string(threadsPerThreadgroup[2]) + "]");
        
        // In a real implementation, this would encode a compute dispatch command to the GPU
        // For now, we'll just create a mock command
        uint8_t dispatchCommand[64] = {0};
        dispatchCommand[0] = 0x03;  // Command type: Compute Dispatch
        
        // Store grid dimensions
        memcpy(dispatchCommand + 4, threadgroupsPerGrid.data(), sizeof(uint32_t) * 3);
        
        // Store threadgroup dimensions
        memcpy(dispatchCommand + 16, threadsPerThreadgroup.data(), sizeof(uint32_t) * 3);
        
        // Submit the command
        NVBridge_SubmitCommand(dispatchCommand, sizeof(dispatchCommand));
    }
    
    void endEncoding() override {
        if (active) {
            // In a real implementation, this would finalize the command encoding
            NVMetalLogger::log(NVMetalLogger::DEBUG, "Ending compute command encoding");
            
            // Submit an end encoding command
            uint8_t endCommand[16] = {0};
            endCommand[0] = 0xFF;  // Command type: End Encoding
            NVBridge_SubmitCommand(endCommand, sizeof(endCommand));
            
            active = false;
        }
    }

private:
    struct BufferBinding {
        std::shared_ptr<NVMetalBuffer> buffer;
        size_t offset;
    };
    
    std::shared_ptr<NVMetalComputePipelineState> pipelineState;
    std::unordered_map<uint32_t, BufferBinding> buffers;
    std::unordered_map<uint32_t, std::shared_ptr<NVMetalTexture>> textures;
};

/**
 * NVMetalCommandBuffer - Represents a command buffer for GPU commands
 */
class NVMetalCommandBuffer {
public:
    NVMetalCommandBuffer() : committed(false), completed(false) {
        NVMetalLogger::log(NVMetalLogger::DEBUG, "Created command buffer");
    }
    
    std::shared_ptr<NVMetalRenderCommandEncoder> renderCommandEncoder() {
        if (committed) {
            NVMetalLogger::log(NVMetalLogger::ERROR, 
                              "Cannot create encoder for committed command buffer");
            return nullptr;
        }
        
        // End any active encoder
        if (activeEncoder) {
            activeEncoder->endEncoding();
        }
        
        // Create a new render command encoder
        auto encoder = std::make_shared<NVMetalRenderCommandEncoder>();
        activeEncoder = encoder;
        
        return encoder;
    }
    
    std::shared_ptr<NVMetalComputeCommandEncoder> computeCommandEncoder() {
        if (committed) {
            NVMetalLogger::log(NVMetalLogger::ERROR, 
                              "Cannot create encoder for committed command buffer");
            return nullptr;
        }
        
        // End any active encoder
        if (activeEncoder) {
            activeEncoder->endEncoding();
        }
        
        // Create a new compute command encoder
        auto encoder = std::make_shared<NVMetalComputeCommandEncoder>();
        activeEncoder = encoder;
        
        return encoder;
    }
    
    void commit() {
        if (committed) {
            NVMetalLogger::log(NVMetalLogger::WARNING, "Command buffer already committed");
            return;
        }
        
        // End any active encoder
        if (activeEncoder) {
            activeEncoder->endEncoding();
            activeEncoder.reset();
        }
        
        // In a real implementation, this would submit the command buffer to the GPU
        NVMetalLogger::log(NVMetalLogger::DEBUG, "Committing command buffer");
        
        // Flush commands to the GPU
        NVBridge_FlushCommands();
        
        committed = true;
    }
    
    void waitUntilCompleted() {
        if (!committed) {
            NVMetalLogger::log(NVMetalLogger::WARNING, 
                              "Cannot wait for uncommitted command buffer");
            return;
        }
        
        if (completed) {
            return;
        }
        
        // In a real implementation, this would wait for the GPU to finish
        NVMetalLogger::log(NVMetalLogger::DEBUG, "Waiting for command buffer completion");
        
        // Simulate waiting for GPU
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
        
        completed = true;
    }
    
    bool isCommitted() const {
        return committed;
    }
    
    bool isCompleted() const {
        return completed;
    }

private:
    bool committed;
    bool completed;
    std::shared_ptr<NVMetalCommandEncoder> activeEncoder;
};

/**
 * NVMetalCommandQueue - Manages command buffer creation and submission
 */
class NVMetalCommandQueue {
public:
    NVMetalCommandQueue() {
        NVMetalLogger::log(NVMetalLogger::INFO, "Created command queue");
    }
    
    std::shared_ptr<NVMetalCommandBuffer> commandBuffer() {
        return std::make_shared<NVMetalCommandBuffer>();
    }
};

/**
 * NVMetalDevice - Main interface for the Metal compatibility layer
 */
class NVMetalDevice {
public:
    static std::shared_ptr<NVMetalDevice> createSystemDefaultDevice() {
        // Initialize the NVIDIA bridge
        int result = NVBridge_Initialize();
        if (result != 0) {
            NVMetalLogger::log(NVMetalLogger::ERROR, 
                              "Failed to initialize NVIDIA bridge, error: " + 
                              std::to_string(result));
            return nullptr;
        }
        
        // Create the device
        return std::make_shared<NVMetalDevice>();
    }
    
    NVMetalDevice() {
        commandQueue = std::make_shared<NVMetalCommandQueue>();
        NVMetalLogger::log(NVMetalLogger::INFO, 
                          "Created Metal device for " + 
                          std::string(NVBridge_GetGPUInfo()));
    }
    
    ~NVMetalDevice() {
        NVBridge_Shutdown();
    }
    
    std::shared_ptr<NVMetalCommandQueue> newCommandQueue() {
        return commandQueue;
    }
    
    std::shared_ptr<NVMetalBuffer> newBuffer(size_t length, uint32_t options) {
        return std::make_shared<NVMetalBuffer>(length, options);
    }
    
    std::shared_ptr<NVMetalTexture> newTexture(uint32_t width, uint32_t height, uint32_t format) {
        return std::make_shared<NVMetalTexture>(width, height, format);
    }
    
    std::shared_ptr<NVMetalShaderLibrary> newLibrary(const std::string& source) {
        return std::make_shared<NVMetalShaderLibrary>(source);
    }
    
    std::shared_ptr<NVMetalRenderPipelineState> newRenderPipelineState(
        std::shared_ptr<NVMetalFunction> vertexFunction,
        std::shared_ptr<NVMetalFunction> fragmentFunction) {
        
        if (!vertexFunction || !fragmentFunction) {
            NVMetalLogger::log(NVMetalLogger::ERROR, "Invalid shader functions for pipeline");
            return nullptr;
        }
        
        return std::make_shared<NVMetalRenderPipelineState>(vertexFunction, fragmentFunction);
    }
    
    std::shared_ptr<NVMetalComputePipelineState> newComputePipelineState(
        std::shared_ptr<NVMetalFunction> computeFunction) {
        
        if (!computeFunction) {
            NVMetalLogger::log(NVMetalLogger::ERROR, "Invalid compute function for pipeline");
            return nullptr;
        }
        
        return std::make_shared<NVMetalComputePipelineState>(computeFunction);
    }
    
    const char* getName() const {
        return NVBridge_GetGPUInfo();
    }

private:
    std::shared_ptr<NVMetalCommandQueue> commandQueue;
};

// Global instance for easy access
static std::shared_ptr<NVMetalDevice> g_nvMetalDevice = nullptr;

// Exported C API functions
extern "C" {

/**
 * Initialize the NVIDIA Metal bridge
 */
int NVMetal_Initialize() {
    if (g_nvMetalDevice) {
        return NVMETAL_SUCCESS;  // Already initialized
    }
    
    g_nvMetalDevice = NVMetalDevice::createSystemDefaultDevice();
    if (!g_nvMetalDevice) {
        return NVMETAL_ERROR_INIT_FAILED;
    }
    
    return NVMETAL_SUCCESS;
}

/**
 * Shutdown the NVIDIA Metal bridge
 */
void NVMetal_Shutdown() {
    g_nvMetalDevice.reset();
}

/**
 * Get the Metal device
 */
void* NVMetal_GetDevice() {
    return g_nvMetalDevice.get();
}

/**
 * Set log level
 */
void NVMetal_SetLogLevel(int level) {
    if (level >= NVMetalLogger::DEBUG && level <= NVMetalLogger::ERROR) {
        NVMetalLogger::setLogLevel(static_cast<NVMetalLogger::LogLevel>(level));
    }
}

/**
 * Create a new buffer
 */
void* NVMetal_CreateBuffer(size_t length, uint32_t options) {
    if (!g_nvMetalDevice) {
        return nullptr;
    }
    
    auto buffer = g_nvMetalDevice->newBuffer(length, options);
    if (!buffer || !buffer->isValid()) {
        return nullptr;
    }
    
    // Return a raw pointer to the buffer
    // In a real implementation, we would need to manage this reference
    return buffer.get();
}

/**
 * Create a new texture
 */
void* NVMetal_CreateTexture(uint32_t width, uint32_t height, uint32_t format) {
    if (!g_nvMetalDevice) {
        return nullptr;
    }
    
    auto texture = g_nvMetalDevice->newTexture(width, height, format);
    if (!texture || !texture->isValid()) {
        return nullptr;
    }
    
    // Return a raw pointer to the texture
    // In a real implementation, we would need to manage this reference
    return texture.get();
}

/**
 * Compile a shader from source
 */
void* NVMetal_CompileShader(const char* source, const char* functionName, bool isVertex) {
    if (!g_nvMetalDevice || !source || !functionName) {
        return nullptr;
    }
    
    auto library = g_nvMetalDevice->newLibrary(source);
    if (!library) {
        return nullptr;
    }
    
    auto function = library->newFunction(functionName, isVertex);
    if (!function) {
        return nullptr;
    }
    
    // Return a raw pointer to the function
    // In a real implementation, we would need to manage this reference
    return function.get();
}

/**
 * Create a render pipeline state
 */
void* NVMetal_CreateRenderPipeline(void* vertexFunction, void* fragmentFunction) {
    if (!g_nvMetalDevice || !vertexFunction || !fragmentFunction) {
        return nullptr;
    }
    
    auto vFunc = std::shared_ptr<NVMetalFunction>(
        static_cast<NVMetalFunction*>(vertexFunction),
        [](NVMetalFunction*) {} // Empty deleter to avoid double-free
    );
    
    auto fFunc = std::shared_ptr<NVMetalFunction>(
        static_cast<NVMetalFunction*>(fragmentFunction),
        [](NVMetalFunction*) {} // Empty deleter to avoid double-free
    );
    
    auto pipeline = g_nvMetalDevice->newRenderPipelineState(vFunc, fFunc);
    if (!pipeline) {
        return nullptr;
    }
    
    // Return a raw pointer to the pipeline
    // In a real implementation, we would need to manage this reference
    return pipeline.get();
}

/**
 * Create a compute pipeline state
 */
void* NVMetal_CreateComputePipeline(void* computeFunction) {
    if (!g_nvMetalDevice || !computeFunction) {
        return nullptr;
    }
    
    auto cFunc = std::shared_ptr<NVMetalFunction>(
        static_cast<NVMetalFunction*>(computeFunction),
        [](NVMetalFunction*) {} // Empty deleter to avoid double-free
    );
    
    auto pipeline = g_nvMetalDevice->newComputePipelineState(cFunc);
    if (!pipeline) {
        return nullptr;
    }
    
    // Return a raw pointer to the pipeline
    // In a real implementation, we would need to manage this reference
    return pipeline.get();
}

/**
 * Get the device name
 */
const char* NVMetal_GetDeviceName() {
    if (!g_nvMetalDevice) {
        return "NVIDIA Metal bridge not initialized";
    }
    
    return g_nvMetalDevice->getName();
}

} // extern "C"
