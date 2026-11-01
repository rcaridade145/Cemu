#pragma once

#include "Cafe/OS/common/OSCommon.h"

#include <vector>

namespace H264
{
	class H264DecoderBackend
	{
	  public:
		struct DecodeResult
		{
			double timestamp{};
			void* imageOutput{nullptr};
			sint32 frameWidth{0};
			sint32 frameHeight{0};
			uint32 bytesPerRow{0};
			bool cropEnable{false};
			sint32 cropTop{0};
			sint32 cropBottom{0};
			sint32 cropLeft{0};
			sint32 cropRight{0};
		};

		virtual ~H264DecoderBackend() = default;
		virtual bool Init() = 0;
		virtual bool Decode(uint8* data, uint32 length, double timestamp, void* imageOutput, std::vector<DecodeResult>& results) = 0;
		virtual bool Flush(std::vector<DecodeResult>& results) = 0;
	};
}