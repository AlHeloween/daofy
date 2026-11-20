# Error Handling Examples

## Core Principles

- `try...finally` is for **resource release** (files/handles/locks/memory)
- `try...except` is for **exception handling** (conversion/logging/rethrowing)
- Inside `except`, at least log; **empty blocks that swallow exceptions are forbidden**
- Catch specific exception types; avoid bare `except`

## Resource Release: try...finally

```pascal
// ✅ Immediately enter try after acquiring the resource; release in finally
var
  LFile: TFileStream;
begin
  LFile := TFileStream.Create(AFileName, fmOpenRead);
  try
    // Read logic (exceptions also reach finally)
    ProcessStream(LFile);
  finally
    LFile.Free;   // Release on both normal and exception paths
  end;
end;
```

## Exception Handling: try...except

```pascal
// ✅ Catch specific exception types + log
try
  SaveToDatabase(ACustomer);
except
  on E: EDatabaseError do
  begin
    Logger.Error('保存客户失败: ' + E.Message);
    raise;  // Rethrow when upper layer needs to handle it
  end;
  on E: Exception do
    Logger.Error('未知错误: ' + E.Message);
end;
```

## Anti-patterns

```pascal
// ❌ Empty except swallows exceptions — problems are silently hidden and very hard to troubleshoot
try
  DoSomething;
except
end;

// ✅ At least log (use specific exception types where possible; see the try...except example above)
try
  DoSomething;
except
  on E: EIOException do
    Logger.Error('DoSomething 失败: ' + E.Message);
end;

// ❌ Bare except catches everything, masking programming errors (too broad)
try
  DoSomething;
except
  on E: Exception do
    Logger.Error('出错: ' + E.Message);
end;
```

## Defensive Checks

```pascal
// ✅ Validate preconditions and fail fast
if AFileName = '' then
  raise EArgumentException.Create('AFileName 不能为空');

// ✅ Full coverage of enum/subrange case (default branch raises)
case AAlign of
  taLeft:   DoLeft;
  taRight:  DoRight;
  taCenter: DoCenter;
else
  raise EArgumentException.CreateFmt('未知对齐方式: %d', [Ord(AAlign)]);
end;
```

## Checklist

- [ ] Is `try` entered immediately after acquiring the resource, and is it released in `finally`?
- [ ] Is `except` an empty block (forbidden)?
- [ ] Are specific exception types caught rather than bare `except`?
- [ ] Do error messages include enough context (variable values/call parameters)?
- [ ] Does it need `raise` to rethrow to the upper layer?

