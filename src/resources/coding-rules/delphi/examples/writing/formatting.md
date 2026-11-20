# Formatting Examples

## Core Rules

- Indent with 2 spaces, line width ≤120
- `begin` on its own line; add spaces after operators/commas, but not inside parentheses
- `uses` grouping + end-of-group comments + alphabetical order within each group

## Correct Example

```pascal
unit CustomerUnit;

interface

uses
  System.SysUtils,        // System units
  System.Classes,
  Vcl.Dialogs,            // VCL units
  Vcl.Forms;

type
  TCustomer = class
  private
    FName: string;
  public
    constructor Create(AName: string);
  end;

implementation

constructor TCustomer.Create(AName: string);
begin
  FName := AName;
end;

end.
```

## Common Mistakes and Fixes

```pascal
// ❌ begin is not on its own line; spaces inside parentheses; no spaces around operators
procedure DoSomething( AValue :Integer);
begin
  if( AValue>0 )then
    ShowMessage(IntToStr( AValue ));
end;

// ✅ After correction
procedure DoSomething(AValue: Integer);
begin
  if AValue > 0 then
    ShowMessage(IntToStr(AValue));
end;
```

## Formatting Tool

```python
# Format with delphi_file (automatically backs up to __history)
delphi_file(action="format", file_path="Unit1.pas")

# Check only, do not modify
delphi_file(action="format", file_path="Unit1.pas", dry_run=True)
```

## Notes

- After formatting, the file is marked **dirty**; before writing again, you must first read or provide old_content
- Use `delphi_file(action="uses", ...)` to add/remove `uses` entries; do not manually calculate line numbers
- Preserve the original encoding when writing (`delphi_file` automatically detects BOM/GBK)

