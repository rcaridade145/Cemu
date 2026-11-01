#!/usr/bin/env python3
# Generate tests/conformance/2d-synthetic/cavlc8x8_deblock.264: a High profile CAVLC
# stream with 8x8 transforms, whose P pictures have two slices: the first macroblock
# row without deblocking (disable_deblocking_filter_idc 1), the second with it (idc 0).
# In the first row an inter macroblock with an 8x8 transform carries only the DC
# coefficient of its bottom-left 8x8 block, which CAVLC codes in the first of the four
# interleaved 4x4 blocks of that 8x8 block, not in its bottom row. The skipped
# macroblock below it shares an edge with that 8x8 block, which 8.7.2.1 filters with
# boundary strength 2, as the 8x8 block has a non-zero coefficient. The reference is a
# flat IDR picture of I_PCM macroblocks. Usage:
#   python3 tests/gen_cavlc8x8_deblock.py tests/conformance/2d-synthetic/cavlc8x8_deblock.264
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_avc
out = sys.argv[1] if len(sys.argv) > 1 else "tests/conformance/2d-synthetic/cavlc8x8_deblock.264"

W, H = 2, 2
sps = dict(nal_ref_idc=3, nal_unit_type=7, profile_idc=100, constraint_set_flags=[0, 0, 0, 0, 0, 0],
	level_idc=3.0, chroma_format_idc=1, bit_depth={"luma": 8, "chroma": 8}, qpprime_y_zero_transform_bypass_flag=0,
	log2_max_frame_num=4, pic_order_cnt_type=2, max_num_ref_frames=1,
	gaps_in_frame_num_value_allowed_flag=0, pic_size_in_mbs={"width": W, "height": H},
	frame_mbs_only_flag=1, direct_8x8_inference_flag=1)
pps = dict(nal_ref_idc=3, nal_unit_type=8, pic_parameter_set_id=0, entropy_coding_mode_flag=0,
	bottom_field_pic_order_in_frame_present_flag=0, num_slice_groups=1,
	num_ref_idx_default_active={"l0": 1, "l1": 1}, weighted_pred_flag=0, weighted_bipred_idc=0,
	pic_init_qp=28, chroma_qp_index_offset=0, deblocking_filter_control_present_flag=1,
	constrained_intra_pred_flag=0, redundant_pic_cnt_present_flag=0,
	transform_8x8_mode_flag=1, pic_scaling_matrix_present_flag=0, second_chroma_qp_index_offset=0)
pcm = dict(mb_type=25, pcm_samples={"bits_Y": 8, "bits_C": 8, "Y": [100] * 256, "Cb": [128] * 64, "Cr": [128] * 64})

def p_picture(frame_num, dc):
	# first row: an 8x8-transform macroblock with the DC of its bottom-left 8x8 block,
	# then a skipped one; second row: skipped macroblocks
	coded = dict(mb_skip_run=0, mb_type=0, ref_idx={}, mvds=[[0, 0]], coded_block_pattern=4,
		transform_size_8x8_flag=1, mb_qp_delta=0,
		coeffLevels=[{"nC": 0, "c": [dc] + [0] * 15}] + [{"nC": 0, "c": [0] * 16}] * 3)
	common = dict(nal_ref_idc=3, nal_unit_type=1, slice_type=5, pic_parameter_set_id=0,
		frame_num={"bits": 4, "absolute": frame_num}, pic_order_cnt={"type": 2},
		num_ref_idx_active={"override_flag": 0, "l0": 1}, slice_qp_delta=0)
	return [dict(common, first_mb_in_slice=0, disable_deblocking_filter_idc=1, macroblocks_cavlc=[coded, {"mb_skip_run": 1}]),
		dict(common, first_mb_in_slice=W, disable_deblocking_filter_idc=0, slice_alpha_c0_offset=0, slice_beta_offset=0,
			macroblocks_cavlc=[{"mb_skip_run": W}])]

nals = [sps, pps, dict(nal_ref_idc=3, nal_unit_type=5, first_mb_in_slice=0, slice_type=7, pic_parameter_set_id=0,
	frame_num={"bits": 4, "absolute": 0}, idr_pic_id=0, pic_order_cnt={"type": 2}, no_output_of_prior_pics_flag=0,
	long_term_reference_flag=0, slice_qp_delta=0, disable_deblocking_filter_idc=1, macroblocks_cavlc=[pcm] * (W * H))]
for i, dc in enumerate([3, -4, 6]):
	nals += p_picture(i + 1, dc)

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
