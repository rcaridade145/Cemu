#!/usr/bin/env python3
# Generate tests/conformance/2d-synthetic/plane_without_d.264: three 1920x1080 IDR
# pictures of two slices each. Slice 1 covers macroblocks 0..7259 in flat gray,
# except its last macroblock 7259, an I_PCM block of 255 (luma) and 200 (chroma).
# Slice 2 starts in the middle of a row at 7260 and covers the rest in flat gray,
# except macroblock 7260 + 120 one row below its start, which signals Intra_16x16
# and chroma Plane prediction. Its left (A) and upper (B) neighbours belong to
# slice 2, but its upper-left neighbour D is macroblock 7259 of slice 1, which
# Plane prediction needs (8.3.3.4, 8.3.4.4) and which is unavailable across the
# slice boundary - a non-conformant stream. Usage:
#   python3 tests/gen_plane_without_d.py tests/conformance/2d-synthetic/plane_without_d.264
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_avc
out = sys.argv[1] if len(sys.argv) > 1 else "tests/conformance/2d-synthetic/plane_without_d.264"

W, H, PICS = 120, 68, 3
F = 60 * W + 60 # first macroblock of slice 2, in the middle of row 60
sps = dict(nal_ref_idc=3, nal_unit_type=7, profile_idc=66, constraint_set_flags=[0, 0, 0, 0, 0, 0],
	level_idc=4.0, log2_max_frame_num=4, pic_order_cnt_type=2, max_num_ref_frames=1, chroma_format_idc=1,
	gaps_in_frame_num_value_allowed_flag=0, pic_size_in_mbs={"width": W, "height": H},
	frame_mbs_only_flag=1, direct_8x8_inference_flag=1,
	frame_crop_offsets={"left": 0, "right": 0, "top": 0, "bottom": 8})
pps = dict(nal_ref_idc=3, nal_unit_type=8, pic_parameter_set_id=0, entropy_coding_mode_flag=0,
	bottom_field_pic_order_in_frame_present_flag=0, num_slice_groups=1,
	num_ref_idx_default_active={"l0": 1, "l1": 1}, weighted_pred_flag=0, weighted_bipred_idc=0,
	pic_init_qp=26, chroma_qp_index_offset=0, deblocking_filter_control_present_flag=1,
	constrained_intra_pred_flag=0, redundant_pic_cnt_present_flag=0)
flat = dict(mb_type=0, rem_intra4x4_pred_modes=[-1] * 16, intra_chroma_pred_mode=0, coded_block_pattern=0)
pcm = dict(mb_type=25, pcm_samples={"bits_Y": 8, "bits_C": 8, "Y": [255] * 256, "Cb": [200] * 64, "Cr": [200] * 64})
plane = dict(mb_type=4, intra_chroma_pred_mode=3, mb_qp_delta=0, coeffLevels=[{"nC": 0, "c": []}]) # I_16x16_3_0_0
def slice(first, mbs, idr_pic_id):
	return dict(nal_ref_idc=3, nal_unit_type=5, first_mb_in_slice=first, slice_type=7,
		pic_parameter_set_id=0, frame_num={"bits": 4, "absolute": 0}, idr_pic_id=idr_pic_id,
		pic_order_cnt={"type": 2}, no_output_of_prior_pics_flag=0, long_term_reference_flag=0,
		slice_qp_delta=0, disable_deblocking_filter_idc=1, macroblocks_cavlc=mbs)
nals = [sps, pps]
for p in range(PICS):
	nals.append(slice(0, [flat] * (F - 1) + [pcm], p % 2))
	nals.append(slice(F, [flat] * W + [plane] + [flat] * (W * H - F - W - 1), p % 2))

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
