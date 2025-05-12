# =============================================================================
#
# Copyright (c) 2023, Qualcomm Innovation Center, Inc. All rights reserved.
#
# SPDX-License-Identifier: BSD-3-Clause
#
# =============================================================================

import os
from collections import OrderedDict
from qai_appbuilder import geniebuilder


def prepend_path(new_path):
    sep = ";"
    paths = list(filter(None, os.environ["PATH"].split(sep)))
    paths.insert(0, new_path)
    paths = list(OrderedDict.fromkeys(paths))
    os.environ["PATH"] = sep.join(paths)


class GenieContext:
    """High-level Python wrapper for a GenieBuilder model."""

    def __init__(self, config: str = "None") -> None:
        self.config = config
        # Since we will put QnnHtp.dll in the same directory as geniecontext.py
        prepend_path(os.path.dirname(os.path.abspath(__file__)))
        self.m_context = geniebuilder.GenieContext(config)

    def Query(self, prompt, callback):
        return self.m_context.Query(prompt, callback)

    def Stop(self):
        return self.m_context.Stop()

    def SetParams(self, max_length, temp, top_k, top_p):
        return self.m_context.SetParams(max_length, temp, top_k, top_p)

    def GetProfile(self):
        return self.m_context.GetProfile()

    def TokenLength(self, text):
        return self.m_context.TokenLength(text)

    def __del__(self):
        if hasattr(self, "m_context") and self.m_context is not None:
            del self.m_context
            self.m_context = None
