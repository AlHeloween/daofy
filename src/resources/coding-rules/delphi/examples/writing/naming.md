# Naming Convention Examples

## Basic Prefixes

| Category | Convention | ✅ Correct | ❌ Wrong |
|----------|------------|------------|----------|
| Class/Interface/Exception | T/I/E/P prefix | `TMyClass`, `IMyInterface` | `MyClass`, `MyInterface` |
| Field | F prefix | `FName: string;` | `Name: string;` |
| Property/Method | UpperCamelCase | `property Name` / `procedure CalculateTotal` | `property name` / `procedure calculateTotal` |
| Event | On→Form suffix | `Form1Create` | `CreateForm1` |
| Parameter | A prefix | `procedure SetName(AName: string);` | `procedure SetName(Name: string);` |
| Enum | Type prefix abbreviation | `taLeft, taRight, taCenter` | `Left, Right, Center` |
| Constant | All uppercase | `MAX_BUFFER_SIZE` | `MaxBufferSize` / `max_buffer_size` |

## Complete Example

```pascal
type
  // Class: T prefix
  TCustomer = class
  private
    FName: string;      // Field: F prefix
    FAge: Integer;
  public
    constructor Create(AName: string; AAge: Integer);  // Parameter: A prefix
    function GetDisplayName: string;                   // Method: UpperCamelCase
    property Name: string read FName write FName;      // Property: UpperCamelCase
    property Age: Integer read FAge write FAge;
  end;

  // Interface: I prefix
  IRepository = interface
    function FindById(AId: Integer): TCustomer;
  end;

  // Exception: E prefix
  ECustomerNotFound = class(Exception);

  // Enum: type prefix abbreviation
  TAlignment = (taLeft, taCenter, taRight);

const
  MAX_RETRY_COUNT = 3;   // Constant: all uppercase
```

## Naming Checklist

- [ ] Do new classes have the T/I/E/P prefix?
- [ ] Do private fields have the F prefix?
- [ ] Do method parameters have the A prefix?
- [ ] Are properties/methods in UpperCamelCase?
- [ ] Are constants all uppercase (underscore-separated)?
- [ ] Do event handlers use the Form/Control suffix?

