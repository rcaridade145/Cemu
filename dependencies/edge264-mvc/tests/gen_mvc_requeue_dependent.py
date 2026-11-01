#!/usr/bin/env python3
# Generate tests/liveness/mvc_requeue_dependent.yaml (then .264 with gen_avc.py): a
# damaged 1x1-macroblock Stereo High MVC stream that fills the DPB while its caller
# receives one frame per round (tests/partial_receive_check.c). 8 paired reference
# access units, then 16 base pictures without dependent view, then an access unit
# whose dependent view comes before its base view - decoded into the last free DPB
# slot, so that its base view finds the DPB full - then 20 base pictures. Every
# picture is an I_PCM macroblock whose luma tells its view and POC (base
# 16 + 2 * POC, dependent 17 + 2 * POC). Usage:
#   python3 tests/gen_mvc_requeue_dependent.py tests/liveness/mvc_requeue_dependent.yaml
#   python3 tests/gen_avc.py tests/liveness/mvc_requeue_dependent.yaml tests/liveness/mvc_requeue_dependent.264
import sys
out = sys.argv[1] if len(sys.argv) > 1 else "tests/liveness/mvc_requeue_dependent.yaml"
UNPAIRED = 16

def pcm_mb(slice_type, y):
	Y = ",".join(["%d" % y] * 256)
	C = ",".join(["128"] * 64)
	skip = "" if slice_type == 2 else "mb_skip_run: 0\n    " # P slices signal no skip first
	return (f"  - {skip}mb_type: {25 if slice_type == 2 else 30}\n"
		f"    pcm_samples: {{bits_Y: 8, bits_C: 8, Y: [{Y}], Cb: [{C}], Cr: [{C}]}}\n")

def base(nut, fn, poc, nri):
	slice_type = 2 if nut == 5 else 0
	idr = "  idr_pic_id: 0\n" if nut == 5 else ""
	extra = ("  no_output_of_prior_pics_flag: 0\n  long_term_reference_flag: 0\n" if nut == 5 else
		"  num_ref_idx_active: {override_flag: 0, l0: 1}\n")
	return (f"- nal_ref_idc: {nri}\n  nal_unit_type: 14\n  non_idr_flag: {0 if nut == 5 else 1}\n"
		f"  priority_id: 0\n  view_id: 0\n  temporal_id: 0\n  anchor_pic_flag: {1 if nut == 5 else 0}\n  inter_view_flag: 1\n"
		f"- nal_ref_idc: {nri}\n  nal_unit_type: {nut}\n  first_mb_in_slice: 0\n  slice_type: {slice_type}\n"
		f"  pic_parameter_set_id: 0\n  frame_num: {{bits: 10, absolute: {fn}}}\n{idr}"
		f"  pic_order_cnt: {{type: 0, bits: 8, absolute: {poc}}}\n{extra}"
		f"  slice_qp_delta: 0\n  macroblocks_cavlc:\n{pcm_mb(slice_type, 16 + 2 * poc)}")

def dep(nut, fn, poc, nri):
	slice_type = 2 if nut == 5 else 0
	idr = "  idr_pic_id: 0\n" if nut == 5 else ""
	extra = ("  no_output_of_prior_pics_flag: 0\n  long_term_reference_flag: 0\n" if nut == 5 else
		"  num_ref_idx_active: {override_flag: 0, l0: 1}\n")
	return (f"- nal_ref_idc: {nri}\n  nal_unit_type: 20\n  non_idr_flag: {0 if nut == 5 else 1}\n"
		f"  priority_id: 0\n  view_id: 1\n  temporal_id: 0\n  anchor_pic_flag: {1 if nut == 5 else 0}\n  inter_view_flag: 0\n"
		f"  first_mb_in_slice: 0\n  slice_type: {slice_type}\n  pic_parameter_set_id: 1\n"
		f"  frame_num: {{bits: 10, absolute: {fn}}}\n{idr}"
		f"  pic_order_cnt: {{type: 0, bits: 8, absolute: {poc}}}\n{extra}"
		f"  slice_qp_delta: 0\n  macroblocks_cavlc:\n{pcm_mb(slice_type, 17 + 2 * poc)}")

SPS = """  constraint_set_flags: [0,0,0,0,0,0]
  level_idc: 4.1
  chroma_format_idc: 1
  bit_depth: {luma: 8, chroma: 8}
  log2_max_frame_num: 10
  pic_order_cnt_type: 0
  log2_max_pic_order_cnt_lsb: 8
  max_num_ref_frames: 8
  gaps_in_frame_num_value_allowed_flag: 1
  pic_size_in_mbs: {width: 1, height: 1}
  frame_mbs_only_flag: 1
  direct_8x8_inference_flag: 0
"""
PPS = """  entropy_coding_mode_flag: 0
  bottom_field_pic_order_in_frame_present_flag: 0
  num_slice_groups: 1
  num_ref_idx_default_active: {l0: 1, l1: 1}
  weighted_pred_flag: 0
  weighted_bipred_idc: 0
  pic_init_qp: 0
  chroma_qp_index_offset: 0
  deblocking_filter_control_present_flag: 0
  constrained_intra_pred_flag: 0
  redundant_pic_cnt_present_flag: 0
"""
parts = ["--- # see tests/gen_mvc_requeue_dependent.py\n",
	"- nal_ref_idc: 3\n  nal_unit_type: 7\n  profile_idc: 66\n" + SPS,
	"- nal_ref_idc: 3\n  nal_unit_type: 8\n  pic_parameter_set_id: 0\n" + PPS,
	"- nal_ref_idc: 3\n  nal_unit_type: 15\n  profile_idc: 128\n  qpprime_y_zero_transform_bypass_flag: 0\n" + SPS +
	"  view_ids: [0,1]\n  num_anchor_refs: {l0: 0, l1: 0}\n  num_non_anchor_refs: {l0: 0, l1: 0}\n"
	"  level_values_signalled:\n    - idc: 4.1\n      operation_points: [{temporal_id: 0, target_views: [0,1], num_views: 2}]\n",
	"- nal_ref_idc: 3\n  nal_unit_type: 8\n  pic_parameter_set_id: 1\n" + PPS]
for i in range(8): # paired references
	parts += [base(5 if i == 0 else 1, i, 2 * i, 3), dep(5 if i == 0 else 1, i, 2 * i, 3)]
for k in range(UNPAIRED): # base pictures without dependent view
	parts.append(base(1, 8, 16 + 2 * k, 0))
D = 16 + 2 * UNPAIRED
parts += [dep(1, 8, D, 0), base(1, 8, D, 0)] # dependent view first
for poc in range(D + 2, D + 42, 2):
	parts.append(base(1, 8, poc, 0))
open(out, "w").write("".join(parts))
print(f"wrote {out}")
