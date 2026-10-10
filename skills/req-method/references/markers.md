# `@REQ_REF` — referencing requirements from code and tests

`req` scans the source tree for markers and links them to requirements. That link is
what makes `coverage` and `trace` statements about the code rather than about intentions.

```
@REQ_REF(<ID>) <a few words on what the requirement asks for>
```

## The rules

**One ID per marker, and a description after it.** A marker naming three requirements
reads as one obligation and hides that the three may have diverged; and source read on its
own should say roughly what it owes, without the requirement file open beside it. Three
requirements means three lines.

**On the code that implements the requirement — never on an interface.** A requirement is
discharged by the implementation, not by a declaration of intent, and an interface with
two implementations would otherwise claim the requirement twice while satisfying it once.
File stems listed in `interface_suffixes` are rejected.

**Once, on the declaration.** Where a language splits declaration and implementation (C,
C++, Objective-C), the marker goes on the header and never also in the `.c` — a promise
restated in two places is one that can disagree. `declaration_extensions` in
`.reqkit.toml` enforces this; languages with one file per type (Swift, Kotlin, Python)
mark the type's declaration.

**In a test, on the test function — never on the fixture.** A fixture covers whatever its
tests happen to cover, which no one can check. Each test states what it verifies, so if
four tests cover one requirement, all four carry the marker.

**At the level that reaches code.** Mark the sub-system or interface requirement the code
implements. A level with `traced = false` is never marked; `check` rejects it.

**A path containing `test` or `spec`** (configurable as `test_paths`) is a test
reference; anything else is code.

## Examples

C, on the implementing header:

```c
/**
 * @file pwm_py32.h
 * @brief The PY32F003 implementation of pwm_interface.
 *
 * @REQ_REF(TSSR_FWN_023) no code above the abstraction may name a vendor register
 */
```

Swift, on the type that implements it:

```swift
/// Keeps one connection per Master and addresses each independently.
///
/// @REQ_REF(TSSR_APP_001) several Masters from one client, none aware of another
final class MasterConnections { … }
```

A test, with Given/When/Then — every test function gets this block, marker or not:

```cpp
/**
 * @test Each colour reaches the PWM channel the board assigned to it.
 *
 * Given an indicator wired to channels 4, 5 and 6 for red, green and blue.
 * When  a distinct value is set on each element.
 * Then  each value is written to that element's own channel, and to no other.
 *
 * @REQ_REF(TSSR_FWM_006) a discrete RGB indicator under independent PWM per colour
 */
TEST_F(IndicatorTest, WritesEachElementToItsOwnChannel)
```

```swift
/// @test A Master keeps its name across a reconnect over a different transport.
///
/// Given a Master named "Station" over WiFi.
/// When  it reconnects over USB.
/// Then  the app shows it as "Station", as one Master.
///
/// @REQ_REF(TSSR_APP_002) names key to device identity, not to an address
func testNameSurvivesTransportChange() { … }
```

## What `check` enforces

A marker naming several IDs, a marker with no description, a marker on an interface, a
non-test marker outside `declaration_extensions`, a marker to an undefined requirement,
and a marker on a level that is never traced directly. Whether the *right* code carries
the marker is a judgement — make it honestly, and never add a marker to close a gap the
code does not close.
