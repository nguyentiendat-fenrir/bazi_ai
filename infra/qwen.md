# Qwen3-8B (vLLM) on this host

The RAG pilot's only LLM is the `qwen3-8b` container already running on this machine. It is not part of
`infra/compose.yaml`. The api, worker and reasoner services reach it at
`http://host.docker.internal:8000/v1` (`extra_hosts: host-gateway`, `edge` network) with model name `qwen3-8b`.

## Current container (recreated 2026-10-21)

```bash
docker run -d --name qwen3-8b --runtime nvidia --gpus all --ipc host -p 8000:8000 \
  -v /home/workinno/llm-models/checkpoints/Qwen3-8B-FP8/:/model:ro --restart unless-stopped \
  --entrypoint vllm sha256:befccf0e7e4089aa23926bb6f887a85c0d46c2a99e6de5c5ffdf5cb7957c5b34 serve \
  --model /model --host 0.0.0.0 --port 8000 --max-model-len 16384 --gpu-memory-utilization 0.53 \
  --max-num-seqs 8 --kv-cache-dtype fp8 --served-model-name qwen3-8b /model --reasoning-parser qwen3
```

The image is pinned by ID; it was `vllm/vllm-openai:latest` at the time.
`/model` stays a served alias, so older clients that ask for `/model` keep working.

## Why these numbers

Goal: a 16k context so the LLM sees 6–8 parent sections (about 9k tokens), using as little VRAM as possible.

| Setting | Result |
|---|---|
| util 0.5, 16k | fails to start: 0.82 GiB of KV cache left, a 16k sequence needs 1.12 GiB (FP8 KV) |
| util 0.5, `--max-num-batched-tokens 4096` | worse: 0.61 GiB (bigger activation reserve than the default 2048) |
| util 0.55, 16k | fails: 0.92 GiB |
| **util 0.53, `--max-num-seqs 8`, 16k** | **starts: 1.31 GiB KV = 19,088 tokens, 1.17 full-length requests at once** |

Of the 0.53 × 23 GiB budget, 8.9 GiB is FP8 weights and about 1.7 GiB is CUDA context, graphs and activations.
With Gemma's llama.cpp container (about 5.9 GB) and SenOCR-Vi during OCR (about 3.2 GB), the card peaks around 20.6 GB of 23 GB.

To serve more concurrent long requests, raise `--gpu-memory-utilization`; don't raise `--max-num-batched-tokens`.

## Rollback

The original container (8k context, util 0.6) is kept stopped as `qwen3-8b-prev`:

```bash
docker rm -f qwen3-8b && docker rename qwen3-8b-prev qwen3-8b && docker start qwen3-8b
```

After a rollback, set `RAG_CONTEXT_TOKENS` to 5000 or less in `.env`, otherwise prompts no longer fit.
