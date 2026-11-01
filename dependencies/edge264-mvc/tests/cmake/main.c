#include <stdio.h>
#include "edge264mvc.h"

int main(void) {
	Edge264MvcDecoder *dec;
	if (edge264mvc_api_version() >> 16 != EDGE264MVC_API_VERSION_MAJOR || edge264mvc_open(&dec, NULL) != EDGE264MVC_OK)
		return 1;
	edge264mvc_close(&dec);
	printf("edge264mvc %s linked through CMake\n", edge264mvc_version());
	return 0;
}
