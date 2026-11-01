#!/usr/bin/env python3
# Give the second slice of every picture its own deblocking filter offsets.
#
# Input: an Annex-B stream of IDR pictures (x264 keyint=1) with several CABAC
# slices per picture and deblocking_filter_control_present_flag = 1. Every
# slice header is re-serialized with slice_alpha_c0_offset_div2 and
# slice_beta_offset_div2 set to +ALPHA/+BETA in odd slices (counted per
# picture) and left as encoded in the others, then padded with
# cabac_alignment_one_bit up to the unchanged slice data. The result is a
# picture whose macroblocks must be deblocked with the parameters of their own
# slice (8.7), which a decoder finishing a picture with another slice's
# parameters gets wrong.
#
# Usage: gen_slice_deblock_offsets.py <in.264> <out.264> [alpha_div2] [beta_div2]
import sys


class Reader:
	def __init__(self, data):
		self.bits = ''.join(f'{b:08b}' for b in data)
		self.pos = 0
	def u(self, n):
		v = int(self.bits[self.pos:self.pos + n], 2) if n else 0
		self.pos += n
		return v
	def ue(self, ):
		z = 0
		while self.bits[self.pos] == '0':
			z += 1
			self.pos += 1
		self.pos += 1
		return (1 << z) - 1 + self.u(z)
	def se(self):
		k = self.ue()
		return (k + 1) // 2 if k & 1 else -(k // 2)


class Writer:
	def __init__(self):
		self.bits = []
	def u(self, n, v):
		self.bits.append(format(v, f'0{n}b') if n else '')
	def ue(self, v):
		b = format(v + 1, 'b')
		self.bits.append('0' * (len(b) - 1) + b)
	def se(self, v):
		self.ue(2 * v - 1 if v > 0 else -2 * v)
	def get(self):
		return ''.join(self.bits)


def unescape(nal):
	out, zeros = bytearray(), 0
	for b in nal:
		if zeros >= 2 and b == 3:
			zeros = 0
			continue
		out.append(b)
		zeros = zeros + 1 if b == 0 else 0
	return bytes(out)


def escape(rbsp):
	out, zeros = bytearray(), 0
	for b in rbsp:
		if zeros >= 2 and b <= 3:
			out.append(3)
			zeros = 0
		out.append(b)
		zeros = zeros + 1 if b == 0 else 0
	return bytes(out)


def split_nals(buf):
	starts = []
	i = 0
	while i < len(buf) - 2:
		if buf[i] == 0 and buf[i + 1] == 0 and buf[i + 2] == 1:
			starts.append(i + 3)
			i += 3
		else:
			i += 1
	nals = []
	for k, s in enumerate(starts):
		e = starts[k + 1] - 3 if k + 1 < len(starts) else len(buf)
		while e > s and buf[e - 1] == 0:
			e -= 1
		nals.append(buf[s:e])
	return nals


def main():
	if len(sys.argv) not in (3, 5):
		raise SystemExit('usage: gen_slice_deblock_offsets.py <in.264> <out.264> [alpha_div2] [beta_div2]')
	alpha = int(sys.argv[3]) if len(sys.argv) == 5 else 3
	beta = int(sys.argv[4]) if len(sys.argv) == 5 else 3
	sps = pps = None
	out = bytearray()
	slice_idx = 0
	for nal in split_nals(open(sys.argv[1], 'rb').read()):
		t = nal[0] & 0x1f
		rbsp = unescape(nal[1:])
		if t == 7:
			r = Reader(rbsp)
			profile = r.u(8); r.u(16); r.ue()
			if profile in (100, 110, 122, 244, 44, 83, 86, 118, 128, 138, 139, 134, 135):
				assert r.ue() == 1 # chroma_format_idc 4:2:0
				r.ue(); r.ue(); r.u(1)
				assert r.u(1) == 0 # no seq_scaling_matrix
			sps = {'log2_max_frame_num': r.ue() + 4, 'poc_type': r.ue()}
			assert sps['poc_type'] in (0, 2)
			sps['log2_max_poc_lsb'] = r.ue() + 4 if sps['poc_type'] == 0 else 0
		elif t == 8:
			r = Reader(rbsp)
			r.ue(); r.ue()
			assert r.u(1) == 1 # CABAC, so that slice data starts byte-aligned
			assert r.u(1) == 0 # bottom_field_pic_order_in_frame_present_flag
			assert r.ue() == 0 # num_slice_groups_minus1
			r.ue(); r.ue(); r.u(1); r.u(2); r.se(); r.se(); r.se()
			pps = {'deblock_ctrl': r.u(1)}
			assert pps['deblock_ctrl'] == 1
		elif t == 5:
			r, w = Reader(rbsp), Writer()
			first_mb = r.ue(); w.ue(first_mb)
			slice_idx = 0 if first_mb == 0 else slice_idx + 1
			slice_type = r.ue(); w.ue(slice_type)
			assert slice_type % 5 == 2 # I slices only
			w.ue(r.ue()) # pic_parameter_set_id
			w.u(sps['log2_max_frame_num'], r.u(sps['log2_max_frame_num']))
			w.ue(r.ue()) # idr_pic_id
			w.u(sps['log2_max_poc_lsb'], r.u(sps['log2_max_poc_lsb']))
			w.u(1, r.u(1)); w.u(1, r.u(1)) # dec_ref_pic_marking
			w.se(r.se()) # slice_qp_delta
			idc = r.ue(); w.ue(idc)
			assert idc != 1
			a, b = r.se(), r.se()
			if slice_idx & 1:
				a, b = alpha, beta
			w.se(a); w.se(b)
			while r.pos & 7: # cabac_alignment_one_bit
				r.u(1)
			bits = w.get()
			bits += '1' * (-len(bits) % 8)
			rbsp = bytes(int(bits[i:i + 8], 2) for i in range(0, len(bits), 8)) + rbsp[r.pos // 8:]
		out += b'\x00\x00\x00\x01' + nal[:1] + escape(rbsp)
	open(sys.argv[2], 'wb').write(out)


if __name__ == '__main__':
	main()
