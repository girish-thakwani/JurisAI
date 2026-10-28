# Problem : 

Predicting the next element within the website DOM for a specific workflow using multimodal web agents,
although the model knows which element to click but it picks the wrong. 

# Problem initiation :

While automating a couple of tasks within the organization (justyouapparels.in), the creation of workflow was
itself a tedious process. Tried to implement these task directly using multimodal webagents like stagehand and 
browseruse but were failing and clicking the wrong button. Found that most of them uses images and plain DOM text
for there step prediction.

# Research :

Found the dataset from Mind2Web(https://osu-nlp-group.github.io/Mind2Web/) and analysed 
and funneled that the issue is not action or element prediction but actually element grounding. Most of the
systems turns the page DOM into plain text and hope a large model infers the structure.

# Intuition towards the solution :

Instead of forcing an LLM to understand an entire web page from scratch on every task, you give it a 
structured representation of the page and train a relatively small set of components to combine that 
information effectively.

We can convert each webpage’s DOM elements into a directed graph to capture their structure and relationships.
This information is combined with the frozen Qwen3-VL-8B (https://ollama.com/library/qwen3-vl:8b) model using
a Graph Attention Network and a lightweight cross-attention adapter. We can use LoRA to fine-tune only a small 
number of parameters, allowing the entire system to be trained.



