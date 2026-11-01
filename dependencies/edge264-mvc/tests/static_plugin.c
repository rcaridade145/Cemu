// A plugin that links the static library in, built by CI: it must export
// only its own entry point, not the decoder API (see OBJFLAGS in Makefile).

#include "edge264mvc.h"

#ifdef _WIN32
	__declspec(dllexport)
#else
	__attribute__((visibility("default")))
#endif
unsigned plugin_entry(void) {
	return edge264mvc_api_version();
}
