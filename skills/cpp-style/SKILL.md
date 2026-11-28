---
name: cpp-style
description: >
  The ROS 2 C++ style rules that differ from the Google style guide and that agents get wrong:
  100 columns, .hpp/.cpp, open braces for definitions and cuddled braces for control flow,
  "char * c" pointer spacing, 2-space indent, path-based include guards, no "using namespace",
  and the C++ standard per distribution. Use whenever writing or editing C++ in a ROS 2 package
  (rclcpp, rcl, rmw, demos, or any ament_cmake package), before running ament_uncrustify and
  ament_cpplint, or when the user asks about ROS 2 C++ conventions.
---

# ROS 2 C++ style

`ament_uncrustify` and `ament_cpplint` decide what is correct.
This skill lists the rules an agent trained on Google-style C++ gets wrong, so the first lint run is clean.
The full guide is the [code style page](https://docs.ros.org/en/rolling/The-ROS2-Project/Contributing/Code-Style-Language-Versions.html).

## Standard

C++17 for every active distribution from Humble on; `rolling` is also C++17 unless the package's `CMakeLists.txt` says otherwise.
Check the package, not your memory: `grep -n CMAKE_CXX_STANDARD CMakeLists.txt`.
No Boost in core packages.
Exceptions are allowed; `-fno-exceptions` is not a ROS 2 convention.

## Layout

- 100 columns, 2-space indent, spaces only, one trailing newline.
- Files: `.hpp` and `.cpp`, never `.h` or `.cc`.
  Headers under `include/<package>/`, sources under `src/`.
- Include guard from the path, screaming snake case with double underscores: `include/rclcpp/node.hpp` gets `RCLCPP__NODE_HPP_`.
  `ament_cpplint` checks this exact form.
- Every file starts with the Apache-2.0 license header; `ament_copyright --add-missing "<holder>" apache2` writes it.

## Braces

Open braces for function, class, struct, enum, and namespace definitions.
Cuddled braces for `if`, `else`, `while`, `for`, `switch`, and lambdas.
If a condition wraps onto a second line, use an open brace instead so the body stands out.
Always use braces, even for a single statement.

```cpp
void
Node::do_thing(int value)
{
  if (value > 0) {
    helper(value);
  } else {
    other(value);
  }
  if (
    some_long_condition(value) &&
    another_long_condition(value))
  {
    helper(value);
  }
}
```

Core packages put the return type of a function definition on its own line, as above.
Follow the surrounding file.

## Pointers, references, naming

- `char * c;` and `char & c;`, with spaces on both sides.
- Types in CamelCase, functions and variables in snake_case, constants and macros in ALL_CAPS.
- Member variables end with an underscore: `node_base_`.
  Global variables start with `g_`.
- Namespaces are not indented; close them with `}  // namespace rclcpp`.
- No `using namespace`.
  `using` declarations for single names are fine inside a function or class.

## Wrapping

Wrap long calls at the opening parenthesis and indent the arguments two spaces, each on its own line; do not align to the parenthesis.

```cpp
auto sub = create_subscription<std_msgs::msg::String>(
  "topic", rclcpp::QoS(10),
  [this](std_msgs::msg::String::ConstSharedPtr msg) {handle(msg);});
```

Boolean operators go at the end of the line, as in the condition above.

## Comments and documentation

`//` for comments; `///` or `/** */` Doxygen on public API with `\brief`, `\param`, `\return`, and `\throws`.
Mark unused parameters `(void)param;` or omit the name.

## Check before committing

```bash
ament_uncrustify --reformat <files>   # or without --reformat to see the diff
ament_cpplint <files>
```

Record the run with `ros2-gate run --` when the result will be reported.
