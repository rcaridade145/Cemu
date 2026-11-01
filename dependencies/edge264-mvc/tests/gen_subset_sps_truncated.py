#!/usr/bin/env python3
# Generate tests/asan/subset_sps_truncated.264: an SPS, then 400 copies of a Stereo
# High subset SPS whose last 3 bytes are cut off (8 bytes are left), so that the counts of
# its MVC extension (levels, operation points, target views) are read past the end
# of the NAL, where the bit reader returns the largest value each count allows.
# Usage:
#   python3 tests/gen_subset_sps_truncated.py tests/asan/subset_sps_truncated.264
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_avc
out = sys.argv[1] if len(sys.argv) > 1 else "tests/asan/subset_sps_truncated.264"

COPIES, CUT = 400, 3 # CUT bytes removed from the end of each subset SPS
sps = dict(nal_ref_idc=3, nal_unit_type=7, profile_idc=66, constraint_set_flags=[0, 0, 0, 0, 0, 0],
	level_idc=3.0, log2_max_frame_num=4, pic_order_cnt_type=2, max_num_ref_frames=1, chroma_format_idc=1,
	gaps_in_frame_num_value_allowed_flag=0, pic_size_in_mbs={"width": 1, "height": 1},
	frame_mbs_only_flag=1, direct_8x8_inference_flag=1)
ssps = dict(nal_ref_idc=3, nal_unit_type=15, profile_idc=128, constraint_set_flags=[0, 0, 0, 0, 0, 0],
	level_idc=3.0, chroma_format_idc=1, bit_depth={"luma": 8, "chroma": 8}, qpprime_y_zero_transform_bypass_flag=0,
	log2_max_frame_num=4, pic_order_cnt_type=2, max_num_ref_frames=1, gaps_in_frame_num_value_allowed_flag=0,
	pic_size_in_mbs={"width": 1, "height": 1}, frame_mbs_only_flag=1, direct_8x8_inference_flag=1,
	view_ids=[0, 1], num_anchor_refs={"l0": 0, "l1": 0}, num_non_anchor_refs={"l0": 0, "l1": 0},
	level_values_signalled=[{"idc": 3.0, "operation_points": [{"temporal_id": 0, "target_views": [0], "num_views": 1}]}])

def nal_bytes(nal):
	class Sink:
		data = b""
		def write(self, b): self.data += b
	f = Sink()
	bits = 1 << 1
	bits = bits << 2 | nal.nal_ref_idc
	bits = bits << 5 | nal.nal_unit_type
	bits = gen_avc.gen_bits[nal.nal_unit_type](bits, f, nal)
	bits = bits << 1 | 1
	num = bits.bit_length() - 1
	bits ^= 1 << num
	bits <<= -num % 8
	return f.data + bits.to_bytes((num + 7) // 8, byteorder="big")

sps_nal, ssps_nal = (nal_bytes(n) for n in gen_avc.map_dicts([sps, ssps]))
with open(out, "wb") as f:
	f.write(b"\x00\x00\x00\x01" + gen_avc.escape(sps_nal))
	for _ in range(COPIES):
		f.write(b"\x00\x00\x00\x01" + gen_avc.escape(ssps_nal[:-CUT]))
print(f"wrote {out}")
