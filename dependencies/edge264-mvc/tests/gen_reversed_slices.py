#!/usr/bin/env python3
# Generate tests/conformance/2d-synthetic/reversed_slices.264 from the committed
# slice_deblock_offsets.264 by sending the slices of every picture in reverse
# order (each picture is an IDR whose slices alternate their deblocking filter
# offsets). Arbitrary slice order is legal only in Baseline profile, so for this
# CABAC stream it is damaged input: a decoder must still give the same output
# however its threads interleave the slices. Usage:
#   python3 tests/gen_reversed_slices.py tests/conformance/2d-synthetic/slice_deblock_offsets.264 \
#     tests/conformance/2d-synthetic/reversed_slices.264
import sys
from gen_slice_deblock_offsets import split_nals

src, out = sys.argv[1], sys.argv[2]
result, picture = bytearray(), []
def flush():
	for nal in reversed(picture):
		result.extend(b"\x00\x00\x00\x01" + nal)
	picture.clear()
for nal in split_nals(open(src, "rb").read()):
	if nal[0] & 0x1f in (1, 5):
		if nal[1] & 0x80 and picture: # first_mb_in_slice == 0 starts a picture (ue(0) is a single 1 bit)
			flush()
		picture.append(nal)
	else:
		flush()
		result.extend(b"\x00\x00\x00\x01" + nal)
flush()
open(out, "wb").write(result)
print(f"wrote {out}")
