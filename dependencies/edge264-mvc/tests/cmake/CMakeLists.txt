# A minimal consumer of edge264-mvc through CMake, as the README documents it
# (add_subdirectory here, FetchContent in a real project): CI configures,
# builds and runs it, so the imported target edge264mvc::edge264mvc keeps working.
cmake_minimum_required(VERSION 3.14)
project(edge264mvc_consumer C)
add_subdirectory(${CMAKE_CURRENT_SOURCE_DIR}/../.. edge264mvc)
add_executable(consumer main.c)
target_link_libraries(consumer PRIVATE edge264mvc::edge264mvc)
