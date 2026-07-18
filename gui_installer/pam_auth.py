"""
Minimal PAM authentication via ctypes — stdlib only, no python-pam pip
dependency (this tool must run against the bare system python3, before
PiFinder's own venv exists). Mirrors PiFinder's own
sys_utils.verify_password("stellarmate", password), which uses PAM through
the python-pam package inside PiFinder's venv.
"""

import ctypes
import ctypes.util
from ctypes import (
    CFUNCTYPE,
    POINTER,
    Structure,
    c_char_p,
    c_int,
    c_size_t,
    c_void_p,
    cast,
    pointer,
    sizeof,
)

_PAM_PROMPT_ECHO_OFF = 1
_PAM_SUCCESS = 0


class _PamMessage(Structure):
    _fields_ = [("msg_style", c_int), ("msg", c_char_p)]


class _PamResponse(Structure):
    _fields_ = [("resp", c_char_p), ("resp_retcode", c_int)]


_CONV_FUNC = CFUNCTYPE(
    c_int,
    c_int,
    POINTER(POINTER(_PamMessage)),
    POINTER(POINTER(_PamResponse)),
    c_void_p,
)


class _PamConv(Structure):
    _fields_ = [("conv", _CONV_FUNC), ("appdata_ptr", c_void_p)]


_libpam = ctypes.CDLL(ctypes.util.find_library("pam"))
_libc = ctypes.CDLL(ctypes.util.find_library("c"))

# ctypes defaults restype to c_int (32-bit) for undeclared functions, which
# truncates the 64-bit pointers calloc()/strdup() return on aarch64/x86_64
# and segfaults PAM when it dereferences the corrupted pointer. Must be
# declared explicitly.
_libc.calloc.argtypes = [c_size_t, c_size_t]
_libc.calloc.restype = c_void_p
_libc.strdup.argtypes = [c_char_p]
_libc.strdup.restype = c_void_p

_libpam.pam_start.argtypes = [c_char_p, c_char_p, POINTER(_PamConv), POINTER(c_void_p)]
_libpam.pam_start.restype = c_int
_libpam.pam_authenticate.argtypes = [c_void_p, c_int]
_libpam.pam_authenticate.restype = c_int
_libpam.pam_acct_mgmt.argtypes = [c_void_p, c_int]
_libpam.pam_acct_mgmt.restype = c_int
_libpam.pam_end.argtypes = [c_void_p, c_int]
_libpam.pam_end.restype = c_int


def verify_password(username: str, password: str, service: str = "login") -> bool:
    """Checks the given password against the given system user via PAM."""
    password_bytes = password.encode("utf-8")

    def _conv(n_messages, messages, p_response, _app_data):
        addr = _libc.calloc(n_messages, sizeof(_PamResponse))
        resp_array = cast(addr, POINTER(_PamResponse))
        for i in range(n_messages):
            msg = messages[i].contents
            if msg.msg_style == _PAM_PROMPT_ECHO_OFF:
                resp_array[i].resp = cast(_libc.strdup(password_bytes), c_char_p)
                resp_array[i].resp_retcode = 0
        p_response[0] = resp_array
        return _PAM_SUCCESS

    conv_func = _CONV_FUNC(_conv)
    conv = _PamConv(conv_func, None)
    pamh = c_void_p()

    rc = _libpam.pam_start(service.encode(), username.encode(), pointer(conv), pointer(pamh))
    if rc != _PAM_SUCCESS:
        return False
    try:
        rc = _libpam.pam_authenticate(pamh, 0)
        if rc != _PAM_SUCCESS:
            return False
        return _libpam.pam_acct_mgmt(pamh, 0) == _PAM_SUCCESS
    finally:
        _libpam.pam_end(pamh, rc)
