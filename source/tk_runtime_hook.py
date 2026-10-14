"""Keep bundled Tcl paths absolute, including unusual Windows profile mappings."""

import os
import sys


def configure_tcl_paths():
    if sys.platform != "win32":
        return
    for variable in ("TCL_LIBRARY", "TK_LIBRARY"):
        value = os.environ.get(variable, "")
        if value and not value.startswith(("\\\\?\\", "//?/")):
            value = os.path.abspath(value)
            value = "\\\\?\\UNC\\" + value[2:] if value.startswith("\\\\") else "\\\\?\\" + value
            os.environ[variable] = value.replace("\\", "/")
