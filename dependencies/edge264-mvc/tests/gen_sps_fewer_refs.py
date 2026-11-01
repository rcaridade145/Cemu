#!/usr/bin/env python3
# Generate tests/conformance/2d-synthetic/sps_fewer_refs.264: an SPS allowing four
# reference pictures, an IDR picture and three reference P pictures of I_PCM
# samples, then the same SPS allowing one, without an IDR picture (which 7.4.1.2.1
# requires for a new SPS), a non-reference and a reference P picture of skipped
# macroblocks. Usage:
#   python3 tests/gen_sps_fewer_refs.py tests/conformance/2d-synthetic/sps_fewer_refs.264
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_avc
out = sys.argv[1] if len(sys.argv) > 1 else "tests/conformance/2d-synthetic/sps_fewer_refs.264"

W, H = 2, 2
sps = dict(nal_ref_idc=3, nal_unit_type=7, profile_idc=77, constraint_set_flags=[0, 0, 0, 0, 0, 0],
	level_idc=3.0, log2_max_frame_num=4, pic_order_cnt_type=2, max_num_ref_frames=1, chroma_format_idc=1,
	gaps_in_frame_num_value_allowed_flag=0, pic_size_in_mbs={"width": W, "height": H},
	frame_mbs_only_flag=1, direct_8x8_inference_flag=1)
pps = dict(nal_ref_idc=3, nal_unit_type=8, pic_parameter_set_id=0, entropy_coding_mode_flag=0,
	bottom_field_pic_order_in_frame_present_flag=0, num_slice_groups=1,
	num_ref_idx_default_active={"l0": 1, "l1": 1}, weighted_pred_flag=0, weighted_bipred_idc=0,
	pic_init_qp=26, chroma_qp_index_offset=0, deblocking_filter_control_present_flag=1,
	constrained_intra_pred_flag=0, redundant_pic_cnt_present_flag=0)

def pcm(luma, p_slice):
	mb = dict(mb_type=30 if p_slice else 25, pcm_samples={"bits_Y": 8, "bits_C": 8, "Y": [luma] * 256, "Cb": [128] * 64, "Cr": [luma] * 64})
	if p_slice:
		mb["mb_skip_run"] = 0
	return mb

def idr(idr_pic_id, luma, lt=1):
	return dict(nal_ref_idc=3, nal_unit_type=5, first_mb_in_slice=0, slice_type=7, pic_parameter_set_id=0,
		frame_num={"bits": 4, "absolute": 0}, idr_pic_id=idr_pic_id, pic_order_cnt={"type": 2},
		no_output_of_prior_pics_flag=0, long_term_reference_flag=lt, slice_qp_delta=0,
		disable_deblocking_filter_idc=1, macroblocks_cavlc=[pcm(luma, False)] * (W * H))

def p(frame_num, mbs, first=0):
	return dict(nal_ref_idc=2, nal_unit_type=1, first_mb_in_slice=first, slice_type=5, pic_parameter_set_id=0,
		frame_num={"bits": 4, "absolute": frame_num}, pic_order_cnt={"type": 2},
		num_ref_idx_active={"override_flag": 0, "l0": 1}, slice_qp_delta=0,
		disable_deblocking_filter_idc=1, macroblocks_cavlc=mbs)

sps4 = dict(sps, max_num_ref_frames=4)
nonref = dict(p(4, [{"mb_skip_run": W * H}]), nal_ref_idc=0)
nals = [sps4, pps, idr(0, 90, 0), *[p(i, [pcm(90 + 30 * i, True)] * (W * H)) for i in (1, 2, 3)], sps, nonref,
	p(4, [{"mb_skip_run": W * H}])]

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
