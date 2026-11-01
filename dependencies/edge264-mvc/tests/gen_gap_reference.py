#!/usr/bin/env python3
# Generate tests/conformance/2d-synthetic/gap_reference.264: a 176x144 Main-profile
# stream with one reference picture removed, so the next picture predicts from the
# frame that 8.2.5.2 infers for the frame_num gap. Input is a libx264 encode of
# FFmpeg's testsrc2 with a single reference frame and no B-frames, so every P
# picture predicts from the one before it:
#   ffmpeg -f lavfi -i testsrc2=size=176x144:rate=25 -frames:v 16 -c:v libx264 \
#     -profile:v main -pix_fmt yuv420p \
#     -x264-params ref=1:bframes=0:keyint=100:min-keyint=100:scenecut=0 -f h264 base.264
# The x264 output depends on its version, so the committed .264 is the reference.
# Usage:
#   python3 tests/gen_gap_reference.py base.264 tests/conformance/2d-synthetic/gap_reference.264
import re, sys
src, out = sys.argv[1], sys.argv[2]
DROP = 6 # index of the removed picture (0 = the IDR)

data = open(src, "rb").read()
starts = [m.end() for m in re.finditer(b"\x00\x00\x01", data)]
nals = []
for k, s in enumerate(starts):
	e = starts[k + 1] - 3 if k + 1 < len(starts) else len(data)
	while e > s and data[e - 1] == 0 and k + 1 < len(starts):
		e -= 1
	nals.append(data[s:e])
slices = [k for k, n in enumerate(nals) if n[0] & 0x1f in (1, 5)]
assert nals[slices[DROP]][0] >> 5, "the removed picture must be a reference picture"
open(out, "wb").write(b"".join(b"\x00\x00\x00\x01" + n for k, n in enumerate(nals) if k != slices[DROP]))
print(f"wrote {out}: picture {DROP} of {len(slices)} removed")
