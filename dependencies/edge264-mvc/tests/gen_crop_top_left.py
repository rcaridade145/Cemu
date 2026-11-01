#!/usr/bin/env python3
# Generate tests/conformance/2d-synthetic/crop_top_left.264: three 64x48 IDR pictures
# of I_PCM macroblocks with sample gradients, cropped by 8 samples on every side to
# 48x32, so that the first and the last macroblock of each row and column lie partly
# outside the output picture. Usage:
#   python3 tests/gen_crop_top_left.py tests/conformance/2d-synthetic/crop_top_left.264
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_avc
out = sys.argv[1] if len(sys.argv) > 1 else "tests/conformance/2d-synthetic/crop_top_left.264"

W, H = 4, 3
sps = dict(nal_ref_idc=3, nal_unit_type=7, profile_idc=66, constraint_set_flags=[0, 0, 0, 0, 0, 0],
	level_idc=3.0, log2_max_frame_num=4, pic_order_cnt_type=2, max_num_ref_frames=1, chroma_format_idc=1,
	gaps_in_frame_num_value_allowed_flag=0, pic_size_in_mbs={"width": W, "height": H},
	frame_mbs_only_flag=1, direct_8x8_inference_flag=1,
	frame_crop_offsets={"left": 8, "right": 8, "top": 8, "bottom": 8})
pps = dict(nal_ref_idc=3, nal_unit_type=8, pic_parameter_set_id=0, entropy_coding_mode_flag=0,
	bottom_field_pic_order_in_frame_present_flag=0, num_slice_groups=1,
	num_ref_idx_default_active={"l0": 1, "l1": 1}, weighted_pred_flag=0, weighted_bipred_idc=0,
	pic_init_qp=26, chroma_qp_index_offset=0, deblocking_filter_control_present_flag=1,
	constrained_intra_pred_flag=0, redundant_pic_cnt_present_flag=0)

def pcm(mb, seed):
	return dict(mb_type=25, pcm_samples={"bits_Y": 8, "bits_C": 8,
		"Y": [(x * 7 + y * 11 + mb * 29 + seed) % 256 for y in range(16) for x in range(16)],
		"Cb": [(x * 13 + y * 5 + mb * 17 + seed) % 256 for y in range(8) for x in range(8)],
		"Cr": [(x * 3 + y * 19 + mb * 23 + seed) % 256 for y in range(8) for x in range(8)]})

nals = [sps, pps]
for p in range(3):
	nals.append(dict(nal_ref_idc=3, nal_unit_type=5, first_mb_in_slice=0, slice_type=7,
		pic_parameter_set_id=0, frame_num={"bits": 4, "absolute": 0}, idr_pic_id=p % 2,
		pic_order_cnt={"type": 2}, no_output_of_prior_pics_flag=0, long_term_reference_flag=0,
		slice_qp_delta=0, disable_deblocking_filter_idc=1, macroblocks_cavlc=[pcm(a, p * 50) for a in range(W * H)]))

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
