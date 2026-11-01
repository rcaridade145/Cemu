#!/usr/bin/env python3
# Generate tests/asan/long_subset_sps.264: an SPS, a Stereo High subset SPS and a PPS.
# The subset SPS signals 150 operation points and an MVC VUI extension with 8 more,
# each with HRD parameters, all of which the header trace logs, so that the trace of
# this one NAL of about 200 bytes is longer than the decoder's trace buffer. The
# counts make the line that crosses the end of the buffer one of the long HRD lines,
# which ends 129 bytes past it, farther than the padding at the end of the decoder
# object can be. Usage:
#   python3 tests/gen_long_subset_sps.py tests/asan/long_subset_sps.264
import os, sys
from types import SimpleNamespace
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_avc
out = sys.argv[1] if len(sys.argv) > 1 else "tests/asan/long_subset_sps.264"

OPERATION_POINTS, VUI_OPERATION_POINTS = 150, 8
sps = dict(nal_ref_idc=3, nal_unit_type=7, profile_idc=66, constraint_set_flags=[0, 0, 0, 0, 0, 0],
	level_idc=3.0, log2_max_frame_num=4, pic_order_cnt_type=2, max_num_ref_frames=1, chroma_format_idc=1,
	gaps_in_frame_num_value_allowed_flag=0, pic_size_in_mbs={"width": 1, "height": 1},
	frame_mbs_only_flag=1, direct_8x8_inference_flag=1)
ssps = dict(nal_ref_idc=3, nal_unit_type=15, profile_idc=128, constraint_set_flags=[0, 0, 0, 0, 0, 0],
	level_idc=3.0, chroma_format_idc=1, bit_depth={"luma": 8, "chroma": 8}, qpprime_y_zero_transform_bypass_flag=0,
	log2_max_frame_num=4, pic_order_cnt_type=2, max_num_ref_frames=1, gaps_in_frame_num_value_allowed_flag=0,
	pic_size_in_mbs={"width": 1, "height": 1}, frame_mbs_only_flag=1, direct_8x8_inference_flag=1,
	view_ids=[0, 1], num_anchor_refs={"l0": 0, "l1": 0}, num_non_anchor_refs={"l0": 0, "l1": 0},
	level_values_signalled=[{"idc": 3.0, "operation_points":
		[{"temporal_id": 0, "target_views": [0], "num_views": 1}] * OPERATION_POINTS}])
ssps["mvc_vui_parameters"] = SimpleNamespace(vui_mvc_operation_points=[{"temporal_id": 0, "target_views": [0]}] * VUI_OPERATION_POINTS,
	nal_hrd_parameters={"cpbs": [{"bit_rate": 64 << 20, "size": 16 << 20, "cbr_flag": 0}], "initial_cpb_removal_delay_length": 24,
		"cpb_removal_delay_length": 24, "dpb_output_delay_length": 24, "time_offset_length": 24},
	low_delay_hrd_flag=0, pic_struct_present_flag=0)
pps = dict(nal_ref_idc=3, nal_unit_type=8, pic_parameter_set_id=0, entropy_coding_mode_flag=0,
	bottom_field_pic_order_in_frame_present_flag=0, num_slice_groups=1,
	num_ref_idx_default_active={"l0": 1, "l1": 1}, weighted_pred_flag=0, weighted_bipred_idc=0,
	pic_init_qp=26, chroma_qp_index_offset=0, deblocking_filter_control_present_flag=0,
	constrained_intra_pred_flag=0, redundant_pic_cnt_present_flag=0)

with open(out, "wb") as f: # the NAL loop of gen_avc.main
	for nal in gen_avc.map_dicts([sps, ssps, pps]):
		f.write(b"\x00\x00\x00\x01")
		bits = 1 << 1
		bits = bits << 2 | nal.nal_ref_idc
		bits = bits << 5 | nal.nal_unit_type
		bits = gen_avc.gen_bits[nal.nal_unit_type](bits, f, nal)
		bits = bits << 1 | 1
		num = bits.bit_length() - 1
		bits ^= 1 << num
		bits <<= -num % 8
		f.write(gen_avc.escape(bits.to_bytes((num + 7) // 8, byteorder="big")))
print(f"wrote {out}")
