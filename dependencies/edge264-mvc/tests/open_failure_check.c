// edge264mvc_open with worker threads, when creating one of them fails (a thread
// or process limit, or memory): it must return EDGE264MVC_NOMEM after stopping
// and joining the workers it created, before it frees the decoder they use.
// pthread_create is interposed so that its k-th call fails, for every k up to
// one past the number of workers, and after each failed open the process must
// be back to the threads it had before. Under AddressSanitizer (the CI sanitizer job) it
// also catches a worker still running on the freed decoder. Linux only, as it
// relies on ELF symbol interposition and /proc/self/task.
//
// Usage: open_failure_check

#define _GNU_SOURCE
#include <dirent.h>
#include <dlfcn.h>
#include <errno.h>
#include <pthread.h>
#include <stdio.h>
#include <unistd.h>

#include "edge264mvc.h"

static int calls, fail_at;

// a sanitizer runtime linked into the executable intercepts pthread_create
// under this name, and must see every thread it is to join
extern int __interceptor_pthread_create(pthread_t *, const pthread_attr_t *, void *(*)(void *), void *) __attribute__((weak));

int pthread_create(pthread_t *thread, const pthread_attr_t *attr, void *(*start)(void *), void *arg) {
	static int (*real)(pthread_t *, const pthread_attr_t *, void *(*)(void *), void *);
	if (real == NULL)
		real = __interceptor_pthread_create ? __interceptor_pthread_create : (int (*)(pthread_t *, const pthread_attr_t *, void *(*)(void *), void *))dlsym(RTLD_NEXT, "pthread_create");
	if (++calls == fail_at)
		return EAGAIN;
	return real(thread, attr, start, arg);
}

// a joined thread may still be listed for a moment while the kernel ends it
static int count_threads(int expected) {
	int n = -1;
	for (int tries = 0; tries < 1000 && n != expected; tries++) {
		if (tries)
			usleep(1000);
		DIR *d = opendir("/proc/self/task");
		if (d == NULL)
			return -1;
		n = 0;
		for (struct dirent *e; (e = readdir(d)) != NULL; )
			n += e->d_name[0] != '.';
		closedir(d);
	}
	return n;
}

int main(void) {
	enum { WORKERS = 8, ROUNDS = 20 };
	int failures = 0;
	int base = count_threads(-1); // a sanitizer runtime may have its own threads
	for (int round = 0; round < ROUNDS; round++) {
		for (fail_at = 1; fail_at <= WORKERS + 1; fail_at++) {
			calls = 0;
			Edge264MvcSettings s;
			edge264mvc_default_settings(&s);
			s.n_threads = WORKERS;
			Edge264MvcDecoder *dec = NULL;
			int res = edge264mvc_open(&dec, &s);
			if (fail_at <= WORKERS) {
				if (res != EDGE264MVC_NOMEM || dec != NULL) {
					printf("FAIL creating worker %d failing: open returned %d\n", fail_at, res);
					failures++;
				}
			} else if (res != EDGE264MVC_OK) {
				printf("FAIL open returned %d with every worker created\n", res);
				failures++;
			}
			edge264mvc_close(&dec);
			int threads = count_threads(base);
			if (threads != base) {
				printf("FAIL creating worker %d failing: %d threads left after open\n", fail_at, threads - base);
				failures++;
			}
		}
	}
	if (failures) {
		printf("open failure check: %d checks FAILED\n", failures);
		return 1;
	}
	printf("open failure check PASS\n");
	return 0;
}
