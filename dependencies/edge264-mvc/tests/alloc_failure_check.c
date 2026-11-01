// Decoding when the memory for a new picture cannot be allocated: aligned_alloc
// is interposed so that every picture allocation fails after the first <n>, for
// every n up to past the size of the DPB, on an MVC stream (whose two views share
// the DPB slots). edge264mvc_send_nal must then report EDGE264MVC_NOMEM ("it may
// be sent again") rather than EDGE264MVC_AGAIN, which promises frames to receive:
// a caller draining frames on AGAIN must never go round without progress. Linux
// only, as it relies on ELF symbol interposition.
//
// Usage: alloc_failure_check <stream.264>

#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#include "edge264mvc.h"

static int frame_allocs, allowed = -1;

// a sanitizer runtime linked into the executable intercepts aligned_alloc under
// this name, and must see every allocation it is to free
extern void *__interceptor_aligned_alloc(size_t, size_t) __attribute__((weak));

void *aligned_alloc(size_t alignment, size_t size) {
	static void *(*real)(size_t, size_t);
	if (real == NULL)
		real = __interceptor_aligned_alloc ? __interceptor_aligned_alloc : (void *(*)(size_t, size_t))dlsym(RTLD_NEXT, "aligned_alloc");
	// pictures are the only allocations larger than the decoder itself
	if (size >= 200000 && allowed >= 0 && frame_allocs++ >= allowed)
		return NULL;
	return real(alignment, size);
}

int main(int argc, char *argv[]) {
	if (argc != 2) {
		fprintf(stderr, "Usage: %s <stream.264>\n", argv[0]);
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
	const char *nt = getenv("EDGE264MVC_THREADS");
	int failures = 0;
	for (int n = 0; n <= 40; n++) {
		Edge264MvcSettings s;
		edge264mvc_default_settings(&s);
		s.n_threads = nt ? atoi(nt) : 1;
		Edge264MvcDecoder *dec;
		if (edge264mvc_open(&dec, &s) != EDGE264MVC_OK) {
			fprintf(stderr, "edge264mvc_open failed\n");
			return 2;
		}
		frame_allocs = 0;
		allowed = n;
		int nomem = 0, stalled = 0;
		Edge264MvcFrame frame;
		for (size_t pos = edge264mvc_find_start_code(buf, size), next; pos < (size_t)size && !stalled; pos = next) {
			size_t start = pos + 3;
			next = start + edge264mvc_find_start_code(buf + start, size - start);
			int res, idle = 0;
			while ((res = edge264mvc_send_nal(dec, buf + start, next - start, 0, 0)) == EDGE264MVC_AGAIN) {
				int got = 0;
				while (edge264mvc_receive_frame(dec, &frame) == EDGE264MVC_OK) {
					edge264mvc_release_frame(dec, &frame);
					got = 1;
				}
				if (!got && ++idle == 100) {
					printf("FAIL with %d pictures allocated: send_nal returned AGAIN without any frame to receive\n", n);
					failures++;
					stalled = 1;
					break;
				}
			}
			nomem += res == EDGE264MVC_NOMEM; // the NAL is skipped here, as a caller short of memory may
			while (edge264mvc_receive_frame(dec, &frame) == EDGE264MVC_OK)
				edge264mvc_release_frame(dec, &frame);
		}
		allowed = -1;
		edge264mvc_send_end(dec);
		while (edge264mvc_receive_frame(dec, &frame) == EDGE264MVC_OK)
			edge264mvc_release_frame(dec, &frame);
		edge264mvc_close(&dec);
		if (!stalled && frame_allocs > n && nomem == 0) {
			printf("FAIL with %d pictures allocated: a failed allocation was not reported as NOMEM\n", n);
			failures++;
		}
	}
	free(buf);
	if (failures) {
		printf("allocation failure check: %d checks FAILED\n", failures);
		return 1;
	}
	printf("allocation failure check PASS\n");
	return 0;
}
