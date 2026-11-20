<!-- @when: After code compilation is complete and ready for review, check item by item according to this table -->
<!-- @chain: before=testing/ui.md, after=compile.md -->

## Review

### Consistency
| Checklist item | Description |
|--------|------|
| `__history` backup integrity | Confirm that the backup exists and the version number is ≥ 1 |
| Naming conventions | Types/fields/methods/parameters conform to the rules, old and new are consistent |
| Exception patterns | Exception handling in the same module is consistent; `try...finally` is used for resource release, `try...except` is used for exception handling |
| Formatting | Indentation/spaces/begin-end consistent with the project |
| OleVariant vs Variant | Use `OleVariant` for COM, `Variant` for ordinary logic |
| Platform compatibility | `SizeOf`/`Length`/`NativeInt`/endianness |
| Event release (multithreading) | Check for race conditions when setting to nil |

### Completeness
| Checklist item | Description |
|--------|------|
| All branches | if/else, case/else, try/except fully covered |
| Boundary conditions | Empty array/nil/empty string/MaxInt |
| Input validation | Validate external parameters/files/streams |
| Resource release | finally ensures release on exception paths as well |
| Concurrency safety | Lock protection, deadlock risk, thread exit cleanup |
| Function return values | Explicit return; implicit uninitialized Result is forbidden |
| const/out/var parameters | Correctly annotated; `const` must not be modified |
| Assert usage | Precondition/postcondition checks; note that it is removed in Release |
| initialization/finalization | Leaks/order dependencies |
| Log output | Distinguish levels; include timestamps and context |

### Resource Leaks
| Checklist item | Description |
|--------|------|
| Create/Free pairing | Every Create has a corresponding Free/FreeAndNil |
| try/finally | Immediately try after acquiring resources, and release in finally |
| Files/handles | TFileStream/THandle/TMemoryStream are closed after use |
| Database connections | TSQLConnection/TADOConnection are released after use |
| GDI/system resources | TFont/TBitmap/HPEN/HBRUSH |
| Interface references | Ensure release before leaving scope; avoid circular references |
| Large strings/arrays | Clear when no longer used (`SetLength(s, 0)`) |
| TObjectList | `OwnsObjects` is set correctly |

### Delphi-specific Pitfalls
| Checklist item | Description |
|--------|------|
| Interface reference counting | Automatic `_AddRef`/`_Release`; avoid manual intervention |
| Circular references | Interfaces referencing each other cause leaks; use `[weak]` to break them |
| TComponent ownership | Owner receives Free notifications; do not Free repeatedly |
| String types | string=UnicodeString is managed automatically; pay attention to encoding for AnsiString |
| String concatenation | Use `TStringBuilder` inside loops |
| Variant | Prefer concrete types; pay attention to reference counting for COM |
| published section | Properties/events loaded by streaming remain public/published |
| RTTI | Release `TRttiContext` after use |
| Platform compatibility | Win32/Win64 pointer/handle size differences |
| Record value semantics | Modifying fields inside a method only affects the copy |
| Enums/subranges | case covers all (add `else raise`) |
| Set types | Upper limit 256 elements; use `[]` for empty Set |
| Class Helper conflicts | Naming uniqueness |
| Delegate lifecycle | Anonymous methods capturing variables must prevent dangling pointers |

### Common Error Patterns
| Checklist item | Description |
|--------|------|
| Empty except | At least log inside `except`; empty blocks that swallow exceptions are forbidden |
| Type conversion safety | Confirm with `is` before `as`; avoid hard casting `Type(x)` |
| Event release | Set `OnClick := nil` before releasing the object |
| Anonymous method capture | Use local variable copies to capture values inside loops |
| Thread access to VCL | Must use `TThread.Queue`/`Synchronize` |
| `with` statement | Avoid use |
| Dynamic arrays | Clarify the difference between `array of T`/`TArray<T>`/open array |
| record managed fields | Assignment of `string`/`TArray`/`IInterface` is not by reference |

### Code Quality
| Checklist item | Description |
|--------|------|
| Method size | ≤80 lines, single responsibility |
| Cyclomatic complexity | Nesting ≤3 levels; simplify with guard clauses/extracted methods |
| Magic numbers | Extract as named constants |
| Comment conventions | Key logic/algorithms/TODOs need comments; clean up misleading comments |
| Code duplication | DRY principle; extract common methods |
| Test naming | `Test_[method]_[condition]_[expected]` |

### Data Conversion
| Checklist item | Description |
|--------|------|
| Conversion isolation | Use a dedicated layer for JSON/XML/binary conversion |
| Field mapping | Prefer declarative mapping; avoid manually writing field-by-field |
| Input validation | Perform structure and range validation during deserialization |
| Encoding consistency | Explicitly specify character encoding |

### Security
| Checklist item | Description |
|--------|------|
| SQL injection | Parameterized queries; string concatenation is forbidden |
| Hardcoded credentials | Passwords/keys/API Keys use configuration or environment variables |
| i18n | User-visible strings use `resourcestring` |
| Buffer overflow | Move/CopyMemory checks boundaries |
| Input sanitization | External data undergoes format and range validation |

### Performance
| Checklist item | Description |
|--------|------|
| Allocation inside loops | Forbid creating objects/allocating large memory inside loops |
| String operations | Use `TStringBuilder` for long concatenation |
| Unnecessary type conversions | Avoid repeated `as`/`Type()` inside loops |
| RTTI overhead | Cache `TRttiContext` on high-frequency paths |

### Review Result Confirmation
| Category | Handling |
|------|---------|
| 🔴 Affects logic/architecture | Mark "Needs user confirmation"; wait for confirmation before changing |
| 🟡 Design ambiguity | List options for the user to choose |
| 🟢 Obvious coding errors | Fix first, then report, noting that it has been fixed |

