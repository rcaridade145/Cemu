#!/usr/bin/env python3
"""Check that edge264mvc_test compares every sample of a frame with its .yuv reference.

For each stream, the decoded frames (written with -o) serve as the reference
YUV, which must PASS. Then a single sample is changed at a corner of the first
or the last frame, in each plane, and every such change must FAIL - including
the right-hand columns and the bottom rows, and the corners of a cropped picture,
whose differing macroblock is then printed in part. A reference one frame short
or one frame long must FAIL too, for the base view and, on an MVC stream, for
the dependent view (.1.yuv).
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

STREAMS = (
	Path("tests/conformance/2d/BA1_Sony_D.264"), # 176x144
	Path("tests/conformance/2d-synthetic/plane_without_d.264"), # 1920x1080, cropped from 1088
	Path("tests/conformance/2d-synthetic/crop_top_left.264"), # 48x32, cropped by 8 on every side
)
MVC_STREAM = Path("tests/conformance/mvc/MVCDS-5.264")


def run(exe, stream, timeout):
	return subprocess.run([exe, "-s", str(stream)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)


def decoded_frames(exe, source, mode, timeout):
	# the frames edge264mvc_test writes as Y4M (-o: base view, -O: both side by side)
	y4m = subprocess.run([exe, "-s", mode, str(source)], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=timeout).stdout
	header, _, body = y4m.partition(b"\n")
	fields = dict((f[:1], f[1:]) for f in header.split()[1:])
	width, height = int(fields[b"W"]), int(fields[b"H"])
	frame_size = width * height * 3 // 2
	frames = [f[:frame_size] for f in body.split(b"FRAME\n")[1:]]
	if not frames or any(len(f) != frame_size for f in frames):
		return None, width, height
	return frames, width, height


def split_views(frame, width, height):
	# a side-by-side frame into its base and dependent views, plane by plane
	views = (bytearray(), bytearray())
	offset = 0
	for w, h in ((width, height), (width // 2, height // 2), (width // 2, height // 2)):
		for y in range(h):
			row = frame[offset + y * w:offset + (y + 1) * w]
			views[0].extend(row[:w // 2])
			views[1].extend(row[w // 2:])
		offset += w * h
	return bytes(views[0]), bytes(views[1])


def check_length(exe, stream, yuv, frames, label, message, timeout):
	# a reference one frame short or one frame long FAILs, with its message
	failures = 0
	for name, reference, text in (
		("one frame short", b"".join(frames[:-1]), b"More frames than the reference"),
		("one frame long", b"".join(frames + frames[-1:]), b"Fewer frames than the reference"),
	):
		yuv.write_bytes(reference)
		result = run(exe, stream, timeout)
		if result.returncode != 1 or text not in result.stdout:
			print(f"FAIL {label}: a {message} {name} gives exit status {result.returncode}" + ("" if text in result.stdout else ", without saying so"))
			failures += 1
	yuv.write_bytes(b"".join(frames))
	return failures


def main():
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--exe", default="./edge264mvc_test")
	parser.add_argument("--timeout", type=float, default=60)
	args = parser.parse_args()
	exe = str(Path(args.exe).resolve())
	failures = 0
	with tempfile.TemporaryDirectory() as tmp:
		for source in STREAMS:
			stream = Path(tmp) / source.name
			shutil.copyfile(source, stream)
			y4m = subprocess.run([exe, "-s", "-o", str(source)], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=args.timeout).stdout
			header, _, body = y4m.partition(b"\n")
			fields = dict((f[:1], f[1:]) for f in header.split()[1:])
			width, height = int(fields[b"W"]), int(fields[b"H"])
			frame_size = width * height * 3 // 2
			frames = [f[:frame_size] for f in body.split(b"FRAME\n")[1:]]
			if not frames or any(len(f) != frame_size for f in frames):
				print(f"FAIL {source}: could not read the decoded frames")
				failures += 1
				continue
			reference = b"".join(frames)
			yuv = stream.with_suffix(".yuv")
			yuv.write_bytes(reference)
			if run(exe, stream, args.timeout).returncode != 0:
				print(f"FAIL {source}: the decoded frames do not PASS as their own reference")
				failures += 1
				continue
			# the corners of each plane, in the first and the last frame
			planes = ((0, width, height), (width * height, width // 2, height // 2), (width * height * 5 // 4, width // 2, height // 2))
			for frame in (0, len(frames) - 1):
				for plane, (offset, w, h) in enumerate(planes):
					for x, y in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
						pos = frame * frame_size + offset + y * w + x
						changed = bytearray(reference)
						changed[pos] ^= 0x55
						yuv.write_bytes(changed)
						result = run(exe, stream, args.timeout).returncode
						if result != 1: # FAIL, after printing the macroblock, rather than PASS or a crash
							print(f"FAIL {source}: a change at frame {frame}, plane {plane}, x {x}, y {y} gives exit status {result}, not 1")
							failures += 1
			yuv.write_bytes(reference)
			failures += check_length(exe, stream, yuv, frames, source, "reference", args.timeout)
		# the dependent view of an MVC stream has its own reference (.1.yuv)
		stream = Path(tmp) / MVC_STREAM.name
		shutil.copyfile(MVC_STREAM, stream)
		frames, width, height = decoded_frames(exe, MVC_STREAM, "-O", args.timeout)
		if frames is None:
			print(f"FAIL {MVC_STREAM}: could not read the decoded frames")
			failures += 1
		else:
			views = [split_views(f, width, height) for f in frames]
			base, dependent = stream.with_suffix(".yuv"), stream.with_suffix(".1.yuv")
			base.write_bytes(b"".join(v[0] for v in views))
			dependent.write_bytes(b"".join(v[1] for v in views))
			if run(exe, stream, args.timeout).returncode != 0:
				print(f"FAIL {MVC_STREAM}: the decoded views do not PASS as their own reference")
				failures += 1
			else:
				failures += check_length(exe, stream, dependent, [v[1] for v in views], MVC_STREAM, "dependent-view reference", args.timeout)
	if failures:
		print(f"edge264mvc_test YUV comparison: {failures} checks FAILED")
		return 1
	print(f"edge264mvc_test YUV comparison PASS ({len(STREAMS) + 1} streams)")
	return 0


if __name__ == "__main__":
	sys.exit(main())
