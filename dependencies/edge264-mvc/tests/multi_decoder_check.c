// Several decoders used from several threads at the same time, which the API
// allows (edge264mvc.h, "Threading"): each thread decodes a stream three times
// with its own decoder, single-threaded or with its own worker threads, and
// every run must give the frame count of a run alone. Under ThreadSanitizer
// (the CI sanitizer job) it also proves that decoders share no writable state.
//
// Usage: multi_decoder_check <stream.264> <frames> [<stream.264> <frames>]...

#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#include "edge264mvc.h"

typedef struct {
	const char *path;
	int expected;
	int n_threads;
	int failures;
} Job;

static void *run(void *arg) {
	Job *j = arg;
	FILE *f = fopen(j->path, "rb");
	if (f == NULL) {
		j->failures++;
		return NULL;
	}
	fseek(f, 0, SEEK_END);
	long n = ftell(f);
	rewind(f);
	uint8_t *buf = malloc(n);
	if (buf == NULL || fread(buf, 1, n, f) != (size_t)n) {
		fclose(f);
		free(buf);
		j->failures++;
		return NULL;
	}
	fclose(f);
	for (int rep = 0; rep < 3; rep++) {
		Edge264MvcSettings s;
		edge264mvc_default_settings(&s);
		s.n_threads = j->n_threads;
		Edge264MvcDecoder *dec;
		if (edge264mvc_open(&dec, &s) != EDGE264MVC_OK) {
			j->failures++;
			break;
		}
		Edge264MvcFrame frame;
		int frames = 0;
		size_t pos = edge264mvc_find_start_code(buf, n);
		while (pos < (size_t)n) {
			size_t start = pos + 3;
			size_t next = start + edge264mvc_find_start_code(buf + start, n - start);
			for (int rounds = 0; edge264mvc_send_nal(dec, buf + start, next - start, 0, 0) == EDGE264MVC_AGAIN && rounds < 64; rounds++)
				for (; edge264mvc_receive_frame(dec, &frame) == EDGE264MVC_OK; frames++)
					edge264mvc_release_frame(dec, &frame);
			for (; edge264mvc_receive_frame(dec, &frame) == EDGE264MVC_OK; frames++)
				edge264mvc_release_frame(dec, &frame);
			pos = next;
		}
		edge264mvc_send_end(dec);
		for (; edge264mvc_receive_frame(dec, &frame) == EDGE264MVC_OK; frames++)
			edge264mvc_release_frame(dec, &frame);
		edge264mvc_close(&dec);
		if (frames != j->expected) {
			printf("FAIL %s (%d threads): %d frames instead of %d\n", j->path, j->n_threads, frames, j->expected);
			j->failures++;
		}
	}
	free(buf);
	return NULL;
}

int main(int argc, char *argv[]) {
	if (argc < 3 || argc % 2 == 0) {
		fprintf(stderr, "Usage: %s <stream.264> <frames> [<stream.264> <frames>]...\n", argv[0]);
		return 2;
	}
	int streams = (argc - 1) / 2;
	Job jobs[16];
	pthread_t threads[16];
	int n = 0;
	for (int i = 0; i < streams && n + 2 <= 16; i++) {
		for (int t = 0; t < 2; t++) {
			jobs[n] = (Job){argv[1 + 2 * i], atoi(argv[2 + 2 * i]), t ? 4 : 1, 0};
			pthread_create(&threads[n], NULL, run, &jobs[n]);
			n++;
		}
	}
	int failures = 0;
	for (int i = 0; i < n; i++) {
		pthread_join(threads[i], NULL);
		failures += jobs[i].failures;
	}
	printf(failures ? "multi-decoder FAILED\n" : "%d decoders in parallel PASS\n", n);
	return failures != 0;
}
