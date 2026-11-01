#!/usr/bin/env python3
# Generate tests/conformance/2d-synthetic/ref_flip.264: the ITU conformance stream
# CABA3_SVA_B with the nal_ref_idc of its non-reference slices changed from 0 to 1, a
# damaged but valid-looking header. Its B slices then read memory management
# operations from their other bits, frame_num gaps appear and two slices fail, so
# some pictures are concealed; later B pictures predict with temporal direct
# prediction from pictures holding concealed macroblocks. Usage:
#   python3 tests/gen_ref_flip.py tests/conformance/2d-synthetic/ref_flip.264
import os, sys
here = os.path.dirname(os.path.abspath(__file__))
out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "conformance/2d-synthetic/ref_flip.264")

data = bytearray(open(os.path.join(here, "conformance/2d/CABA3_SVA_B.264"), "rb").read())
i = 0
while (i := data.find(b"\x00\x00\x01", i)) >= 0 and i + 3 < len(data):
	if data[i + 3] & 0x1f == 1 and data[i + 3] >> 5 & 3 == 0: # a non-reference slice
		data[i + 3] |= 0x20
	i += 3
open(out, "wb").write(data)
print(f"wrote {out}")
