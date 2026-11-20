<!-- @when: After AI generates or modifies VCL/FMX forms, frames, or dialogs, UI layout quality needs to be checked -->
<!-- @chain: before=testing/ui.md, after=review-table.md -->

## UI Layout Specification and Audit

After AI generates Delphi GUI, layout quality must be audited as part of code quality. Compilation passing only means the code can run; it does not mean the interface is comfortable, neat, and readable.

### Goals

| Dimension | Requirement |
|------|------|
| Alignment | Controls with content in the same column have consistent Left; button groups have consistent Top/Height; text labels are aligned with the center line of fields |
| Spacing | Use an 8px baseline grid; 4~16px is recommended between text labels and fields; vertical spacing between controls of the same type remains consistent |
| Hierarchy | Form content is organized by area; prefer Panel/GroupBox/PageControl for partitioning so controls are not scattered |
| Boundaries | Controls must not exceed the parent container; under different DPI they must not be truncated, compressed, or overlapped |
| Resize | Resizable windows should preferentially use Align and container partitioning; when absolute coordinates must be used, set a sufficient minimum size for the parent container |
| TabOrder | Tab order matches the visual reading order: top to bottom, left to right |

### Static Audit

After AI generates or modifies DFM, first run the static layout audit:

```python
delphi_project(action="layout", base_dir="src")
delphi_project(action="layout", file_path="MainForm.dfm")
delphi_project(action="layout", file_path="MainForm.dfm", output_format="json")
```

`layout` reads text DFM; binary DFM will be temporarily converted to text as much as possible; it does not modify the original file. The audit is based on DFM properties and geometric relationships, and does not depend on a fixed list of control types. Current check items:

| Rule | Check content | Typical fix |
|------|----------|----------|
| LAYOUT-001 | Manually laid out controls within the same parent container overlap | Adjust position/size, or use container partitioning |
| LAYOUT-002 | Controls exceed the parent container boundary | Correct Width/Height/Left/Top, or introduce ScrollBox |
| LAYOUT-003 | Controls with content in the same column have inconsistent Left | Unify Left in the same column |
| LAYOUT-004 | Controls with content in the same column have inconsistent vertical spacing | Unify row height and row spacing |
| LAYOUT-005 | Text labels are not vertically centered with fields | Adjust text label Top or field Top |
| LAYOUT-006 | Horizontal spacing between text label and field is too large or too small | Unify the spacing from the right edge of the text label to the left edge of the field |
| LAYOUT-007 | TabOrder is inconsistent with visual order | Reset TabOrder |
| LAYOUT-008 | Resizable parent container uses absolute coordinates and the minimum size is insufficient | Prefer Align; otherwise set sufficient Constraints.MinWidth/MinHeight |

### Generation Specification

When creating a form, lay out in the following order:

1. First determine the content areas: title area, input area, list area, action area, status area.
2. Use an independent container for each area, and place controls inside the container.
3. Input forms use a two-column structure: the text label column is right-aligned, and the field column is left-aligned.
4. Do not use randomly fine-tuned coordinates; use a unified set of numbers for Left, Top, Width, and Height of controls in the same group.
5. For main content areas such as tables, Memo, TreeView, and ListView, prefer `Align=alClient` or `Anchors=[akLeft, akTop, akRight, akBottom]`.
6. Keep the bottom button area at a fixed height; arrange buttons in primary/secondary order with consistent spacing.
7. Reserve enough width for Chinese Caption; do not rely on AutoSize squeezing adjacent controls.
8. In resizable windows, arrange elements preferentially through `Align` and nested containers; if `Left/Top` absolute coordinates must be retained, the parent container's `Constraints.MinWidth/MinHeight` must cover the manually laid out content boundaries.

### Runtime Verification

After the static audit passes, perform real runtime verification:

```python
automate_delphi(action="gui", app_path="App.exe", script=[
    {"cmd": "goto", "target": "TMainForm"},
    {"cmd": "dumpstate", "props": "name,left,top,width,height,class,anchors,align"},
    {"cmd": "capture", "target": "layout-main"},
    {"cmd": "exit"}
])
```

Key runtime verification points:

- No overlap, truncation, or text ellipsis under 100% / 125% / 150% DPI.
- After the main form is resized, the content area can stretch, and buttons and status area do not drift.
- Popups, wizard pages, and TabSheet interiors must also be audited separately; do not look only at the main form.
- For non-VCL controls such as custom-drawn, WebView, and ActiveX, use `ocr(action="detect")` to check text box positions and truncation.

### Audit Conclusion

When severe issues are found in the layout audit, delivery of the interface should not continue. First fix overlaps, out-of-bounds, and obvious misalignment, then proceed with compilation and automated UI verification.

