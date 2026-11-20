"""
create_component_dfm — Compile and run Delphi code to serialize a component into DFM text

Workflow:
  1. AI provides Pascal code that creates the component (complete function body + uses units)
  2. The code is injected into a template .dpr → compiled → run
  3. Serialize via WriteComponent + ObjectBinaryToText
  4. Return DFM text (including the component name)

Template conventions:
  - AI's code must define function CreateComponent(AOwner: TComponent): TComponent;
  - The function may create TForm/TFrame and other containers as Parent context
  - WriteComponent is called on the returned component; container cleanup need not be handled
  - Events serialize their names by assigning methods of the container Form

Typical AI code example (VCL TButton):
  ```pascal
  type
    TGenForm = class(TForm)
    public
      constructor Create(AOwner: TComponent); override;
    published
      procedure BtnClick(Sender: TObject);
    end;

  constructor TGenForm.Create(AOwner: TComponent);
  begin
    inherited CreateNew(AOwner);  // Do not load DFM resources
  end;

  procedure TGenForm.BtnClick(Sender: TObject);
  begin
  end;

  function CreateComponent(AOwner: TComponent): TComponent;
  var
    F: TGenForm;
    B: TButton;
  begin
    F := TGenForm.Create(nil);
    B := TButton.Create(nil);
    B.Name := 'Button1';
    B.Parent := F;
    B.Caption := 'Click Me';
    B.OnClick := F.BtnClick;
    Result := F;  // ← Return the Form (the tool automatically unwraps and extracts the child component DFM)
  end;
  ```

  Corresponding uses: ["Vcl.Forms", "Vcl.StdCtrls"]
  Corresponding init_code: "RegisterClass(TGenForm);"
"""

import os
import sys
import tempfile
import subprocess
import shutil
import re
import ctypes
from ctypes import wintypes
from typing import Optional, Dict, Any, List, Tuple, Set

from ..constants import (
    TIMEOUT_COMPONENT_CREATION_EXEC,
    TIMEOUT_DELPHI_COMPONENT_COMPILE,
    TIMEOUT_SUBPROCESS_SHORT,
)
from ..utils.logger import get_logger

logger = get_logger(__name__)

# ============================================================
# Sandbox — dangerous operation block list
# ============================================================
# Layer 1: Static analysis — forbidden units (provide low-level OS access)
_DENY_UNITS: Set[str] = {
    # Direct Win32 API access
    'Windows', 'Winapi.Windows',
    # Shell operations
    'ShellAPI', 'Winapi.ShellAPI', 'Winapi.Shell', 'ShlObj', 'Winapi.ShlObj',
    # Registry
    'Registry', 'System.Win.Registry',
    # File I/O (low-level)
    'SysUtils',  # Contains DeleteFile/RemoveDir — but is also a base VCL unit; use with caution
    # Process/thread operations
    'TlHelp32', 'Winapi.TlHelp32',
    # Network
    'WinSock', 'Winapi.WinSock', 'WinHTTP', 'Winapi.WinHTTP',
    'WinINet', 'Winapi.WinINet',
    # Security
    'AclAPI', 'Winapi.AclAPI',
}

# Layer 1: Static analysis — forbidden function/keyword patterns
_DENY_PATTERNS: List[str] = [
    # File system destruction
    r'\bDeleteFile\b',
    r'\bRemoveDir\b',
    r'\bRenameFile\b',
    # Process/code execution
    r'\bCreateProcess\b',
    r'\bWinExec\b',
    r'\bShellExecute\b',
    r'\bShellExecuteEx\b',
    r'\bExecuteProcess\b',
    r'\bRunDLL\b',
    # Memory operations
    r'\bWriteProcessMemory\b',
    r'\bReadProcessMemory\b',
    r'\bVirtualProtect\b',
    r'\bVirtualAllocEx\b',
    # Process control
    r'\bTerminateProcess\b',
    r'\bCreateRemoteThread\b',
    r'\bOpenProcess\b',
    # DLL injection
    r'\bLoadLibrary\b',
    r'\bGetProcAddress\b',
    r'\bSetWindowsHookEx\b',
    # External imports (bypassing uses checks)
    r'\bexternal\b',
    r'\bdelayload\b',
]

# Layer 2: Job Object constants (Windows SDK)
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
_JOB_OBJECT_LIMIT_JOB_TIME = 0x0004
_JOB_OBJECT_LIMIT_PROCESS_TIME = 0x0002
_JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x0008
_JOB_OBJECT_LIMIT_JOB_MEMORY = 0x0200
_PROCESS_CREATE_SUSPENDED = 0x00000004


def _validate_code_uses(uses: List[str]) -> Optional[str]:
    """Layer 1a: Check whether uses contains forbidden units."""
    for unit_name in uses:
        stripped = unit_name.strip()
        if stripped in _DENY_UNITS:
            return f"Forbidden dangerous unit '{stripped}': it may be abused to perform destructive operations"
    return None


def _validate_code_patterns(code: str, uses: List[str]) -> Optional[str]:
    """Layer 1b: Check whether the code contains dangerous function calls.

    SysUtils is an exception — base VCL units must be available,
    but if code contains both SysUtils + dangerous function calls, special handling is needed.
    """
    has_sysutils = any(u.strip() == 'SysUtils' for u in uses)

    for pattern in _DENY_PATTERNS:
        m = re.search(pattern, code, re.IGNORECASE)
        if m:
            func_name = m.group(0)
            # DeleteFile/RemoveDir in SysUtils are normal RTL functions
            # But if code explicitly calls them, it is still dangerous
            return f"Dangerous function call detected in code '{func_name}': execution is blocked"
    return None


def _validate_code_sandbox(code: str, uses: Optional[List[str]]) -> Optional[str]:
    """Sandbox entry point: statically analyze the code and block dangerous operations.

    Returns:
        None = passes the check
        str = rejection reason
    """
    safe_uses = uses or []
    err = _validate_code_uses(safe_uses)
    if err:
        return err
    err = _validate_code_patterns(code, safe_uses)
    if err:
        return err
    return None


# ============================================================
# Windows Job Object sandbox (Layer 2)
# ============================================================

class _JobObjectSandbox:
    """Windows Job Object process sandbox.

    Calls kernel32 API directly through ctypes, with no pywin32 dependency.
    Limits:
      - Process/child process total CPU time ≤ 15 seconds
      - Automatically terminates all child processes when the Job handle is closed
      - Maximum active process count 5 (prevents fork bombs)
    """

    def __init__(self):
        self._handle = None
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    def create(self) -> bool:
        """Create a Job Object."""
        # CreateJobObjectW(NULL, NULL)
        self._kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
        self._kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        self._handle = self._kernel32.CreateJobObjectW(None, None)
        if not self._handle:
            logger.warning("CreateJobObject failed; skipping Job Object sandbox")
            return False
        return self._set_limits()

    def _set_limits(self) -> bool:
        """Set Job Object limits."""
        # Construct JOBOBJECT_EXTENDED_LIMIT_INFORMATION
        # Use bytearray for manual layout (avoid defining the full struct)
        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
                ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_ulonglong),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        # 15 seconds of CPU time, in 100ns units
        TIME_15S = 15 * 10_000_000

        basic = JOBOBJECT_BASIC_LIMIT_INFORMATION()
        basic.PerProcessUserTimeLimit = TIME_15S
        basic.PerJobUserTimeLimit = TIME_15S
        basic.LimitFlags = (
            _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE |
            _JOB_OBJECT_LIMIT_JOB_TIME |
            _JOB_OBJECT_LIMIT_PROCESS_TIME |
            _JOB_OBJECT_LIMIT_ACTIVE_PROCESS
        )
        basic.ActiveProcessLimit = 5

        # JOBOBJECT_EXTENDED_LIMIT_INFORMATION contains basic + 3 more fields
        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", wintypes.DWORD * 3),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        ext = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        ext.BasicLimitInformation = basic
        ext.JobMemoryLimit = 256 * 1024 * 1024  # 256 MB total memory limit

        self._kernel32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE, wintypes.DWORD,
            wintypes.LPVOID, wintypes.DWORD,
        ]
        self._kernel32.SetInformationJobObject.restype = wintypes.BOOL

        JobObjectExtendedLimitInformation = 9
        ok = self._kernel32.SetInformationJobObject(
            self._handle, JobObjectExtendedLimitInformation,
            ctypes.byref(ext), ctypes.sizeof(ext),
        )
        if not ok:
            logger.warning("SetInformationJobObject failed; using kill-on-close only")
        return True

    def assign(self, pid: int) -> bool:
        """Add the process to the Job Object."""
        if not self._handle:
            return False
        self._kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self._kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        ph = self._kernel32.OpenProcess(0x1000 | 0x0010, False, pid)  # PROCESS_SET_QUOTA | PROCESS_TERMINATE
        if not ph:
            logger.warning("OpenProcess(%d) failed; cannot add to Job Object", pid)
            return False
        ok = self._kernel32.AssignProcessToJobObject(self._handle, ph)
        self._kernel32.CloseHandle(ph)
        if not ok:
            logger.warning("AssignProcessToJobObject(%d) failed", pid)
        return ok

    def close(self):
        """Close the Job Object handle (automatically terminates all processes in it)."""
        if self._handle:
            self._kernel32.CloseHandle(self._handle)
            self._handle = None

# ============================================================
# Template — minimal dpr, no VCL/FMX coupling
# All framework code (Form declarations, event stubs, etc.) is provided by AI in the code parameter
# ============================================================

_TEMPLATE = r"""program dfmgen;

{$APPTYPE CONSOLE}

uses
  System.SysUtils,
  System.Classes{USER_UNITS};

{USER_TYPE_DECL}

{USER_CODE}

var
  comp: TComponent;
  ms: TMemoryStream;
  fs: TFileStream;
  outFile: string;
begin
  if ParamCount < 1 then
  begin
    WriteLn('ERROR:No output file specified');
    Halt(1);
  end;
  outFile := ParamStr(1);
  try
    {USER_INIT}
    comp := CreateComponent(nil);
    try
      ms := TMemoryStream.Create;
      try
        ms.WriteComponent(comp);
        ms.Position := 0;
        fs := TFileStream.Create(outFile, fmCreate);
        try
          ObjectBinaryToText(ms, fs);
        finally
          fs.Free;
        end;
      finally
        ms.Free;
      end;
    finally
      comp.Free;
    end;
  except
    on E: Exception do
    begin
      WriteLn('ERROR:' + E.Message);
      Halt(1);
    end;
  end;
end.
"""

# Compiler path cache (shares dfm_utils lookup logic)
_compiler_dcc32_path: Optional[str] = None


# ============================================================
# Compiler lookup (kept consistent with dfm_utils)
# ============================================================

def set_compiler_path(path: str):
    """Set the dcc32.exe path"""
    global _compiler_dcc32_path
    _compiler_dcc32_path = path


def _find_dcc32() -> Optional[str]:
    """Find an available dcc32.exe (same logic as dfm_utils._find_dcc32)"""
    if _compiler_dcc32_path and os.path.isfile(_compiler_dcc32_path):
        return _compiler_dcc32_path

    which_cmd = "where" if sys.platform == "win32" else "which"
    try:
        result = subprocess.run(
            [which_cmd, "dcc32.exe" if sys.platform == "win32" else "dcc32"],
            capture_output=True, text=True, timeout=TIMEOUT_SUBPROCESS_SHORT,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        if result.returncode == 0:
            path = result.stdout.strip().split('\n')[0].strip()
            if path and os.path.isfile(path):
                return path
    except Exception:
        logger.debug("Failed to find dcc32 via where/which", exc_info=True)
    return None


def _find_library_path(dcc32: str) -> Optional[str]:
    """
    Derive the RTL library path from the dcc32 path.

    Args:
        dcc32: Full path to dcc32.exe

    Returns:
        Library path, or None if not found
    """
    dcc_dir = os.path.dirname(os.path.abspath(dcc32))
    root = os.path.dirname(dcc_dir)
    candidates = [
        os.path.join(root, "lib", "win32", "release"),
        os.path.join(root, "lib", "Win32", "Release"),
        os.path.join(root, "lib"),
    ]
    for p in candidates:
        if os.path.isdir(p):
            return p
    return None


# ============================================================
# Template code generation
# ============================================================

def _generate_dpr(
    uses: List[str],
    code: str,
    type_decl: str = "",
    init_code: str = "",
) -> str:
    """
    Generate the dfmgen project .dpr source.

    Args:
        uses: Additional uses unit list specified by AI (excluding base units such as System.SysUtils)
        code: Implementation code section (must contain the CreateComponent function definition)
        type_decl: Type declaration section (Form classes, event stubs, etc.)
        init_code: Initialization code section (executed before CreateComponent),
                   used for global initialization such as RegisterClass

    Returns:
        Complete .dpr content
    """
    # Format the uses clause
    # Template format: "System.Classes{USER_UNITS};"
    # {USER_UNITS} must start with ",\n  <unit>" (when non-empty)
    cleaned = [u.strip() for u in uses if u.strip()]
    if cleaned:
        items = ",\n  ".join(cleaned)
        uses_block = ",\n  " + items
    else:
        uses_block = ""

    dpr = _TEMPLATE.replace("{USER_UNITS}", uses_block)
    dpr = dpr.replace("{USER_TYPE_DECL}", type_decl.strip())
    dpr = dpr.replace("{USER_INIT}", init_code.strip())
    dpr = dpr.replace("{USER_CODE}", code.strip())

    return dpr


def _extract_component_name(dfm_text: str) -> Optional[str]:
    """
    Extract the component name from DFM text.

    Args:
        dfm_text: Text-format DFM content

    Returns:
        Component Name value, or None if not found
    """
    m = re.search(r'^\s*(?:object|inherited)\s+(\w+)\s*:\s*\w+', dfm_text, re.MULTILINE)
    if m:
        return m.group(1)
    return None


def _unwrap_form_dfm(dfm_text: str) -> Optional[str]:
    """
    If the DFM root node is a Form (visual container), extract the first child component DFM inside it.
    If the root node is not a Form, return None (indicating the original text should be used directly).

    Form detection: the root node class name contains "Form" and has nested object/inherited.

    Args:
        dfm_text: Text-format DFM content

    Returns:
        Child component DFM text, or None (no unwrapping needed)
    """
    text = dfm_text.strip()
    if not text:
        return None

    # Extract root object declaration and class name
    m = re.search(r'^(object|inherited)\s+(\w+)\s*:\s*(\w+)', text, re.MULTILINE)
    if not m:
        return None

    root_class = m.group(3)  # e.g. TForm1, TForm, TGenForm
    has_form = 'Form' in root_class

    if not has_form:
        return None  # Not a Form container; do not unwrap

    # Find the first nested object/inherited (child component)
    # Start searching after the root object declaration
    start_pos = m.end()
    remaining = text[start_pos:]

    child_m = re.search(r'^[ \t]+(object|inherited)\s+(\w+)\s*:\s*(\w+)', remaining, re.MULTILINE)
    if not child_m:
        return None  # Form but no child components

    # Find the child component indentation level (supports spaces or tabs)
    raw_indent = child_m.group().rstrip()
    indent_text = raw_indent[:len(raw_indent) - len(raw_indent.lstrip())]
    child_start = start_pos + child_m.start()

    # Extract child component text: start at the child declaration and end at the matching end
    # The child's end is at the same indentation level (spaces/tabs both work)
    escaped_indent = re.escape(indent_text)
    end_pattern = re.compile(r'^' + escaped_indent + r'end\b', re.MULTILINE)
    end_m = end_pattern.search(text, child_start)
    if not end_m:
        return None

    child_dfm = text[child_start:end_m.end()]
    return child_dfm


def _read_dfm_output(out_file: str) -> Dict[str, Any]:
    """
    Read and process the DFM output file.
    If the DFM is wrapped in a Form, automatically unwrap and extract the child component.

    Args:
        out_file: DFM file path

    Returns:
        {"success": True, "dfm_text": "...", "component_name": "..."}
        or {"success": False, "error": "...", "stage": "output"}
    """
    if not os.path.isfile(out_file):
        return {"success": False, "error": "Execution succeeded but no output file was generated", "stage": "output"}

    with open(out_file, "r", encoding="utf-8", errors="replace") as f:
        raw_text = f.read().strip()

    if not raw_text:
        return {"success": False, "error": "Output DFM file is empty", "stage": "output"}

    # Try to unwrap the Form container
    unwrapped = _unwrap_form_dfm(raw_text)
    if unwrapped:
        dfm_text = unwrapped
    else:
        dfm_text = raw_text

    component_name = _extract_component_name(dfm_text)
    return {
        "success": True,
        "dfm_text": dfm_text,
        "component_name": component_name or "",
    }


# ============================================================
# Compile & execute
# ============================================================

def _compile_project(
    tmp_dir: str,
    timeout: int = TIMEOUT_DELPHI_COMPONENT_COMPILE,
) -> Tuple[bool, str]:
    """
    Compile the dfmgen project.

    Args:
        tmp_dir: Temporary directory (contains dfmgen.dpr)

    Returns:
        (success: bool, message: str)
    """
    dpr_path = os.path.join(tmp_dir, "dfmgen.dpr")
    exe_path = os.path.join(tmp_dir, "dfmgen.exe")

    dcc32 = _find_dcc32()
    if not dcc32:
        return False, "dcc32.exe not found; check the Delphi compiler installation"

    try:
        lib_path = _find_library_path(dcc32)

        # Try compiling without the -U parameter
        cmd = [dcc32, dpr_path, f"-E{tmp_dir}", "-Q", "-B"]
        logger.info(f"Compiling DFM generator: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )

        # If it fails and a library path exists, retry with -U
        if result.returncode != 0 and lib_path:
            cmd2 = [dcc32, dpr_path, f"-E{tmp_dir}", "-Q", "-B", f"-U{lib_path}"]
            logger.info(f"Retrying compile (with -U): {' '.join(cmd2)}")
            result = subprocess.run(
                cmd2,
                capture_output=True,
                text=True,
                timeout=timeout,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            )

        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            stdout = (result.stdout or "").strip()
            detail = stderr or stdout or f"Exit code {result.returncode}"
            return False, f"Compilation failed:\n{detail}"

        if not os.path.isfile(exe_path):
            return False, f"Executable not found after compilation: {exe_path}"

        return True, exe_path

    except subprocess.TimeoutExpired:
        return False, f"Compilation timed out ({timeout}s)"
    except Exception as e:
        logger.error(f"Compilation exception: {e}", exc_info=True)
        return False, f"Compilation exception: {e}"


def _execute_gen(
    exe_path: str,
    out_file: str,
    timeout: int = TIMEOUT_COMPONENT_CREATION_EXEC,
) -> Tuple[bool, str]:
    """
    Execute the compiled dfmgen.exe (sandbox environment).

    Args:
        exe_path: dfmgen.exe path
        out_file: Output DFM file path
        timeout: Execution timeout in seconds

    Returns:
        (success: bool, message: str)
        On success, message is empty; on failure, message is the error information
    """
    # [Sandbox] Layer 2: Windows Job Object — automatically kill process on timeout + kill-on-close
    job = _JobObjectSandbox()
    job_created = job.create()

    try:
        # Start the process, then immediately add it to the Job Object
        proc = subprocess.Popen(
            [exe_path, out_file],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )

        # Add to the Job Object (continue even if this fails; degrade but do not block)
        if job_created:
            job.assign(proc.pid)

        # Wait for completion
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            raise

        # Check runtime errors (the template writes an ERROR: prefix to stdout)
        out_text = (stdout or "").strip()
        if out_text.startswith("ERROR:"):
            return False, out_text[len("ERROR:"):].strip()

        if proc.returncode != 0:
            err_text = (stderr or "").strip()
            return False, err_text or f"Process exit code {proc.returncode}"

        # Validate that the output file exists
        if not os.path.isfile(out_file):
            return False, "No output file was generated"

        return True, ""

    except subprocess.TimeoutExpired:
        return False, f"Execution timed out ({timeout}s) — the component creation code may be stuck in an infinite loop"
    except Exception as e:
        logger.error(f"Execution exception: {e}", exc_info=True)
        return False, f"Execution exception: {e}"
    finally:
        job.close()


# ============================================================
# Main entry
# ============================================================

async def generate_component_dfm(
    code: str,
    uses: Optional[List[str]] = None,
    type_decl: str = "",
    init_code: str = "",
    compile_timeout: int = TIMEOUT_DELPHI_COMPONENT_COMPILE,
    exec_timeout: int = TIMEOUT_COMPONENT_CREATION_EXEC,
) -> Dict[str, Any]:
    """
    Compile and run Delphi code, then generate DFM text through WriteComponent serialization.

    Args:
        code: Pascal implementation code written by AI.
              Must contain the definition of function CreateComponent(AOwner: TComponent): TComponent.
              May contain helper types/procedures/functions.
        uses: Unit list that AI specifies for reference, e.g. ["Vcl.Forms", "Vcl.StdCtrls"]
        type_decl: Type declaration section (optional), used to declare Form classes, event stubs, etc.
        init_code: Initialization code section (optional), executed before CreateComponent.
                   Used for global registration such as "RegisterClass(TGenForm);"
        compile_timeout: Compilation timeout in seconds (default 60)
        exec_timeout: Execution timeout in seconds (default 15)

    Returns:
        When success=True:
          {
            "success": True,
            "dfm_text": "...DFM text...",
            "component_name": "Button1"
          }
        When success=False:
          {
            "success": False,
            "error": "...error description...",
            "stage": "compile|execute|output"
          }

    Usage (AI Agent):
      # 1. Check the KB to confirm the component class name, unit, and VCL/FMX ownership
      # 2. Write the CreateComponent function (including container Form + event stubs)
      #    A custom Form class needs RegisterClass: init_code="RegisterClass(TGenForm);"
      # 3. Call this tool → obtain DFM text
      # 4. Use dfm_merge to merge into the target / write event stubs to .pas
    """
    code = (code or "").strip()
    if not code:
        return {"success": False, "error": "The code parameter cannot be empty", "stage": "input"}

    uses = uses or []
    type_decl = (type_decl or "").strip()
    init_code = (init_code or "").strip()

    # Verify that code contains the CreateComponent function
    if "CreateComponent" not in code:
        return {
            "success": False,
            "error": "code must define a CreateComponent(AOwner: TComponent): TComponent function",
            "stage": "input",
        }

    # [Sandbox] Static analysis: block dangerous units and function calls
    sandbox_err = _validate_code_sandbox(code, uses)
    if sandbox_err:
        logger.warning("Sandbox blocked: %s", sandbox_err)
        return {"success": False, "error": f"Code rejected by sandbox: {sandbox_err}", "stage": "sandbox"}

    # Create temporary working directory
    tmp_dir = tempfile.mkdtemp(prefix="dfmgen_")
    out_file = os.path.join(tmp_dir, "output.dfm")

    try:
        # 1. Generate .dpr
        dpr_content = _generate_dpr(
            uses=uses,
            code=code,
            type_decl=type_decl,
            init_code=init_code,
        )
        dpr_path = os.path.join(tmp_dir, "dfmgen.dpr")
        with open(dpr_path, "w", encoding="utf-8") as f:
            f.write(dpr_content)

        # 2. Compile
        ok, msg = _compile_project(tmp_dir, timeout=compile_timeout)
        if not ok:
            return {"success": False, "error": msg, "stage": "compile"}

        exe_path = msg  # _compile_project returns exe_path in msg on success

        # 3. Execute
        ok, err_msg = _execute_gen(exe_path, out_file, timeout=exec_timeout)
        if not ok:
            return {"success": False, "error": err_msg, "stage": "execute"}

        # 4. Read output DFM (automatically unwraps Form containers)
        result = _read_dfm_output(out_file)
        if not result["success"]:
            return result

        # 5. Write a parsed DFM and return it
        return result

    finally:
        # Clean up temporary files
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            logger.debug("Failed to clean temporary directory: %s", tmp_dir, exc_info=True)

