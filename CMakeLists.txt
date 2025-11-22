cmake_minimum_required(VERSION 3.20)
find_package(OpenSSL REQUIRED)
find_package(ZLIB REQUIRED)
project(ap_bridge LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# --------------------------------------------------
# Désactiver les tests (on n'en a pas besoin ici)
# --------------------------------------------------
set(BUILD_TESTING OFF CACHE BOOL "Disable all tests" FORCE)
set(APCLIENTPP_BUILD_TESTS OFF CACHE BOOL "Disable apclientpp tests" FORCE)

# --------------------------------------------------
# apclientpp : va télécharger asio + websocketpp + json via FetchContent
# --------------------------------------------------
add_subdirectory(third_party/apclientpp third_party/apclientpp_build)

# --------------------------------------------------
# Executable : ap_fetcher
# --------------------------------------------------
add_executable(ap_fetcher
    fetcher/src/main.cpp
)

target_include_directories(ap_fetcher PRIVATE
    # apclientpp
    ${CMAKE_CURRENT_SOURCE_DIR}/third_party/apclientpp

    # wswrap
    ${CMAKE_CURRENT_SOURCE_DIR}/third_party/wswrap/include

    # nlohmann_json (clone local)
    ${CMAKE_CURRENT_SOURCE_DIR}/third_party/nlohmann_json/single_include

    # Asio standalone (FetchContent)
    ${CMAKE_BINARY_DIR}/_deps/asio-src/asio/include

    # WebSocket++ (FetchContent)
    ${CMAKE_BINARY_DIR}/_deps/websocketpp-src

    # ✅ Valijson cloné dans third_party
    ${CMAKE_CURRENT_SOURCE_DIR}/third_party/valijson/include
)




# Asio en mode standalone (sans Boost)
target_compile_definitions(ap_fetcher PRIVATE
    ASIO_STANDALONE
)

# Link avec la lib apclientpp
target_link_libraries(ap_fetcher PRIVATE
    apclientpp
    OpenSSL::SSL
    OpenSSL::Crypto
    ZLIB::ZLIB
)
