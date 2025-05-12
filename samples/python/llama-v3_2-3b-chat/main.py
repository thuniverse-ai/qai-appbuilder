import os
import sys
import time
from importlib.metadata import version
from huggingface_hub import snapshot_download

# import dlltracer
# with dlltracer.Trace(out=sys.stdout):
from qai_appbuilder.geniecontext import GenieContext

def callback(result):
    global g_count
    print(f"[Callback] {result}", flush=True)
    return False # Return true to terminate the generation

def main():
    print(f"PID={os.getpid()}")
    print("Version of qai_appbuilder=" + version("qai_appbuilder"))

    model_dir = snapshot_download(repo_id="thuniverse-ai/Llama-v3.2-3B-Chat-GENIE")
    os.chdir(model_dir)
    model = GenieContext("genie_config.json")
    print("model loaded")
    prompt = "<|begin_of_text|><|start_header_id|>user<|end_header_id|>\n\nIntroduce yourself.<|eot_id|><|start_header_id|>assistant<|end_header_id|>"
    print("[Begin inference]")
    model.Query(prompt=prompt, callback=callback)
    print("[End inference]")
    model.Release()
    print("[Released memories]")
    time.sleep(5)

    sys.stdout.flush()

if __name__ == "__main__":
    main()
