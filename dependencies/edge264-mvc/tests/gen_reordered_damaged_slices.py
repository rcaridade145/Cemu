#!/usr/bin/env python3
# Generate tests/liveness/reordered_damaged_slices.264: one 176x160 IDR picture
# coded as ten slices of one macroblock row each (I_NxN without residual), sent
# in the order 1..9, 0 with the last byte of slices 1..9 cut off. Nine damaged
# slices thus arrive before the slice that precedes them in the picture - more
# than the 8 worker threads of the multithreaded liveness run, which all used
# to wait for that slice while none was left to decode it. Usage:
#   python3 tests/gen_reordered_damaged_slices.py tests/liveness/reordered_damaged_slices.264
import io, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_avc
out = sys.argv[1] if len(sys.argv) > 1 else "tests/liveness/reordered_damaged_slices.264"

W, H = 11, 10
sps = dict(nal_ref_idc=3, nal_unit_type=7, profile_idc=66, constraint_set_flags=[0, 0, 0, 0, 0, 0],
	level_idc=1.0, log2_max_frame_num=4, pic_order_cnt_type=2, max_num_ref_frames=1, chroma_format_idc=1,
	gaps_in_frame_num_value_allowed_flag=0, pic_size_in_mbs={"width": W, "height": H},
	frame_mbs_only_flag=1, direct_8x8_inference_flag=1)
pps = dict(nal_ref_idc=3, nal_unit_type=8, pic_parameter_set_id=0, entropy_coding_mode_flag=0,
	bottom_field_pic_order_in_frame_present_flag=0, num_slice_groups=1,
	num_ref_idx_default_active={"l0": 1, "l1": 1}, weighted_pred_flag=0, weighted_bipred_idc=0,
	pic_init_qp=26, chroma_qp_index_offset=0, deblocking_filter_control_present_flag=0,
	constrained_intra_pred_flag=0, redundant_pic_cnt_present_flag=0)
flat = dict(mb_type=0, rem_intra4x4_pred_modes=[-1] * 16, intra_chroma_pred_mode=0, coded_block_pattern=0)
def row(y):
	return dict(nal_ref_idc=3, nal_unit_type=5, first_mb_in_slice=y * W, slice_type=7,
		pic_parameter_set_id=0, frame_num={"bits": 4, "absolute": 0}, idr_pic_id=0,
		pic_order_cnt={"type": 2}, no_output_of_prior_pics_flag=0, long_term_reference_flag=0,
		slice_qp_delta=0, macroblocks_cavlc=[flat] * W)

def encode(nal): # the NAL loop of gen_avc.main, returning the escaped bytes after the start code
	f = io.BytesIO()
	bits = 1 << 1
	bits = bits << 2 | nal.nal_ref_idc
	bits = bits << 5 | nal.nal_unit_type
	bits = gen_avc.gen_bits[nal.nal_unit_type](bits, f, nal)
	bits = bits << 1 | 1
	num = bits.bit_length() - 1
	bits ^= 1 << num
	bits <<= -num % 8
	f.write(gen_avc.escape(bits.to_bytes((num + 7) // 8, byteorder="big")))
	return f.getvalue()

nals = [encode(n) for n in gen_avc.map_dicts([sps, pps])]
rows = [encode(n) for n in gen_avc.map_dicts([row(y) for y in range(H)])]
nals += [rows[y][:-1] for y in range(1, H)] + [rows[0]]
open(out, "wb").write(b"".join(b"\x00\x00\x00\x01" + n for n in nals))
print(f"wrote {out}")
