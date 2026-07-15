# Questions & Learning Diary

This file documents questions asked during the build process and their answers.
Use it as a reference for future projects.

---

**Q: Should I use OpenAI or Anthropic LLMs?**
A: Both work. OpenAI (GPT-4o) is faster and cheaper. Anthropic (Claude) has better instruction following and structured outputs. For this agent, Claude is slightly better for multi-pod analysis. The agent abstracts this with litellm — you can swap without code changes.

**Q: Is there a free LLM tier?**
A: Yes. Google Gemini has 60 req/min free. Groq has free tier with rate limits. Ollama runs locally for free. litellm supports all of them.

**Q: What is litellm?**
A: A Python library that provides a unified API for 100+ LLM providers. Write code once, switch providers by changing a config string.

**Q: What is subprocess?**
A: Python's way of running terminal commands. `subprocess.run(["kubectl", "get", "pods"])` is the same as typing `kubectl get pods` in your terminal.

**Q: Do I need a Kubernetes cluster to develop this?**
A: No. The agent auto-detects whether a cluster is available and falls back to realistic mock data. You can build and test without any K8s setup.

**Q: What is kubectl vs the Kubernetes Python SDK?**
A: kubectl is the command-line tool. The Python SDK is a library. For read-only pod queries, subprocess + kubectl is simpler and requires no extra dependencies or auth setup.

**Q: What is the Model-Tools-Instructions pattern?**
A: The three essential components of any agent:
- Model = the LLM (brain)
- Tools = external functions the agent can use (hands)
- Instructions = system prompt defining behavior (rules)

**Q: How do I test an agent without real data?**
A: Use mock data. Our k8s_client.py has 10 realistic mock pods with various statuses (Running, CrashLoopBackOff, Pending, etc.) so you can test the summarization without a cluster.

**Q: What is a kubeconfig?**
A: A YAML file (usually at ~/.kube/config) that stores cluster connection details, certificates, and authentication tokens. kubectl reads this automatically.
