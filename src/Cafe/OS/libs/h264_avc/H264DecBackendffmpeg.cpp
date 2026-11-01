#include "H264DecInternal.h"

#include <algorithm>
#include <bit>
#include <climits>
#include <cstdint>
#include <cstring>

extern "C"
{
#include <libavcodec/avcodec.h>
#include <libavutil/error.h>
#include <libavutil/frame.h>
}

namespace H264
{
	bool H264_IsBotW();

	class H264FFmpegDecoder final : public H264DecoderBackend
	{
	  public:
		~H264FFmpegDecoder() override
		{
			FreeDecoderState();
		}

		bool Init() override
		{
			FreeDecoderState();
			const AVCodec* codec = avcodec_find_decoder(AV_CODEC_ID_H264);
			if (!codec)
			{
				cemuLog_log(LogType::Force, "H264: FFmpeg H.264 decoder is unavailable");
				return false;
			}

			m_codecContext = avcodec_alloc_context3(codec);
			m_packet = av_packet_alloc();
			m_frame = av_frame_alloc();
			if (!m_codecContext || !m_packet || !m_frame)
			{
				cemuLog_log(LogType::Force, "H264: FFmpeg failed to allocate decoder state");
				return false;
			}

			m_codecContext->thread_count = 1;
			m_codecContext->pkt_timebase = { 1, 1 };
			const int status = avcodec_open2(m_codecContext, codec, nullptr);
			if (status < 0)
			{
				LogFFmpegError("failed to initialize decoder", status);
				return false;
			}
			return true;
		}

		bool Decode(uint8* data, uint32 length, double timestamp, void* imageOutput, std::vector<DecodeResult>& results) override
		{
			if (!m_codecContext || !data || length == 0 || length > static_cast<uint32>(INT_MAX))
			{
				cemuLog_log(LogType::Force, "H264: Invalid input or uninitialized FFmpeg decoder");
				return false;
			}

			const bool hasStartCode = length >= 3 && data[0] == 0 && data[1] == 0 &&
				(data[2] == 1 || (length >= 4 && data[2] == 0 && data[3] == 1));
			const int prefixSize = hasStartCode ? 0 : 4;
			if (length > static_cast<uint32>(INT_MAX - prefixSize))
			{
				cemuLog_log(LogType::Force, "H264: Input packet is too large for FFmpeg");
				return false;
			}

			av_packet_unref(m_packet);
			const int packetSize = static_cast<int>(length) + prefixSize;
			int status = av_new_packet(m_packet, packetSize);
			if (status < 0)
			{
				LogFFmpegError("failed to allocate input packet", status);
				return false;
			}
			if (prefixSize)
			{
				m_packet->data[0] = 0;
				m_packet->data[1] = 0;
				m_packet->data[2] = 0;
				m_packet->data[3] = 1;
			}
			std::memcpy(m_packet->data + prefixSize, data, length);
			m_packet->pts = std::bit_cast<int64_t>(timestamp);

			m_pendingOutputs.push_back({ timestamp, imageOutput });
			status = avcodec_send_packet(m_codecContext, m_packet);
			if (status == AVERROR(EAGAIN))
			{
				if (!DrainReadyFrames(results))
				{
					m_pendingOutputs.pop_back();
					return false;
				}
				status = avcodec_send_packet(m_codecContext, m_packet);
			}
			if (status < 0)
			{
				m_pendingOutputs.pop_back();
				LogFFmpegError("failed to submit input packet", status);
				return false;
			}
			return DrainReadyFrames(results);
		}

		bool Flush(std::vector<DecodeResult>& results) override
		{
			if (!m_codecContext)
				return true;

			int status = avcodec_send_packet(m_codecContext, nullptr);
			if (status == AVERROR(EAGAIN))
			{
				if (!DrainReadyFrames(results))
					return false;
				status = avcodec_send_packet(m_codecContext, nullptr);
			}
			if (status < 0 && status != AVERROR_EOF)
			{
				LogFFmpegError("failed to flush decoder", status);
				return false;
			}

			if (!DrainFlushedFrames(results))
				return false;
			m_pendingOutputs.clear();
			avcodec_flush_buffers(m_codecContext);
			return true;
		}

	  private:
		void FreeDecoderState()
		{
			av_packet_free(&m_packet);
			av_frame_free(&m_frame);
			avcodec_free_context(&m_codecContext);
		}
		struct PendingOutput
		{
			double timestamp;
			void* imageOutput;
		};

		static void LogFFmpegError(const char* operation, int status)
		{
			char errorBuffer[AV_ERROR_MAX_STRING_SIZE]{};
			av_strerror(status, errorBuffer, sizeof(errorBuffer));
			cemuLog_log(LogType::Force, "H264: FFmpeg {}: {}", operation, errorBuffer);
		}

		bool DrainReadyFrames(std::vector<DecodeResult>& results)
		{
			bool succeeded = true;
			for (;;)
			{
				const int status = avcodec_receive_frame(m_codecContext, m_frame);
				if (status == AVERROR(EAGAIN) || status == AVERROR_EOF)
					return succeeded;
				if (status < 0)
				{
					LogFFmpegError("failed to receive a frame", status);
					return false;
				}

				if (!ConsumeFrame(results))
					succeeded = false;
				av_frame_unref(m_frame);
			}
		}

		bool DrainFlushedFrames(std::vector<DecodeResult>& results)
		{
			bool succeeded = true;
			for (;;)
			{
				const int status = avcodec_receive_frame(m_codecContext, m_frame);
				if (status == AVERROR_EOF || status == AVERROR(EAGAIN))
					return succeeded;
				if (status < 0)
				{
					LogFFmpegError("failed while draining frames", status);
					return false;
				}

				if (!ConsumeFrame(results))
					succeeded = false;
				av_frame_unref(m_frame);
			}
		}

		bool ConsumeFrame(std::vector<DecodeResult>& results)
		{
			const int cropStatus = av_frame_apply_cropping(m_frame, AV_FRAME_CROP_UNALIGNED);
			if (cropStatus < 0)
			{
				LogFFmpegError("failed to apply frame cropping", cropStatus);
				return false;
			}

			const auto pixelFormat = static_cast<AVPixelFormat>(m_frame->format);
			const bool planar = pixelFormat == AV_PIX_FMT_YUV420P || pixelFormat == AV_PIX_FMT_YUVJ420P;
			const bool semiPlanar = pixelFormat == AV_PIX_FMT_NV12;
			if ((!planar && !semiPlanar) || m_frame->width <= 0 || m_frame->height <= 0 ||
				(m_frame->width & 1) != 0 || (m_frame->height & 1) != 0 ||
				!m_frame->data[0] || !m_frame->data[1] || (!semiPlanar && !m_frame->data[2]) ||
				m_frame->linesize[0] < m_frame->width ||
				m_frame->linesize[1] < (semiPlanar ? m_frame->width : m_frame->width / 2) ||
				(!semiPlanar && m_frame->linesize[2] < m_frame->width / 2))
			{
				cemuLog_log(LogType::Force, "H264: FFmpeg returned an unsupported frame layout (format {})", m_frame->format);
				return false;
			}
			if (m_pendingOutputs.empty())
			{
				cemuLog_log(LogType::Force, "H264: FFmpeg returned a frame without a queued output buffer");
				return false;
			}

			auto outputIt = m_pendingOutputs.end();
			if (m_frame->pts != AV_NOPTS_VALUE)
			{
				outputIt = std::find_if(m_pendingOutputs.begin(), m_pendingOutputs.end(),
					[this](const PendingOutput& output)
					{
						return std::bit_cast<int64_t>(output.timestamp) == m_frame->pts;
					});
			}
			if (outputIt == m_pendingOutputs.end())
			{
				outputIt = std::min_element(m_pendingOutputs.begin(), m_pendingOutputs.end(),
					[](const PendingOutput& left, const PendingOutput& right)
					{
						return left.timestamp < right.timestamp;
					});
			}
			const PendingOutput pendingOutput = *outputIt;
			m_pendingOutputs.erase(outputIt);
			if (!pendingOutput.imageOutput)
			{
				cemuLog_log(LogType::Force, "H264: queued output buffer is null");
				return false;
			}

			sint32 imageHeight = m_frame->height;
			if (H264_IsBotW() && m_frame->width == 1920 && imageHeight == 1088)
				imageHeight = 1080;

			const uint32 outputStride = (static_cast<uint32>(m_frame->width) + 0xFF) & ~0xFF;
			auto* output = static_cast<uint8*>(pendingOutput.imageOutput);
			for (sint32 row = 0; row < imageHeight; ++row)
			{
				std::memcpy(output + static_cast<size_t>(row) * outputStride,
					m_frame->data[0] + static_cast<size_t>(row) * m_frame->linesize[0],
					m_frame->width);
			}

			uint8* chromaOutput = output + static_cast<size_t>(outputStride) * imageHeight;
			for (sint32 row = 0; row < imageHeight / 2; ++row)
			{
				uint8* uvRow = chromaOutput + static_cast<size_t>(row) * outputStride;
				if (semiPlanar)
				{
					std::memcpy(uvRow, m_frame->data[1] + static_cast<size_t>(row) * m_frame->linesize[1], m_frame->width);
				}
				else
				{
					const uint8* cbRow = m_frame->data[1] + static_cast<size_t>(row) * m_frame->linesize[1];
					const uint8* crRow = m_frame->data[2] + static_cast<size_t>(row) * m_frame->linesize[2];
					for (sint32 column = 0; column < m_frame->width / 2; ++column)
					{
						uvRow[column * 2] = cbRow[column];
						uvRow[column * 2 + 1] = crRow[column];
					}
				}
			}

			DecodeResult result;
			result.timestamp = pendingOutput.timestamp;
			result.imageOutput = pendingOutput.imageOutput;
			result.frameWidth = m_frame->width;
			result.frameHeight = imageHeight;
			result.bytesPerRow = outputStride;
			results.push_back(result);
			return true;
		}

		AVCodecContext* m_codecContext{ nullptr };
		AVPacket* m_packet{ nullptr };
		AVFrame* m_frame{ nullptr };
		std::vector<PendingOutput> m_pendingOutputs;
	};

	H264DecoderBackend* CreateAVCDecoder()
	{
		return new H264FFmpegDecoder();
	}
};
