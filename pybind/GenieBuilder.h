//==============================================================================
//
// Copyright (c) 2023, Qualcomm Innovation Center, Inc. All rights reserved.
// 
// SPDX-License-Identifier: BSD-3-Clause
//
//==============================================================================

#pragma once

#ifndef _GENIEBUILDER_H
#define _GENIEBUILDER_H

#include <iostream>
#include <memory> // unique_ptr
#include <vector> // vector
#include <fstream>
#include <string>
#include <direct.h>
#include <stdio.h>
#include <streambuf>
#include <istream>
#include <thread>
#include <mutex>
#include <condition_variable>
#include <windows.h>

#include <pybind11/functional.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include "GenieCommon.h"
#include "GenieDialog.h"

using namespace std;
namespace py = pybind11;

using Callback = std::function<bool(const std::string&)>;

class GenieContext {
    public:
        GenieContext(const std::string& config);
        ~GenieContext();

        bool Query(const std::string& prompt, const Callback callback);
        bool Stop();
        bool SetParams(const std::string max_length, const std::string temp, const std::string top_k, const std::string top_p);
        std::string GetProfile();
        size_t TokenLength(const std::string& text);
        void Release();

    public:
        std::mutex m_stream_lock;
        std::string m_stream_answer {""};

    private:
        void inference_thread();

        GenieDialogConfig_Handle_t m_ConfigHandle = nullptr;
        GenieDialog_Handle_t m_DialogHandle = nullptr;
        GenieSamplerConfig_Handle_t m_SamplerConfigHandle = NULL;
        GenieSampler_Handle_t m_SamplerHandle = NULL;
        GenieProfile_Handle_t m_ProfileHandle = NULL;

        // Inference thread.
        std::unique_ptr<std::thread> m_stream_thread {nullptr};
        std::mutex m_request_lock;
        bool m_request_ready {false};
        std::condition_variable m_request_cond;
        bool m_thread_exit {false};
        bool m_inference_busy {false};

        std::string m_prompt {""};
};

#endif
