#!/usr/bin/env python3
# Generate tests/conformance/2d-synthetic/cavlc_ac_overflow.264: a damaged High profile
# CAVLC picture of two macroblocks. The first is Intra_16x16 whose first luma AC block
# (15 coefficients) codes one coefficient with total_zeros 15 - a value the total_zeros
# table only allows for blocks of 16 coefficients (9.2.3), placing it one past the end
# of the block's scan. The second is Intra_8x8 with a coded 8x8 block without any
# coefficient. gen_avc picks the total_zeros table from the length of the coefficient
# list, so a list of 16 entries writes the damaged code. Usage:
#   python3 tests/gen_cavlc_ac_overflow.py tests/conformance/2d-synthetic/cavlc_ac_overflow.264
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_avc
out = sys.argv[1] if len(sys.argv) > 1 else "tests/conformance/2d-synthetic/cavlc_ac_overflow.264"

W, H = 2, 1
sps = dict(nal_ref_idc=3, nal_unit_type=7, profile_idc=100, constraint_set_flags=[0, 0, 0, 0, 0, 0],
	level_idc=3.0, chroma_format_idc=1, bit_depth={"luma": 8, "chroma": 8}, qpprime_y_zero_transform_bypass_flag=0,
	log2_max_frame_num=4, pic_order_cnt_type=2, max_num_ref_frames=1,
	gaps_in_frame_num_value_allowed_flag=0, pic_size_in_mbs={"width": W, "height": H},
	frame_mbs_only_flag=1, direct_8x8_inference_flag=1)
pps = dict(nal_ref_idc=3, nal_unit_type=8, pic_parameter_set_id=0, entropy_coding_mode_flag=0,
	bottom_field_pic_order_in_frame_present_flag=0, num_slice_groups=1,
	num_ref_idx_default_active={"l0": 1, "l1": 1}, weighted_pred_flag=0, weighted_bipred_idc=0,
	pic_init_qp=26, chroma_qp_index_offset=0, deblocking_filter_control_present_flag=1,
	constrained_intra_pred_flag=0, redundant_pic_cnt_present_flag=0,
	transform_8x8_mode_flag=1, pic_scaling_matrix_present_flag=0, second_chroma_qp_index_offset=0)

# I_16x16_2_0_1 (DC prediction, no chroma residual, all luma AC blocks coded): the DC
# block holds one coefficient, the first AC block the damaged one, the others are empty
intra16x16 = dict(mb_type=15, intra_chroma_pred_mode=0, mb_qp_delta=0,
	coeffLevels=[{"nC": 0, "c": [8] + [0] * 15}, {"nC": 0, "c": [0] * 15 + [20]}] + [{"nC": 0, "c": [0] * 15}] * 15)
# I_NxN with an 8x8 transform, every block predicted DC, the first 8x8 block coded
intra8x8 = dict(mb_type=0, transform_size_8x8_flag=1, rem_intra8x8_pred_modes=[-1] * 4,
	intra_chroma_pred_mode=0, coded_block_pattern=1, mb_qp_delta=0,
	coeffLevels=[{"nC": 0, "c": [0] * 16}] * 4)

nals = [sps, pps, dict(nal_ref_idc=3, nal_unit_type=5, first_mb_in_slice=0, slice_type=7, pic_parameter_set_id=0,
	frame_num={"bits": 4, "absolute": 0}, idr_pic_id=0, pic_order_cnt={"type": 2}, no_output_of_prior_pics_flag=0,
	long_term_reference_flag=0, slice_qp_delta=0, disable_deblocking_filter_idc=1,
	macroblocks_cavlc=[intra16x16, intra8x8])]

with open(out, "wb") as f: # the NAL loop of gen_avc.main
	for nal in gen_avc.map_dicts(nals):
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
