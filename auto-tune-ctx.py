# Auto-tune: detects GPU VRAM + architecture, sets num_ctx per model accordingly.
# Runs on every Overlkd-Coder start -> swap the GPU = automatically more context.
import subprocess, os

SETTINGS = os.path.join(os.path.expanduser("~"), ".aider.model.settings.yml")

def gpu_info():
    try:
        out = subprocess.run(["nvidia-smi","--query-gpu=memory.total,compute_cap","--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=15).stdout.strip().splitlines()[0]
        mem_mib, cap = out.split(",")
        vram = int(float(mem_mib))/1024  # GB
        cap = float(cap)
        return vram, cap
    except Exception:
        return 6.0, 6.1  # Fallback: 1060

def tier(vram, cap):
    pascal = cap < 7.0  # Pascal (1060/1080Ti) -> FlashAttention crash on long context
    if vram <= 7:   t = "s"
    elif vram <= 13: t = "m"
    elif vram <= 17: t = "l"
    else:            t = "xl"
    return t, pascal

# num_ctx per model and VRAM tier (s=6GB, m=12GB, l=16GB, xl=24GB+)
CTX = {
 "qwen3.5:9b":       {"s":12288,"m":24576,"l":32768,"xl":32768},
 "qwen3.5:4b":       {"s":16384,"m":32768,"l":32768,"xl":32768},
 "qwen2.5-coder:7b": {"s":8192, "m":24576,"l":32768,"xl":32768},
 "qwen3:14b":        {"s":4096, "m":16384,"l":24576,"xl":32768},
 "deepseek-r1:7b":   {"s":8192, "m":24576,"l":32768,"xl":32768},
}
EXTRA = {  # use_repo_map / phi etc.
 "qwen3:14b": {"think":True}, "qwen3.5:9b":{"think":True}, "qwen3.5:4b":{"think":True},
}

def build(vram, cap):
    t, pascal = tier(vram, cap)
    lines = [f"# Overlkd Aider model settings - AUTO-tuned for {vram:.0f}GB VRAM (cap {cap}){' [Pascal cap]' if pascal else ''}",
             "# Regenerated on every Overlkd-Coder start (auto-tune-ctx.py). Do not edit by hand.\n"]
    for model, sizes in CTX.items():
        ctx = sizes[t]
        if pascal: ctx = min(ctx, 12288)  # Pascal FA-crash guard
        block = [f"- name: ollama_chat/{model}",
                 "  edit_format: whole",
                 "  use_repo_map: true",
                 "  use_temperature: 0.0"]
        if EXTRA.get(model,{}).get("think"): block.append('  system_prompt_prefix: "/no_think"')
        if model=="deepseek-r1:7b": block.append("  reasoning_tag: think")
        block += ["  extra_params:", f"    num_ctx: {ctx}", ""]
        lines += block
    return "\n".join(lines)

if __name__ == "__main__":
    vram, cap = gpu_info()
    with open(SETTINGS,"w",encoding="utf-8") as f:
        f.write(build(vram, cap))
    t,pascal = tier(vram,cap)
    print(f"Auto-tune: {vram:.0f}GB VRAM, cap {cap} -> tier '{t}'{' (Pascal cap 12K)' if pascal else ''}")
    print(f"num_ctx set: qwen3.5:9b={min(CTX['qwen3.5:9b'][t],12288 if pascal else 99999)}, qwen3.5:4b={min(CTX['qwen3.5:4b'][t],12288 if pascal else 99999)}")
