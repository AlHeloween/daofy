# Documentation Comment Examples

## Unit Header Comment

```pascal
{*************************************************************************}
{ Unit: CustomerUnit.pas                                                    }
{ Purpose: Customer entity and repository implementation, unified entry point for the business layer }
{ Author: TeamName                                                           }
{ Date: 2026-07-17                                                          }
{ Version: 1.0.0                                                               }
{*************************************************************************}
```

## Class and Method Comments (XML Doc Style)

```pascal
type
  /// <summary>Customer entity, encapsulates basic customer information.</summary>
  TCustomer = class
  private
    FName: string;
    FAge: Integer;
  public
    /// <summary>Creates a customer instance.</summary>
    /// <param name="AName">Customer name; must not be empty</param>
    /// <param name="AAge">Customer age, 0-150</param>
    /// <returns>Initialized customer instance</returns>
    constructor Create(AName: string; AAge: Integer);

    /// <summary>Calculates the customer display name.</summary>
    /// <returns>Display string in name (age) format</returns>
    function GetDisplayName: string;
  end;
```

## Complex Method Comments

```pascal
/// <summary>Imports customer data in batches.</summary>
/// <param name="AFileNames">List of file paths to import; at least one item</param>
/// <param name="AOverwrite">Whether to overwrite when it already exists</param>
/// <returns>Number of customers successfully imported</returns>
/// <exception cref="EFileNotFoundException">Thrown when any file does not exist</exception>
function ImportCustomers(AFileNames: TArray<string>; AOverwrite: Boolean): Integer;
```

## Comment Conventions

| Scenario | Requirement |
|----------|-------------|
| Public API (published/public methods) | Must include `<summary>`; add `<param>` for complex parameters |
| Throws exceptions | Mark with `<exception>` |
| Private helper methods | A single-line comment explaining the purpose is sufficient |
| Magic numbers/complex logic | Add inline comments explaining why, not repeating the code |
| Change history | For important logic changes, append an `@since vX.Y` note to the method comment |

## Anti-patterns

```pascal
// ❌ Comment repeats the code (no information)
i := i + 1;  // i plus 1

// ✅ Comment explains intent
i := i + 1;  // Skip already processed records to avoid consuming them twice
```

