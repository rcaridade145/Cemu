// Committed memory-safety regression for edge264-mvc, built with
// AddressSanitizer (`make check-asan`).
//
// Decodes each bundled crafted bitstream under tests/asan/ with a LOG CALLBACK
// SET, because the SEI parser (parse_sei) only runs in the logging path - the
// default decode routes SEI NALs to ignore_NAL. Under ASAN, a regression that
// reintroduces an out-of-bounds access aborts with a clear report (non-zero
// exit); a regression that reintroduces the unbounded payloadSize skip loop is
// caught by the `timeout` wrapper in the Makefile target (the loop spins
// billions of iterations). With the fixes in place every fixture decodes
// cleanly and quickly, so the harness exits 0.
//
// Fixtures (tests/asan/manifest.txt lists the names):
//   sei_payloadtype_oob  - SEI with payloadType > 205; guards the unguarded
//                          payloadType_names[] / parse_sei_message[] index (M2).
//   sei_payloadsize_dos  - SEI with a huge payloadSize for an unsupported type;
//                          guards the unbounded skip loop (M5).
//
// Self-contained: only edge264mvc.h + libc. Usage: asan_check run <manifest> <dir>

#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "edge264mvc.h"

#define RED "\e[0;31m"
#define GREEN "\e[0;32m"
#define RESET "\e[0m"

// A non-NULL log callback is required so the decoder selects the log-enabled
// parsers (parse_sei_log); it deliberately does nothing with the strings.
static void logcb(const char *s, void *a) { (void)s; (void)a; }

static uint8_t *load_file(const char *path, size_t *size_out) {
	// read into memory rather than mmap, so that the harness builds on Windows too
	FILE *f = fopen(path, "rb");
	if (f == NULL)
		return NULL;
	uint8_t *m = NULL;
	long size = 0;
	if (fseek(f, 0, SEEK_END) == 0 && (size = ftell(f)) > 0 && fseek(f, 0, SEEK_SET) == 0 &&
		(m = malloc(size)) != NULL && fread(m, 1, size, f) != (size_t)size) {
		free(m);
		m = NULL;
	}
	fclose(f);
	if (m != NULL)
		*size_out = size;
	return m;
}

// Returns the number of NALs reported as corrupt, so a "clean" fixture (a
// valid stream) can be asserted to decode without any invalid-stream error.
static int decode_all(const uint8_t *buf, size_t size) {
	Edge264MvcSettings settings;
	edge264mvc_default_settings(&settings);
	// EDGE264MVC_THREADS as in the other harnesses (default 0 = single-thread,
	// <0 = auto), for the fixtures that only stall under multithreading
	const char *nt = getenv("EDGE264MVC_THREADS");
	int threads = nt ? atoi(nt) : 0;
	settings.n_threads = threads < 0 ? 0 : threads == 0 ? 1 : threads;
	settings.log_cb = logcb;
	Edge264MvcDecoder *dec;
	if (edge264mvc_open(&dec, &settings) != EDGE264MVC_OK)
		return -1;
	Edge264MvcFrame f;
	int badmsg = 0;
	// Decode like a player: a damaged NAL is skipped rather than ending the
	// stream, and the end of the stream receives the held frames. Every
	// EDGE264MVC_AGAIN round must make progress, so a run of rounds without
	// any frame is a stall the caller cannot resolve.
	size_t pos = edge264mvc_find_start_code(buf, size);
	while (pos < size) {
		size_t start = pos + 3;
		size_t next = start + edge264mvc_find_start_code(buf + start, size - start);
		int res;
		for (int stalled = 0; (res = edge264mvc_send_nal(dec, buf + start, next - start, 0, 0)) == EDGE264MVC_AGAIN; ) {
			int received = 0;
			while (edge264mvc_receive_frame(dec, &f) == EDGE264MVC_OK) {
				edge264mvc_release_frame(dec, &f);
				received++;
			}
			if (received == 0 && ++stalled > 64) {
				edge264mvc_close(&dec);
				return -1;
			}
		}
		badmsg += res == EDGE264MVC_CORRUPT;
		while (edge264mvc_receive_frame(dec, &f) == EDGE264MVC_OK)
			edge264mvc_release_frame(dec, &f);
		pos = next;
	}
	edge264mvc_send_end(dec);
	while (edge264mvc_receive_frame(dec, &f) == EDGE264MVC_OK)
		edge264mvc_release_frame(dec, &f);
	edge264mvc_close(&dec);
	return badmsg;
}

static int do_run(const char *manifest, const char *dir) {
	FILE *mf = fopen(manifest, "r");
	if (!mf) {
		fprintf(stderr, "cannot open manifest %s\n", manifest);
		return 1;
	}
	char line[1024];
	int total = 0;
	while (fgets(line, sizeof(line), mf)) {
		if (line[0] == '#' || line[0] == '\n')
			continue;
		char name[512], flag[64] = "";
		int nf = sscanf(line, "%511s %63s", name, flag);
		if (nf < 1)
			continue;
		int must_be_clean = nf == 2 && strcmp(flag, "clean") == 0;
		total++;
		char path[4096];
		snprintf(path, sizeof(path), "%s/%s.264", dir, name);
		size_t size = 0;
		uint8_t *buf = load_file(path, &size);
		if (!buf) {
			printf(RED "FAIL" RESET " %s (missing fixture)\n", name);
			fclose(mf);
			return 1;
		}
		// If a memory-safety regression is present, ASAN aborts here.
		int badmsg = decode_all(buf, size);
		free(buf);
		if (badmsg < 0) {
			printf(RED "FAIL" RESET " %s (stall: EDGE264MVC_AGAIN without progress)\n", name);
			fclose(mf);
			return 1;
		}
		// A "clean" fixture is a valid stream: any corrupt NAL is a regression (e.g.
		// a small trailing SEI mis-skipped and misreturned as an invalid stream).
		if (must_be_clean && badmsg != 0) {
			printf(RED "FAIL" RESET " %s (valid stream reported corrupt NALs x%d)\n", name, badmsg);
			fclose(mf);
			return 1;
		}
	}
	fclose(mf);
	printf("%d / %d asan fixtures " GREEN "PASS" RESET " (no sanitizer error)\n", total, total);
	return 0;
}

int main(int argc, char *argv[]) {
	if (argc == 4 && strcmp(argv[1], "run") == 0)
		return do_run(argv[2], argv[3]);
	fprintf(stderr, "Usage: %s run <manifest> <fixtures-dir>\n", argv[0]);
	return 2;
}
