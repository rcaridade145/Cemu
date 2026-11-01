#!/usr/bin/env python3
# Generate tests/asan/reflist_num_overflow.264: a damaged stream whose P slice
# modifies its reference list with abs_diff_pic_num_minus1 = 2^31 - 1, far beyond the
# MaxPicNum - 1 that 7.4.3.1 allows, so that adding 1 to it overflows a signed int.
# Usage:
#   python3 tests/gen_reflist_num_overflow.py tests/asan/reflist_num_overflow.264
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_avc
out = sys.argv[1] if len(sys.argv) > 1 else "tests/asan/reflist_num_overflow.264"

sps = dict(nal_ref_idc=3, nal_unit_type=7, profile_idc=66, constraint_set_flags=[0, 0, 0, 0, 0, 0],
	level_idc=1.0, log2_max_frame_num=4, pic_order_cnt_type=2, max_num_ref_frames=1, chroma_format_idc=1,
	gaps_in_frame_num_value_allowed_flag=0, pic_size_in_mbs={"width": 1, "height": 1},
	frame_mbs_only_flag=1, direct_8x8_inference_flag=1)
pps = dict(nal_ref_idc=3, nal_unit_type=8, pic_parameter_set_id=0, entropy_coding_mode_flag=0,
	bottom_field_pic_order_in_frame_present_flag=0, num_slice_groups=1,
	num_ref_idx_default_active={"l0": 1, "l1": 1}, weighted_pred_flag=0, weighted_bipred_idc=0,
	pic_init_qp=26, chroma_qp_index_offset=0, deblocking_filter_control_present_flag=0,
	constrained_intra_pred_flag=0, redundant_pic_cnt_present_flag=0)
pcm = dict(mb_type=25, pcm_samples={"bits_Y": 8, "bits_C": 8, "Y": [100] * 256, "Cb": [128] * 64, "Cr": [128] * 64})
idr = dict(nal_ref_idc=3, nal_unit_type=5, first_mb_in_slice=0, slice_type=7, pic_parameter_set_id=0,
	frame_num={"bits": 4, "absolute": 0}, idr_pic_id=0, pic_order_cnt={"type": 2},
	no_output_of_prior_pics_flag=0, long_term_reference_flag=0, slice_qp_delta=0, macroblocks_cavlc=[pcm])
p = dict(nal_ref_idc=2, nal_unit_type=1, first_mb_in_slice=0, slice_type=5, pic_parameter_set_id=0,
	frame_num={"bits": 4, "absolute": 1}, pic_order_cnt={"type": 2},
	num_ref_idx_active={"override_flag": 0, "l0": 1},
	ref_pic_list_modification_l0=[("sref", -(1 << 31))], # abs_diff_pic_num_minus1 = 2^31 - 1
	slice_qp_delta=0, macroblocks_cavlc=[{"mb_skip_run": 1}])

with open(out, "wb") as f: # the NAL loop of gen_avc.main
	for nal in gen_avc.map_dicts([sps, pps, idr, p]):
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
