cmake_minimum_required(VERSION 2.8)

project(orchestra)

find_package(Protobuf REQUIRED)

set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -std=c++11")

include_directories("${CMAKE_SOURCE_DIR}/include")

set(PROTO_PATH "${CMAKE_SOURCE_DIR}/protos")

set(ORCHESTRA_PROTO "${PROTO_PATH}/orchestra.proto")
set(TYPES_PROTO "${PROTO_PATH}/types.proto")
set(GENERATED_PROTOBUF_PATH "${CMAKE_BINARY_DIR}/generated")
file(MAKE_DIRECTORY ${GENERATED_PROTOBUF_PATH})

set(ORCHESTRA_PB_CPP_FILE "${GENERATED_PROTOBUF_PATH}/orchestra.pb.cc")
set(ORCHESTRA_PB_H_FILE "${GENERATED_PROTOBUF_PATH}/orchestra.pb.h")
set(ORCHESTRA_GRPC_PB_CPP_FILE "${GENERATED_PROTOBUF_PATH}/orchestra.grpc.pb.cc")
set(ORCHESTRA_GRPC_PB_H_FILE "${GENERATED_PROTOBUF_PATH}/orchestra.grpc.pb.h")

set(TYPES_PB_CPP_FILE "${GENERATED_PROTOBUF_PATH}/types.pb.cc")
set(TYPES_PB_H_FILE "${GENERATED_PROTOBUF_PATH}/types.pb.h")
set(TYPES_GRPC_PB_CPP_FILE "${GENERATED_PROTOBUF_PATH}/types.grpc.pb.cc")
set(TYPES_GRPC_PB_H_FILE "${GENERATED_PROTOBUF_PATH}/types.grpc.pb.h")

add_custom_command(
    OUTPUT "${ORCHESTRA_PB_H_FILE}"
           "${ORCHESTRA_PB_CPP_FILE}"
           "${ORCHESTRA_GRPC_PB_H_FILE}"
           "${ORCHESTRA_GRPC_PB_CPP_FILE}"
    COMMAND ${PROTOBUF_PROTOC_EXECUTABLE}
    ARGS "--proto_path=${PROTO_PATH}"
         "--cpp_out=${GENERATED_PROTOBUF_PATH}"
         "${ORCHESTRA_PROTO}"
    COMMAND ${PROTOBUF_PROTOC_EXECUTABLE}
    ARGS "--proto_path=${PROTO_PATH}"
         "--grpc_out=${GENERATED_PROTOBUF_PATH}"
         "--plugin=protoc-gen-grpc=/usr/local/bin/grpc_cpp_plugin"
         "${ORCHESTRA_PROTO}"
    )

add_custom_command(
    OUTPUT "${TYPES_PB_H_FILE}"
           "${TYPES_PB_CPP_FILE}"
           "${TYPES_GRPC_PB_H_FILE}"
           "${TYPES_GRPC_PB_CPP_FILE}"
    COMMAND ${PROTOBUF_PROTOC_EXECUTABLE}
    ARGS "--proto_path=${PROTO_PATH}"
         "--cpp_out=${GENERATED_PROTOBUF_PATH}"
         "${TYPES_PROTO}"
    COMMAND ${PROTOBUF_PROTOC_EXECUTABLE}
    ARGS "--proto_path=${PROTO_PATH}"
         "--grpc_out=${GENERATED_PROTOBUF_PATH}"
         "--plugin=protoc-gen-grpc=/usr/local/bin/grpc_cpp_plugin"
         "${TYPES_PROTO}"
    )

set(GENERATED_PROTOBUF_FILES ${ORCHESTRA_PB_H_FILE} ${ORCHESTRA_PB_CPP_FILE}
    ${ORCHESTRA_GRPC_PB_H_FILE} ${ORCHESTRA_GRPC_PB_CPP_FILE}
    ${TYPES_PB_H_FILE} ${TYPES_PB_CPP_FILE}
    ${TYPES_GRPC_PB_H_FILE} ${TYPES_GRPC_PB_CPP_FILE})

include_directories(${GENERATED_PROTOBUF_PATH})
link_libraries(grpc++_unsecure grpc pthread rt ${PROTOBUF_LIBRARY})

add_executable(objstore src/objstore.cc ${GENERATED_PROTOBUF_FILES})
add_executable(scheduler_server src/scheduler_server.cc ${GENERATED_PROTOBUF_FILES})
add_library(orchlib SHARED src/orchlib.cc ${GENERATED_PROTOBUF_FILES})

install(TARGETS objstore scheduler_server orchlib DESTINATION ${CMAKE_SOURCE_DIR}/lib/orchpy/orchpy)