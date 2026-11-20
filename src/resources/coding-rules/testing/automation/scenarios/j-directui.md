<!-- @when: Handle VCL Style / IFileDialog / TTaskDialog / non-VCL owner-drawn pop-ups -->
<!-- @part-of: ui-testing -->

#### J. DirectUI Pop-ups / Modern System Dialogs

| Element | Content |
|------|------|
| **Goal** | Handle DirectUI pop-ups rendered by VCL Style, Windows IFileDialog, TTaskDialog, and other dialogs that cannot be covered by standard Win32 messages |
| **Strategy** | Three levels: ① prefer VCL pipeline commands (RTTI penetration) → ② fall back to `uia.xxx` → ③ screenshot OCR as last resort |
| **Key commands** | `uia.click`, `uia.goto`, `uia.set`, `uia.scan`, `uia.wait`, `capture`+`daofy_ocr` |

**Background**: DirectUI controls (VCL Style rendering, OwnerDraw custom drawing, DevExpress Skin) are still VCL objects underneath; DaofyAutomation's `goto`/`rget`/`click` can operate normally through in-pipeline RTTI without special handling. **The following cases truly require `uia.xxx`**:

| Situation | Cause | Recommended method |
|------|------|---------|
| IFileDialog (Windows 10+ modern Open/Save) | COM dialog, not VCL Form | `uia.click`/`uia.goto` |
| TTaskDialog / TCustomTaskDialog | Uses `TaskDialogIndirect` API, not standard MessageBox | `uia.scan` + `uia.click` |
| Third-party DirectUI frameworks (e.g., Chromium Embedded) | Draws all controls inside a single HWND | `capture` + OCR |
| VCL Styles-themed TForm | Appearance changed but VCL controls still present | Pipeline commands work normally (no uia needed) |

##### J0. `uia.xxx` usage rules (mandatory)

When the test involves the following dialogs, **you must** provide a `uia.xxx` fallback branch:

| Trigger scenario | Reason must use uia.xxx | Otherwise consequence |
|---------|----------------------|---------|
| No OpenDialog detected after `dlgfile` operation | Windows 10+ IFileDialog is a COM dialog, not a VCL window | `msgscan` returns NOD, test hangs |
| Clicking a button should pop up a standard "Save As" dialog | Modern Windows Explorer dialog | `dlgscan` cannot find it, step hangs |
| Confirmation box uses `TTaskDialog` (not MessageBox) | Uses `TaskDialogIndirect` API, no standard message pump | `msgscan` always NOD |
| Delete/batch operation shows a custom-styled confirmation pop-up | Unsure whether VCL or modern dialog | First try `msgscan` → after timeout fall back to `uia.scan` |

`uia.xxx` fallback integration pattern:

```json
[
  {"cmd":"click","target":"BtnImport","note":"Trigger OpenDialog"},

  {"cmd":"msgscan","timeout":2000,"note":"First quickly try msgscan (VCL MessageBox)"},
  {"cmd":"wait","ms":300,"note":"Give the dialog time to render"},

  {"cmd":"uia.goto","target":"Open","timeout":5000,
   "note":"msgscan has no result, fall back to uia.goto to find IFileDialog title"},

  {"cmd":"uia.set","target":"File name(N):","text":"C:\\data\\import.xlsx"},
  {"cmd":"uia.click","target":"Open(&O)"},

  {"cmd":"goto","target":"TMainForm","timeout":10000},
  {"cmd":"capture","target":"import_fallback_done"},
  {"cmd":"exit"}
]
```

**Rule**: Any test step involving file dialogs must `msgscan` (quickly try VCL dialog) + `wait 300ms` (give system rendering time) + `uia.goto` fallback (5s timeout). The three-step safeguard ensures it will not hang due to incorrect dialog type judgment.

##### J1. Modern OpenDialog (IFileDialog) — `uia.xxx`

```json
[
  {"cmd":"click","target":"BtnImport"},

  {"cmd":"uia.goto","target":"Open","note":"UIA penetrates to find IFileDialog","timeout":5000},
  {"cmd":"uia.set","target":"File name(N):","text":"C:\\data\\import.xlsx"},
  {"cmd":"uia.click","target":"Open(&O)"},

  {"cmd":"waitfor","target":"TMainForm","prop":"Visible","value":"True","timeout":10000},
  {"cmd":"rget","target":"StatusBar.Caption","assert_expr":"'Import' in actual or 'Success' in actual"},
  {"cmd":"capture","target":"import_uia_done"},
  {"cmd":"exit"}
]
```

##### J2. TTaskDialog confirmation pop-up — `uia.xxx`

```json
[
  {"cmd":"click","target":"BtnDeleteBatch"},

  {"cmd":"uia.scan","target":"TTaskDialog","timeout":5000,
   "expected":"TTaskDialog detected"},
  {"cmd":"uia.click","target":"Yes(&Y)","note":"TaskDialog buttons have no HWND, must use UIA"},

  {"cmd":"waitfor","target":"StatusBar","prop":"Caption","value":"Batch delete completed","timeout":5000},
  {"cmd":"capture","target":"taskdialog_done"},
  {"cmd":"exit"}
]
```

##### J3. VCL Style themed pop-up — pipeline commands still work (example only)

Even if VCL Style completely changes MessageBox appearance, standard `msgscan` + `dlgclick` still works (underneath it is still a `TForm`):

```json
[
  {"cmd":"click","target":"BtnDelete"},

  {"cmd":"msgscan","expected":"VCL Style-themed delete confirmation"},
  {"cmd":"dlgclick","target":"btnYes","note":"Under VCL Style, dlgclick still works because the button is a VCL control"},

  {"cmd":"capture","target":"styled_after_delete"},
  {"cmd":"exit"}
]
```

##### J4. Non-VCL owner-drawn pop-up — screenshot OCR fallback

When `uia.xxx` also cannot identify controls (e.g., WebView2 pop-ups, DirectX Overlay), fall back to image recognition:

```json
[
  {"cmd":"click","target":"BtnShowCustom"},

  {"cmd":"waitfor","target":"Custom popup class name","prop":"Visible","value":"True","timeout":5000,"note":"Wait for pop-up to appear"},
  {"cmd":"goto","target":"TDirectUIPopup","note":"Under VCL it can still use goto; skip this step under non-VCL"},
  {"cmd":"capture","target":"directui_popup"},

  {"cmd":"exit"}
]
```

Afterwards analyze the screenshot on the Python side with `daofy_ocr`:
```python
# Recognize pop-up text
ocr = daofy_ocr(action="recognize", image_path="snapshots/directui_popup.png")
# Or use color analysis to detect selected state
color = daofy_ocr(action="color", image_path="snapshots/directui_popup.png", region=[100,200,50,20])
```

**Decision flow** (the large model makes decisions according to this, without guessing):

```
Encounter pop-up
├─ Is it a VCL Form (class has T prefix) → pipeline commands goto/rget/click, handle normally
├─ Is it MessageBox (ShowMessage/MessageDlg) → msgscan + dlgclick
├─ Is it IFileDialog / TTaskDialog → uia.xxx
├─ Is it a standard #32770 Dialog → prefer dlgscan/dlgclick, fall back to uia.xxx on failure
├─ Is it a WebView2 / Chromium internal pop-up → capture + OCR
└─ Completely unknown → capture → OCR text recognition → then choose approach
```

**Pitfall**: `uia.xxx` target uses **the text displayed in the UI** (e.g., "Open(&O)", "Yes(&Y)"), not VCL control names; for IFileDialog file name input use `uia.set` + `text` instead of `type`; screenshot OCR fallback is the last resort, prefer pipeline and UIA first.

