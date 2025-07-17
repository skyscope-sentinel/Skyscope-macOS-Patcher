/**
 * arc_bridge.cpp
 * Core implementation of Intel Arc GPU bridge for macOS
 * 
 * This file provides the core functionality for bridging Intel Arc 770
 * graphics cards to macOS Metal framework, enabling hardware acceleration
 * on unsupported systems.
 * 
 * Copyright (c) 2025 SkyScope Project
 */

#include <IOKit/IOKitLib.h>
#include <IOKit/graphics/IOGraphicsLib.h>
#include <Metal/Metal.h>
#include <CoreFoundation/CoreFoundation.h>
#include <iostream>
#include <vector>
#include <map>
#include <mutex>
#include <string>
#include <memory>
#include <thread>
#include <atomic>
#include <condition_variable>

// Intel Arc (Alchemist/Xe-HPG) specific definitions
#define INTEL_VENDOR_ID           0x8086
#define INTEL_ARC_A770_DEVICE_ID  0x56A0
#define INTEL_XE_HPG_ARCHITECTURE 0x0200  // Xe-HPG architecture code

// Memory management constants
#define ARC_DEFAULT_VRAM_CHUNK   (4 * 1024 * 1024)  // 4MB chunks
#define ARC_MAX_COMMAND_SIZE     (1 * 1024 * 1024)  // 1MB command buffer

// Error codes
enum ArcBridgeError {
    ARC_SUCCESS = 0,
    ARC_ERROR_DEVICE_NOT_FOUND = -1,
    ARC_ERROR_INIT_FAILED = -2,
    ARC_ERROR_MEMORY_ALLOC = -3,
    ARC_ERROR_COMMAND_SUBMISSION = -4,
    ARC_ERROR_INVALID_PARAMETER = -5,
    ARC_ERROR_UNSUPPORTED_FUNCTION = -6
};

// Forward declarations
class ArcMemoryManager;
class ArcCommandProcessor;
class ArcMetalBridge;

/**
 * ArcBridgeLogger - Logging utility for the Intel Arc bridge
 */
class ArcBridgeLogger {
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
            std::cerr << "[ArcBridge][" << level_strings[level] << "] " << message << std::endl;
        }
    }

    static void setLogLevel(LogLevel level) {
        currentLogLevel = level;
    }

private:
    static LogLevel currentLogLevel;
};

// Initialize static member
ArcBridgeLogger::LogLevel ArcBridgeLogger::currentLogLevel = ArcBridgeLogger::INFO;

/**
 * ArcMemoryManager - Manages VRAM allocations for the Intel Arc GPU
 */
class ArcMemoryManager {
public:
    ArcMemoryManager() : initialized(false), totalVRAM(0), availableVRAM(0) {}
    
    ~ArcMemoryManager() {
        shutdown();
    }

    bool initialize(io_service_t device) {
        std::lock_guard<std::mutex> lock(memMutex);
        
        if (initialized) {
            return true;
        }
        
        // Get VRAM size from device properties
        CFTypeRef vramSizeRef;
        vramSizeRef = IORegistryEntryCreateCFProperty(device, 
                                                     CFSTR("VRAM,totalsize"), 
                                                     kCFAllocatorDefault, 
                                                     0);
        if (vramSizeRef) {
            totalVRAM = CFNumberGetValue((CFNumberRef)vramSizeRef, kCFNumberSInt64Type, &totalVRAM) ? 
                        totalVRAM : 16ULL * 1024 * 1024 * 1024; // Default to 16GB if can't determine
            CFRelease(vramSizeRef);
        } else {
            // Arc A770 typically has 16GB of VRAM
            totalVRAM = 16ULL * 1024 * 1024 * 1024;
        }
        
        availableVRAM = totalVRAM;
        initialized = true;
        
        ArcBridgeLogger::log(ArcBridgeLogger::INFO, 
                           "Memory manager initialized with " + 
                           std::to_string(totalVRAM / (1024 * 1024)) + " MB VRAM");
        return true;
    }
    
    void shutdown() {
        std::lock_guard<std::mutex> lock(memMutex);
        
        if (!initialized) {
            return;
        }
        
        // Free all allocated memory
        for (auto& allocation : allocations) {
            freeMemoryInternal(allocation.first);
        }
        
        allocations.clear();
        initialized = false;
    }
    
    void* allocateMemory(size_t size, bool contiguous = true) {
        std::lock_guard<std::mutex> lock(memMutex);
        
        if (!initialized) {
            ArcBridgeLogger::log(ArcBridgeLogger::ERROR, "Memory manager not initialized");
            return nullptr;
        }
        
        if (size > availableVRAM) {
            ArcBridgeLogger::log(ArcBridgeLogger::ERROR, 
                               "Not enough VRAM available for allocation of " + 
                               std::to_string(size) + " bytes");
            return nullptr;
        }
        
        // Align size to 4K boundary for Intel Arc
        size_t alignedSize = (size + 4095) & ~4095;
        
        // Allocate memory from GPU
        void* gpuAddress = allocateMemoryInternal(alignedSize, contiguous);
        if (!gpuAddress) {
            ArcBridgeLogger::log(ArcBridgeLogger::ERROR, "Failed to allocate GPU memory");
            return nullptr;
        }
        
        // Track the allocation
        MemoryAllocation allocation;
        allocation.size = alignedSize;
        allocation.contiguous = contiguous;
        
        allocations[gpuAddress] = allocation;
        availableVRAM -= alignedSize;
        
        ArcBridgeLogger::log(ArcBridgeLogger::DEBUG, 
                           "Allocated " + std::to_string(alignedSize) + 
                           " bytes at " + std::to_string((uintptr_t)gpuAddress));
        
        return gpuAddress;
    }
    
    bool freeMemory(void* address) {
        std::lock_guard<std::mutex> lock(memMutex);
        
        if (!initialized) {
            ArcBridgeLogger::log(ArcBridgeLogger::ERROR, "Memory manager not initialized");
            return false;
        }
        
        auto it = allocations.find(address);
        if (it == allocations.end()) {
            ArcBridgeLogger::log(ArcBridgeLogger::ERROR, "Invalid memory address for free");
            return false;
        }
        
        size_t size = it->second.size;
        
        if (freeMemoryInternal(address)) {
            allocations.erase(it);
            availableVRAM += size;
            
            ArcBridgeLogger::log(ArcBridgeLogger::DEBUG, 
                               "Freed " + std::to_string(size) + 
                               " bytes at " + std::to_string((uintptr_t)address));
            return true;
        }
        
        return false;
    }
    
    size_t getAvailableVRAM() const {
        return availableVRAM;
    }
    
    size_t getTotalVRAM() const {
        return totalVRAM;
    }

private:
    struct MemoryAllocation {
        size_t size;
        bool contiguous;
    };
    
    // In a real implementation, these would interface with the actual GPU driver
    void* allocateMemoryInternal(size_t size, bool contiguous) {
        // Simulated allocation - in real implementation, this would call into IOKit
        return malloc(size);  // Simulate GPU memory allocation with system memory
    }
    
    bool freeMemoryInternal(void* address) {
        // Simulated free - in real implementation, this would call into IOKit
        free(address);
        return true;
    }
    
    bool initialized;
    size_t totalVRAM;
    size_t availableVRAM;
    std::map<void*, MemoryAllocation> allocations;
    std::mutex memMutex;
};

/**
 * ArcCommandProcessor - Handles command submission to the Intel Arc GPU
 */
class ArcCommandProcessor {
public:
    ArcCommandProcessor() : initialized(false) {}
    
    ~ArcCommandProcessor() {
        shutdown();
    }
    
    bool initialize(io_service_t device) {
        std::lock_guard<std::mutex> lock(cmdMutex);
        
        if (initialized) {
            return true;
        }
        
        // Initialize command submission channels
        // In a real implementation, this would set up DMA channels to the GPU
        commandBuffer = std::make_unique<uint8_t[]>(ARC_MAX_COMMAND_SIZE);
        if (!commandBuffer) {
            ArcBridgeLogger::log(ArcBridgeLogger::ERROR, "Failed to allocate command buffer");
            return false;
        }
        
        // Initialize the command processor state
        commandBufferPos = 0;
        initialized = true;
        
        ArcBridgeLogger::log(ArcBridgeLogger::INFO, "Command processor initialized");
        return true;
    }
    
    void shutdown() {
        std::lock_guard<std::mutex> lock(cmdMutex);
        
        if (!initialized) {
            return;
        }
        
        // Flush any pending commands
        if (commandBufferPos > 0) {
            flushCommands();
        }
        
        commandBuffer.reset();
        initialized = false;
    }
    
    int submitCommand(const void* cmd, size_t size) {
        std::lock_guard<std::mutex> lock(cmdMutex);
        
        if (!initialized) {
            ArcBridgeLogger::log(ArcBridgeLogger::ERROR, "Command processor not initialized");
            return ARC_ERROR_INIT_FAILED;
        }
        
        if (!cmd || size == 0) {
            ArcBridgeLogger::log(ArcBridgeLogger::ERROR, "Invalid command parameters");
            return ARC_ERROR_INVALID_PARAMETER;
        }
        
        // Check if there's enough space in the command buffer
        if (commandBufferPos + size > ARC_MAX_COMMAND_SIZE) {
            // Flush the current command buffer first
            if (!flushCommands()) {
                ArcBridgeLogger::log(ArcBridgeLogger::ERROR, "Failed to flush command buffer");
                return ARC_ERROR_COMMAND_SUBMISSION;
            }
        }
        
        // Copy the command to the buffer
        memcpy(commandBuffer.get() + commandBufferPos, cmd, size);
        commandBufferPos += size;
        
        // If the buffer is getting full, flush it
        if (commandBufferPos >= ARC_MAX_COMMAND_SIZE / 2) {
            if (!flushCommands()) {
                ArcBridgeLogger::log(ArcBridgeLogger::ERROR, "Failed to flush command buffer");
                return ARC_ERROR_COMMAND_SUBMISSION;
            }
        }
        
        return ARC_SUCCESS;
    }
    
    bool flushCommands() {
        if (!initialized || commandBufferPos == 0) {
            return true;  // Nothing to do
        }
        
        // In a real implementation, this would submit the command buffer to the GPU
        // For now, we'll just reset the buffer position
        ArcBridgeLogger::log(ArcBridgeLogger::DEBUG, 
                           "Flushing " + std::to_string(commandBufferPos) + 
                           " bytes of commands");
        
        // Simulate command submission delay
        std::this_thread::sleep_for(std::chrono::microseconds(50));
        
        commandBufferPos = 0;
        return true;
    }

private:
    bool initialized;
    std::unique_ptr<uint8_t[]> commandBuffer;
    size_t commandBufferPos;
    std::mutex cmdMutex;
};

/**
 * ArcHardwareInfo - Provides information about the Intel Arc GPU hardware
 */
class ArcHardwareInfo {
public:
    static bool isIntelDevice(io_service_t device) {
        uint32_t vendorID = 0;
        CFTypeRef vendorIDRef = IORegistryEntryCreateCFProperty(device, 
                                                              CFSTR("vendor-id"), 
                                                              kCFAllocatorDefault, 
                                                              0);
        if (vendorIDRef) {
            CFNumberGetValue((CFNumberRef)vendorIDRef, kCFNumberSInt32Type, &vendorID);
            CFRelease(vendorIDRef);
        }
        
        return vendorID == INTEL_VENDOR_ID;
    }
    
    static bool isArcA770(io_service_t device) {
        uint32_t deviceID = 0;
        CFTypeRef deviceIDRef = IORegistryEntryCreateCFProperty(device, 
                                                             CFSTR("device-id"), 
                                                             kCFAllocatorDefault, 
                                                             0);
        if (deviceIDRef) {
            CFNumberGetValue((CFNumberRef)deviceIDRef, kCFNumberSInt32Type, &deviceID);
            CFRelease(deviceIDRef);
        }
        
        return deviceID == INTEL_ARC_A770_DEVICE_ID;
    }
    
    static std::string getDeviceName(io_service_t device) {
        std::string name = "Unknown Intel GPU";
        
        CFTypeRef modelNameRef = IORegistryEntryCreateCFProperty(device, 
                                                              CFSTR("model"), 
                                                              kCFAllocatorDefault, 
                                                              0);
        if (modelNameRef && CFGetTypeID(modelNameRef) == CFStringGetTypeID()) {
            char buffer[256];
            if (CFStringGetCString((CFStringRef)modelNameRef, 
                                  buffer, 
                                  sizeof(buffer), 
                                  kCFStringEncodingUTF8)) {
                name = buffer;
            }
            CFRelease(modelNameRef);
        }
        
        return name;
    }
    
    static uint32_t getEUCount(io_service_t device) {
        // Arc A770 has 32 Xe-cores with 16 EUs each = 512 EUs
        return 512;
    }
    
    static uint32_t getXMXCount(io_service_t device) {
        // Arc A770 has 32 Xe-cores with 16 XMX units each = 512 XMX units
        return 512;
    }
};

/**
 * ArcShaderCompiler - Handles shader compilation for Intel Arc
 */
class ArcShaderCompiler {
public:
    ArcShaderCompiler() {}
    
    // Compile Metal shader to Intel Xe-HPG compatible format
    std::vector<uint8_t> compileMetalToXe(const std::string& metalSource, 
                                         const std::string& entryPoint,
                                         bool isVertex) {
        ArcBridgeLogger::log(ArcBridgeLogger::DEBUG, 
                            "Compiling Metal shader to Xe format: " + entryPoint);
        
        // In a real implementation, this would use Intel's shader compiler
        // For now, we'll create a mock compiled shader
        std::vector<uint8_t> compiledShader;
        
        // Add mock shader header
        const char* header = "XE_HPG_COMPILED_SHADER";
        compiledShader.insert(compiledShader.end(), header, header + strlen(header));
        
        // Add entry point name
        compiledShader.insert(compiledShader.end(), 
                             entryPoint.begin(), 
                             entryPoint.end());
        
        // Add shader type marker
        const char* typeMarker = isVertex ? "_VERTEX" : "_FRAGMENT_OR_COMPUTE";
        compiledShader.insert(compiledShader.end(), 
                             typeMarker, 
                             typeMarker + strlen(typeMarker));
        
        // Add null terminator
        compiledShader.push_back(0);
        
        // Add mock shader body (just some random bytes for demonstration)
        for (size_t i = 0; i < 1024; i++) {
            compiledShader.push_back(static_cast<uint8_t>(i & 0xFF));
        }
        
        ArcBridgeLogger::log(ArcBridgeLogger::DEBUG, 
                            "Shader compilation complete, size: " + 
                            std::to_string(compiledShader.size()) + " bytes");
        
        return compiledShader;
    }
    
    // Optimize shader for Xe-HPG architecture
    bool optimizeShaderForXeHPG(std::vector<uint8_t>& shader) {
        // In a real implementation, this would optimize the shader for Xe-HPG
        // For now, just pretend we did something
        ArcBridgeLogger::log(ArcBridgeLogger::DEBUG, "Optimizing shader for Xe-HPG architecture");
        
        // Append an "optimized" marker to the shader
        const char* marker = "XE_HPG_OPTIMIZED";
        shader.insert(shader.end(), marker, marker + strlen(marker));
        
        return true;
    }
};

/**
 * ArcMetalShaderLibrary - Manages compiled shader functions for Metal compatibility
 */
class ArcMetalShaderLibrary {
public:
    ArcMetalShaderLibrary(const std::string& source) : source(source) {
        compiler = std::make_unique<ArcShaderCompiler>();
    }
    
    std::vector<uint8_t> compileFunction(const std::string& functionName, bool isVertex) {
        // Check if we've already compiled this function
        auto it = compiledFunctions.find(functionName + (isVertex ? "_v" : "_f"));
        if (it != compiledFunctions.end()) {
            return it->second;
        }
        
        // Compile the function
        auto compiledCode = compiler->compileMetalToXe(source, functionName, isVertex);
        if (compiledCode.empty()) {
            ArcBridgeLogger::log(ArcBridgeLogger::ERROR, 
                                "Failed to compile function: " + functionName);
            return {};
        }
        
        // Optimize for Xe-HPG
        compiler->optimizeShaderForXeHPG(compiledCode);
        
        // Store the compiled function
        compiledFunctions[functionName + (isVertex ? "_v" : "_f")] = compiledCode;
        
        return compiledCode;
    }

private:
    std::string source;
    std::unordered_map<std::string, std::vector<uint8_t>> compiledFunctions;
    std::unique_ptr<ArcShaderCompiler> compiler;
};

/**
 * ArcBridgeCore - Main class for the Intel Arc bridge driver
 */
class ArcBridgeCore {
public:
    ArcBridgeCore() : initialized(false), device(IO_OBJECT_NULL) {}
    
    ~ArcBridgeCore() {
        shutdown();
    }
    
    int initialize() {
        if (initialized) {
            return ARC_SUCCESS;
        }
        
        // Find Intel Arc GPU
        if (!findIntelArcDevice()) {
            ArcBridgeLogger::log(ArcBridgeLogger::ERROR, "No compatible Intel Arc GPU found");
            return ARC_ERROR_DEVICE_NOT_FOUND;
        }
        
        // Initialize memory manager
        memoryManager = std::make_unique<ArcMemoryManager>();
        if (!memoryManager->initialize(device)) {
            ArcBridgeLogger::log(ArcBridgeLogger::ERROR, "Failed to initialize memory manager");
            return ARC_ERROR_INIT_FAILED;
        }
        
        // Initialize command processor
        commandProcessor = std::make_unique<ArcCommandProcessor>();
        if (!commandProcessor->initialize(device)) {
            ArcBridgeLogger::log(ArcBridgeLogger::ERROR, "Failed to initialize command processor");
            return ARC_ERROR_INIT_FAILED;
        }
        
        initialized = true;
        ArcBridgeLogger::log(ArcBridgeLogger::INFO, "Intel Arc Bridge Core initialized successfully");
        
        // Log hardware capabilities
        logHardwareCapabilities();
        
        return ARC_SUCCESS;
    }
    
    void shutdown() {
        if (!initialized) {
            return;
        }
        
        // Shutdown components in reverse order
        if (commandProcessor) {
            commandProcessor->shutdown();
        }
        
        if (memoryManager) {
            memoryManager->shutdown();
        }
        
        if (device != IO_OBJECT_NULL) {
            IOObjectRelease(device);
            device = IO_OBJECT_NULL;
        }
        
        initialized = false;
        ArcBridgeLogger::log(ArcBridgeLogger::INFO, "Intel Arc Bridge Core shut down");
    }
    
    bool isInitialized() const {
        return initialized;
    }
    
    ArcMemoryManager* getMemoryManager() {
        return memoryManager.get();
    }
    
    ArcCommandProcessor* getCommandProcessor() {
        return commandProcessor.get();
    }
    
    std::string getGPUInfo() const {
        if (!initialized || device == IO_OBJECT_NULL) {
            return "No GPU information available";
        }
        
        return ArcHardwareInfo::getDeviceName(device);
    }

private:
    bool findIntelArcDevice() {
        io_iterator_t iterator;
        kern_return_t kr;
        
        // Create a matching dictionary for IOPCIDevice
        CFMutableDictionaryRef matchingDict = IOServiceMatching("IOPCIDevice");
        if (!matchingDict) {
            ArcBridgeLogger::log(ArcBridgeLogger::ERROR, "Failed to create matching dictionary");
            return false;
        }
        
        // Get an iterator for all PCI devices
        kr = IOServiceGetMatchingServices(kIOMasterPortDefault, matchingDict, &iterator);
        if (kr != KERN_SUCCESS) {
            ArcBridgeLogger::log(ArcBridgeLogger::ERROR, "Failed to get matching services");
            return false;
        }
        
        // Iterate through all PCI devices
        bool found = false;
        io_service_t service;
        while ((service = IOIteratorNext(iterator)) != IO_OBJECT_NULL) {
            // Check if this is an Intel device
            if (ArcHardwareInfo::isIntelDevice(service)) {
                // Check if this is specifically an Arc A770
                if (ArcHardwareInfo::isArcA770(service)) {
                    // Found our target device
                    device = service;
                    found = true;
                    
                    std::string deviceName = ArcHardwareInfo::getDeviceName(service);
                    ArcBridgeLogger::log(ArcBridgeLogger::INFO, 
                                       "Found Intel Arc A770: " + deviceName);
                    break;
                }
            }
            
            // Release this service reference
            IOObjectRelease(service);
        }
        
        // Release the iterator
        IOObjectRelease(iterator);
        
        return found;
    }
    
    void logHardwareCapabilities() {
        if (!initialized || device == IO_OBJECT_NULL) {
            return;
        }
        
        uint32_t euCount = ArcHardwareInfo::getEUCount(device);
        uint32_t xmxCount = ArcHardwareInfo::getXMXCount(device);
        size_t vramSize = memoryManager->getTotalVRAM() / (1024 * 1024); // MB
        
        ArcBridgeLogger::log(ArcBridgeLogger::INFO, 
                           "Intel Arc A770 capabilities:");
        ArcBridgeLogger::log(ArcBridgeLogger::INFO, 
                           "- Execution Units (EUs): " + std::to_string(euCount));
        ArcBridgeLogger::log(ArcBridgeLogger::INFO, 
                           "- XMX Units: " + std::to_string(xmxCount));
        ArcBridgeLogger::log(ArcBridgeLogger::INFO, 
                           "- VRAM: " + std::to_string(vramSize) + " MB");
    }
    
    bool initialized;
    io_service_t device;
    std::unique_ptr<ArcMemoryManager> memoryManager;
    std::unique_ptr<ArcCommandProcessor> commandProcessor;
};

/**
 * ArcMetalDevice - Represents a Metal-compatible device for Intel Arc
 */
class ArcMetalDevice {
public:
    ArcMetalDevice(ArcBridgeCore* core) : core(core) {
        if (core && core->isInitialized()) {
            ArcBridgeLogger::log(ArcBridgeLogger::INFO, 
                               "Created Metal device for " + core->getGPUInfo());
        }
    }
    
    bool isValid() const {
        return core && core->isInitialized();
    }
    
    ArcMemoryManager* getMemoryManager() const {
        return core ? core->getMemoryManager() : nullptr;
    }
    
    ArcCommandProcessor* getCommandProcessor() const {
        return core ? core->getCommandProcessor() : nullptr;
    }
    
    std::string getName() const {
        return core ? core->getGPUInfo() : "Invalid Arc Metal Device";
    }
    
    std::unique_ptr<ArcMetalShaderLibrary> createShaderLibrary(const std::string& source) {
        if (!isValid()) {
            return nullptr;
        }
        
        return std::make_unique<ArcMetalShaderLibrary>(source);
    }

private:
    ArcBridgeCore* core;
};

// Global instance for easy access
static std::unique_ptr<ArcBridgeCore> g_arcBridgeCore = nullptr;
static std::unique_ptr<ArcMetalDevice> g_arcMetalDevice = nullptr;

// Exported C API functions
extern "C" {

/**
 * Initialize the Intel Arc bridge
 */
int ArcBridge_Initialize() {
    if (g_arcBridgeCore) {
        return ARC_SUCCESS;  // Already initialized
    }
    
    g_arcBridgeCore = std::make_unique<ArcBridgeCore>();
    int result = g_arcBridgeCore->initialize();
    
    if (result == ARC_SUCCESS) {
        // Create the Metal device
        g_arcMetalDevice = std::make_unique<ArcMetalDevice>(g_arcBridgeCore.get());
        if (!g_arcMetalDevice->isValid()) {
            g_arcBridgeCore->shutdown();
            g_arcBridgeCore.reset();
            return ARC_ERROR_INIT_FAILED;
        }
    }
    
    return result;
}

/**
 * Shutdown the Intel Arc bridge
 */
void ArcBridge_Shutdown() {
    g_arcMetalDevice.reset();
    
    if (g_arcBridgeCore) {
        g_arcBridgeCore->shutdown();
        g_arcBridgeCore.reset();
    }
}

/**
 * Allocate GPU memory
 */
void* ArcBridge_AllocateMemory(size_t size, bool contiguous) {
    if (!g_arcBridgeCore || !g_arcBridgeCore->isInitialized()) {
        return nullptr;
    }
    
    return g_arcBridgeCore->getMemoryManager()->allocateMemory(size, contiguous);
}

/**
 * Free GPU memory
 */
bool ArcBridge_FreeMemory(void* address) {
    if (!g_arcBridgeCore || !g_arcBridgeCore->isInitialized()) {
        return false;
    }
    
    return g_arcBridgeCore->getMemoryManager()->freeMemory(address);
}

/**
 * Submit a command to the GPU
 */
int ArcBridge_SubmitCommand(const void* cmd, size_t size) {
    if (!g_arcBridgeCore || !g_arcBridgeCore->isInitialized()) {
        return ARC_ERROR_INIT_FAILED;
    }
    
    return g_arcBridgeCore->getCommandProcessor()->submitCommand(cmd, size);
}

/**
 * Flush pending commands
 */
bool ArcBridge_FlushCommands() {
    if (!g_arcBridgeCore || !g_arcBridgeCore->isInitialized()) {
        return false;
    }
    
    return g_arcBridgeCore->getCommandProcessor()->flushCommands();
}

/**
 * Get GPU information
 */
const char* ArcBridge_GetGPUInfo() {
    static std::string gpuInfo;
    
    if (!g_arcBridgeCore || !g_arcBridgeCore->isInitialized()) {
        gpuInfo = "Intel Arc Bridge not initialized";
    } else {
        gpuInfo = g_arcBridgeCore->getGPUInfo();
    }
    
    return gpuInfo.c_str();
}

/**
 * Set log level
 */
void ArcBridge_SetLogLevel(int level) {
    if (level >= ArcBridgeLogger::DEBUG && level <= ArcBridgeLogger::ERROR) {
        ArcBridgeLogger::setLogLevel(static_cast<ArcBridgeLogger::LogLevel>(level));
    }
}

/**
 * Compile Metal shader for Intel Arc
 */
void* ArcBridge_CompileMetalShader(const char* source, 
                                  const char* functionName, 
                                  bool isVertex) {
    if (!g_arcMetalDevice || !g_arcMetalDevice->isValid() || !source || !functionName) {
        return nullptr;
    }
    
    auto library = g_arcMetalDevice->createShaderLibrary(source);
    if (!library) {
        return nullptr;
    }
    
    auto compiledCode = library->compileFunction(functionName, isVertex);
    if (compiledCode.empty()) {
        return nullptr;
    }
    
    // Allocate memory for the compiled shader
    void* shaderMemory = ArcBridge_AllocateMemory(compiledCode.size(), true);
    if (!shaderMemory) {
        return nullptr;
    }
    
    // Copy the compiled shader to GPU memory
    memcpy(shaderMemory, compiledCode.data(), compiledCode.size());
    
    return shaderMemory;
}

/**
 * Free compiled shader
 */
bool ArcBridge_FreeShader(void* shader) {
    return ArcBridge_FreeMemory(shader);
}

/**
 * Check if hardware supports XMX (Matrix) instructions
 */
bool ArcBridge_SupportsXMX() {
    // Arc A770 supports XMX instructions
    return true;
}

/**
 * Get available VRAM
 */
size_t ArcBridge_GetAvailableVRAM() {
    if (!g_arcBridgeCore || !g_arcBridgeCore->isInitialized()) {
        return 0;
    }
    
    return g_arcBridgeCore->getMemoryManager()->getAvailableVRAM();
}

/**
 * Get total VRAM
 */
size_t ArcBridge_GetTotalVRAM() {
    if (!g_arcBridgeCore || !g_arcBridgeCore->isInitialized()) {
        return 0;
    }
    
    return g_arcBridgeCore->getMemoryManager()->getTotalVRAM();
}

/**
 * Create Metal compatibility layer
 */
void* ArcBridge_CreateMetalDevice() {
    if (!g_arcMetalDevice || !g_arcMetalDevice->isValid()) {
        if (ArcBridge_Initialize() != ARC_SUCCESS) {
            return nullptr;
        }
    }
    
    // Return a pointer to the Metal device
    // In a real implementation, we would need proper reference counting
    return g_arcMetalDevice.get();
}

} // extern "C"
