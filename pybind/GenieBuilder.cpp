//==============================================================================
//
// Copyright (c) 2023, Qualcomm Innovation Center, Inc. All rights reserved.
// 
// SPDX-License-Identifier: BSD-3-Clause
//
//==============================================================================

#include <fstream>
#include <iostream>
#include "GenieBuilder.h"
#include "common.h"

// #define GENIE_BUILDER_DEBUG 1
#define CONTENT_LENGTH 4096  // TODO. need to calculate.

static int g_CurLength = 0;
static int g_MaxLength = CONTENT_LENGTH;

void SamplerProcess(const uint32_t logitsSize, const void* logits, const uint32_t numTokens, int32_t* tokens) {
//    g_CurLength += numTokens;
// #ifdef GENIE_BUILDER_DEBUG
    std::cerr << "SamplerProcess: logitsSize=" << logitsSize << ", numTokens=" << numTokens << ", curLength=" << g_CurLength << std::endl;
// #endif
}

void GenieCallBack(const char* response, const GenieDialog_SentenceCode_t sentence_code, const void* user_data) {
    GenieContext* self = static_cast<GenieContext*>(const_cast<void*>(user_data));
    if (response) {
        std::lock_guard<std::mutex> guard(self->m_stream_lock);
        self->m_stream_answer += response;
        // std::cout << response << std::flush;
    }

    g_CurLength += self->TokenLength(response);    // TODO: We need use 'SamplerProcess' to calculate the length of the tokens when Genie 'GenieSampler_registerCallback' works.
                                            //      We should calculate the input length together. input + output < CONTENT_LENGTH.
    // printf("g_CurLength = %d, g_MaxLength = %d\n", g_CurLength, g_MaxLength);

    if(g_CurLength >= g_MaxLength) { // Stop current generation.
        self->Stop();
    }

#ifdef GENIE_BUILDER_DEBUG
    std::cout << response;

    if (sentence_code == GenieDialog_SentenceCode_t::GENIE_DIALOG_SENTENCE_END) {
        printf("\n-----------------------------------------------------\n");
    }
#endif
}

void GenieContext::inference_thread() {
    while(true) {
        std::unique_lock<std::mutex> lock(m_request_lock);
        m_request_cond.wait(lock, [this]{return m_request_ready;});     // m_request_ready == true, wakeup thread; m_request_ready == false, sleep continually.
        if(m_thread_exit) {
            return;
        }

        auto status = GenieDialog_query(m_DialogHandle, m_prompt.c_str(), GenieDialog_SentenceCode_t::GENIE_DIALOG_SENTENCE_COMPLETE, GenieCallBack, this);
        if (GENIE_STATUS_SUCCESS != status && GENIE_STATUS_WARNING_ABORTED != status) {
            std::cerr << "Failed to get response from GenieDialog.\n";
        }

        m_inference_busy = false;
        m_request_ready = false;
    }
}

bool GenieContext::Query(const std::string& prompt, const Callback callback) {
    if (GENIE_STATUS_SUCCESS != GenieDialog_reset(m_DialogHandle)) {    // TODO: add a Python function for this.
        std::cerr << "Failed to reset Genie Dialog.\n";
    }

    g_CurLength = 0;
    m_prompt = prompt;

#ifdef GENIE_BUILDER_DEBUG
    std::cout << "\n[Prompt]:\n";
    std::cout << prompt << "\n\n";
    std::cout << "\n[Response]:\n";
#endif

    m_request_ready = true;
    m_inference_busy = true;
    m_request_cond.notify_one();   // Notify the inference thread to work.

    std::string response = "";
    while(m_inference_busy) {
        if (m_stream_answer.size() > 0) {
            std::lock_guard<std::mutex> guard(m_stream_lock);
            response = m_stream_answer;
            m_stream_answer = "";
        }

        if (response.size() > 0) {
            //std::cout << response << std::flush;
            bool should_stop = callback(response);
            if(should_stop){
                this->Stop();
            }
        }

        response = "";
        Sleep(10);
    }

    // Sleep(10);
    if (m_stream_answer.size() > 0) {   // send remainder data.
        // std::cout << remainder << std::flush;
        // std::cout << "[more data]" << std::flush;
        callback(m_stream_answer);
        m_stream_answer = "";
    }

    return true;
}

GenieContext::GenieContext(const std::string& config) {
    std::string config_str;
    std::string sample_config_str = "{\n  \"sampler\" : {\n      \"version\" : 1,\n      \"temp\" : 1.2,\n      \"top-k\" : 25,\n      \"top-p\" : 0.8\n  }\n}";
    int32_t status = 0;

    std::ifstream config_file(config);
    if (!config_file) {
        std::cerr << "Failed to open Genie config file: " + config;
    }
    config_str.assign((std::istreambuf_iterator<char>(config_file)), std::istreambuf_iterator<char>());

    // std::cerr << sample_config_str << std::endl;
    // std::cerr << config_str << std::endl;

    // Create Genie config
    if (GENIE_STATUS_SUCCESS != GenieDialogConfig_createFromJson(config_str.c_str(), &m_ConfigHandle)) {
        std::cerr << "Failed to create the Genie Dialog config.\n";
        return;
    }

    status = GenieProfile_create(nullptr, &m_ProfileHandle);
    if (GENIE_STATUS_SUCCESS != status) {
        std::cerr <<  "Failed to create the profile handle.\n";
        return;
    }

    status = GenieDialogConfig_bindProfiler(m_ConfigHandle, m_ProfileHandle);
    if (GENIE_STATUS_SUCCESS != status) {
        std::cerr <<  "Failed to bind the profile handle with the dialog config.\n";
        return;
    }

    // Create Genie dialog handle
    if (GENIE_STATUS_SUCCESS != GenieDialog_create(m_ConfigHandle, &m_DialogHandle)) {
        std::cerr <<  "Failed to create the Genie Dialog.\n";
        return;
    }

    status = GenieSamplerConfig_createFromJson(sample_config_str.c_str(), &m_SamplerConfigHandle);
    if (GENIE_STATUS_SUCCESS != status) {
        std::cerr <<  "Failed to create sampler config.\n";
        return;
    }

    status = GenieDialog_getSampler(m_DialogHandle, &m_SamplerHandle);
    if (GENIE_STATUS_SUCCESS != status) {
      std::cerr <<  "Failed to get sampler.\n";
      return;
    }

    status = GenieSampler_registerCallback("GenieBuilder", SamplerProcess);
    if (GENIE_STATUS_SUCCESS != status) {
      std::cerr <<  "Failed to register sampler callback.\n";
      return;
    }

    if(!m_stream_thread) {
        m_stream_thread = std::make_unique<std::thread>(&GenieContext::inference_thread, this);
    }
}

GenieContext::~GenieContext() {
#ifdef GENIE_BUILDER_DEBUG
    std::cout << "\nGenieContext::~GenieContext():\n";
#endif
    Release();
}

void GenieContext::Release() {
#ifdef GENIE_BUILDER_DEBUG
    std::cout << "\nGenieContext::Release():\n";
#endif
    // Notify thread exiting.
    if(m_stream_thread) {
        m_thread_exit = true;
        m_request_ready = true;
        m_request_cond.notify_one();
    }

    if (m_ConfigHandle != nullptr) {
        if (GENIE_STATUS_SUCCESS != GenieDialogConfig_free(m_ConfigHandle)) {
            std::cerr << "Failed to free the Genie Dialog config.\n";
        }
        m_ConfigHandle = nullptr;
    }

    if (m_DialogHandle != nullptr) {
        if (GENIE_STATUS_SUCCESS != GenieDialog_free(m_DialogHandle)) {
            std::cerr << "Failed to free the Genie Dialog.\n";
        }
        m_DialogHandle = nullptr;
    }

    if (m_SamplerConfigHandle != nullptr) {
        if (GENIE_STATUS_SUCCESS != GenieSamplerConfig_free(m_SamplerConfigHandle)) {
            std::cerr << "Failed to free the sampler config." << std::endl;
        }
        m_SamplerConfigHandle = nullptr;
    }

    if (m_ProfileHandle != nullptr){
        if (GENIE_STATUS_SUCCESS != GenieProfile_free(m_ProfileHandle)) {
            std::cerr << "Failed to free the profile handle." << std::endl;
        }
        m_ProfileHandle = nullptr;
    }

    // Waiting thread clean.
    if(m_stream_thread) {
        m_stream_thread->join();
        m_stream_thread = nullptr;

        // reset the global variable.
        m_request_ready = false;
        m_thread_exit = false;
    }
}

bool GenieContext::Stop() {

    if (GENIE_STATUS_SUCCESS != GenieDialog_signal(m_DialogHandle, GENIE_DIALOG_ACTION_ABORT)) {
        std::cerr << "Failed to stop generation.\n";
        return false;
    }

    return true;
}

bool GenieContext::SetParams(const std::string max_length, const std::string temp, const std::string top_k, const std::string top_p) {
    int32_t status = 0;

    g_MaxLength = std::stoi(max_length);

    status = GenieSamplerConfig_setParam(m_SamplerConfigHandle, "temp", temp.c_str());
    if (GENIE_STATUS_SUCCESS != status) {
      std::cerr << "Failed to setParam.\n";
      return false;
    }

    status = GenieSamplerConfig_setParam(m_SamplerConfigHandle, "top-k", top_k.c_str());
    if (GENIE_STATUS_SUCCESS != status) {
      std::cerr << "Failed to setParam.\n";
      return false;
    }

    status = GenieSamplerConfig_setParam(m_SamplerConfigHandle, "top-p", top_p.c_str());
    if (GENIE_STATUS_SUCCESS != status) {
      std::cerr << "Failed to setParam.\n";
      return false;
    }

    status = GenieSampler_applyConfig(m_SamplerHandle, m_SamplerConfigHandle);
    if (GENIE_STATUS_SUCCESS != status) {
      std::cerr << "Failed to apply sampler config.\n";
      return false;
    }

    return true;
}

std::string GenieContext::GetProfile() {
    const Genie_AllocCallback_t callback([](size_t size, const char** data) {
        *data = (char*)malloc(size);
        if (*data == nullptr) {
          std::cerr << "Cannot allocate memory for JSON data.\n";
        }
      });

    const char* jsonData = nullptr;
    const int32_t status = GenieProfile_getJsonData(m_ProfileHandle, callback, &jsonData);
    if (GENIE_STATUS_SUCCESS != status) {
      std::cerr << "Failed to get the profile data.\n";
      return "";
    }

    std::string strProfileData(jsonData);
    free((char*)jsonData);

    return strProfileData;
}

size_t GenieContext::TokenLength(const std::string& text) {
    // std::vector<int32_t> tokens;
    // return GenieDialog_encode(m_DialogHandle, text, tokens);

    // TODO: Mock token length calculation since GenieDialog_encode
    // is not available in QNN SDK 2.34.0.250424 and previous version.
    return text.length();
}

PYBIND11_MODULE(geniebuilder, m) {
    m.doc() = R"pbdoc(
        Pybind11 GenieBuilder Extension.
        -----------------------
        .. currentmodule:: qai_geniebuilder
        .. autosummary::
            :toctree: _generate

            Query
            )pbdoc";

    m.attr("__name__") = "qai_geniebuilder";
    m.attr("__version__") = APPBUILDER_VERSION;
    m.attr("__author__") = "quic-zhanweiw";
    m.attr("__name__") = "qai_geniebuilder";

    py::class_<GenieContext>(m, "GenieContext")
        .def(py::init<const std::string&>())
        .def("Query", &GenieContext::Query)
        .def("SetParams", &GenieContext::SetParams)
        .def("GetProfile", &GenieContext::GetProfile)
        .def("TokenLength", &GenieContext::TokenLength)
        .def("Stop", &GenieContext::Stop)
        .def("Release", &GenieContext::Release);
}
