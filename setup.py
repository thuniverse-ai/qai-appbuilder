# =============================================================================
#
# Copyright (c) 2023, Qualcomm Innovation Center, Inc. All rights reserved.
#
# SPDX-License-Identifier: BSD-3-Clause
#
# =============================================================================

# Compile Commands:
# Set QNN_SDK_ROOT=C:\Qualcomm\AIStack\QAIRT\2.31.0.250130\
# python setup.py bdist_wheel

import os
import platform
import re
import subprocess
import sys
from pathlib import Path
import shutil
import zipfile
import argparse

from setuptools import Extension, setup, find_packages
from setuptools.command.build_ext import build_ext

def search_library(search_paths, files):
    result = []
    for file in files:
        for dir in search_paths:
            path = os.path.join(dir, file)
            if os.path.exists(path):
                result.append(path)
                break
    return result

VERSION = "2.32.0+kuwa"
CONFIG = "Release"  # Release, RelWithDebInfo
package_name = "qai_appbuilder"

machine = platform.machine()
sysinfo = sys.version

generate = '-G "Visual Studio 17 2022"'
arch = "ARM64"

if machine == "AMD64" or "AMD64" in sysinfo:
    arch = "ARM64EC"
    generate += " -A " + arch

if machine == "aarch64":
    arch = "aarch64"
    generate = ""

print("-- Arch: " + arch)

PYTHON_PACKAGE_PATH = "script"
WHEEL_BUILD_PATH = PYTHON_PACKAGE_PATH + "/" + package_name
CMAKE_BUILD_PATH = "build"

QNN_SDK_ROOT = os.environ.get("QNN_SDK_ROOT")
print("-- QNN_SDK_ROOT: ", QNN_SDK_ROOT)
QNN_LIB_SEARCH_PATH = []
if sys.platform.startswith(
    "win"
):  # Copy Genie library to 'lib' folder for compiling GenieBuilder pyd.
    if arch == "ARM64EC":
        QNN_LIB_SEARCH_PATH.append(QNN_SDK_ROOT + "/lib/arm64x-windows-msvc/")
        QNN_LIB_SEARCH_PATH.append(QNN_SDK_ROOT + "/lib/x86_64-windows-msvc/")
    else:
        QNN_LIB_SEARCH_PATH.append(QNN_SDK_ROOT + "/lib/aarch64-windows-msvc/")
else:
    QNN_LIB_SEARCH_PATH.append(QNN_SDK_ROOT + "/lib/x86_64-linux-clang")
QNN_LIB_SEARCH_PATH.append(QNN_SDK_ROOT + "/lib/hexagon-v73/unsigned/")
QNN_SDK_LIBS = search_library(QNN_LIB_SEARCH_PATH, [
    "Genie.dll",
    "Genie.lib",
    "QnnHtp.dll",
    "QnnSystem.dll",
    "QnnHtpPrepare.dll",
    "QnnHtpNetRunExtensions.dll",
    "QnnHtpNetRunExtensions.lib",
    "QnnHtpV73Stub.dll",
    "libqnnhtpv73.cat",
    "libQnnHtpV73.so",
    "libQnnHtpV73Skel.so",
])
print("QNN_SDK_LIBS: "+'\n  - '.join(QNN_SDK_LIBS))
ARTIFACTS_FOR_PYTHON_PACKAGE = [
    "lib/" + CONFIG + "/libappbuilder.dll",
    "lib/" + CONFIG + "/libappbuilder.pdb",
    "lib/" + "libappbuilder.so",
]
ARTIFACTS_FOR_CPP_PACKAGE = [
    "lib/" + CONFIG + "/QAIAppSvc.exe",
    "lib/" + CONFIG + "/libappbuilder.dll",
    "lib/" + CONFIG + "/libappbuilder.lib",
    "lib/" + CONFIG + "/libappbuilder.pdb",
    "lib/" + CONFIG + "/QAIAppSvc.pdb",
    "lib/" + "/libappbuilder.so",
]

def zip_package(dirpath, outFullName):
    zip = zipfile.ZipFile(outFullName, "w", zipfile.ZIP_DEFLATED)
    for path, dirnames, filenames in os.walk(dirpath):
        fpath = path.replace(dirpath, "")
        for filename in filenames:
            zip.write(os.path.join(path, filename), os.path.join(fpath, filename))
    zip.close()


def build_clean():
    print("Cleaning up")
    shutil.rmtree(PYTHON_PACKAGE_PATH + "/qai_appbuilder.egg-info", ignore_errors=True)
    shutil.rmtree(CMAKE_BUILD_PATH, ignore_errors=True)
    shutil.rmtree("lib", ignore_errors=True)
    artifacts = {
        os.path.basename(f) for f in QNN_SDK_LIBS + ARTIFACTS_FOR_PYTHON_PACKAGE
    }
    for filename in artifacts:
        filename = os.path.join(WHEEL_BUILD_PATH, filename)
        if not os.path.exists(filename):
            continue
        os.remove(filename)
        print(f"Removed {filename}")


def build_cmake():
    if not os.path.exists(CMAKE_BUILD_PATH):
        os.mkdir(CMAKE_BUILD_PATH)
    os.chdir(CMAKE_BUILD_PATH)

    subprocess.run("cmake .. " + generate, shell=True)
    subprocess.run("cmake --build ./ --config " + CONFIG, shell=True)
    os.chdir("../")

    for lib in QNN_SDK_LIBS:
        if not os.path.exists(lib) or os.path.splitext(os.path.basename(lib))[1] == "lib":
            continue
        shutil.copy(lib, "lib/Release")


class CMakeExtension(Extension):
    def __init__(self, name: str, sourcedir: str = "") -> None:
        super().__init__(name, sources=[])
        self.sourcedir = os.fspath(Path(sourcedir).resolve())


class CMakeBuild(build_ext):
    def build_extension(self, ext: CMakeExtension) -> None:
        ext_fullpath = Path.cwd() / self.get_ext_fullpath(ext.name)
        extdir = ext_fullpath.parent.resolve()

        cfg = CONFIG

        cmake_generator = os.environ.get("CMAKE_GENERATOR", "")

        cmake_args = (
            f" -DCMAKE_LIBRARY_OUTPUT_DIRECTORY={extdir}{os.sep}"
            + f" -DPYTHON_EXECUTABLE={sys.executable}"
            + f" -DCMAKE_BUILD_TYPE={cfg}"
        )  # not used on MSVC, but no harm

        build_args = ""

        # We pass in the version to C++. You might not need to.
        cmake_args += f" -DVERSION_INFO={self.distribution.get_version()}"

        # Single config generators are handled "normally"
        single_config = any(x in cmake_generator for x in {"NMake", "Ninja"})

        # CMake allows an arch-in-generator style for backward compatibility
        contains_arch = any(x in cmake_generator for x in {"ARM", "Win64"})

        if not single_config and not contains_arch and not arch == "aarch64":
            cmake_args += " -A " + arch

        # Multi-config generators have a different way to specify configs
        if not single_config:
            cmake_args += f" -DCMAKE_LIBRARY_OUTPUT_DIRECTORY_{cfg.upper()}={extdir}"
            build_args += " --config " + cfg

        if "CMAKE_BUILD_PARALLEL_LEVEL" not in os.environ:
            if hasattr(self, "parallel") and self.parallel:
                # CMake 3.12+ only.
                build_args += f" -j{self.parallel}"

        build_temp = Path(self.build_temp) / ext.name
        if not build_temp.exists():
            build_temp.mkdir(parents=True)

        # cmake_args += " -DCMAKE_CXX_FLAGS='-DGENIE_BUILDER_DEBUG=1'"

        print(cmake_args)
        print(build_args)
        print(ext.sourcedir)

        subprocess.run(
            "cmake " + ext.sourcedir + cmake_args,
            cwd=build_temp,
            check=True,
            shell=True,
        )
        subprocess.run(
            "cmake --build . " + build_args, cwd=build_temp, check=True, shell=True
        )


def build_python_package():
    print("Building python packages")
    for filename in ARTIFACTS_FOR_PYTHON_PACKAGE:
        if not os.path.exists(filename):
            continue
        shutil.copy(filename, WHEEL_BUILD_PATH)

    for lib in QNN_SDK_LIBS:
        if not os.path.exists(lib) or os.path.splitext(lib)[1] == "lib":
            continue
        shutil.copy(lib, WHEEL_BUILD_PATH)

    with open("README.md", "r") as fh:
        long_description = fh.read()

    setup(
        name=package_name,
        version=VERSION,
        packages=[package_name],
        package_dir={"": PYTHON_PACKAGE_PATH},
        package_data={"": ["*.dll", "*.pdb", "*.exe", "*.so", "*.cat"]},
        ext_modules=[CMakeExtension("qai_appbuilder.appbuilder", "pybind")],
        cmdclass={"build_ext": CMakeBuild},
        zip_safe=False,
        description="AppBuilder is Python & C++ extension that simplifies the process of developing AI prototype & App on WoS. It provides several APIs for running QNN models in WoS CPU & HTP, making it easier to manage AI models.",
        long_description=long_description,
        long_description_content_type="text/markdown",
        url="https://github.com/quic/ai-engine-direct-helper",
        author="quic-zhanweiw",
        author_email="quic_zhanweiw@quicinc.com",
        license="BSD-3-Clause",
        python_requires=">=3.10",
        # install_requires=['pybind11>=2.13.6'],
        classifiers=[
            "Development Status :: 3 - Alpha",
            "Intended Audience :: Qualcomm CE",
            "License :: OSI Approved :: BSD License",
            'Operating System :: Windows On Snapdragon"',
            "Programming Language :: Python :: 3.10",
        ],
    )


# build release package for C++ based application.
def build_cpp_package():
    print("Building cpp packages")
    CPP_PACKAGE_PATH = "lib/package"
    CPP_PACKAGE_ZIP = "QAI_AppBuilder-win_arm64-QNN" + VERSION + "-" + CONFIG + ".zip"
    if arch == "ARM64EC":
        CPP_PACKAGE_ZIP = (
            "QAI_AppBuilder-win_arm64ec-QNN" + VERSION + "-" + CONFIG + ".zip"
        )
    elif arch == "aarch64":
        CPP_PACKAGE_ZIP = (
            "QAI_AppBuilder-linux_arm64-QNN" + VERSION + "-" + CONFIG + ".zip"
        )
    include_path = CPP_PACKAGE_PATH + "/include"
    if not os.path.exists(CPP_PACKAGE_PATH):
        os.mkdir(CPP_PACKAGE_PATH)

    if os.path.exists("lib/" + CONFIG + "/QAIAppSvc.exe"):
        shutil.copy("lib/" + CONFIG + "/libappbuilder.dll", CPP_PACKAGE_PATH)
        shutil.copy("lib/" + CONFIG + "/libappbuilder.lib", CPP_PACKAGE_PATH)
        shutil.copy("lib/" + CONFIG + "/QAIAppSvc.exe", CPP_PACKAGE_PATH)

    if os.path.exists("lib/" + CONFIG + "/libappbuilder.pdb"):
        shutil.copy("lib/" + CONFIG + "/libappbuilder.pdb", CPP_PACKAGE_PATH)
    if os.path.exists("lib/" + CONFIG + "/QAIAppSvc.pdb"):
        shutil.copy("lib/" + CONFIG + "/QAIAppSvc.pdb", CPP_PACKAGE_PATH)

    if os.path.exists("lib/" + "/libappbuilder.so"):
        shutil.copy("lib/" + "/libappbuilder.so", CPP_PACKAGE_PATH)

    if not os.path.exists(include_path):
        os.mkdir(include_path)
    shutil.copy("src/LibAppBuilder.hpp", include_path)

    zip_package(CPP_PACKAGE_PATH, "dist/" + CPP_PACKAGE_ZIP)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Script to build qai_appbuilder")
    parser.add_argument("--clean_only", action="store_true", help="If specified, clean the building artifacts.")
    args = parser.parse_args()
    build_clean()
    if not args.clean_only:
        build_cmake()
        build_python_package()
        build_cpp_package()
