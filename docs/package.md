# Package — Component Package Management

> Version: v1.0 | Last updated: 2026-06-08

---

## Contents

1. [Overview](#1-overview)
2. [Action Quick Reference](#2-action-quick-reference)
3. [Install — Compile and install a package](#3-install--compile-and-install-a-package)
4. [List — List what is installed](#4-list--list-what-is-installed)
5. [Workflows](#5-workflows)
6. [Troubleshooting](#6-troubleshooting)

---

## 1. Overview

`package` manages the compilation and installation of Delphi component packages. It supports package files in `.dproj`/`.dpk`/`.groupproj` format.

**Key characteristics**:
- **Design-time packages** are registered with the IDE automatically
- **Runtime packages** are compiled only, never registered
- Multi-platform builds (win32/win64)
- Package dependencies are handled automatically

---

## 2. Action Quick Reference

| Action | Purpose |
|--------|------|
| `install` (default) | Compile and install a component package |
| `list` | List the component packages installed into the IDE |

---

## 3. Install — Compile and install a package

### Basic usage

```python
# 安装 .dpk 包
package(action="install", package_path="MyPackage.dpk")

# 安装 .dproj 包
package(action="install", package_path="MyPackage.dproj")

# 安装 .groupproj 项目组
package(action="install", package_path="MyPackage.groupproj")
```

### Build options

```python
# Release 配置，64 位
package(action="install",
    package_path="MyPackage.dpk",
    target_platform="win64",
    build_configuration="Release")

# 仅编译不注册（运行期包）
package(action="install",
    package_path="MyRuntime.dpk",
    install=False)

# 长超时（大包）
package(action="install",
    package_path="BigPackage.dproj",
    timeout=600)
```

### Parameters

| Parameter | Required | Default | Description |
|------|------|--------|------|
| `package_path` | ✅ | — | Package file path (.dproj/.dpk/.groupproj) |
| `target_platform` | ❌ | win32 | Target platform |
| `build_configuration` | ❌ | Debug | Build configuration |
| `timeout` | ❌ | 300 | Timeout in seconds |
| `install` | ❌ | true | Whether to install into the IDE automatically |

---

## 4. List — List what is installed

Lists the component packages registered in the Delphi IDE.

```python
package(action="list")
```

Returns the list of installed package names, which is how you verify that an installation succeeded.

---

## 5. Workflows

### Installing a component package

```
package(action="install", package_path="MyPackage.dpk")
  ↓
package(action="list")            → 验证安装成功
```

### Multi-platform builds

```
package(action="install", package_path="MyPackage.dpk",
    target_platform="win32")
  ↓
package(action="install", package_path="MyPackage.dpk",
    target_platform="win64")
```

---

## 6. Troubleshooting

| Symptom | Cause | Fix |
|------|------|------|
| Build fails | A dependency package is missing | Install the dependency first, then retry |
| Installation fails | Package signature / version conflict | Check the `install` parameter and try adding `timeout` |
| 64-bit build fails | The 64-bit compiler is missing | Detect it with `check_environment(action="detect")` |
| list does not show the package just installed | The IDE has not refreshed | Restart the IDE, then run list again |
