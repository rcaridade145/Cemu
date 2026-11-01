// A caller that receives only part of the frames that are ready - one frame
// each time edge264mvc_send_nal returns EDGE264MVC_AGAIN, as a player showing
// one frame per refresh does - and holds up to <held> of them before it
// releases the oldest. The decoder must neither change a frame the caller
// holds nor deliver a picture of a view twice, and the end of the stream must
// come. Every frame is checked when it is released.
//
// Usage: partial_receive_check <stream.264> <held>

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "edge264mvc.h"

enum { MAX_HELD = 16, MAX_ORDER = 4096 };
static Edge264MvcDecoder *dec;
static Edge264MvcFrame held[MAX_HELD];
static uint64_t held_hash[MAX_HELD];
static int n_held, max_held, failures, frames;
static unsigned char seen[2][MAX_ORDER];

static uint64_t hash_frame(const Edge264MvcFrame *f) {
	uint64_t h = 14695981039346656037ull;
	for (int v = 0; v < 2 && f->views[v].planes[0] != NULL; v++) {
		for (int p = 0; p < 3; p++) {
			int w = p ? f->width_C : f->width_Y, hgt = p ? f->height_C : f->height_Y, s = p ? f->stride_C : f->stride_Y;
			for (int y = 0; y < hgt; y++)
				for (int x = 0; x < w; x++)
					h = (h ^ f->views[v].planes[p][(size_t)y * s + x]) * 1099511628211ull;
		}
	}
	return h;
}

static void release_oldest(void) {
	if (hash_frame(&held[0]) != held_hash[0]) {
		printf("FAIL a held frame (display order %lld) changed before it was released\n", (long long)held[0].views[0].display_order);
		failures++;
	}
	edge264mvc_release_frame(dec, &held[0]);
	memmove(held, held + 1, --n_held * sizeof(*held));
	memmove(held_hash, held_hash + 1, n_held * sizeof(*held_hash));
}

static int receive_one(void) {
	Edge264MvcFrame f;
	int res = edge264mvc_receive_frame(dec, &f);
	if (res != EDGE264MVC_OK)
		return res;
	frames++;
	for (int v = 0; v < 2 && f.views[v].planes[0] != NULL; v++) {
		int64_t order = f.views[v].display_order;
		if (order >= 0 && order < MAX_ORDER && seen[v][order]++) {
			printf("FAIL view %d of display order %lld was delivered twice\n", v, (long long)order);
			failures++;
		}
	}
	held[n_held] = f;
	held_hash[n_held++] = hash_frame(&f);
	while (n_held > max_held)
		release_oldest();
	return res;
}

int main(int argc, char *argv[]) {
	if (argc != 3 || (max_held = atoi(argv[2])) < 0 || max_held >= MAX_HELD) {
		fprintf(stderr, "Usage: %s <stream.264> <held>\n", argv[0]);
		return 2;
	}
	FILE *file = fopen(argv[1], "rb");
	if (file == NULL) {
		perror(argv[1]);
		return 2;
	}
	fseek(file, 0, SEEK_END);
	long size = ftell(file);
	rewind(file);
	uint8_t *buf = malloc(size > 0 ? size : 1);
	if (buf == NULL || size <= 0 || fread(buf, 1, size, file) != (size_t)size) {
		fprintf(stderr, "cannot read %s\n", argv[1]);
		return 2;
	}
	fclose(file);
	const char *nt = getenv("EDGE264MVC_THREADS");
	Edge264MvcSettings s;
	edge264mvc_default_settings(&s);
	s.n_threads = nt ? atoi(nt) : 1;
	if (edge264mvc_open(&dec, &s) != EDGE264MVC_OK) {
		fprintf(stderr, "edge264mvc_open failed\n");
		return 2;
	}
	size_t pos = edge264mvc_find_start_code(buf, size);
	while (pos < (size_t)size) {
		size_t start = pos + 3;
		size_t next = start + edge264mvc_find_start_code(buf + start, size - start);
		int rounds = 0;
		while (edge264mvc_send_nal(dec, buf + start, next - start, 0, 0) == EDGE264MVC_AGAIN) {
			// receive one frame, or make room by releasing a held one
			if (receive_one() != EDGE264MVC_OK && n_held > 0)
				release_oldest();
			if (++rounds == 1000) {
				printf("FAIL send_nal returned AGAIN for good\n");
				return 1;
			}
		}
		pos = next;
	}
	edge264mvc_send_end(dec);
	int res;
	while ((res = receive_one()) == EDGE264MVC_OK)
		continue;
	if (res != EDGE264MVC_END) {
		printf("FAIL the end of the stream returned %d, not END\n", res);
		failures++;
	}
	while (n_held > 0)
		release_oldest();
	edge264mvc_close(&dec);
	free(buf);
	if (failures) {
		printf("partial receive: %d checks FAILED (%s, holding %d)\n", failures, argv[1], max_held);
		return 1;
	}
	printf("partial receive PASS (%s, holding %d, %d frames)\n", argv[1], max_held, frames);
	return 0;
}
