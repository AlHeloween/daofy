<!-- @when: When you need to choose between RTTI and OCR for verification -->

# RTTI vs OCR Decision Matrix

MCP resource URI: `delphi://automation/rtti-ocr-matrix`.

RTTI = functional verification (is the data correct?) — precise, microsecond-level
OCR = visual integrity verification (is the display correct?) — hundred-millisecond-level, reflecting what the user actually sees
capture = evidence retention — screenshot, human-reviewable

The two are complementary, not substitutes. After an operation, use `rget` to confirm data state; at key points, use `capture+OCR` to verify visual presentation.

> The current version of OCR supports only text recognition, not color/font/format detection.

| Scenario | Recommendation | Reason |
|------|------|------|
| Read Edit input value / button enabled / label caption | `rget(Text/Enabled/Caption)` | Precise, microsecond-level |
| Text truncation/ellipsis/line wrapping | `textbounds` + `rget` | textbounds returns visible_state (clipped/full); rget reads the complete value for comparison |
| HDPI/scaling test | `capture` + `OCR` | RTTI does not know whether controls are misaligned/truncated after rendering |
| Placeholder watermark text | `OCR` | RTTI returns empty Text; OCR sees the hint text |
| Grid/List cells | `textbounds` | paint-hook intercepts GDI text drawing and directly obtains each cell's displayed value and coordinates; OCR is only a fallback |
| WebView / browser content | `OCR` | RTTI cannot see HTML rendering results at all |
| Tooltip hint | `OCR` | RTTI can only read the Hint literal value |
| Internationalization/localization verification | `textbounds` + `OCR` | textbounds detects whether translated text is truncated (clipped field); use OCR for CJK box detection |
| Report/print preview | `OCR` | RTTI cannot see the report engine's rendered output |
| Animation/transition state | `capture` + `OCR` | RTTI does not know visual animation progress |
| Custom drawing/third-party controls | `textbounds` | paint-hook intercepts GDI/GDI+ text drawing and generally covers custom-drawn/third-party controls |
| Error dialog content | `msgscan` | Precisely obtain dialog title + text |
| UI structure analysis | `dumpstate` / `formsum` | Precise control tree + properties |
| Overall UI snapshot | `capture` | Screenshot retention |

> ⚠️ **textbounds scope**: paint-hook intercepts only **GDI (gdi32.dll) + GDI+ (gdiplus.dll)** text drawing functions. Covers: VCL standard/custom drawing, third-party GDI libraries (DevExpress/TMS, etc.), FMX Windows. **Does not cover**: DirectUI (Win8+ system components/Ribbon/new dialog modern views), WPF, UWP/WinUI, Electron/WebView2, Qt Quick—for these scenarios, use `uia.*` commands instead (DirectUI/WPF/UWP all implement UIA Provider) or `capture`+`daofy_ocr` (WebView/Electron/Qt). For complete details, see the "Scope and Limitations" section of `script-schema.md` textbounds.

## Decision Tree

```
What is the verification target?
  ├─ Functional verification (is the data/state correct?)
  │  ├─ Property exposed via published? → rget
  │  └─ Dialog content → msgscan
  ├─ Visual integrity verification (is the text the user sees correct?)
  │  ├─ Text truncation/ellipsis/line wrapping
  │  │   ├─ GDI/GDI+ rendering stack (VCL/FMX Windows/third-party GDI libraries) → textbounds (visible_state/clipped) + rget dual verification
  │  │   └─ DirectUI/WPF/UWP/Electron/Qt/WebView → uia.* or capture + OCR (textbounds does not cover these rendering stacks)
  │  ├─ HDPI/scaling → capture + OCR
  │  ├─ Layout misalignment/overlap → capture + OCR
  │  └─ CJK display anomaly (box □) → OCR
  ├─ Complex control content (display layer RTTI cannot reach)
  │  ├─ In Delphi process + GDI/GDI+ rendering (Grid/List/custom drawing/third-party) → textbounds (paint-hook general interception)
  │  ├─ DirectUI/WPF/UWP controls → uia.* commands (not textbounds)
  │  └─ WebView/report/Tooltip/ActiveX → OCR
  ├─ Runtime text changes
  │  └─ Animation progress/Placeholder/internationalization truncation → textbounds (truncation detection, GDI/GDI+ only) + capture + OCR
  └─ Evidence retention → capture
```

## Typical HDPI Test Workflow

1. capture a baseline screenshot at 100% scaling
2. Switch to 150%/200% scaling
3. After the same operations, capture + OCR
4. Compare: Is text truncated? Is button text complete? Is the layout complete?
5. RTTI assistance: rget Left/Top/Width/Height to confirm control size scaling

