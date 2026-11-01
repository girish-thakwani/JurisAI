# PingPilot

PingPilot is a resilient, resumable outreach automation project for web-based messaging workflows. It combines structured automation ideas with practical Playwright-based execution for workflows such as WhatsApp Web outreach, while keeping the system robust enough to pause, retry, and resume without losing context.

## Problem

Predicting the next element within the website DOM for a specific workflow using multimodal web agents,
although the model knows which element to click but it picks the wrong.

## Problem initiation

While automating a couple of tasks within the organization (justyouapparels.in), the creation of workflow was
itself a tedious process. Tried to implement these task directly using multimodal webagents like stagehand and
browseruse but were failing and clicking the wrong button. Found that most of them uses images and plain DOM text
for there step prediction.

## Research

Found the dataset from Mind2Web(https://osu-nlp-group.github.io/Mind2Web/) and analysed
and funneled that the issue is not action or element prediction but actually element grounding. Most of the
systems turns the page DOM into plain text and hope a large model infers the structure.

## Intuition towards the solution

Instead of forcing an LLM to understand an entire web page from scratch on every task, you give it a
structured representation of the page and train a relatively small set of components to combine that
information effectively.

We can convert each webpage’s DOM elements into a directed graph to capture their structure and relationships.
This information is combined with the frozen Qwen3-VL-8B (https://ollama.com/library/qwen3-vl:8b) model using
a Graph Attention Network and a lightweight cross-attention adapter. We can use LoRA to fine-tune only a small
number of parameters, allowing the entire system to be trained.

## Current focus: Inference and evaluation

This project is currently centered on the inference and evaluation work for grounding and action prediction on Mind2Web-style browser tasks. The core goal is to improve how a model selects the correct element in the DOM, not just predict the next action.

The repository includes an experimental research layer in the `Inference/` folder that directly addresses this challenge. This is the active focus of the project right now.

### What is included

- `batch_inference.py`: a template for running baseline inference across multiple modality settings, including text-only, image-only, multimodal, and axtree-aware setups
- `inference_VLM.py`: an evaluation script that reads model predictions in JSONL format and computes grounding and action quality metrics

### Baseline directions supported

The inference setup is designed to compare several model configurations, such as:

- text-only baselines
- image-only baselines
- multimodal text + image baselines
- axtree / DOM-structure-aware baselines
- multimodal + axtree combinations
- chain-of-thought style variants

This allows the project to benchmark whether structural context improves element grounding compared to using raw text or screenshots alone.

### Evaluation metrics

The evaluation layer measures the core metrics needed to validate browser grounding quality and task completion:

- Element Accuracy (Top-1 grounding)
- Action Accuracy
- Exact Match (element and action together)
- Parse Failure Rate
- Top-k Element Accuracy
- MRR (Mean Reciprocal Rank)
- Per-action Precision / Recall / F1
- Task Success Rate (when task-level labels are available)

### Why this matters

These scripts provide the benchmark layer for the project’s core hypothesis: structured page representations, such as DOM graphs or axtree-style relational structure, can improve grounding accuracy and reduce failures caused by weak localization in browser interfaces. In other words, the model should reason over structure, not just flattened page text.

This research-facing evaluation layer supports the current work: combining graph-structured DOM knowledge with vision-language reasoning to improve robust element selection in real web workflows.

## Project direction

The practical implementation in this repository follows a more engineering-focused version of the same idea: instead of relying on fragile multi-step browser inference alone, PingPilot emphasizes resilient automation, retriable workflows, and clean execution around browser interactions.

This project is designed for:

- WhatsApp Web outreach automation
- CSV or Google Sheets based contact ingestion
- Resumable processing for large outreach runs
- Retry, delay, and offline handling policies
- A structured automation layer built on Playwright

## Current implementation highlights

- Playwright-powered browser automation
- Contact source support from Google Sheets or CSV files
- Message templating via direct text or a file-based message input
- Config-driven policies for retries, batching, and failure handling
- Dry-run and source-channel controls
- Resumable execution patterns for operational stability

## Setup

1. Clone the repository
2. Create and activate a virtual environment
3. Install dependencies

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Or install using the package metadata:

```bash
pip install -e .
```

## Configuration

Create a `.env` file from the sample template:

```bash
copy .env.example .env
```

Key environment variables include:

- `SOURCE`: `sheet` or `csv`
- `CHANNEL`: `whatsapp_web` or `dry_run`
- `SHEET_URL`: Google Sheet URL
- `CREDS_FILE`: credentials JSON path
- `CSV_PATH`: CSV contacts file path
- `MESSAGE`: WhatsApp invite link or message text
- `MESSAGE_FILE`: optional message file
- `CDP_URL`: Chrome DevTools Protocol endpoint
- retry and batching controls such as `MAX_ATTEMPTS`, `BATCH_SIZE`, and `ROW_RETRIES`

## Usage

The project exposes a CLI entry point:

```bash
pingpilot
```

For the browser automation recorder/flow conversion utilities, the repo also contains examples such as:

```bash
python main.py record https://web.whatsapp.com
python main.py edit main.py
python main.py convert main.py
```

These commands are useful when generating or visualizing automation flows from Playwright scripts.

## Workflow philosophy

PingPilot is built around a practical principle: real-world automation is not only about selecting the correct DOM element, but also about designing workflows that recover gracefully from transient failures, network issues, and UI changes. The system aims to keep outreach automation reliable, observable, and resumable in production-like conditions.

## Repository status

This repository is a working prototype and research-direction project intended to bridge the gap between multimodal web-grounding research and practical automation tooling for outreach tasks.

## License

This project is currently maintained as a local research and automation prototype. Licensing terms should be confirmed before production deployment or commercial reuse.


