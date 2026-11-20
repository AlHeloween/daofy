# Manage Component — DFM Component Management

> Version: v1.0 | Last Updated: 2026-06-08

---

## Table of Contents

1. [Overview](#1-overview)
2. [Action Quick Reference](#2-action-quick-reference)
3. [Create — Generate Component DFM](#3-create--generate-component-dfm)
4. [Add — Add Component](#4-add--add-component)
5. [Remove — Delete Component](#5-remove--delete-component)
6. [Modify — Modify Component Properties](#6-modify--modify-component-properties)
7. [PAS Auto-Sync Mechanism](#7-pas-auto-sync-mechanism)
8. [Technical Architecture](#8-technical-architecture)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. Overview

`manage_component` is an all-in-one tool for Delphi DFM component management. It supports component creation, addition, deletion, and property modification, and **automatically synchronizes field declarations and event method code in PAS files**.

It merges in the original `generate_component_dfm` functionality and adds the `add`/`remove`/`modify` operations on top of it.

| Feature | Description |
|------|------|
| Create component DFM | Compile and run Pascal code, serialize as DFM text |
| Add child component | Add a component to an existing DFM, auto-sync PAS |
| Delete component | Delete a component tree from the DFM, auto-clean PAS |
| Modify properties | Modify component properties, sync PAS when events change |

---

## 2. Action Quick Reference

| Action | Purpose | Required Parameters |
|--------|------|---------|
| `create` | Generate component DFM (compile + run serialization) | `code` |
| `add` | Add a child component to an existing DFM | `target_dfm`, `new_component_class` |
| `remove` | Delete a component from the DFM | `target_dfm`, `component_name` |
| `modify` | Modify component properties | `target_dfm`, `component_name`, `properties` |

---

## 3. Create — Generate Component DFM

Compile and run a Pascal code snippet, serializing the visual component it creates into DFM text. Suitable for scenarios that require precise control over component layout.

```python
# Generate a panel with an OK button
manage_component(action="create",
    code="""
function CreateComponent(AOwner: TComponent): TComponent;
var
  Panel: TPanel;
  Btn: TButton;
begin
  Panel := TPanel.Create(AOwner);
  Panel.Caption := '';
  Panel.Width := 300;
  Panel.Height := 200;

  Btn := TButton.Create(Panel);
  Btn.Parent := Panel;
  Btn.Caption := 'OK';
  Btn.Left := 100;
  Btn.Top := 80;
  Btn.Width := 100;
  Btn.Height := 30;

  Result := Panel;
end;
""",
    uses=["Vcl.ExtCtrls", "Vcl.StdCtrls"],
    compile_timeout=60,
    exec_timeout=15)
```

**Parameter Description**:

| Parameter | Required | Default | Description |
|------|------|--------|------|
| `code` | ✅ | — | Pascal code; must contain `function CreateComponent(AOwner: TComponent): TComponent;` |
| `uses` | ❌ | — | List of units to reference |
| `type_decl` | ❌ | — | Type declaration section (e.g. Form class declaration, event stubs, etc.) |
| `init_code` | ❌ | — | Initialization code executed before CreateComponent. Custom Form classes require `RegisterClass` |
| `compile_timeout` | ❌ | 60 | Compile timeout in seconds |
| `exec_timeout` | ❌ | 15 | Execution timeout in seconds |

---

## 4. Add — Add Component

Add a child component to an existing DFM file, automatically synchronizing it to the corresponding PAS file.

```python
# Add button to root component
manage_component(action="add",
    target_dfm="Unit1.dfm",
    target_pas="Unit1.pas",
    new_component_class="TButton",
    new_component_name="BtnOK",
    properties={
        "Caption": "确定",
        "Left": "100",
        "Top": "80",
        "Width": "100",
        "Height": "30",
        "OnClick": "BtnOKClick"   # Auto-generate event stub
    })

# Add to specified parent component
manage_component(action="add",
    target_dfm="Unit1.dfm",
    parent_name="Panel1",
    new_component_class="TEdit",
    new_component_name="EditName",
    properties={"Text": "", "Left": "10", "Top": "10"})

# Use DFM text fragment
manage_component(action="add",
    target_dfm="Unit1.dfm",
    dfm_text="object BtnOK: TButton\n  Caption = 'OK'\n  Left = 100\n  Top = 80\nend")
```

**Parameter Description**:

| Parameter | Required | Description |
|------|------|------|
| `target_dfm` | ✅ | Target DFM file path |
| `target_pas` | ❌ | PAS file path, used for automatic declaration synchronization |
| `parent_name` | ❌ | Parent component name; if not passed, add to the root component |
| `new_component_class` | ❌ | Component class name (e.g. TButton) |
| `new_component_name` | ❌ | Instance name; auto-generated if not passed |
| `properties` | ❌ | Property dictionary |
| `dfm_text` | ❌ | DFM text fragment (replaces class+properties) |

---

## 5. Remove — Delete Component

Delete a component and its subtree from the DFM, automatically cleaning up field declarations and event methods in the PAS file.

```python
# Delete component
manage_component(action="remove",
    target_dfm="Unit1.dfm",
    target_pas="Unit1.pas",
    component_name="BtnCancel")
```

**Automatic Synchronization on Deletion**:
| PAS Content | Handling |
|-------------|---------|
| Field declaration (`BtnCancel: TButton;`) | Delete |
| Event method declaration (`procedure BtnCancelClick(Sender: TObject);`) | Delete |
| Event method implementation | Delete |
| Uses units with empty references | Clean up |

---

## 6. Modify — Modify Component Properties

Modify the properties of an existing component in the DFM. When event properties change (e.g. modifying the `OnClick` event binding), automatically synchronize event method declarations in the PAS file.

```python
# Modify Caption and font
manage_component(action="modify",
    target_dfm="Unit1.dfm",
    target_pas="Unit1.pas",
    component_name="BtnOK",
    properties={
        "Caption": "确认",
        "Font.Size": "12",
        "OnClick": "BtnOKClick"  # Auto-generate/update event stub
    })
```

**PAS Synchronization Rules**:

| Event Change | PAS Handling |
|---------|---------|
| New event binding | Auto-generate method declaration + implementation stub |
| Modify event binding | Keep original method, generate new method |
| Remove event binding | Keep method code (manual confirmation required on whether to delete) |

---

## 7. PAS Auto-Sync Mechanism

This is the core capability of `manage_component`—bidirectional synchronization between DFM and PAS.

### Synchronization Rules

| Operation | DFM | PAS |
|------|-----|-----|
| **add** | Insert component definition | + Field declaration + Event method stub + Required uses units |
| **remove** | Delete component (including subtree) | - Field declaration - Event method (declaration + implementation) - Uses with empty references |
| **modify** event change | Modify event property | +/— Event method declaration |

`add` first generates the complete DFM and PAS updates in memory. Field declarations, event method stubs, and missing
`uses` units are completed in a single PAS write; if the DFM write fails, PAS remains unchanged; if the PAS write
fails, the tool restores the original DFM and returns failure, avoiding the two files being out of sync.

### Synchronization Workflow

```
manage_component(action="add", target_dfm="Unit1.dfm", ...)
    │
    ├─ ① Read DFM → parse component tree
    ├─ ② Insert new component definition
    ├─ ③ Update DFM file (auto backup to __history)
    │
    ├─ ④ Read PAS → parse field/method sections
    ├─ ⑤ Add field declaration (FComponentName: TComponentClass;)
    ├─ ⑥ Add event method declaration (procedure ComponentNameEvent(Sender: TObject);)
    ├─ ⑦ Add event method implementation stub
    ├─ ⑧ Add missing uses units
    └─ ⑨ Update PAS file (auto backup to __history)
```

---

## 8. Technical Architecture

```
AI Agent
    │
    ▼
manage_component(action="create"|"add"|"remove"|"modify")
    │
    ▼
┌───────────────────────────────────────────────┐
│         src/tools/manage_component.py           │
│  · Component operations + PAS sync core logic    │
│  · DFM parsing/generation                       │
│  · Event signature matching (via KB service)     │
└──────┬──────────┬──────────┬───────────────────┘
       │          │          │
       ▼          ▼          ▼
┌──────────┐ ┌──────────┐ ┌──────────┐
│  DFM     │ │  PAS     │ │  Compiler │
│  Parsing │ │  Sync    │ │  (create) │
├──────────┤ ├──────────┤ ├──────────┤
│· Component tree │ │· Fields  │ │· dcc32  │
│· Property parsing │ │· Methods │ │· Run    │
│· Serialization │ │· Events  │ │· Serialization │
└──────────┘ └──────────┘ └──────────┘
       │
       ▼
┌──────────────────────┐
│  KB Service (event signatures) │
│  · Query Delphi API   │
│  · Match event signatures │
│  · Generate correct method declarations │
└──────────────────────┘
```

---

## 9. Troubleshooting

| Symptom | Cause | Solution |
|------|------|------|
| `create` compilation failed | `code` has syntax errors | Check the Pascal code and ensure the `CreateComponent` function signature is correct |
| `create` execution timeout | Component creation code has an infinite loop | Increase `exec_timeout` or check the code |
| PAS not synchronized after `add` | `target_pas` not passed | Add the `target_pas` parameter |
| DFM parsing failed | DFM file format error | Use `delphi_file(action="read")` to view the DFM state |
| Event signature mismatch | Event name misspelled | Check the case of event names such as `OnClick`/`OnChange` |
| Methods left behind after deletion | Method is referenced by another component | Manually check the residual event methods |