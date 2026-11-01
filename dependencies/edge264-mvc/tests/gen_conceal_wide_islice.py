#!/usr/bin/env python3
# Generate tests/conformance/2d-synthetic/conceal_wide_islice.264: a damaged stream of
# CAVLC IDR pictures 140 macroblocks wide and one high, each a single slice of I_PCM
# macroblocks with deblocking, which codes one macroblock more than the picture has,
# so that the slice fails at its end. The concealment of a damaged I slice blends the
# macroblocks of its last row with their DC prediction, each by its error probability,
# which counts up from the start of the slice; in a slice this long the first
# macroblock gets the weight 0 - kept as decoded. Every macroblock carries its own
# I_PCM samples. Usage:
#   python3 tests/gen_conceal_wide_islice.py tests/conformance/2d-synthetic/conceal_wide_islice.264
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_avc
out = sys.argv[1] if len(sys.argv) > 1 else "tests/conformance/2d-synthetic/conceal_wide_islice.264"

W, H, CODED, PICS = 140, 1, 141, 2
sps = dict(nal_ref_idc=3, nal_unit_type=7, profile_idc=66, constraint_set_flags=[0, 0, 0, 0, 0, 0],
	level_idc=5.1, log2_max_frame_num=4, pic_order_cnt_type=2, max_num_ref_frames=1, chroma_format_idc=1,
	gaps_in_frame_num_value_allowed_flag=0, pic_size_in_mbs={"width": W, "height": H},
	frame_mbs_only_flag=1, direct_8x8_inference_flag=1)
pps = dict(nal_ref_idc=3, nal_unit_type=8, pic_parameter_set_id=0, entropy_coding_mode_flag=0,
	bottom_field_pic_order_in_frame_present_flag=0, num_slice_groups=1,
	num_ref_idx_default_active={"l0": 1, "l1": 1}, weighted_pred_flag=0, weighted_bipred_idc=0,
	pic_init_qp=26, chroma_qp_index_offset=0, deblocking_filter_control_present_flag=1,
	constrained_intra_pred_flag=0, redundant_pic_cnt_present_flag=0)

def pcm(i, pic):
	y = 40 + (i * 7 + pic * 50) % 180
	return dict(mb_type=25, pcm_samples={"bits_Y": 8, "bits_C": 8, "Y": [y] * 256,
		"Cb": [60 + i % 120] * 64, "Cr": [200 - i % 120] * 64})

nals = [sps, pps]
for pic in range(PICS):
	nals.append(dict(nal_ref_idc=3, nal_unit_type=5, first_mb_in_slice=0, slice_type=7, pic_parameter_set_id=0,
		frame_num={"bits": 4, "absolute": 0}, idr_pic_id=pic, pic_order_cnt={"type": 2},
		no_output_of_prior_pics_flag=0, long_term_reference_flag=0, slice_qp_delta=0,
		disable_deblocking_filter_idc=0, slice_alpha_c0_offset=0, slice_beta_offset=0, macroblocks_cavlc=[pcm(i, pic) for i in range(CODED)]))

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
