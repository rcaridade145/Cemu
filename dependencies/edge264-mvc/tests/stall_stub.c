// A stand-in for the decoder library that never decodes anything, to check
// that tests/conformance_check.c and edge264mvc_test report a faulty decoder
// as a failure instead of hanging or passing (make check-harness-stall and
// check-test-results). By default every NAL is answered with EDGE264MVC_AGAIN
// and no frame is ever ready; with STALL_STUB_BLOCK set, send_nal blocks
// forever, as a deadlocked decoder would; with STALL_STUB_NOMEM set, it fails
// every NAL with EDGE264MVC_NOMEM; with STALL_STUB_ABORT set, it aborts, as a
// decoder tripping an assert would.

#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "edge264mvc.h"

struct Edge264MvcDecoder { int unused; };

void edge264mvc_default_settings(Edge264MvcSettings *settings) {
	if (settings != NULL)
		memset(settings, 0, sizeof(*settings));
}

int edge264mvc_open(Edge264MvcDecoder **decoder, const Edge264MvcSettings *settings) {
	*decoder = calloc(1, sizeof(**decoder));
	return *decoder ? EDGE264MVC_OK : EDGE264MVC_NOMEM;
}

size_t edge264mvc_find_start_code(const uint8_t *buf, size_t size) {
	for (size_t i = 0; i + 2 < size; i++) {
		if (buf[i] == 0 && buf[i + 1] == 0 && buf[i + 2] == 1)
			return i;
	}
	return size;
}

int edge264mvc_send_nal(Edge264MvcDecoder *dec, const uint8_t *buf, size_t size, int64_t pts, int64_t user_data) {
	if (getenv("STALL_STUB_ABORT") != NULL)
		abort();
	while (getenv("STALL_STUB_BLOCK") != NULL)
		pause();
	return getenv("STALL_STUB_NOMEM") != NULL ? EDGE264MVC_NOMEM : EDGE264MVC_AGAIN;
}

int edge264mvc_send_end(Edge264MvcDecoder *dec) {
	return EDGE264MVC_OK;
}

int edge264mvc_receive_frame(Edge264MvcDecoder *dec, Edge264MvcFrame *frame) {
	return EDGE264MVC_AGAIN;
}

void edge264mvc_release_frame(Edge264MvcDecoder *dec, const Edge264MvcFrame *frame) {}

void edge264mvc_flush(Edge264MvcDecoder *dec) {}

void edge264mvc_close(Edge264MvcDecoder **decoder) {
	free(*decoder);
	*decoder = NULL;
}
