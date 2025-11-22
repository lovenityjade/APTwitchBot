cmake_minimum_required(VERSION 3.16)
project(ap_fetcher)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# apclientpp
add_subdirectory(${CMAKE_SOURCE_DIR}/third_party/apclientpp ${CMAKE_BINARY_DIR}/apclientpp_build)

find_package(nlohmann_json REQUIRED)

add_executable(ap_fetcher
    src/main.cpp
)

target_include_directories(ap_fetcher PRIVATE
    ${CMAKE_SOURCE_DIR}/third_party/apclientpp/include
)

target_link_libraries(ap_fetcher PRIVATE
    apclientpp
    nlohmann_json::nlohmann_json
)
