#!/usr/bin/env python3
# Generate tests/conformance/2d-synthetic/weighted_denom7.264: explicit weighted
# bi-prediction at the largest weight denominator (luma and chroma
# log2_weight_denom 7). A 64x32 IDR picture and a P picture of I_PCM macroblocks
# with sample gradients covering 0..255 are the two references, and eight B pictures
# between them (direct spatial prediction, every macroblock skipped, so each one
# blends both references) use weights and offsets near the limits of 7.4.3.2:
# bright samples blended with weights summing to 127 and large offsets, negative
# weights and offsets, and three more pair the weight of 128 inferred when none is
# signalled with odd negative weights. Usage:
#   python3 tests/gen_weighted_denom7.py tests/conformance/2d-synthetic/weighted_denom7.264
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_avc
out = sys.argv[1] if len(sys.argv) > 1 else "tests/conformance/2d-synthetic/weighted_denom7.264"

class Weights(dict): # gen_avc reads the first entry by attribute and the others as dicts
	__getattr__ = dict.__getitem__

W, H = 4, 2
sps = dict(nal_ref_idc=3, nal_unit_type=7, profile_idc=77, constraint_set_flags=[0, 0, 0, 0, 0, 0],
	level_idc=3.0, log2_max_frame_num=4, pic_order_cnt_type=0, log2_max_pic_order_cnt_lsb=5, max_num_ref_frames=2,
	chroma_format_idc=1, gaps_in_frame_num_value_allowed_flag=0, pic_size_in_mbs={"width": W, "height": H},
	frame_mbs_only_flag=1, direct_8x8_inference_flag=1)
pps = dict(nal_ref_idc=3, nal_unit_type=8, pic_parameter_set_id=0, entropy_coding_mode_flag=0,
	bottom_field_pic_order_in_frame_present_flag=0, num_slice_groups=1,
	num_ref_idx_default_active={"l0": 1, "l1": 1}, weighted_pred_flag=0, weighted_bipred_idc=1,
	pic_init_qp=26, chroma_qp_index_offset=0, deblocking_filter_control_present_flag=1,
	constrained_intra_pred_flag=0, redundant_pic_cnt_present_flag=0)

def pcm(mb, seed):
	# luma rows of rising samples up to 255, chroma of falling ones, shifted per macroblock and picture
	return dict(mb_type=None, pcm_samples={"bits_Y": 8, "bits_C": 8,
		"Y": [min(255, (x * 9 + y * 5 + mb * 23 + seed) % 300) for y in range(16) for x in range(16)],
		"Cb": [max(0, 255 - (x * 17 + y * 11 + mb * 7 + seed) % 290) for y in range(8) for x in range(8)],
		"Cr": [min(255, (x * 13 + y * 19 + mb * 31 + seed) % 280) for y in range(8) for x in range(8)]})

def ref_picture(nal_unit_type, slice_type, frame_num, poc, seed):
	mbs = [pcm(a, seed) for a in range(W * H)]
	for mb in mbs:
		mb["mb_type"] = 25 if slice_type == 7 else 30 # I_PCM in an I or P slice
		if slice_type != 7:
			mb["mb_skip_run"] = 0
	s = dict(nal_ref_idc=3, nal_unit_type=nal_unit_type, first_mb_in_slice=0, slice_type=slice_type,
		pic_parameter_set_id=0, frame_num={"bits": 4, "absolute": frame_num},
		pic_order_cnt={"type": 0, "bits": 5, "absolute": poc}, slice_qp_delta=0,
		disable_deblocking_filter_idc=1, macroblocks_cavlc=mbs)
	if nal_unit_type == 5:
		s.update(idr_pic_id=0, no_output_of_prior_pics_flag=0, long_term_reference_flag=0)
	else:
		s.update(num_ref_idx_active={"override_flag": 0, "l0": 1})
	return s

def b_picture(poc, weights):
	# weights: ((w0, o0), (w1, o1)) for luma, used for chroma too
	(w0, o0), (w1, o1) = weights
	return dict(nal_ref_idc=0, nal_unit_type=1, first_mb_in_slice=0, slice_type=6,
		pic_parameter_set_id=0, frame_num={"bits": 4, "absolute": 2},
		pic_order_cnt={"type": 0, "bits": 5, "absolute": poc}, direct_spatial_mv_pred_flag=1,
		num_ref_idx_active={"override_flag": 0, "l0": 1, "l1": 1},
		explicit_weights_l0=[Weights({p: f"*{w0}>>7+{o0}" for p in ("Y", "Cb", "Cr")})],
		explicit_weights_l1=[Weights({p: f"*{w1}>>7+{o1}" for p in ("Y", "Cb", "Cr")})],
		slice_qp_delta=0, disable_deblocking_filter_idc=1, macroblocks_cavlc=[{"mb_skip_run": W * H}])

nals = [sps, pps, ref_picture(5, 7, 0, 0, 0), ref_picture(1, 5, 1, 12, 41)]
for i, weights in enumerate([((64, 1), (63, 1)), ((100, 127), (27, 127)), ((127, 64), (0, 63)),
		((-10, -128), (127, 127)), ((90, -40), (-30, 100))]):
	nals.append(b_picture(2 + 2 * i, weights))
# the inferred weight 128 (no weight signalled) paired with odd negative weights
for i, weights in enumerate([((128, 0), (-1, 0)), ((128, 0), (-3, 5)), ((128, 0), (-127, -7))]):
	nals.append(b_picture(1 + 2 * i, weights))

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
