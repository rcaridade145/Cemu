// A slice that a worker thread starts before the parser has seen the next NAL
// does not know where it ends yet. When its data runs past the start of the
// next slice (overlapping slices of a damaged stream), it learns that only
// after decoding, deblocking and publishing past it, and has to take that back
// before any other picture reads it. This harness decodes a stream
// single-threaded, then several times with worker threads while pausing before
// every slice NAL that does not start a picture, so that each such slice is
// decoded to its end before the parser sees the next one, and the picture
// after it follows without a pause. Every multithreaded run must give the
// single-threaded output.
//
// Usage: slice_overrun_check <stream.264> <threads> <pause_us> <runs>

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#ifdef _WIN32
	#include <windows.h>
	#define usleep(us) Sleep(((us) + 999) / 1000)
#else
	#include <unistd.h>
#endif

#include "edge264mvc.h"

static uint64_t hash;

static void hash_bytes(const uint8_t *p, int n) {
	for (int i = 0; i < n; i++)
		hash = (hash ^ p[i]) * 1099511628211ull;
}

static void receive(Edge264MvcDecoder *dec) {
	Edge264MvcFrame f;
	while (edge264mvc_receive_frame(dec, &f) == EDGE264MVC_OK) {
		const Edge264MvcView *v = &f.views[0];
		for (int y = 0; y < f.height_Y; y++)
			hash_bytes(v->planes[0] + (size_t)y * f.stride_Y, f.width_Y);
		for (int y = 0; y < f.height_C; y++) {
			hash_bytes(v->planes[1] + (size_t)y * f.stride_C, f.width_C);
			hash_bytes(v->planes[2] + (size_t)y * f.stride_C, f.width_C);
		}
		edge264mvc_release_frame(dec, &f);
	}
}

static uint64_t decode(const uint8_t *buf, size_t size, int n_threads, int pause_us) {
	Edge264MvcSettings s;
	edge264mvc_default_settings(&s);
	s.n_threads = n_threads;
	Edge264MvcDecoder *dec;
	if (edge264mvc_open(&dec, &s) != EDGE264MVC_OK) {
		fprintf(stderr, "edge264mvc_open failed\n");
		exit(2);
	}
	hash = 1469598103934665603ull;
	size_t pos = edge264mvc_find_start_code(buf, size);
	while (pos < size) {
		size_t start = pos + 3;
		size_t next = start + edge264mvc_find_start_code(buf + start, size - start);
		int type = buf[start] & 0x1f;
		// first_mb_in_slice is ue(v), so a slice starting a picture begins with a 1 bit
		const uint8_t *first_mb = buf + start + (type == 20 ? 4 : 1);
		if (pause_us && (type == 1 || type == 5 || type == 20) && first_mb < buf + next && !(*first_mb & 0x80))
			usleep(pause_us);
		while (edge264mvc_send_nal(dec, buf + start, next - start, 0, 0) == EDGE264MVC_AGAIN)
			receive(dec);
		receive(dec);
		pos = next;
	}
	edge264mvc_send_end(dec);
	receive(dec);
	edge264mvc_close(&dec);
	return hash;
}

int main(int argc, char *argv[]) {
	if (argc != 5) {
		fprintf(stderr, "Usage: %s <stream.264> <threads> <pause_us> <runs>\n", argv[0]);
		return 2;
	}
	FILE *f = fopen(argv[1], "rb");
	if (f == NULL) {
		perror(argv[1]);
		return 2;
	}
	fseek(f, 0, SEEK_END);
	long size = ftell(f);
	rewind(f);
	uint8_t *buf = malloc(size > 0 ? size : 1);
	if (buf == NULL || size <= 0 || fread(buf, 1, size, f) != (size_t)size) {
		fprintf(stderr, "cannot read %s\n", argv[1]);
		return 2;
	}
	fclose(f);
	int n_threads = atoi(argv[2]), pause_us = atoi(argv[3]), runs = atoi(argv[4]);
	uint64_t expected = decode(buf, size, 1, 0);
	int failures = 0;
	for (int run = 0; run < runs; run++)
		failures += decode(buf, size, n_threads, pause_us) != expected;
	free(buf);
	if (failures)
		printf("FAIL %s: %d of %d runs with %d threads differ from the single-threaded output\n", argv[1], failures, runs, n_threads);
	else
		printf("%s: %d runs with %d threads PASS\n", argv[1], runs, n_threads);
	return failures != 0;
}
