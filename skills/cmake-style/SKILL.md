---
name: cmake-style
description: >
  The ROS 2 CMake conventions: lowercase commands, snake_case identifiers, two-space indent,
  empty end commands, ament_cmake package structure, target-based dependencies, and the
  ament_lint_auto test block. Use whenever writing or editing CMakeLists.txt or .cmake files in a
  ROS 2 package, creating an ament_cmake package, or when the user asks how to export targets,
  link dependencies, or add tests and linters in CMake.
---

# ROS 2 CMake style

`ament_lint_cmake` decides the formatting.
These are the rules and the package shape it expects.

## Formatting

- Lowercase command names: `find_package`, not `FIND_PACKAGE`.
- snake_case for variables, functions, and targets.
- 2-space indent; no space between a command and its parenthesis.
- Empty `else()`, `endif()`, `endforeach()`, `endfunction()`.
- One argument per line once a command wraps.
- 140 columns is the linter limit; 100 is the house style.

## Package shape (ament_cmake)

```cmake
cmake_minimum_required(VERSION 3.8)
project(my_package)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(std_msgs REQUIRED)

add_library(${PROJECT_NAME} SHARED src/thing.cpp)
target_include_directories(${PROJECT_NAME} PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include/${PROJECT_NAME}>)
target_link_libraries(${PROJECT_NAME} PUBLIC rclcpp::rclcpp ${std_msgs_TARGETS})

add_executable(thing_node src/thing_node.cpp)
target_link_libraries(thing_node PRIVATE ${PROJECT_NAME})

install(TARGETS ${PROJECT_NAME}
  EXPORT export_${PROJECT_NAME}
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION bin)
install(TARGETS thing_node DESTINATION lib/${PROJECT_NAME})
install(DIRECTORY include/ DESTINATION include/${PROJECT_NAME})

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
  find_package(ament_cmake_gtest REQUIRED)
  ament_add_gtest(test_thing test/test_thing.cpp)
  target_link_libraries(test_thing ${PROJECT_NAME})
endif()

ament_export_targets(export_${PROJECT_NAME} HAS_LIBRARY_TARGET)
ament_export_dependencies(rclcpp std_msgs)
ament_package()
```

Rules behind it:

- Prefer `target_link_libraries` with exported targets (`rclcpp::rclcpp`, `${pkg_TARGETS}`) over `ament_target_dependencies`, which is deprecated on recent distributions.
  On Humble, `ament_target_dependencies` is still the common form; follow the package.
- `install(DIRECTORY include/ DESTINATION include/${PROJECT_NAME})` is the modern include layout.
- Every `find_package` has a matching `<depend>` in `package.xml`; every test tool has a `<test_depend>` (`ament_lint_auto`, `ament_lint_common`, `ament_cmake_gtest`).
- `ament_package()` is the last line.
- Message packages use `rosidl_generate_interfaces` and depend on `rosidl_default_generators` (build) and `rosidl_default_runtime` (exec), with `<member_of_group>rosidl_interface_packages</member_of_group>`.

Check before committing:

```bash
ament_lint_cmake CMakeLists.txt
ament_xmllint package.xml
```
