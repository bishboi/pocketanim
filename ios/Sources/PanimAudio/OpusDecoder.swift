// Opus packets to PCM with AudioToolbox, one packet at a time.
//
// The Android player's MediaCodec decodes the Ogg's packets itself; on iOS AudioToolbox has an Opus decoder
// (kAudioFormatOpus) but no Ogg reader, so OggOpusDemuxer finds the packets and this hands each to an
// AudioConverter through its input callback, with the packet's description. Output is Float32 at 48 kHz,
// interleaved when stereo; NarrationReader drops the pre-skip and mixes down.

#if canImport(AudioToolbox)
import AudioToolbox
import Foundation

public struct OpusDecodeError: Error, CustomStringConvertible {
    public let status: OSStatus
    public let step: String
    public var description: String { "the Opus decoder failed (\(step), status \(status))" }
}

public final class AudioToolboxOpusDecoder: OpusPacketDecoder {
    /// What the input callback returns when its one packet is spent: "no more for now", not end of stream.
    static let noMoreInput: OSStatus = 0x6E6F_6D6F      // 'nomo'

    fileprivate let channels: Int
    private var converter: AudioConverterRef?
    private var framesPerPacket = 0
    private var output: UnsafeMutablePointer<Float>
    fileprivate var packet: UnsafeMutableRawPointer
    fileprivate var packetCapacity = 4096
    fileprivate var packetSize = 0
    fileprivate var supplied = false
    fileprivate let packetDescription: UnsafeMutablePointer<AudioStreamPacketDescription>

    public init(channels: Int) {
        self.channels = channels
        output = .allocate(capacity: 5760 * channels)        // 120 ms, the longest packet
        packet = .allocate(byteCount: packetCapacity, alignment: 16)
        packetDescription = .allocate(capacity: 1)
        packetDescription.initialize(to: AudioStreamPacketDescription())
    }

    deinit {
        if let converter { AudioConverterDispose(converter) }
        output.deallocate()
        packet.deallocate()
        packetDescription.deallocate()
    }

    /// The converter is made for one packet duration (the narration's are all 20 ms); a packet of another length
    /// makes a new one, which costs a few ms of decoder state.
    private func makeConverter(framesPerPacket frames: Int) throws {
        if let converter { AudioConverterDispose(converter) }
        converter = nil
        let ch = UInt32(channels)
        var input = AudioStreamBasicDescription(
            mSampleRate: Double(Opus.sampleRate), mFormatID: kAudioFormatOpus, mFormatFlags: 0,
            mBytesPerPacket: 0, mFramesPerPacket: UInt32(frames), mBytesPerFrame: 0,
            mChannelsPerFrame: ch, mBitsPerChannel: 0, mReserved: 0)
        var pcm = AudioStreamBasicDescription(
            mSampleRate: Double(Opus.sampleRate), mFormatID: kAudioFormatLinearPCM,
            mFormatFlags: kAudioFormatFlagIsFloat | kAudioFormatFlagIsPacked,
            mBytesPerPacket: 4 * ch, mFramesPerPacket: 1, mBytesPerFrame: 4 * ch,
            mChannelsPerFrame: ch, mBitsPerChannel: 32, mReserved: 0)
        var made: AudioConverterRef?
        let status = AudioConverterNew(&input, &pcm, &made)
        guard status == noErr, let made else { throw OpusDecodeError(status: status, step: "AudioConverterNew") }
        converter = made
        framesPerPacket = frames
    }

    public func decode(_ opus: OpusPacket) throws -> [Float] {
        if converter == nil || opus.sampleCount != framesPerPacket { try makeConverter(framesPerPacket: opus.sampleCount) }
        if opus.data.count > packetCapacity {
            packet.deallocate()
            packetCapacity = opus.data.count
            packet = .allocate(byteCount: packetCapacity, alignment: 16)
        }
        opus.data.withUnsafeBytes { packet.copyMemory(from: $0.baseAddress!, byteCount: $0.count) }
        packetSize = opus.data.count
        supplied = false

        var frames = UInt32(opus.sampleCount)
        var list = AudioBufferList(
            mNumberBuffers: 1,
            mBuffers: AudioBuffer(mNumberChannels: UInt32(channels), mDataByteSize: frames * UInt32(4 * channels),
                                  mData: UnsafeMutableRawPointer(output)))
        let status = AudioConverterFillComplexBuffer(
            converter!, opusInput, Unmanaged.passUnretained(self).toOpaque(), &frames, &list, nil)
        guard status == noErr || status == Self.noMoreInput else {
            throw OpusDecodeError(status: status, step: "AudioConverterFillComplexBuffer")
        }
        return Array(UnsafeBufferPointer(start: output, count: Int(frames) * channels))
    }

    public func reset() {
        if let converter { AudioConverterReset(converter) }
    }
}

/// Hands the converter the decoder's one packet, then says there is no more for now.
private let opusInput: AudioConverterComplexInputDataProc = { _, ioPackets, ioData, outDescription, user in
    let decoder = Unmanaged<AudioToolboxOpusDecoder>.fromOpaque(user!).takeUnretainedValue()
    guard !decoder.supplied else {
        ioPackets.pointee = 0
        return AudioToolboxOpusDecoder.noMoreInput
    }
    decoder.supplied = true
    ioPackets.pointee = 1
    ioData.pointee.mNumberBuffers = 1
    ioData.pointee.mBuffers.mData = decoder.packet
    ioData.pointee.mBuffers.mDataByteSize = UInt32(decoder.packetSize)
    ioData.pointee.mBuffers.mNumberChannels = UInt32(decoder.channels)
    decoder.packetDescription.pointee = AudioStreamPacketDescription(
        mStartOffset: 0, mVariableFramesInPacket: 0, mDataByteSize: UInt32(decoder.packetSize))
    outDescription?.pointee = decoder.packetDescription
    return noErr
}
#endif
