# Switching AI models

MergeMate ships with GPT-5 as the default. You can swap it for any model LiteLLM supports.

Set the model in your config:

```toml
[config]
model = "your-model-here"
fallback_models = ["fallback-if-primary-fails"]
```

!!! note "Provider-specific env vars"
    Check the [LiteLLM docs](https://litellm.vercel.app/docs/proxy/quick_start#supported-llms) for the exact environment variables each model needs. Missing keys usually result in LiteLLM failing to identify the model type.

---

## Provider recipes

### OpenAI

```toml
# .secrets.toml
[openai]
api_base = "https://api.openai.com/v1"
api_key = "sk-..."
```

Or use env vars (note the double underscore):

```bash
OPENAI__API_BASE=https://api.openai.com/v1
OPENAI__KEY=sk-...
```

### OpenAI Flex Processing

Reduce costs on background tasks:

```toml
[litellm]
extra_body = '{"processing_mode": "flex"}'
```

### Azure

```toml
# .secrets.toml
[openai]
key = ""
api_type = "azure"
api_version = "2023-05-15"
api_base = "https://<resource>.openai.azure.com"
deployment_id = "<deployment-name>"
```

```toml
# configuration.toml
[config]
model = "gpt-4o"
fallback_models = ["gpt-4o"]
```

#### Azure AD (Entra ID)

```toml
# .secrets.toml
[azure_ad]
client_id = ""
client_secret = ""
tenant_id = ""
api_base = "https://openai.xyz.com/"
```

#### Custom headers

Route through an API gateway:

```toml
[litellm]
extra_headers = '{"projectId": "<id>"}'
```

### Ollama (local)

```toml
# configuration.toml
[config]
model = "ollama/qwen2.5-coder:32b"
fallback_models = ["ollama/qwen2.5-coder:32b"]
custom_model_max_tokens = 128000
duplicate_examples = true

# .secrets.toml
[ollama]
api_base = "http://localhost:11434"
```

Ollama defaults to a 2048-token context window — way too small for PR diffs. Bump it up:

```bash
OLLAMA_CONTEXT_LENGTH=8192 ollama serve
```

Make sure `custom_model_max_tokens` matches your `OLLAMA_CONTEXT_LENGTH`.

!!! note "Local vs. cloud models"
    MergeMate works with almost any model, but PR analysis is demanding. GPT-5, Claude Sonnet, and Gemini handle it well. Most open-source models (as of early 2025) struggle with the structured output and large inputs this task requires.

    Local models are fine for experimenting (especially with `/ask`), but stick to commercial models for production workflows.

### Anthropic

```toml
[config]
model = "anthropic/claude-3-opus-20240229"
fallback_models = ["anthropic/claude-3-opus-20240229"]

# .secrets.toml
[anthropic]
KEY = "..."
```

### Google AI Studio

```toml
[config]
model = "gemini/gemini-1.5-flash"
fallback_models = ["gemini/gemini-1.5-flash"]

# .secrets.toml
[google_ai_studio]
gemini_api_key = "..."
```

Or set `GOOGLE_AI_STUDIO.GEMINI_API_KEY` as an env var.

### Vertex AI

```toml
[config]
model = "vertex_ai/codechat-bison"
fallback_models = ["vertex_ai/codechat-bison"]

# .secrets.toml
[vertexai]
vertex_project = "my-google-cloud-project"
vertex_location = ""
```

Uses [application default credentials](https://cloud.google.com/docs/authentication/application-default-credentials). Set `GOOGLE_APPLICATION_CREDENTIALS` if you need explicit auth.

### Amazon Bedrock

```toml
[config]
model = "bedrock/anthropic.claude-3-5-sonnet-20240620-v1:0"
fallback_models = ["bedrock/anthropic.claude-3-5-sonnet-20240620-v1:0"]

# .secrets.toml
[aws]
AWS_ACCESS_KEY_ID = "..."
AWS_SECRET_ACCESS_KEY = "..."
AWS_REGION_NAME = "..."
```

#### IAM roles (recommended on AWS)

Running on EC2, ECS, EKS, or Lambda? Skip the static keys and use ambient credentials:

```yaml
# GitHub Actions
- uses: MergeMate-ai/mergemate@main
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
    AWS_USE_IMDS: "true"
  with:
    command: review
```

Your IAM role needs:

```json
{
  "Effect": "Allow",
  "Action": "bedrock:InvokeModel",
  "Resource": "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-5-sonnet-20240620-v1:0"
}
```

Static keys act as a fallback if ambient credentials fail.

#### Custom inference profiles

```toml
[litellm]
model_id = "your-custom-inference-profile-id"
```

### Hugging Face

```toml
[config]
model = "huggingface/meta-llama/Llama-2-7b-chat-hf"
fallback_models = ["huggingface/meta-llama/Llama-2-7b-chat-hf"]
custom_model_max_tokens = ...

# .secrets.toml
[huggingface]
key = ...
api_base = ...
```

### DeepSeek

```toml
[config]
model = "deepseek/deepseek-v4-flash"
fallback_models = ["deepseek/deepseek-v4-flash"]

# .secrets.toml
[deepseek]
key = ...
```

### DeepInfra

```toml
[config]
model = "deepinfra/deepseek-ai/DeepSeek-R1-Distill-Llama-70B"
fallback_models = ["deepinfra/deepseek-ai/DeepSeek-R1-Distill-Qwen-32B"]

# .secrets.toml
[deepinfra]
key = ...
```

### Mistral / Codestral

```toml
[config]
model = "mistral/mistral-small-latest"
fallback_models = ["mistral/mistral-medium-latest"]

# .secrets.toml
[mistral]
key = ...
```

### OpenRouter

```toml
[config]
model = "openrouter/anthropic/claude-3.7-sonnet"
fallback_models = ["openrouter/deepseek/deepseek-v4-flash"]
custom_model_max_tokens = 20000

# .secrets.toml
[openrouter]
key = ...
```

### Groq

```toml
[config]
model = "groq/llama3-70b-8192"
fallback_models = ["groq/llama3-70b-8192"]

# .secrets.toml
[groq]
key = ...
```

### Replicate

```toml
[config]
model = "replicate/llama-2-70b-chat:<version-hash>"
fallback_models = ["replicate/llama-2-70b-chat:<version-hash>"]

# .secrets.toml
[replicate]
key = ...
```

### SambaNova

```toml
[config]
model = "sambanova/MiniMax-M3"
fallback_models = ["sambanova/MiniMax-M2.7"]

# .secrets.toml
[sambanova]
key = ...
```

### xAI

```toml
[config]
model = "xai/grok-2-latest"
fallback_models = ["xai/grok-2-latest"]

# .secrets.toml
[xai]
key = ...
```

---

## Custom models

If your model isn't in the [supported list](https://github.com/imtiyaazsalie/mergemate/blob/main/mergemate/algo/__init__.py), you can still use it:

1. Set the name:
   ```toml
   [config]
   model = "custom_model_name"
   fallback_models = ["custom_model_name"]
   ```

2. Set the max tokens:
   ```toml
   custom_model_max_tokens = ...
   ```

3. Configure the env vars per [LiteLLM's docs](https://litellm.vercel.app/docs/proxy/quick_start#supported-llms).

4. For reasoning models that don't support chat-style inputs:
   ```toml
   custom_reasoning_model = true
   ```

---

## Model-specific tuning

### OpenAI reasoning effort

```toml
[config]
reasoning_effort = "medium"  # none, minimal, low, medium, high, xhigh
```

### Anthropic extended thinking

```toml
[config]
enable_claude_extended_thinking = false
extended_thinking_budget_tokens = 2048
extended_thinking_max_output_tokens = 4096
```
