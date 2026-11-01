#!/usr/bin/env python3
# Generate tests/asan/reflist_poc_distance.264: a 1x1-macroblock Main-profile stream
# whose picture order counts climb by 32767 per reference frame (an IDR, then seven
# P frames, each pic_order_cnt_lsb step just under half of MaxPicOrderCntLsb = 2^16),
# followed by a B slice. The B slice's initial RefPicList sort then sees short-term
# references 196602 to 262136 below its own picture order count - far outside the
# DiffPicOrderCnt range of 8.2.1, so a damaged or crafted stream. Every macroblock
# is skipped or I_NxN with no residual, so the stream carries no picture data. Usage:
#   python3 tests/gen_reflist_poc_distance.py tests/asan/reflist_poc_distance.264
import os, subprocess, sys, tempfile
out = sys.argv[1] if len(sys.argv) > 1 else "tests/asan/reflist_poc_distance.264"

STEP = 32767
parts = ["""---
- nal_ref_idc: 3
  nal_unit_type: 7
  profile_idc: 77
  constraint_set_flags: [0,0,0,0,0,0]
  level_idc: 4.1
  log2_max_frame_num: 4
  pic_order_cnt_type: 0
  log2_max_pic_order_cnt_lsb: 16
  max_num_ref_frames: 8
  gaps_in_frame_num_value_allowed_flag: 0
  pic_size_in_mbs: {width: 1, height: 1}
  frame_mbs_only_flag: 1
  direct_8x8_inference_flag: 1
- nal_ref_idc: 3
  nal_unit_type: 8
  pic_parameter_set_id: 0
  entropy_coding_mode_flag: 0
  bottom_field_pic_order_in_frame_present_flag: 0
  num_slice_groups: 1
  num_ref_idx_default_active: {l0: 1, l1: 1}
  weighted_pred_flag: 0
  weighted_bipred_idc: 0
  pic_init_qp: 26
  chroma_qp_index_offset: 0
  deblocking_filter_control_present_flag: 0
  constrained_intra_pred_flag: 0
  redundant_pic_cnt_present_flag: 0
- nal_ref_idc: 3
  nal_unit_type: 5
  first_mb_in_slice: 0
  slice_type: 2
  pic_parameter_set_id: 0
  frame_num: {bits: 4, absolute: 0}
  idr_pic_id: 0
  pic_order_cnt: {type: 0, bits: 16, absolute: 0}
  no_output_of_prior_pics_flag: 0
  long_term_reference_flag: 0
  slice_qp_delta: 0
  macroblocks_cavlc:
  - mb_type: 0
    rem_intra4x4_pred_modes: [-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1]
    intra_chroma_pred_mode: 0
    coded_block_pattern: 0
"""]
for n in range(1, 8):
	parts.append(f"""- nal_ref_idc: 3
  nal_unit_type: 1
  first_mb_in_slice: 0
  slice_type: 0
  pic_parameter_set_id: 0
  frame_num: {{bits: 4, absolute: {n}}}
  pic_order_cnt: {{type: 0, bits: 16, absolute: {n * STEP}}}
  num_ref_idx_active: {{override_flag: 0, l0: 1}}
  slice_qp_delta: 0
  macroblocks_cavlc:
  - mb_skip_run: 1
""")
parts.append(f"""- nal_ref_idc: 0
  nal_unit_type: 1
  first_mb_in_slice: 0
  slice_type: 1
  pic_parameter_set_id: 0
  frame_num: {{bits: 4, absolute: 8}}
  pic_order_cnt: {{type: 0, bits: 16, absolute: {8 * STEP}}}
  direct_spatial_mv_pred_flag: 1
  num_ref_idx_active: {{override_flag: 0, l0: 1, l1: 1}}
  slice_qp_delta: 0
  macroblocks_cavlc:
  - mb_skip_run: 1
""")

with tempfile.TemporaryDirectory() as tmp:
	yaml = os.path.join(tmp, "reflist_poc_distance.yaml")
	open(yaml, "w").write("".join(parts))
	subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "gen_avc.py"), yaml, out], check=True, stdout=subprocess.DEVNULL)
print(f"wrote {out}")
