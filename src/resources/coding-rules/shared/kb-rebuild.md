<!-- @when: Knowledge base data is missing and the index must be rebuilt -->
<!-- @chain: independent -->

## Knowledge Base Rebuild

```python
# Delphi source KB (~1 minute, 163737 classes / 300228 functions)
delphi_kb(action="build", kb_type="delphi", rebuild=True, async_mode=true)
# Third-party library KB (~6 seconds, 5606 classes / 51265 functions)
delphi_kb(action="build", kb_type="thirdparty", rebuild=True, async_mode=true)
# Documentation KB (~6 minutes, includes the DCC error-code explanation documents)
delphi_kb(action="build", kb_type="document", rebuild=True, confirm=True, async_mode=true)
# Project KB
delphi_kb(action="build", kb_type="project", project_path="Project.dproj", rebuild=True)

# Progress query (action=result is recommended: returns immediately, zero waiting)
async_task(action="result", task_id="task_xxx")
# Or use short polling action=status (long_poll ≤30s)
async_task(action="status", task_id="task_xxx")
```

> **Documentation KB rebuild safety**: setting `rebuild=True` on a non-empty documentation KB requires adding `confirm=True`, to prevent accidentally wiping the web documents that were already fetched. To keep the old content, pass the old sources or switch to an incremental build.

