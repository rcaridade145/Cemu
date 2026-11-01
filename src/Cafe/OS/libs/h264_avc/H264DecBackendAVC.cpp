#include "H264DecInternal.h"

#include <algorithm>
#include <bit>
#include <cstdint>
#include <cstring>
#include <edge264mvc.h>

namespace H264
{
	bool H264_IsBotW();

	class H264AVCDecoder final : public H264DecoderBackend
	{
	  public:
		~H264AVCDecoder() override
		{
			edge264mvc_close(&m_decoder);
		}

		bool Init() override
		{
			Edge264MvcSettings settings{};
			edge264mvc_default_settings(&settings);
			settings.n_threads = 1;
			settings.max_num_reorder_frames = 2;

			const int status = edge264mvc_open(&m_decoder, &settings);
			if (status != EDGE264MVC_OK)
			{
				cemuLog_log(LogType::Force, "H264: edge264-mvc failed to initialize (status {})", status);
				return false;
			}
			return true;
		}

		bool Decode(uint8* data, uint32 length, double timestamp, void* imageOutput, std::vector<DecodeResult>& results) override
		{
			if (!m_decoder || !data || length == 0)
			{
				cemuLog_log(LogType::Force, "H264: Invalid input or uninitialized edge264-mvc decoder");
				return false;
			}

			m_pendingOutputs.push_back({ timestamp, imageOutput });

			const size_t streamSize = length;
			size_t startCode = edge264mvc_find_start_code(data, streamSize);
			if (startCode == streamSize)
				return SubmitNal(data, streamSize, timestamp, results);

			while (startCode < streamSize)
			{
				const size_t nalStart = startCode + 3;
				if (nalStart >= streamSize)
					break;

				const size_t nextStartCodeOffset = edge264mvc_find_start_code(data + nalStart, streamSize - nalStart);
				size_t nalEnd = nalStart + nextStartCodeOffset;
				while (nalEnd > nalStart && data[nalEnd - 1] == 0)
					--nalEnd;

				if (nalEnd > nalStart)
				{
					if (!SubmitNal(data + nalStart, nalEnd - nalStart, timestamp, results))
						return false;
				}

				if (nextStartCodeOffset == streamSize - nalStart)
					break;
				startCode = nalStart + nextStartCodeOffset;
			}
			return true;
		}

		bool Flush(std::vector<DecodeResult>& results) override
		{
			if (!m_decoder)
				return true;

			const int status = edge264mvc_send_end(m_decoder);
			if (status != EDGE264MVC_OK)
			{
				cemuLog_log(LogType::Force, "H264: edge264-mvc failed to flush (status {})", status);
				return false;
			}

			bool succeeded = true;
			for (;;)
			{
				Edge264MvcFrame frame{};
				const int receiveStatus = edge264mvc_receive_frame(m_decoder, &frame);
				if (receiveStatus == EDGE264MVC_END)
				{
					m_pendingOutputs.clear();
					return succeeded;
				}
				if (receiveStatus != EDGE264MVC_OK)
				{
					cemuLog_log(LogType::Force, "H264: edge264-mvc failed while draining frames (status {})", receiveStatus);
					return false;
				}

				if (!ConsumeFrame(frame, results))
					succeeded = false;
				edge264mvc_release_frame(m_decoder, &frame);
			}
		}

	  private:
		bool SubmitNal(const uint8* nal, size_t nalSize, double timestamp, std::vector<DecodeResult>& results)
		{
			const int64_t pts = std::bit_cast<int64_t>(timestamp);

			int status = edge264mvc_send_nal(m_decoder, nal, nalSize, pts, 0);
			while (status == EDGE264MVC_AGAIN)
			{
				if (!DrainReadyFrames(results))
					return false;
				status = edge264mvc_send_nal(m_decoder, nal, nalSize, pts, 0);
			}

			if (status == EDGE264MVC_UNSUPPORTED || status == EDGE264MVC_CORRUPT)
			{
				cemuLog_log(LogType::H264, "H264: edge264-mvc skipped NAL (status {})", status);
			}
			else if (status != EDGE264MVC_OK)
			{
				cemuLog_log(LogType::Force, "H264: edge264-mvc failed to decode NAL (status {})", status);
				return false;
			}

			return DrainReadyFrames(results);
		}

		bool DrainReadyFrames(std::vector<DecodeResult>& results)
		{
			bool succeeded = true;
			for (;;)
			{
				Edge264MvcFrame frame{};
				const int status = edge264mvc_receive_frame(m_decoder, &frame);
				if (status == EDGE264MVC_AGAIN)
					return succeeded;
				if (status != EDGE264MVC_OK)
				{
					cemuLog_log(LogType::Force, "H264: edge264-mvc failed to receive a frame (status {})", status);
					return false;
				}

				if (!ConsumeFrame(frame, results))
					succeeded = false;
				edge264mvc_release_frame(m_decoder, &frame);
			}
		}

		bool ConsumeFrame(const Edge264MvcFrame& frame, std::vector<DecodeResult>& results)
		{
			const Edge264MvcView& baseView = frame.views[0];
			if (!baseView.planes[0])
				return true;

			if (frame.bit_depth_Y != 8 || frame.bit_depth_C != 8 ||
				frame.width_Y <= 0 || frame.height_Y <= 0 || (frame.width_Y & 1) != 0 || (frame.height_Y & 1) != 0 ||
				frame.width_C != frame.width_Y / 2 || frame.height_C != frame.height_Y / 2 ||
				frame.stride_Y < frame.width_Y || frame.stride_C < frame.width_C ||
				!baseView.planes[1] || !baseView.planes[2])
			{
				cemuLog_log(LogType::Force, "H264: edge264-mvc returned an unsupported frame layout");
				return false;
			}
			if (m_pendingOutputs.empty())
			{
				cemuLog_log(LogType::Force, "H264: edge264-mvc returned a frame without a queued output buffer");
				return false;
			}
			// Match the old backend: pair display-order frames with the guest buffer having the earliest timestamp.
			const auto outputIt = std::min_element(m_pendingOutputs.begin(), m_pendingOutputs.end(),
				[](const PendingOutput& left, const PendingOutput& right)
				{
					return left.timestamp < right.timestamp;
				});
			const PendingOutput pendingOutput = *outputIt;
			m_pendingOutputs.erase(outputIt);
			if (!pendingOutput.imageOutput)
			{
				cemuLog_log(LogType::Force, "H264: queued output buffer is null");
				return false;
			}
			sint32 imageHeight = frame.height_Y;
			if (H264_IsBotW() && frame.width_Y == 1920 && imageHeight == 1088)
				imageHeight = 1080;

			const uint32 outputStride = (static_cast<uint32>(frame.width_Y) + 0xFF) & ~0xFF;
			auto* output = static_cast<uint8*>(pendingOutput.imageOutput);
			for (sint32 row = 0; row < imageHeight; ++row)
			{
				memcpy(output + static_cast<size_t>(row) * outputStride,
					baseView.planes[0] + static_cast<size_t>(row) * frame.stride_Y,
					frame.width_Y);
			}

			uint8* chromaOutput = output + static_cast<size_t>(outputStride) * imageHeight;
			for (sint32 row = 0; row < imageHeight / 2; ++row)
			{
				const uint8* cbRow = baseView.planes[1] + static_cast<size_t>(row) * frame.stride_C;
				const uint8* crRow = baseView.planes[2] + static_cast<size_t>(row) * frame.stride_C;
				uint8* uvRow = chromaOutput + static_cast<size_t>(row) * outputStride;
				for (sint32 column = 0; column < frame.width_C; ++column)
				{
					uvRow[column * 2] = cbRow[column];
					uvRow[column * 2 + 1] = crRow[column];
				}
			}

			DecodeResult result;
			result.timestamp = pendingOutput.timestamp;
			result.imageOutput = pendingOutput.imageOutput;
			result.frameWidth = frame.width_Y;
			result.frameHeight = imageHeight;
			result.bytesPerRow = outputStride;
			results.push_back(result);
			return true;
		}

		Edge264MvcDecoder* m_decoder{nullptr};
		struct PendingOutput
		{
			double timestamp;
			void* imageOutput;
		};
		std::vector<PendingOutput> m_pendingOutputs;
	};

	H264DecoderBackend* CreateAVCDecoder()
	{
		return new H264AVCDecoder();
	}
};
